from __future__ import annotations
"""Scripted fake Liner API on httpx.MockTransport. No real network.

Shapes follow real responses captured on 2026-11-16 (Decisions, Rerank, Search Agent SSE, Visualization SSE,
Router chat with `model`, credits balance). `requests` holds the paid calls; free credit reads go to
`free_requests` so call-count assertions stay about billable work.
"""

import json
from collections.abc import Callable, Mapping
from typing import Any

import base64
import io

import httpx
from PIL import Image

from app.liner import (
    AI_SEARCH_URL, BALANCE_URL, CHAT_URL, DECISIONS_URL, IMAGES_URL, RERANK_URL, SEARCH_URL, TRANSCRIPTION_URL,
    USAGE_URL, VISUALIZATION_URL,
)

DEFAULT_SEARCH_BODY = {"results": []}
START_BALANCE = 200_000_000  # micro-USD ($200)
COST_PER_CALL = 1_000  # $0.001 per paid fake call
FAKE_VIZ_HTML = (
    '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@liner-fe/design-token@^3.0.0/lib/index.css">'
    "<style>.flow-node{padding:8px}</style></head><body><div id=\"step-container\"></div>"
    '<img src="https://example.com/x.png" alt="">'
    "<script>document.getElementById('step-container').textContent='가입 → 요일 선택 → 결제';</script>"
    "</body></html>"
)


def tiny_png() -> str:
    """A deterministic 24×16 PNG (base64) standing in for a generated picture."""
    buffer = io.BytesIO()
    Image.new("RGB", (24, 16), (236, 170, 190)).save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


IMAGE_USAGE = {"prompt_tokens": 43, "completion_tokens": 4175, "total_tokens": 4218, "cost": 0.0184}


STREAM_ERROR = object()  # a scripted chat output that answers with an SSE error event


def sse(*payloads: Mapping[str, Any]) -> str:
    lines = [":ping", ""]
    for p in payloads:
        lines += ["event:data", f"data:{json.dumps(p, ensure_ascii=False)}", ""]
    return "\n".join([*lines, "data:[DONE]", ""])


def ai_search_sse(search_body: Mapping[str, Any]) -> str:
    """A Search Agent stream whose chunks are the web search results (content = snippet)."""
    results = [r for r in search_body.get("results", []) if isinstance(r, Mapping)]
    text = lambda r: str(r.get("snippet") or r.get("description") or "")  # noqa: E731
    refs = [{"title": r.get("title"), "url": r.get("url"), "description": text(r), "date": r.get("date")}
            for r in results]
    chunks = [{"num": i, "id": f"chunk-{i}", "content": text(r), "description": text(r), "date": r.get("date"),
               "sourceTitle": r.get("title"), "sourceUrl": r.get("url")} for i, r in enumerate(results, start=1)]
    return sse({"type": "start"}, {"type": "data-search-references", "data": {"references": refs}},
               {"type": "data-search-chunks", "data": {"referenceChunks": chunks}},
               {"type": "text-delta", "id": "text-1", "delta": "가짜 AI 검색 답 ((1))"}, {"type": "finish"})


def default_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    """noul → 0.9 yes; choice → the first option at 0.9 with confidence 0.8."""
    answers: dict[str, Any] = {}
    for name, q in payload["questions"].items():
        if q["type"] == "noul":
            answers[name] = {"type": "noul", "noul": 0.9}
        else:
            options = list(q["criteria"])
            probs = {o: (0.9 if i == 0 else round(0.1 / max(1, len(options) - 1), 3)) for i, o in enumerate(options)}
            answers[name] = {"type": "choice", "choice": options[0], "confidence": 0.8, "probabilities": probs}
    return answers


def overlap_score(query: str, document: str) -> float:
    words = set(query.split())
    return round(sum(1 for w in words if w in document) / max(1, len(words)), 4)


