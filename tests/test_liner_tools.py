from __future__ import annotations
"""Liner client: router routing_strategy, Decisions, Rerank, AI Search / Visualization SSE, credits, audio."""

import json
from pathlib import Path

import httpx
import pytest

from app.liner import (
    AI_SEARCH_URL, BALANCE_URL, CHAT_URL, DECISIONS_URL, RERANK_URL, SEARCH_URL, TRANSCRIPTION_URL, USAGE_URL,
    VISUALIZATION_URL, LinerAPIError, LinerClient, LinerConfigError, is_router,
)
from tests.fake_liner import FakeLiner, sse

RESULTS = {"results": [{"title": "꽃 구독", "url": "https://example.com/a", "snippet": "배송은 토요일에 한 번 나간다"}]}


def client_for(env: Path, fake: FakeLiner, **values: str) -> LinerClient:
    env.write_text(env.read_text(encoding="utf-8") + "".join(f"{k}={v}\n" for k, v in values.items()),
                   encoding="utf-8")
    return LinerClient(env_file=env, transport=fake.transport())


@pytest.mark.parametrize("model, router", [
    ("liner-claude-router", True), ("liner-gpt-router-1.0", True), ("liner-gemini-router-1.1", True),
    ("liner-mark-1.3", False), ("liner-mark", False), ("anthropic/claude-opus-5.5", False), (None, False)])
def test_is_router(model: str | None, router: bool) -> None:
    assert is_router(model) is router


def test_routing_strategy_sent_only_to_router_models(key_env: Path) -> None:
    fake = FakeLiner({"x": [{"ok": True}]})
    client = client_for(key_env, fake)
    fmt = {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}
    client.chat([{"role": "user", "content": "a"}], fmt, model="liner-claude-router", routing_strategy="quality")
    client.chat([{"role": "user", "content": "a"}], fmt, model="liner-mark-1.3", routing_strategy="quality")
    first, second = fake.payloads(CHAT_URL)
    assert first["routing_strategy"] == "quality"
    assert "routing_strategy" not in second  # liner-mark answers 400 unsupported_parameter


def test_decisions_need_model_setting_in_korean(key_env: Path) -> None:
    fake = FakeLiner({})
    client = client_for(key_env, fake)
    with pytest.raises(LinerConfigError, match="LINER_DECISION_MODEL") as exc:
        client.decide({"a": 1}, {"q": {"type": "noul", "instructions": "x"}})
    assert "typesafe/jev-1.13" in str(exc.value) and fake.requests == []


def test_decisions_send_model_state_questions_with_bearer(key_env: Path) -> None:
    fake = FakeLiner({})
    client = client_for(key_env, fake, LINER_DECISION_MODEL="typesafe/jev-1.13")
    body = client.decide({"complaint": "x"}, {"q": {"type": "noul", "instructions": "x"}})
    assert body["answers"]["q"]["noul"] == 0.9
    (request,) = fake.requests
    assert str(request.url) == DECISIONS_URL and request.headers["Authorization"] == "Bearer test-key-123"
    assert json.loads(request.content)["model"] == "typesafe/jev-1.13"


def test_rerank_needs_model_and_sends_top_n(key_env: Path) -> None:
    fake = FakeLiner({})
    with pytest.raises(LinerConfigError, match="LINER_RERANK_MODEL"):
        client_for(key_env, fake).rerank("배송 요일", ["a"])
    client = client_for(key_env, fake, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    body = client.rerank("배송 요일", ["결제는 자동", "배송 요일은 토요일"], top_n=1)
    assert body["results"] == [{"index": 1, "relevance_score": 1.0}]
    assert fake.payloads(RERANK_URL)[0] == {"model": "cohere/rerank-5-fast", "query": "배송 요일",
                                            "documents": ["결제는 자동", "배송 요일은 토요일"], "top_n": 1}


def test_ai_search_parses_references_and_chunks(key_env: Path) -> None:
    fake = FakeLiner({}, search_body=RESULTS)
    body = client_for(key_env, fake).ai_search("꽃 구독 배송 요일")
    assert body["answer"].startswith("가짜 AI 검색 답")
    (chunk,) = body["chunks"]
    assert chunk["content"] == "배송은 토요일에 한 번 나간다" and chunk["url"] == "https://example.com/a"
    payload = fake.payloads(AI_SEARCH_URL)[0]
    assert payload["messages"][-1]["content"] == "꽃 구독 배송 요일" and payload["lang"] == "ko"
    assert fake.requests[0].headers["x-api-key"] == "test-key-123"


def test_sse_error_event_and_empty_stream_raise(key_env: Path) -> None:
    def transport(text: str) -> httpx.MockTransport:
        return httpx.MockTransport(lambda request: httpx.Response(200, text=text))

    for text in (sse({"type": "error", "errorText": "boom"}), sse({"type": "finish"})):
        with pytest.raises(LinerAPIError):
            LinerClient(env_file=key_env, transport=transport(text)).ai_search("q")
        with pytest.raises(LinerAPIError):
            LinerClient(env_file=key_env, transport=transport(text)).visualize("q")


def test_visualization_returns_atlas_html(key_env: Path) -> None:
    fake = FakeLiner({})
    body = client_for(key_env, fake).visualize("가입 → 결제")
    assert "<html" in body["html"] and body["description"] == "가짜 흐름도" and body["theme"] == "process"
    assert fake.payloads(VISUALIZATION_URL) == [{"query": "가입 → 결제"}]


def test_credits_balance_and_usage_are_free_reads(key_env: Path) -> None:
    fake = FakeLiner({})
    client = client_for(key_env, fake)
    assert client.credits_balance()["balance"] == 200_000_000
    assert client.credits_usage() == {"data": []}
    assert [str(r.url) for r in fake.free_requests] == [BALANCE_URL, USAGE_URL] and fake.requests == []
    assert all(r.method == "GET" for r in fake.free_requests)


def test_transcribe_posts_multipart_with_model_and_language(key_env: Path) -> None:
    fake = FakeLiner({}, transcript="토요일 배송이요")
    with pytest.raises(LinerConfigError, match="LINER_STT_MODEL"):
        client_for(key_env, fake).transcribe("a.mp3", b"ID3...")
    client = client_for(key_env, fake, LINER_STT_MODEL="openai/gpt-transcribe")
    assert client.transcribe("회의.mp3", b"ID3 audio")["text"] == "토요일 배송이요"
    (request,) = fake.requests
    assert str(request.url) == TRANSCRIPTION_URL and request.headers["content-type"].startswith("multipart/form-data")
    content = request.content
    assert b'name="model"' in content and b"openai/gpt-transcribe" in content and b'name="language"' in content
    assert b"ID3 audio" in content


def test_web_search_url_unchanged(key_env: Path) -> None:
    fake = FakeLiner({}, search_body=RESULTS)
    client_for(key_env, fake).search("q")
    assert [str(r.url) for r in fake.requests] == [SEARCH_URL]
