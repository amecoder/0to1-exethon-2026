from __future__ import annotations
"""FR-23 G7: Liner call cap per project and elapsed-time cap per stage → stop card with 「계속」."""

from pathlib import Path

import pytest

from app.limits import DEFAULT_MAX_LINER_CALLS, DEFAULT_MAX_SCREENS, DEFAULT_MAX_STAGE_SECONDS, Limits
from app.orchestrator import PipelineStateError
from tests.pipeline_helpers import build, events


def write_env(env_file: Path, **values: str) -> None:
    extra = "".join(f"{k}={v}\n" for k, v in values.items())
    env_file.write_text(env_file.read_text(encoding="utf-8") + extra, encoding="utf-8")


def test_defaults_are_provisional_constants(key_env: Path) -> None:
    limits = Limits.from_env(key_env)
    assert (limits.max_calls, limits.max_stage_seconds, limits.max_screens) == (
        DEFAULT_MAX_LINER_CALLS, DEFAULT_MAX_STAGE_SECONDS, DEFAULT_MAX_SCREENS)
    assert DEFAULT_MAX_SCREENS == 5


def test_env_overrides_and_rejects_bad_values(key_env: Path) -> None:
    write_env(key_env, EXETHON_MAX_LINER_CALLS="7", EXETHON_MAX_SCREENS="3")
    limits = Limits.from_env(key_env)
    assert (limits.max_calls, limits.max_screens) == (7, 3)
    write_env(key_env, EXETHON_MAX_STAGE_SECONDS="열 분")
    with pytest.raises(ValueError, match="EXETHON_MAX_STAGE_SECONDS"):
        Limits.from_env(key_env)


def test_call_cap_stops_before_the_next_call_and_continue_resumes(repo_root: Path, key_env: Path) -> None:
    write_env(key_env, EXETHON_MAX_LINER_CALLS="2")
    orch, ws, fake = build(repo_root, key_env)
    orch.ingest(["저희 꽃집 정기구독 앱을 만들고 싶어요. 배송은 서울만 해요."])
    orch.advance()
    # S2 makes problem_scope + search; the third call (research_evidence) is refused before it is sent.
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S2", "stopped")
    assert len(fake.requests) == 2
    assert "상한" in ws.pipeline["error"] and "2회" in ws.pipeline["error"]
    g7 = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G7"]
    assert g7[-1]["outcome"] == "blocked" and g7[-1]["limit"] == "calls" and g7[-1]["used"] == 2

    orch.continue_after_limit()
    orch.advance()
    assert ws.pipeline["status"] != "stopped" or len(fake.requests) > 2
    resumed = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G7" and e["data"]["outcome"] == "resumed"]
    assert resumed and resumed[0]["limit"] == "calls"


def test_continue_only_when_stopped(repo_root: Path, key_env: Path) -> None:
    orch, _, _ = build(repo_root, key_env)
    with pytest.raises(PipelineStateError):
        orch.continue_after_limit()


def test_stage_time_cap_stops_work_stage(repo_root: Path, key_env: Path) -> None:
    write_env(key_env, EXETHON_MAX_STAGE_SECONDS="0")
    orch, ws, fake = build(repo_root, key_env)
    orch.ingest(["저희 꽃집 정기구독 앱을 만들고 싶어요."])
    orch.advance()
    assert ws.pipeline["status"] == "stopped" and fake.requests == []
    g7 = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G7"][-1]
    assert g7["limit"] == "time" and g7["stage"] == "S2"
    assert "문제 인식" in ws.pipeline["error"]


def test_question_at_a_confirmation_restarts_the_stage_clock() -> None:
    """Reading a confirmation for an hour is the client's time: the answer work gets a fresh clock."""
    from datetime import datetime, timedelta, timezone

    from app.limits import check, stage_started_at

    entered = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
    asked = entered + timedelta(hours=1)
    evs = ({"type": "stage_started", "ts": entered.isoformat(), "data": {"stage": "CP1"}},
           {"type": "client_message", "ts": asked.isoformat(), "data": {"cp": "CP1", "text": "가족은 몇 명?"}})
    assert stage_started_at(evs, "CP1") == asked
    check(evs, "CP1", Limits(), timed=True, now=asked + timedelta(minutes=1))  # no LimitReachedError
    assert stage_started_at(evs[:1], "CP1") == entered


def test_attachment_reads_count_toward_the_call_cap(key_env: Path) -> None:
    """X2 (11-21): reading an attachment is a paid model call, so G7 counts it (README 「G7 에 포함」)."""
    from app.limits import LimitReachedError, calls_used, check
    reads = tuple({"type": "liner_attachment", "actor": "system", "data": {}} for _ in range(DEFAULT_MAX_LINER_CALLS))
    assert calls_used(reads) == DEFAULT_MAX_LINER_CALLS
    with pytest.raises(LimitReachedError, match="calls"):
        check(reads, "S1", Limits.from_env(key_env), timed=False)
