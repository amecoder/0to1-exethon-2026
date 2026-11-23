from __future__ import annotations
"""Long generations (documents, prototype) must stream: Liner closes a silent request after ~125 s (docs
"Chat Completions › Streaming"). Real run 2026-11-17 failed twice at S5 with ReadTimeout before this."""

import json
from pathlib import Path

import httpx
import pytest

from app.liner import LinerAPIError, LinerClient


def _sse(*chunks: dict | str) -> str:
    lines = [f"data: {c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)}" for c in chunks]
    return "\n\n".join(lines) + "\n\n"


def _chunk(content: str | None = None, model: str = "claude-sonnet-5.5", finish: str | None = None) -> dict:
    delta = {"content": content} if content is not None else {}
    return {"object": "chat.completion.chunk", "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def _client(env: Path, calls: list[httpx.Request], body: str, content_type: str = "text/event-stream") -> LinerClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=body, headers={"content-type": content_type})

    return LinerClient(env_file=env, transport=httpx.MockTransport(handler))


def test_chat_asks_for_a_stream_with_usage(key_env: Path) -> None:
    calls: list[httpx.Request] = []
    client = _client(key_env, calls, _sse(_chunk("안"), _chunk("녕", finish="stop"), "[DONE]"))
    client.chat([{"role": "user", "content": "인사"}], model="liner-claude-router")
    sent = json.loads(calls[0].content)
    assert sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}


def test_streamed_chunks_are_assembled_into_a_normal_completion(key_env: Path) -> None:
    usage = {"object": "chat.completion.chunk", "model": "claude-sonnet-5.5", "choices": [],
             "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13, "cost": 0.0001}}
    body = _sse(_chunk('{"items":'), _chunk('["토요일"]}'), _chunk(finish="stop"), usage, "[DONE]")
    result = _client(key_env, [], body).chat([{"role": "user", "content": "x"}], model="liner-claude-router")
    assert result["model"] == "claude-sonnet-5.5"
    assert result["choices"][0]["message"] == {"role": "assistant", "content": '{"items":["토요일"]}'}
    assert result["choices"][0]["finish_reason"] == "stop"
    assert result["usage"]["cost"] == 0.0001


def test_plain_json_answer_still_works(key_env: Path) -> None:
    body = json.dumps({"model": "m", "choices": [{"message": {"role": "assistant", "content": "ok"}}]})
    result = _client(key_env, [], body, "application/json").chat([{"role": "user", "content": "x"}], model="m")
    assert result["choices"][0]["message"]["content"] == "ok"


def test_error_inside_the_stream_raises_without_provider_text(key_env: Path) -> None:
    body = _sse(_chunk("반쯤"), {"error": {"message": "Invalid key sk-should-not-leak"}}, "[DONE]")
    with pytest.raises(LinerAPIError) as exc:
        _client(key_env, [], body).chat([{"role": "user", "content": "x"}], model="m")
    assert "sk-should-not-leak" not in str(exc.value)
    assert exc.value.kind == "stream_error"


def test_empty_stream_is_a_bad_response(key_env: Path) -> None:
    with pytest.raises(LinerAPIError) as exc:
        _client(key_env, [], _sse("[DONE]")).chat([{"role": "user", "content": "x"}], model="m")
    assert exc.value.kind == "bad_response"
