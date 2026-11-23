from __future__ import annotations
"""Runs one agent turn through Liner Model (json_schema) or the Liner Search tool, logging each call."""

import json
import time
from collections.abc import Mapping, Sequence
from typing import Any

from app.attachments import REQUESTS, Attachment, data_part, file_model, system_lines
from app.definitions import AgentDef
from app.guardrails import (
    LABELS, PERSONAL_LABELS, mask_personal, redact, sensitive_labels, strings_in, strip_data_uris, strip_secrets,
)
from app.liner import LinerAPIError, LinerClient, LinerConfigError, is_router
from app.limits import (
    BUDGET_MODE_SHARE, LimitReachedError, Limits, budget_mode_due, budget_mode_switched, check, predict_stage,
)
from app.workspace import Workspace
from app.tools import TOOLS

_URL_KEYS = ("url", "link", "source_url")
_TEXT_KEYS = ("snippet", "content", "text", "description", "summary")
_LIST_KEYS = ("results", "data", "items", "documents")
MAX_CHUNKS_PER_QUERY = 8  # 제안: AI Search returned 57 chunks for one query; the researcher reads the first 8


SYSTEM_ACTOR = "system"


def elapsed_ms(started: float) -> int:
    """Wall time of one Liner call since `started` (time.monotonic()), for the per-agent log."""
    return max(0, round((time.monotonic() - started) * 1000))


class AgentOutputError(RuntimeError):
    """The model answered, but not with JSON matching the requested shape."""


def system_prompt(agent: AgentDef) -> str:
    """Persona, role and instructions come only from the agent definition file (FR-02)."""
    return f"{agent.instructions}\n\n[페르소나] {agent.persona}\n[역할] {agent.role}\n" \
           "응답은 요청한 JSON 스키마만 따른다. 공유 원본에 없는 사실을 지어내지 않는다."


