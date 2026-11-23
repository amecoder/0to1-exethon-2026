from __future__ import annotations
"""Parsers for Liner's SSE answers (`event:data` + `data:{json}` lines, ending with `data:[DONE]`).

Shapes are the ones seen in real calls on 2026-11-16 (docs/reports/2026-11-16_엑스톤_Liner_API_최신_전수조사.md):
- Search Agent `/agents/search`: `text-delta` (answer), `data-search-references` (`data.references[]`),
  `data-search-chunks` (`data.referenceChunks[]` with num/id/content/description/date/sourceTitle/sourceUrl)
- Visualization `/tools/visualization`: `data-atlas` (`data.atlasArtifact.html/description/theme/resourceId`)
"""

import json
from collections.abc import Iterator
from typing import Any

_ERROR_TYPES = frozenset({"error", "data-error"})


def sse_payloads(text: str) -> Iterator[dict[str, Any]]:
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            payload = json.loads(raw)
        except ValueError:
            continue
        if isinstance(payload, dict):
            yield payload


def _fail(url: str, payload: dict[str, Any]) -> None:
    """The provider's error text may echo the request or a key, so only a fixed message is raised."""
    from app.liner import LinerAPIError  # local: app.liner imports this module

    raise LinerAPIError(f"Liner 응답 스트림이 오류로 끝났어요: {url}. 잠시 뒤 다시 시도하세요.", "stream_error")


def _text(value: Any) -> str:
    return str(value) if value is not None else ""


def parse_ai_search(text: str, url: str) -> dict[str, Any]:
    answer: list[str] = []
    references: list[dict[str, str]] = []
    chunks: list[dict[str, str]] = []
    for payload in sse_payloads(text):
        kind, data = payload.get("type"), payload.get("data")
        if kind in _ERROR_TYPES:
            _fail(url, payload)
        elif kind == "text-delta":
            answer.append(_text(payload.get("delta")))
        elif kind == "data-search-references" and isinstance(data, dict) and isinstance(data.get("references"), list):
            references = [{"url": _text(r.get("url")), "title": _text(r.get("title")),
                           "description": _text(r.get("description")), "date": _text(r.get("date"))}
                          for r in data["references"] if isinstance(r, dict)]
        elif kind == "data-search-chunks" and isinstance(data, dict) and isinstance(data.get("referenceChunks"), list):
            chunks = [{"num": _text(c.get("num")), "chunk_id": _text(c.get("id")), "content": _text(c.get("content")),
                       "description": _text(c.get("description")), "date": _text(c.get("date")),
                       "title": _text(c.get("sourceTitle")), "url": _text(c.get("sourceUrl"))}
                      for c in data["referenceChunks"] if isinstance(c, dict)]
    if not answer and not references and not chunks:
        from app.liner import LinerAPIError

        raise LinerAPIError(f"Liner AI 검색 응답에 답·출처가 없습니다: {url}", "bad_response")
    return {"answer": "".join(answer), "references": references, "chunks": chunks}


def assemble_chat_stream(text: str, url: str) -> dict[str, Any]:
    """Chat Completions SSE (`chat.completion.chunk` …, usage chunk with empty choices, `[DONE]`) →
    the same shape as a non-streaming completion, so callers do not care which one arrived."""
    content: list[str] = []
    model, finish, usage, seen = "", None, None, False
    for payload in sse_payloads(text):
        if "error" in payload:
            _fail(url, payload)
        model = _text(payload.get("model")) or model
        if isinstance(payload.get("usage"), dict):
            usage = payload["usage"]
        for choice in payload.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            seen = True
            delta = choice.get("delta") or {}
            if isinstance(delta, dict) and delta.get("content"):
                content.append(_text(delta["content"]))
            finish = choice.get("finish_reason") or finish
    if not seen:
        from app.liner import LinerAPIError

        raise LinerAPIError(f"Liner 대화 응답 스트림이 비어 있습니다: {url}", "bad_response")
    result: dict[str, Any] = {"object": "chat.completion", "model": model,
                              "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(content)},
                                           "finish_reason": finish}]}
    if usage is not None:
        result["usage"] = usage
    return result


def parse_visualization(text: str, url: str) -> dict[str, Any]:
    for payload in sse_payloads(text):
        kind, data = payload.get("type"), payload.get("data")
        if kind in _ERROR_TYPES:
            _fail(url, payload)
        if kind == "data-atlas" and isinstance(data, dict) and isinstance(data.get("atlasArtifact"), dict):
            art = data["atlasArtifact"]
            if art.get("html"):
                return {"html": _text(art.get("html")), "description": _text(art.get("description")),
                        "theme": _text(art.get("theme")), "resource_id": _text(art.get("resourceId"))}
    from app.liner import LinerAPIError

    raise LinerAPIError(f"Liner 시각화 응답에 HTML 이 없습니다: {url}", "bad_response")
