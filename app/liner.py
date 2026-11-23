from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from app.config import read_env, require_api_key
from app.guardrails import LABELS, sensitive_labels, strings_in, strip_data_uris
from app.liner_sse import assemble_chat_stream, parse_ai_search, parse_visualization

BASE_URL = "https://platform.liner.com/api/v1"
CHAT_URL = f"{BASE_URL}/chat/completions"
SEARCH_URL = f"{BASE_URL}/tools/search/web"
AI_SEARCH_URL = f"{BASE_URL}/agents/search"
DECISIONS_URL = f"{BASE_URL}/decisions"
RERANK_URL = f"{BASE_URL}/rerank"
VISUALIZATION_URL = f"{BASE_URL}/tools/visualization"
TRANSCRIPTION_URL = f"{BASE_URL}/audio/transcriptions"
BALANCE_URL = f"{BASE_URL}/credits/balance"
USAGE_URL = f"{BASE_URL}/credits/usage"
IMAGES_URL = f"{BASE_URL}/images/generations"
# Docs: no streaming; a long generation keeps the connection open with leading spaces, up to ~420 s.
IMAGE_TIMEOUT = 450.0

_ROUTER = re.compile(r"liner-[a-z0-9]+-router(?:-[0-9.]+)?")
# Web Search: Korean pages first, no knowledge panel (docs: "Body" of /tools/search/web).
SEARCH_OPTIONS = {"lang": "ko", "country_code": "kr", "include_knowledge": False}
# Settings that are required only by the feature that uses them, with the value we propose (README).
MODEL_SETTINGS = {
    "LINER_DECISION_MODEL": ("판정(Decisions)", "typesafe/jev-1.13"),
    "LINER_RERANK_MODEL": ("재정렬(Rerank)", "cohere/rerank-5-fast"),
    "LINER_STT_MODEL": ("음성 받아쓰기", "openai/gpt-transcribe"),
    "LINER_IMAGE_MODEL": ("프로토타입 상품 이미지", "qwen/qwen-image-2.1-turbo"),
}


class LinerConfigError(RuntimeError):
    """Raised when a non-secret Liner setting (e.g. LINER_MODEL) is missing."""


class LinerAPIError(RuntimeError):
    """A Liner call failed. `kind` names the failure; the message is fixed text, never the provider's body."""

    def __init__(self, message: str, kind: str = "other") -> None:
        super().__init__(message)
        self.kind = kind


# HTTP status → (kind, what the client should check). The response body is never shown or recorded.
_HTTP_KINDS = (
    ((401, 403), "auth", "키가 올바른지 확인하세요."),
    ((402,), "credits", "크레딧이 남았는지 확인하세요."),
    ((429,), "rate_limit", "요청이 너무 많아요. 잠시 뒤 다시 시도하세요."),
    ((400, 404, 409, 422), "bad_request", "설정한 모델 이름과 요청 형식을 확인하세요."),
)


def http_error(url: str, status: int) -> LinerAPIError:
    kind, hint = next(((k, h) for codes, k, h in _HTTP_KINDS if status in codes),
                      ("server", "Liner 쪽 오류예요. 잠시 뒤 다시 시도하세요.") if status >= 500
                      else ("other", "키가 올바른지, 크레딧이 남았는지 확인하세요."))
    return LinerAPIError(f"Liner API 호출 실패: {url} → HTTP {status}. {hint}", kind)


_URL = re.compile(r"https?://\S+")


def outgoing_labels(payload: Any, secrets: tuple[str, ...] = ()) -> list[str]:
    """G3 on a whole request body. URLs (search sources) and embedded images are skipped: long slugs and
    base64 look like keys but are not."""
    texts = [_URL.sub(" ", strip_data_uris(t)) for t in strings_in(payload)]
    labels = sensitive_labels(texts)
    if any(secret and secret in t for secret in secrets for t in strings_in(payload)):
        labels = [*labels, LABELS["api_key"]] if LABELS["api_key"] not in labels else labels
    return labels


