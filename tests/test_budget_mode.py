from __future__ import annotations
"""Budget mode (G7 cost): from 60% of the budget every router call uses routing_strategy "cost",
and a work stage whose typical cost would cross the budget is stopped before it starts."""

from pathlib import Path

import pytest

from app.liner import CHAT_URL
from app.views import client_todo
from tests.pipeline_helpers import CHUNKS, build, events

ROUTER = "liner-claude-router"


def add_env(env_file: Path, **values: str) -> None:
    env_file.write_text(env_file.read_text(encoding="utf-8") + "".join(f"{k}={v}\n" for k, v in values.items()),
                        encoding="utf-8")


def budget_events(ws) -> list[dict]:
    return [e["data"] for e in events(ws, "guardrail")
            if e["data"]["id"] == "G7" and e["data"]["outcome"] == "flagged" and e["data"].get("limit") == "budget_mode"]


def to_s3(orch) -> None:
    orch.ingest(CHUNKS)
    orch.advance()  # S2: 3 fake calls → $0.003 spent at the "after S2" reading
    orch.confirm("CP1", True, "발주사")
    orch.advance()


@pytest.fixture
def no_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake calls cost $0.001; without this the real stage table ($0.34+) would stop every tiny budget."""
    monkeypatch.setattr("app.limits.STAGE_TYPICAL_COST_USD", {})


def test_router_calls_switch_to_cost_at_60_percent_with_one_event(repo_root: Path, key_env: Path,
                                                                    monkeypatch: pytest.MonkeyPatch,
                                                                    no_prediction: None) -> None:
    monkeypatch.setenv("LINER_MODEL", ROUTER)
    add_env(key_env, EXETHON_MAX_COST_USD="0.0045")  # 60% = $0.0027 < $0.003 after S2
    orch, ws, fake = build(repo_root, key_env)
    to_s3(orch)
    chats = events(ws, "liner_chat")
    s2 = [c["data"] for c in chats if c["data"]["schema"] in ("problem_scope", "research_evidence")]
    assert s2 and all(not c["budget_mode"] and c["routing_strategy"] == "balanced" for c in s2)
    s3 = [c["data"] for c in chats if c["data"]["schema"] in ("requirement_candidates", "qa_findings", "question_cards")]
    assert s3 and all(c["budget_mode"] and c["routing_strategy"] == "cost" for c in s3)
    sent = {p["response_format"]["json_schema"]["name"]: p.get("routing_strategy") for p in fake.payloads(CHAT_URL)}
    assert sent["requirement_candidates"] == "cost" and sent["qa_findings"] == "cost"  # pm, qa default balanced
    flagged = budget_events(ws)
    assert len(flagged) == 1
    assert "예산의 60%" in flagged[0]["detail"] and "싼 모델" in flagged[0]["detail"]


def test_without_a_budget_nothing_changes(repo_root: Path, key_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINER_MODEL", ROUTER)
    orch, ws, fake = build(repo_root, key_env)
    to_s3(orch)
    assert budget_events(ws) == []
    assert all(not c["data"]["budget_mode"] for c in events(ws, "liner_chat"))
    sent = {p["response_format"]["json_schema"]["name"]: p.get("routing_strategy") for p in fake.payloads(CHAT_URL)}
    assert sent["requirement_candidates"] == "balanced" and sent["question_cards"] == "cost"


def test_non_router_model_never_gets_a_strategy_in_budget_mode(repo_root: Path, key_env: Path,
                                                                no_prediction: None) -> None:
    add_env(key_env, EXETHON_MAX_COST_USD="0.0045")  # LINER_MODEL=test-model (not a router)
    orch, ws, fake = build(repo_root, key_env)
    to_s3(orch)
    assert len(budget_events(ws)) == 1
    assert all("routing_strategy" not in p for p in fake.payloads(CHAT_URL))
    assert all(c["data"]["routing_strategy"] is None for c in events(ws, "liner_chat"))


def test_stage_is_stopped_before_it_starts_when_its_typical_cost_would_cross_the_budget(
        repo_root: Path, key_env: Path) -> None:
    add_env(key_env, EXETHON_MAX_COST_USD="0.5")  # S2 typical $0.34 fits; S3 $0.60 does not
    orch, ws, fake = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()
    assert ws.pipeline["stage"] == "CP1"
    orch.confirm("CP1", True, "발주사")
    calls = len(fake.requests)
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S3", "stopped")
    assert len(fake.requests) == calls  # nothing was sent
    assert not any(e["data"]["stage"] == "S3" for e in events(ws, "stage_started"))
    g7 = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G7"][-1]
    assert (g7["outcome"], g7["limit"], g7["predicted"]) == ("blocked", "cost", 0.6)
    assert "$0.60" in ws.pipeline["error"] and "구체화" in ws.pipeline["error"]
    todo = client_todo(ws.source)
    assert todo["kind"] == "limit" and todo["limit"] == "cost"
    # 「계속」 runs the stage anyway (the client chose to); the after-the-fact cap still applies.
    orch.continue_after_limit()
    orch.advance()
    assert any(e["data"]["stage"] == "S3" for e in events(ws, "stage_started"))
    assert len(fake.requests) > calls


def test_no_budget_means_no_prediction(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()
    assert ws.pipeline["stage"] == "CP1"
    assert not [e for e in events(ws, "guardrail") if e["data"]["id"] == "G7"]


def test_stage_cost_table_is_the_measured_one() -> None:
    from app.limits import STAGE_TYPICAL_COST_USD

    assert STAGE_TYPICAL_COST_USD == {"S2": 0.34, "S3": 0.60, "S4": 0.40, "S5": 2.48, "S6": 0.88}
