from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import LinerKeyMissingError, read_env
from app.liner import CHAT_URL, SEARCH_URL, LinerAPIError, LinerClient, LinerConfigError


def recording_transport(calls: list[httpx.Request], status: int = 200, body: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=body if body is not None else {"ok": True})

    return httpx.MockTransport(handler)


def test_missing_key_raises_korean_error_with_setup_hint(no_key_env: Path) -> None:
    calls: list[httpx.Request] = []
    client = LinerClient(env_file=no_key_env, transport=recording_transport(calls))
    with pytest.raises(LinerKeyMissingError) as exc:
        client.search("꽃 구독 결제 실패 처리")
    message = str(exc.value)
    assert "LINER_API_KEY" in message
    assert ".env" in message
    assert calls == []


def test_missing_key_also_blocks_chat(no_key_env: Path) -> None:
    client = LinerClient(env_file=no_key_env, transport=recording_transport([]))
    with pytest.raises(LinerKeyMissingError):
        client.chat([{"role": "user", "content": "안녕"}])


def test_key_read_from_env_file_at_use_time(no_key_env: Path) -> None:
    assert read_env("LINER_API_KEY", no_key_env) is None
    no_key_env.write_text("LINER_API_KEY=later-key\n", encoding="utf-8")
    assert read_env("LINER_API_KEY", no_key_env) == "later-key"


def test_process_env_wins_over_env_file(key_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINER_API_KEY", "from-process")
    assert read_env("LINER_API_KEY", key_env) == "from-process"


def test_chat_sends_bearer_auth_and_model_from_env(key_env: Path) -> None:
    calls: list[httpx.Request] = []
    body = {"choices": [{"message": {"content": "네"}}]}
    client = LinerClient(env_file=key_env, transport=recording_transport(calls, body=body))
    result = client.chat([{"role": "user", "content": "안녕"}])
    assert result == body
    (request,) = calls
    assert str(request.url) == CHAT_URL
    assert request.headers["Authorization"] == "Bearer test-key-123"
    payload = json.loads(request.content)
    assert payload["model"] == "test-model"
    assert payload["messages"] == [{"role": "user", "content": "안녕"}]
    assert "response_format" not in payload


def test_chat_passes_response_format(key_env: Path) -> None:
    calls: list[httpx.Request] = []
    client = LinerClient(env_file=key_env, transport=recording_transport(calls))
    fmt = {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}}
    client.chat([{"role": "user", "content": "x"}], response_format=fmt)
    assert json.loads(calls[0].content)["response_format"] == fmt


def test_chat_without_model_raises(no_key_env: Path) -> None:
    no_key_env.write_text("LINER_API_KEY=k\n", encoding="utf-8")
    client = LinerClient(env_file=no_key_env, transport=recording_transport([]))
    with pytest.raises(LinerConfigError) as exc:
        client.chat([{"role": "user", "content": "x"}])
    assert "LINER_MODEL" in str(exc.value)


def test_search_sends_x_api_key_and_query(key_env: Path) -> None:
    calls: list[httpx.Request] = []
    client = LinerClient(env_file=key_env, transport=recording_transport(calls, body={"results": []}))
    assert client.search("정기구독 결제 실패 재시도 관행") == {"results": []}
    (request,) = calls
    assert str(request.url) == SEARCH_URL
    assert request.headers["x-api-key"] == "test-key-123"
    assert "Authorization" not in request.headers
    assert json.loads(request.content) == {"query": "정기구독 결제 실패 재시도 관행", "lang": "ko",
                                           "country_code": "kr", "include_knowledge": False}


def test_http_error_wrapped_without_leaking_key(key_env: Path) -> None:
    client = LinerClient(env_file=key_env, transport=recording_transport([], status=401, body={"e": 1}))
    with pytest.raises(LinerAPIError) as exc:
        client.search("x")
    assert "401" in str(exc.value)
    assert "test-key-123" not in str(exc.value)


# --- review fixes (2026-11-14): every failure surfaces as LinerAPIError, keys are trimmed


def test_non_json_success_body_wrapped(key_env: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>oops</html>"))
    client = LinerClient(env_file=key_env, transport=transport)
    with pytest.raises(LinerAPIError) as exc:
        client.search("결제 실패")
    assert "test-key-123" not in str(exc.value)


def test_transport_error_wrapped_without_key(key_env: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = LinerClient(env_file=key_env, transport=httpx.MockTransport(handler))
    with pytest.raises(LinerAPIError) as exc:
        client.chat([{"role": "user", "content": "안녕"}])
    assert "test-key-123" not in str(exc.value)


def test_key_whitespace_is_trimmed(no_key_env: Path) -> None:
    no_key_env.write_text("LINER_API_KEY=  spaced-key \n", encoding="utf-8")
    calls: list[httpx.Request] = []
    LinerClient(env_file=no_key_env, transport=recording_transport(calls)).search("q")
    assert calls[0].headers["x-api-key"] == "spaced-key"


def test_whitespace_only_key_counts_as_missing(no_key_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINER_API_KEY", "   ")
    assert read_env("LINER_API_KEY", no_key_env) is None