def is_router(model: str | None) -> bool:
    """`liner-gpt-router`, `liner-claude-router-1.0` … accept routing_strategy; `liner-mark*` answers 400."""
    return bool(model) and _ROUTER.fullmatch(str(model)) is not None


class LinerClient:
    """Thin client for the Liner Router/Model, Search, Agent, Tools and Credits APIs.

    The key is read on every call, so adding .env later works without restarting tests.
    Pass `transport` (e.g. httpx.MockTransport) to avoid real network calls.
    """

    def __init__(
        self,
        env_file: Path | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._env_file = env_file
        self._transport = transport
        self._timeout = timeout

    @property
    def env_file(self) -> Path | None:
        """The .env path settings are read from (also used for the G7/G8 limits)."""
        return self._env_file

    def configured_model(self) -> str | None:
        """LINER_MODEL as chat() would read it (no default), for recording in events."""
        return read_env("LINER_MODEL", self._env_file)

    def secrets(self) -> tuple[str, ...]:
        """Values that must never appear in a request body, an event or an export (the configured key)."""
        key = read_env("LINER_API_KEY", self._env_file)
        return (key,) if key else ()

    def setting_model(self, name: str) -> str:
        """A feature model (LINER_DECISION_MODEL …). Required only when that feature is used."""
        value = read_env(name, self._env_file)
        if not value:
            what, proposal = MODEL_SETTINGS[name]
            raise LinerConfigError(
                f"{name} 이 설정되지 않아 {what} 기능을 쓸 수 없습니다. "
                f".env 에 '{name}=<모델 이름>' 을 넣으세요 (제안: {proposal}).")
        return value

    # --- Router / Model API ---------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        routing_strategy: str | None = None,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        key = require_api_key(self._env_file)
        chosen = model or read_env("LINER_MODEL", self._env_file)
        if not chosen:
            raise LinerConfigError(
                "LINER_MODEL 이 설정되지 않았습니다. .env 에 'LINER_MODEL=<모델 이름>' 을 넣으세요 "
                "(권장: liner-claude-router)."
            )
        # Stream: Liner drops a request that sends nothing for ~125 s, and documents/prototypes take longer.
        payload: dict[str, Any] = {"model": chosen, "messages": messages, "stream": True,
                                   "stream_options": {"include_usage": True}}
        if routing_strategy is not None and is_router(chosen):
            payload["routing_strategy"] = routing_strategy
        if reasoning_effort is not None and is_router(chosen):  # checked on liner-claude-router only (11-22)
            payload["reasoning_effort"] = reasoning_effort
        if response_format is not None:
            payload["response_format"] = response_format
        response = self._send("POST", CHAT_URL, self._bearer(key), json=payload)
        if "text/event-stream" in response.headers.get("content-type", ""):
            return assemble_chat_stream(response.text, CHAT_URL)
        return self._parse_json(response, CHAT_URL)

    def decide(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        model = self.setting_model("LINER_DECISION_MODEL")
        key = require_api_key(self._env_file)
        return self._json("POST", DECISIONS_URL, self._bearer(key),
                          json={"model": model, "state": state, "questions": questions})

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> dict[str, Any]:
        model = self.setting_model("LINER_RERANK_MODEL")
        key = require_api_key(self._env_file)
        payload: dict[str, Any] = {"model": model, "query": query, "documents": documents}
        if top_n is not None:
            payload["top_n"] = top_n
        return self._json("POST", RERANK_URL, self._bearer(key), json=payload)

    def transcribe(self, filename: str, data: bytes) -> dict[str, Any]:
        model = self.setting_model("LINER_STT_MODEL")
        key = require_api_key(self._env_file)
        return self._json("POST", TRANSCRIPTION_URL, self._bearer(key),
                          data={"model": model, "language": "ko"}, files={"file": (filename, data)})

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> dict[str, Any]:
        """Images API → {"data": [{"b64_json", "media_type"}], "usage": {...}}. A failure late in a long
        generation arrives as HTTP 200 with a top-level `error`, so that is turned into an error here."""
        model = self.setting_model("LINER_IMAGE_MODEL")
        key = require_api_key(self._env_file)
        body = self._json("POST", IMAGES_URL, self._bearer(key), timeout=IMAGE_TIMEOUT,
                          json={"model": model, "prompt": prompt, "resolution": "1K", "aspect_ratio": aspect_ratio})
        data = body.get("data")
        if body.get("error") or not isinstance(data, list) or not data or not data[0].get("b64_json"):
            raise LinerAPIError(f"Liner 이미지 생성이 실패했어요: {IMAGES_URL}. 잠시 뒤 다시 시도하세요.", "server")
        return {**body, "model": body.get("model") or model}

    # --- Search / Agent / Tools API -------------------------------------------------------------
    def search(self, query: str) -> dict[str, Any]:
        key = require_api_key(self._env_file)
        return self._json("POST", SEARCH_URL, {"x-api-key": key}, json={"query": query, **SEARCH_OPTIONS})

    def ai_search(self, query: str) -> dict[str, Any]:
        """Search Agent (SSE) → {answer, references, chunks}. Chunks carry date/sourceTitle/sourceUrl."""
        key = require_api_key(self._env_file)
        body = {"messages": [{"role": "user", "content": query}], "lang": "ko", "mode": "general"}
        return parse_ai_search(self._text("POST", AI_SEARCH_URL, {"x-api-key": key}, json=body), AI_SEARCH_URL)

    def visualize(self, query: str) -> dict[str, Any]:
        """Visualization (SSE `data-atlas`) → {html, description, theme, resource_id}."""
        key = require_api_key(self._env_file)
        text = self._text("POST", VISUALIZATION_URL, {"x-api-key": key}, json={"query": query})
        return parse_visualization(text, VISUALIZATION_URL)

    # --- Credits (free reads) -------------------------------------------------------------------
    def credits_balance(self) -> dict[str, Any]:
        """{"billing_type", "balance" (micro-USD int), "balance_usd" (str), "currency"}."""
        key = require_api_key(self._env_file)
        return self._json("GET", BALANCE_URL, {"x-api-key": key})

    def credits_usage(self) -> dict[str, Any]:
        """Usage over time. The docs name the endpoint but not its body, so it is returned as received."""
        key = require_api_key(self._env_file)
        return self._json("GET", USAGE_URL, {"x-api-key": key})

    # --- transport ------------------------------------------------------------------------------
    @staticmethod
    def _bearer(key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}"}

    def _send(self, method: str, url: str, headers: dict[str, str], **kwargs: Any) -> httpx.Response:
        # Last G3 gate: whatever built the body, nothing sensitive leaves this process.
        labels = outgoing_labels([kwargs.get("json"), kwargs.get("data")], self.secrets())
        if labels:
            raise LinerAPIError(
                f"보내려던 요청에 개인정보·비밀값으로 보이는 문자열({', '.join(labels)})이 있어 Liner 로 보내지 않았어요. "
                "해당 부분을 가린 뒤 다시 시도하세요.", "blocked_sensitive")
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                response = client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            # Message deliberately omits the exception text so headers can never leak.
            raise LinerAPIError(
                f"Liner API 에 연결하지 못했습니다: {url} ({type(exc).__name__}). 네트워크를 확인하세요.", "network"
            ) from None
        if response.is_error:
            raise http_error(url, response.status_code)
        return response

    def _json(self, method: str, url: str, headers: dict[str, str], **kwargs: Any) -> dict[str, Any]:
        return self._parse_json(self._send(method, url, headers, **kwargs), url)

    @staticmethod
    def _parse_json(response: httpx.Response, url: str) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            raise LinerAPIError(f"Liner API 응답이 JSON 이 아닙니다: {url} → HTTP {response.status_code}",
                                "bad_response") from None
        if not isinstance(body, dict):
            raise LinerAPIError(f"Liner API 응답이 JSON 객체가 아닙니다: {url}", "bad_response")
        return body

    def _text(self, method: str, url: str, headers: dict[str, str], **kwargs: Any) -> str:
        return self._send(method, url, headers, **kwargs).text
