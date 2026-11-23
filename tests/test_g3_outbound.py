from __future__ import annotations
"""Review fix 2: every free-text input passes G3, and the Liner client checks the whole body before sending."""

import contextlib
from pathlib import Path

import pytest

from app.liner import LinerAPIError, LinerClient
from app.orchestrator import PipelineStateError
from tests.fake_liner import FakeLiner
from tests.pipeline_helpers import CHUNKS, CP3_WAIVERS, build, events, to_cp3
from tests.test_change_desk import PAUSE, completed

PHONE = "010-2345-6789"


def sent_bodies(fake: FakeLiner) -> list[str]:
    return [r.content.decode("utf-8", errors="ignore") for r in fake.requests]


def test_rejection_reason_with_a_phone_number_never_reaches_liner(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()
    assert ws.pipeline["stage"] == "CP1"
    with contextlib.suppress(PipelineStateError):
        orch.confirm("CP1", False, "발주사", f"담당자 {PHONE} 로 다시 물어봐 주세요")
    orch.advance()
    assert all(PHONE not in body for body in sent_bodies(fake))
    assert PHONE not in str(ws.source)
    assert any(e["data"]["id"] == "G3" and e["data"]["outcome"] == "blocked" for e in events(ws, "guardrail"))


def test_waiver_reason_with_a_phone_number_is_blocked(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    bad = {k: f"{v} — 문의 {PHONE}" for k, v in CP3_WAIVERS.items()}
    with pytest.raises(PipelineStateError, match="전화번호"):
        orch.confirm("CP3", True, "발주사", waivers=bad)
    assert PHONE not in str(ws.source)


def test_cp5_rejection_reason_with_a_phone_number_is_blocked(repo_root: Path, key_env: Path) -> None:
    _, ws, _, desk = completed(repo_root, key_env)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    with pytest.raises(PipelineStateError, match="전화번호"):
        desk.decide(change["id"], False, "발주사", f"{PHONE} 로 연락 주세요")
    assert PHONE not in str(ws.source)


def test_client_refuses_to_send_a_body_with_sensitive_text(key_env: Path) -> None:
    fake = FakeLiner({})
    client = LinerClient(env_file=key_env, transport=fake.transport())
    with pytest.raises(LinerAPIError, match="보내지 않았"):
        client.chat([{"role": "user", "content": f"연락처 {PHONE}"}])
    with pytest.raises(LinerAPIError, match="보내지 않았"):
        client.search(f"{PHONE} 누구 번호")
    assert fake.requests == []


def test_client_still_sends_urls_with_long_slugs(key_env: Path) -> None:
    fake = FakeLiner({"x": [{"ok": True}]})
    client = LinerClient(env_file=key_env, transport=fake.transport())
    slug = "https://example.com/blog/how-to-run-a-flower-subscription-service-2026"
    client.chat([{"role": "user", "content": f"출처 {slug}"}],
                response_format={"type": "json_schema", "json_schema": {"name": "x", "schema": {}}})
    assert len(fake.requests) == 1