class FakeLiner:
    """Answers chat calls by response_format schema name; other endpoints with fixed or derived bodies.

    `chat_outputs[name]` is a list of outputs used in order; the last one repeats.
    An output may be a callable taking the request payload (to echo ids, etc.).
    `search_status` applies to both Web Search and the Search Agent (AI Search).
    """

    def __init__(
        self,
        chat_outputs: Mapping[str, list[Any]],
        search_body: Mapping[str, Any] | None = None,
        search_status: int = 200,
        ai_search_status: int | None = None,
        decision: Callable[[Mapping[str, Any]], dict[str, Any]] = default_decision,
        decision_status: int = 200,
        rerank_status: int = 200,
        viz_status: int = 200,
        viz_html: str = FAKE_VIZ_HTML,
        transcript: str = "배송은 토요일에만 해요. 일시정지는 꼭 넣어 주세요.",
        credits_status: int = 200,
        answered_model: str | None = None,
        image_error: bool = False,
    ) -> None:
        self._outputs = {name: list(items) for name, items in chat_outputs.items()}
        self._search_body = dict(search_body) if search_body is not None else DEFAULT_SEARCH_BODY
        self._search_status = search_status
        self._ai_status = search_status if ai_search_status is None else ai_search_status
        self._decision = decision
        self._decision_status = decision_status
        self._rerank_status = rerank_status
        self._viz_status = viz_status
        self._viz_html = viz_html
        self._transcript = transcript
        self._credits_status = credits_status
        self._answered_model = answered_model
        self._image_error = image_error
        self.requests: list[httpx.Request] = []
        self.free_requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    # --- inspection -----------------------------------------------------------------------------
    def _payloads(self, url: str) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests if str(r.url) == url]

    @property
    def chat_names(self) -> list[str]:
        return [p["response_format"]["json_schema"]["name"] for p in self._payloads(CHAT_URL)]

    @property
    def web_search_queries(self) -> list[str]:
        return [p["query"] for p in self._payloads(SEARCH_URL)]

    @property
    def ai_search_queries(self) -> list[str]:
        return [p["messages"][-1]["content"] for p in self._payloads(AI_SEARCH_URL)]

    @property
    def search_queries(self) -> list[str]:
        """Research queries in the order they were first asked (AI Search or its Web Search fallback)."""
        return list(dict.fromkeys(self.ai_search_queries + self.web_search_queries))

    def chat_payloads(self, name: str) -> list[dict[str, Any]]:
        return [p for p in self._payloads(CHAT_URL) if p["response_format"]["json_schema"]["name"] == name]

    def payloads(self, url: str) -> list[dict[str, Any]]:
        return self._payloads(url)

    # --- answering ------------------------------------------------------------------------------
    def _handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in (BALANCE_URL, USAGE_URL):
            self.free_requests.append(request)
            return self._credits(url)
        self.requests.append(request)
        if url == SEARCH_URL:
            return httpx.Response(self._search_status, json=self._search_body)
        if url == AI_SEARCH_URL:
            return httpx.Response(self._ai_status, text=ai_search_sse(self._search_body))
        if url == DECISIONS_URL:
            payload = json.loads(request.content)
            return httpx.Response(self._decision_status, json={
                "model": payload["model"], "answers": self._decision(payload), "usage": {"cost": 1.7e-05}})
        if url == RERANK_URL:
            return self._rerank(json.loads(request.content))
        if url == VISUALIZATION_URL:
            atlas = {"type": "data-atlas", "data": {"atlasArtifact": {
                "html": self._viz_html, "theme": "process", "description": "가짜 흐름도", "resourceId": "viz_fake"}}}
            return httpx.Response(self._viz_status, text=sse({"type": "start"}, atlas, {"type": "finish"}))
        if url == IMAGES_URL:
            if self._image_error:  # docs: a late failure is HTTP 200 with a top-level `error`
                return httpx.Response(200, text="   " + json.dumps({"error": {"message": "generation failed"}}))
            return httpx.Response(200, json={"created": 1, "data": [{"b64_json": tiny_png(), "media_type": "image/png"}],
                                             "usage": IMAGE_USAGE})
        if url == TRANSCRIPTION_URL:
            return httpx.Response(200, json={"text": self._transcript, "usage": {"cost": 0.0012}})
        return self._chat(json.loads(request.content))

    def _credits(self, url: str) -> httpx.Response:
        if url == USAGE_URL:
            return httpx.Response(self._credits_status, json={"data": []})
        balance = START_BALANCE - COST_PER_CALL * len(self.requests)
        return httpx.Response(self._credits_status, json={
            "billing_type": "prepaid", "balance": balance, "balance_usd": f"{balance / 1e6:.6f}", "currency": "USD"})

    def _rerank(self, payload: Mapping[str, Any]) -> httpx.Response:
        if self._rerank_status != 200:
            return httpx.Response(self._rerank_status, json={"error": "rerank failed"})
        scored = sorted(((overlap_score(payload["query"], d), i) for i, d in enumerate(payload["documents"])),
                        key=lambda x: (-x[0], x[1]))
        top = scored[: payload.get("top_n") or len(scored)]
        return httpx.Response(200, json={"model": "rerank-fake", "results": [
            {"index": i, "relevance_score": s} for s, i in top], "usage": {"total_tokens": 10, "cost": 6.6e-07}})

    def _chat(self, payload: Mapping[str, Any]) -> httpx.Response:
        name = payload["response_format"]["json_schema"]["name"]
        queue = self._outputs.get(name)
        if not queue:
            return httpx.Response(500, json={"error": f"no scripted output for {name}"})
        output = queue.pop(0) if len(queue) > 1 else queue[0]
        if output is STREAM_ERROR:  # 11-22: Liner ended a ~300 s developer stream with an error event
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text=sse({"error": {"message": "upstream timeout"}}))
        if isinstance(output, Callable):
            output = output(payload)
        content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        body: dict[str, Any] = {"choices": [{"message": {"role": "assistant", "content": content}}]}
        if self._answered_model:
            body = {**body, "model": self._answered_model, "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.0021}}
        return httpx.Response(200, json=body)