def response_format(name: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": dict(schema)}}


def normalize_hits(body: Mapping[str, Any]) -> list[dict[str, str]]:
    """Accept a few plausible Search response shapes; keep url/title/snippet only."""
    items = next((body[k] for k in _LIST_KEYS if isinstance(body.get(k), list)), [])
    hits = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        url = next((str(item[k]) for k in _URL_KEYS if item.get(k)), "")
        snippet = next((str(item[k]) for k in _TEXT_KEYS if item.get(k)), "")
        hits.append({"url": url, "title": str(item.get("title") or ""), "snippet": snippet,
                     "date": str(item.get("date") or ""), "via": "search"})
    return hits


def chunk_hits(body: Mapping[str, Any]) -> list[dict[str, str]]:
    """AI Search → hits. Each referenceChunk is one hit (content = snippet); references fill in when no chunks."""
    chunks = [c for c in body.get("chunks", []) if c.get("content")]
    if chunks:
        return [{"url": c["url"], "title": c["title"], "snippet": c["content"], "date": c["date"],
                 "chunk_id": c["chunk_id"], "description": c["description"], "via": "ai_search"}
                for c in chunks[:MAX_CHUNKS_PER_QUERY]]
    return [{"url": r["url"], "title": r["title"], "snippet": r["description"], "date": r["date"], "via": "ai_search"}
            for r in body.get("references", [])[:MAX_CHUNKS_PER_QUERY] if r.get("description")]


def _count(usage: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def usage_fields(body: Mapping[str, Any]) -> dict[str, Any]:
    """`usage` of a Liner response → event fields. Chat-style (prompt/completion) and audio-style
    (input/output) token names both map to prompt_tokens/completion_tokens; absent values stay None."""
    usage = body.get("usage")
    usage = usage if isinstance(usage, Mapping) else {}
    prompt = _count(usage, "prompt_tokens", "input_tokens")
    completion = _count(usage, "completion_tokens", "output_tokens")
    total = _count(usage, "total_tokens")
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    cost = usage.get("cost")
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total,
            "cost": float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None}


def reasoning_tokens(body: Mapping[str, Any]) -> int | None:
    """Chat usage's completion_tokens_details.reasoning_tokens (how much of the answer time went to thinking)."""
    usage = body.get("usage")
    details = usage.get("completion_tokens_details") if isinstance(usage, Mapping) else None
    return _count(details, "reasoning_tokens") if isinstance(details, Mapping) else None


class ToolNotAllowedError(LinerConfigError):
    """The agent's file does not declare this tool (app/tools.py). A config error, so callers that skip a failed
    rerank or decision on LinerConfigError (fail-open) treat it the same way."""


class AgentRunner:
    def __init__(self, client: LinerClient, agents: Mapping[str, AgentDef], workspace: Workspace) -> None:
        self._client = client
        self._agents = agents
        self._ws = workspace

    @property
    def client(self) -> LinerClient:
        return self._client

    @property
    def limits(self) -> Limits:
        """Read per call (like the key), so a changed .env applies without restarting."""
        return Limits.from_env(self._client.env_file)

    def _check_limits(self, agent_id: str) -> None:
        """G7 before every Liner call. Time counts only while a work stage is running."""
        pipeline = self._ws.pipeline
        try:
            check(self._ws.log.events, pipeline["stage"], self.limits, timed=pipeline["status"] == "running")
        except LimitReachedError as exc:
            self._ws.guardrail("G7", "blocked", "상한에 닿아 Liner 호출을 멈춤", actor=agent_id, limit=exc.limit,
                               used=exc.used, max=exc.maximum, stage=exc.stage)
            raise

    def check_stage_budget(self, stage: str) -> None:
        """G7 before a work stage starts: stop when its typical cost would pass the budget."""
        try:
            predict_stage(self._ws.log.events, stage, self.limits)
        except LimitReachedError as exc:
            self._ws.guardrail("G7", "blocked", "단계 예상 비용이 예산을 넘어 시작 전에 멈춤", limit=exc.limit,
                               used=exc.used, max=exc.maximum, stage=exc.stage, predicted=exc.predicted)
            raise

    def _budget_mode(self, agent_id: str) -> bool:
        """On from BUDGET_MODE_SHARE of the cost budget; the switch is recorded once (G7 flagged)."""
        limits = self.limits
        if limits.max_cost_usd is None:
            return False
        events = self._ws.log.events
        if budget_mode_switched(events):
            return True
        if not budget_mode_due(events, limits):
            return False
        self._ws.guardrail("G7", "flagged", f"예산의 {round(BUDGET_MODE_SHARE * 100)}%를 써서 이제부터 싼 모델로 답하게 했어요",
                           actor=agent_id, limit="budget_mode", stage=self._ws.pipeline["stage"])
        return True

    def ask(self, agent_id: str, task: str, name: str, schema: Mapping[str, Any],
            extra: Mapping[str, Any] | None = None, reads: Sequence[str] | None = None,
            retry_cut: bool = True) -> dict[str, Any]:
        """`reads`: send only these kinds (within the agent's read permission) instead of its whole list.
        `retry_cut`: a stream Liner ended with an error is asked once more (11-22: S5 stopped on one after 41 s);
        S6 turns it off because it runs its own attempts."""
        agent = self._agents[agent_id]
        self._check_limits(agent_id)
        self._ws.set_pipeline(active_agent=agent_id)
        model = agent.model or self._client.configured_model()
        kinds = agent.reads if reads is None else [kind for kind in agent.reads if kind in reads]
        context = {kind: list(self._ws.items(kind)) for kind in kinds if self._ws.items(kind)}
        # Prototype photos are base64 data URIs: no agent needs the bytes, and they cost ~100k tokens per call.
        user = f"{task}\n\n[공유 원본 — 읽기 권한 항목]\n{strip_data_uris(json.dumps(context, ensure_ascii=False))}"
        if extra:
            user += f"\n\n[추가 입력]\n{strip_data_uris(json.dumps(dict(extra), ensure_ascii=False))}"
        messages = [{"role": "system", "content": system_prompt(agent)}, {"role": "user", "content": user}]
        budget_mode = self._budget_mode(agent_id)
        # Non-router models (liner-mark) answer 400 to routing_strategy: never sent, budget mode or not.
        strategy = ("cost" if budget_mode else agent.routing_strategy) if is_router(model) else None
        effort = agent.reasoning_effort if is_router(model) else None
        started = time.monotonic()
        try:
            body = self._client.chat(messages, response_format=response_format(name, schema), model=model,
                                     routing_strategy=strategy, reasoning_effort=effort)
        except LinerAPIError as exc:
            if not retry_cut or exc.kind != "stream_error":
                raise
            self._ws.emit("liner_retry", agent_id, {"agent": agent_id, "schema": name, "kind": exc.kind,
                                                     "after_ms": elapsed_ms(started)})
            self._check_limits(agent_id)
            started = time.monotonic()
            body = self._client.chat(messages, response_format=response_format(name, schema), model=model,
                                     routing_strategy=strategy, reasoning_effort=effort)
        output = self._clean(agent_id, self._parse(agent, body))
        answered = body.get("model") if isinstance(body.get("model"), str) else None
        self._ws.emit("liner_chat", agent_id, {
            "api": "model", "model": model, "schema": name, "task": task, "output": output,
            # The router names the model that actually answered; liner-mark does not (docs "Response model").
            "answered_model": self._clean(agent_id, answered) if answered else None,
            "routing_strategy": strategy, "reasoning_effort": effort, "budget_mode": budget_mode, **usage_fields(body),
            "reasoning_tokens": reasoning_tokens(body), "duration_ms": elapsed_ms(started),
        })
        return output

    def _tool(self, agent_id: str, tool: str) -> None:
        """Only tools the agent's file declares (app/tools.py registry); a refusal is recorded (G4) before any call."""
        if tool not in self._agents[agent_id].tools:
            self._ws.guardrail("G4", "blocked", f"{tool} 도구는 {agent_id} 에게 허용되지 않아 부르지 않음",
                               actor=agent_id, tool=tool)
            raise ToolNotAllowedError(f"{agent_id} 에게는 {TOOLS[tool].title} 도구가 없습니다")

    def search(self, agent_id: str, query: str) -> list[dict[str, str]]:
        """Liner Web Search as the agent's tool. A failure is logged and returns no hits (G1 keeps 미확인)."""
        self._tool(agent_id, "liner_search")
        self._check_limits(agent_id)
        self._ws.set_pipeline(active_agent=agent_id)
        started = time.monotonic()
        try:
            hits = self._clean_hits(agent_id, normalize_hits(self._client.search(query)))
            error = None
        except LinerAPIError as exc:
            hits, error = [], self._error_text(exc)
        self._ws.emit("liner_search", agent_id, {
            "api": "search", "query": query, "result_count": len(hits), "results": hits, "error": error,
            "duration_ms": elapsed_ms(started),
        })
        return hits

    def research(self, agent_id: str, query: str) -> list[dict[str, str]]:
        """AI Search (answer + source chunks) first; on failure fall back to Web Search when the agent has it."""
        agent = self._agents[agent_id]
        if "liner_ai_search" not in agent.tools:  # a choice, not a refusal: no G4 — web search still gates itself
            return self.search(agent_id, query)
        self._check_limits(agent_id)
        self._ws.set_pipeline(active_agent=agent_id)
        started = time.monotonic()
        try:
            body = self._client.ai_search(query)
            hits = self._clean_hits(agent_id, chunk_hits(body))
            error, answer = None, self._clean(agent_id, str(body.get("answer", "")))
        except LinerAPIError as exc:
            hits, error, answer = [], self._error_text(exc), ""
        self._ws.emit("liner_search", agent_id, {
            "api": "ai_search", "query": query, "result_count": len(hits), "results": hits, "error": error,
            "answer": answer[:1000], "fallback": error is not None and "liner_search" in agent.tools,
            "duration_ms": elapsed_ms(started),
        })
        if error is not None and "liner_search" in agent.tools:
            return self.search(agent_id, query)
        return hits

    def decide(self, agent_id: str, purpose: str, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        """Decisions API. Config errors (no LINER_DECISION_MODEL) raise before anything is sent or counted."""
        self._tool(agent_id, "liner_decisions")
        self._client.setting_model("LINER_DECISION_MODEL")
        return self._counted("liner_decision", agent_id, {"api": "decisions", "purpose": purpose},
                             lambda: self._clean(agent_id, self._client.decide(state, questions)),
                             lambda body: {"answers": body.get("answers"), "model": body.get("model"),
                                           **usage_fields(body)})

    def rerank(self, agent_id: str, query: str, documents: list[str], top_n: int) -> dict[str, Any]:
        self._tool(agent_id, "liner_rerank")
        self._client.setting_model("LINER_RERANK_MODEL")
        return self._counted("liner_rerank", agent_id, {"api": "rerank", "query": query, "documents": len(documents)},
                             lambda: self._clean(agent_id, self._client.rerank(query, documents, top_n)),
                             lambda body: {"results": body.get("results"), "model": body.get("model"),
                                           **usage_fields(body)})

    def visualize(self, agent_id: str, query: str) -> dict[str, Any]:
        self._tool(agent_id, "liner_visualization")
        # HTML: only the personal patterns are masked — long ids/hashes in markup are not keys.
        return self._counted("liner_visualization", agent_id, {"api": "visualization", "query": query},
                             lambda: self._clean(agent_id, self._client.visualize(query), html=True),
                             lambda body: {"description": body.get("description"), "chars": len(body.get("html", ""))})

    def image(self, agent_id: str, slot: str, prompt: str) -> dict[str, Any]:
        """Images API for one prototype slot. G3 runs on the prompt before anything is counted or recorded;
        the event keeps model, slot, prompt and usage — never the picture itself."""
        self._tool(agent_id, "liner_images")
        model = self._client.setting_model("LINER_IMAGE_MODEL")
        labels = sensitive_labels([prompt])
        if labels:
            self._ws.guardrail("G3", "blocked", "이미지 프롬프트에 민감 정보가 있어 보내지 않음", actor=agent_id,
                               kinds=labels, slot=slot)
            raise LinerAPIError(f"이미지 프롬프트에 개인정보·비밀값으로 보이는 문자열({', '.join(labels)})이 있어요",
                                "blocked_sensitive")
        return self._counted("liner_image", agent_id, {"api": "images", "model": model, "slot": slot, "prompt": prompt},
                             lambda: self._client.generate_image(prompt),
                             lambda body: {"media_type": body["data"][0].get("media_type"), **usage_fields(body)})

    def transcribe(self, filename: str, data: bytes) -> dict[str, Any]:
        """Speech-to-text for S1. The event keeps size and length only — the text is checked by G3 first
        (ingest blocks or masks it), so only the configured key is stripped here."""
        self._client.setting_model("LINER_STT_MODEL")
        return self._counted("liner_transcription", SYSTEM_ACTOR,
                             {"api": "audio", "filename": filename, "bytes": len(data)},
                             lambda: redact(self._client.transcribe(filename, data), self._client.secrets(), False),
                             lambda body: {"chars": len(str(body.get("text", ""))), **usage_fields(body)})

    def read_attachment(self, filename: str, found: Attachment, data: bytes, purpose: str) -> dict[str, Any]:
        """One chat call reading an image (router, LINER_MODEL) or a PDF (catalog model, LINER_FILE_MODEL).
        Counted for G7; the event keeps file name, kind, size, length and usage — never the data or the text.
        The answer passes G3 masking before it is returned."""
        name, schema, prompt = REQUESTS[purpose]
        model = self._client.configured_model() if found.kind == "image" else file_model(self._client.env_file)
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}, data_part(found, filename, data)]}]

        def call() -> dict[str, Any]:
            body = self._client.chat(messages, response_format=response_format(name, schema), model=model)
            try:
                output = json.loads(body["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError, ValueError):
                output = None
            if not isinstance(output, dict):
                raise LinerAPIError("첨부를 읽은 답을 알아보지 못했어요. 다시 올려 주세요", "bad_response")
            return {"output": self._clean(SYSTEM_ACTOR, output), "usage": body.get("usage")}

        def chars(result: Mapping[str, Any]) -> int:
            output = result["output"]
            return len(str(output.get("text", ""))) if purpose == "memo" else len(system_lines(output.get("systems")))

        result = self._counted("liner_attachment", SYSTEM_ACTOR,
                               {"api": "model", "model": model, "purpose": purpose, "filename": filename,
                                "kind": found.kind, "bytes": len(data)},
                               call, lambda r: {"chars": chars(r), **usage_fields(r)})
        return result["output"]

    def _counted(self, event: str, actor: str, data: Mapping[str, Any], call: Any, summary: Any) -> dict[str, Any]:
        """G7 check, call, and one counted event whether it worked or not. Errors are re-raised."""
        self._check_limits(actor)
        if actor != SYSTEM_ACTOR:
            self._ws.set_pipeline(active_agent=actor)
        started = time.monotonic()
        try:
            body = call()
        except LinerAPIError as exc:
            self._ws.emit(event, actor, {**data, "error": self._error_text(exc), "duration_ms": elapsed_ms(started)})
            raise
        self._ws.emit(event, actor, {**data, **summary(body), "error": None, "duration_ms": elapsed_ms(started)})
        return body

    # --- G3 on what comes back: nothing is recorded or returned before this -------------------------
    def _clean(self, actor: str, value: Any, html: bool = False) -> Any:
        """Mask sensitive patterns and the configured key in a Liner answer; record a G3 event if anything changed."""
        secrets = self._client.secrets()
        labels = [] if html else sensitive_labels(strings_in(value))
        leaked = any(secret in text for secret in secrets for text in strings_in(value))
        if html:
            cleaned = redact(value, secrets, False)
            labels = [label for label in PERSONAL_LABELS if label in sensitive_labels(strings_in(cleaned))]
            cleaned = mask_personal(cleaned)
        else:
            cleaned = redact(value, secrets)
        if labels or leaked:
            kinds = [*labels, *([LABELS["api_key"]] if leaked and LABELS["api_key"] not in labels else [])]
            self._ws.guardrail("G3", "masked", "Liner 응답의 민감 정보를 가린 뒤 기록", actor=actor, kinds=kinds)
        return cleaned

    def _clean_hits(self, actor: str, hits: list[dict[str, str]]) -> list[dict[str, str]]:
        """Search results: text fields fully; URLs keep their slugs (only the configured key is stripped)."""
        texts = self._clean(actor, [{k: v for k, v in h.items() if k != "url"} for h in hits])
        return [{**t, "url": strip_secrets(h.get("url", ""), self._client.secrets())} for t, h in zip(texts, hits)]

    def _error_text(self, exc: LinerAPIError) -> str:
        """Our own fixed messages; still scrubbed in case a future message carries provider text."""
        return redact(str(exc), self._client.secrets())

    @staticmethod
    def _parse(agent: AgentDef, body: Mapping[str, Any]) -> dict[str, Any]:
        try:
            content = body["choices"][0]["message"]["content"]
            output = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError):
            raise AgentOutputError(f"{agent.name}({agent.id}) 의 응답을 JSON 으로 읽지 못했습니다") from None
        if not isinstance(output, dict):
            raise AgentOutputError(f"{agent.name}({agent.id}) 의 응답이 JSON 객체가 아닙니다")
        return output
