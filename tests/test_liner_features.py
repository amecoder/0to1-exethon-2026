from __future__ import annotations
"""Liner features in the pipeline: router model record, AI Search, G1 support (Decisions), FR-21 rerank,
FR-22 decision, S5 flow chart (Visualization), credits / G7 cost cap."""

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.agent_runner import AgentRunner
from app.change_desk import ChangeDesk
from app.definitions import DefinitionError, load_definitions, parse_agent
from app.export import build_bundle
from app.limits import calls_used
from app.liner import CHAT_URL, LinerClient
from app.orchestrator import Orchestrator
from app.store import empty_source
from app.views import client_todo
from app.workspace import Workspace
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs
from tests.pipeline_helpers import CHUNKS, CP3_WAIVERS, events, to_cp2, to_cp3, to_cp4

PAUSE = "일시정지는 배송 하루 전까지 되게 해 주세요"


def add_env(env_file: Path, **values: str) -> Path:
    env_file.write_text(env_file.read_text(encoding="utf-8") + "".join(f"{k}={v}\n" for k, v in values.items()),
                        encoding="utf-8")
    return env_file


def build(repo_root: Path, env_file: Path, **fake_kwargs: Any) -> tuple[Orchestrator, Workspace, FakeLiner]:
    agents, teams = load_definitions(repo_root)
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY, **fake_kwargs)
    ws = Workspace(empty_source(), agents)
    runner = AgentRunner(LinerClient(env_file=env_file, transport=fake.transport()), agents, ws)
    return Orchestrator(ws, teams["default"], runner), ws, fake


def completed_desk(repo_root: Path, env_file: Path, **fake_kwargs: Any):
    orch, ws, fake = build(repo_root, env_file, **fake_kwargs)
    to_cp4(orch, ws)
    orch.confirm("CP4", True, "발주사")
    orch.advance()
    _, teams = load_definitions(repo_root)
    return ws, fake, ChangeDesk(ws, teams["default"], orch._ctx.runner)


def choice(name: str, confidence: float):
    def answer(payload: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for key, q in payload["questions"].items():
            if q["type"] == "choice":
                other = "violation" if name == "new_change" else "new_change"
                out[key] = {"type": "choice", "choice": name, "confidence": confidence,
                            "probabilities": {name: 0.7, other: 0.3}}
            else:
                out[key] = {"type": "noul", "noul": 0.2}
        return out
    return answer


# --- 1. router models ---------------------------------------------------------------------------
def test_router_gets_agent_strategy_and_answered_model_is_recorded(repo_root: Path, key_env: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINER_MODEL", "liner-claude-router")
    orch, ws, fake = build(repo_root, key_env, answered_model="claude-sonnet-5.5")
    orch.ingest(CHUNKS)
    orch.advance()
    first = fake.payloads(CHAT_URL)[0]
    assert first["model"] == "liner-claude-router" and first["routing_strategy"] == "balanced"  # fde_lead
    chat = events(ws, "liner_chat")[0]["data"]
    assert (chat["answered_model"], chat["routing_strategy"], chat["cost"]) == ("claude-sonnet-5.5", "balanced", 0.0021)


def test_non_router_model_gets_no_strategy(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()
    assert all("routing_strategy" not in p for p in fake.payloads(CHAT_URL))
    assert events(ws, "liner_chat")[0]["data"]["routing_strategy"] is None


def test_agent_strategies_are_valid_and_bad_values_rejected(repo_root: Path) -> None:
    agents, _ = load_definitions(repo_root)
    assert {a.id: a.routing_strategy for a in agents.values()} == {
        "consumer": "cost", "coordinator": "cost", "designer": "quality", "developer": "quality",
        "fde_lead": "balanced", "pm": "balanced", "qa": "balanced", "researcher": "balanced"}
    data = {"id": "x", "name": "x", "persona": "p", "role": "r", "instructions": "i", "tools": [], "writes": [],
            "reads": [], "guardrails": [], "model": None, "version": 1, "routing_strategy": "fast"}
    with pytest.raises(DefinitionError, match="routing_strategy"):
        parse_agent(data, "x.json")


# --- 3. AI Search -------------------------------------------------------------------------------
def test_research_uses_ai_search_chunks_as_evidence(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()
    assert fake.ai_search_queries == ["정기구독 결제 실패 처리 관행"] and fake.web_search_queries == []
    search = events(ws, "liner_search")
    assert [s["data"]["api"] for s in search] == ["ai_search"] and search[0]["data"]["answer"]
    ev = ws.items("evidence")[0]
    assert ev["via"] == "ai_search" and ev["chunk_id"] == "chunk-1" and ev["status"] == "확인"


def test_ai_search_failure_falls_back_to_web_search(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env, ai_search_status=503)
    orch.ingest(CHUNKS)
    orch.advance()
    assert fake.web_search_queries == ["정기구독 결제 실패 처리 관행"]
    apis = [(s["data"]["api"], bool(s["data"]["error"])) for s in events(ws, "liner_search")]
    assert apis == [("ai_search", True), ("search", False)]
    assert ws.items("evidence")[0]["via"] == "search"
    assert calls_used(ws.log.events) == 4  # problem_scope, ai_search, search, research_evidence


# --- 2. Decisions: G1 support -------------------------------------------------------------------
def test_g1_support_low_probability_adds_info_note_never_blocks(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="typesafe/jev-1.13")
    orch, ws, fake = build(repo_root, key_env, decision=choice("violation", 0.9))
    orch.ingest(CHUNKS)
    orch.advance()
    assert ws.pipeline["stage"] == "CP1"
    claims = ws.items("problem_statement")[0]["claims"]
    checked = [c for c in claims if c["status"] == "확인"]
    assert checked and all(c["support"] == 0.2 and "참고" in c["support_note"] for c in checked)
    assert ws.items("evidence")[0]["support"] == 0.2 and ws.items("evidence")[0]["status"] == "확인"
    check = [e["data"] for e in events(ws, "check_result") if e["data"]["check"] == "g1_support"][-1]
    assert check["outcome"] == "flagged"
    (decision,) = [e for e in events(ws, "liner_decision") if e["data"]["purpose"] != "purpose"]  # G9 at S1
    assert decision["data"]["purpose"] == "g1_support"
    ps, scope = ws.items("problem_statement")[0], ws.items("scope")[0]
    sentences = [c for group in (ps["claims"], ps["interpretations"], scope["in"], scope["out"]) for c in group
                 if c["status"] == "확인"]
    questions = fake.payloads("https://platform.liner.com/api/v1/decisions")[1]["questions"]  # [0] is G9
    assert len(questions) == len(sentences) + 1  # one call: every checked sentence + the evidence


def test_g1_support_without_model_is_skipped_and_not_counted(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()
    check = [e["data"] for e in events(ws, "check_result") if e["data"]["check"] == "g1_support"][-1]
    assert check["outcome"] == "skipped" and "LINER_DECISION_MODEL" in check["details"][0]
    assert events(ws, "liner_decision") == []


def test_decision_calls_count_toward_g7(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="m", EXETHON_MAX_LINER_CALLS="4")
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()
    # G9 purpose (S1), problem_scope, ai_search, research_evidence = 4 → the G1 decision is the 5th and is refused
    assert ws.pipeline["status"] == "stopped"
    assert [e["data"]["purpose"] for e in events(ws, "liner_decision")] == ["purpose"]


# --- 4. Rerank in FR-21 --------------------------------------------------------------------------
def test_rerank_gives_pm_top_candidates(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    ws, fake, desk = completed_desk(repo_root, key_env)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["status"] == "awaiting_cp5" and 1 <= len(item["candidates"]) <= 5
    assert item["candidates"][0]["score"] >= item["candidates"][-1]["score"]
    content = fake.chat_payloads("change_mapping")[0]["messages"][-1]["content"]
    assert "후보(재정렬 점수)" in content
    assert events(ws, "liner_rerank")[0]["data"]["query"] == PAUSE


def test_rerank_failure_leaves_pm_to_choose_alone(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    ws, fake, desk = completed_desk(repo_root, key_env, rerank_status=500)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["status"] == "awaiting_cp5" and item["candidates"] == []
    assert events(ws, "liner_rerank")[0]["data"]["error"]
    extra = fake.chat_payloads("change_mapping")[0]["messages"][-1]["content"].split("[추가 입력]")[1]
    assert "후보(재정렬 점수)" not in extra


# --- 2. Decisions: FR-22 -------------------------------------------------------------------------
COMPLAINT = "일요일에도 받고 싶은데 왜 안 되죠?"
SAME_AS_CONFIRMED = "배송 요일을 수·토 중 고름으로 하기로 했는데 화면에 없어요"


def test_complaint_uses_decision_and_keeps_probabilities(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="typesafe/jev-1.13")
    ws, fake, desk = completed_desk(repo_root, key_env, decision=choice("violation", 0.9))
    complaint = desk.open_complaint(COMPLAINT)
    desk.check_complaint(complaint["id"])
    item = ws.get("complaints", complaint["id"])
    assert item["model_classification"] == "새 변경 요청"  # QA's vote
    assert item["classification"] == "합의 위반"  # the decision's vote wins over QA
    assert item["decision"]["probabilities"] == {"violation": 0.7, "new_change": 0.3}
    assert item["decision"]["confidence"] == 0.9 and item["needs_human"] is False
    state = fake.payloads("https://platform.liner.com/api/v1/decisions")[-1]["state"]
    assert state["complaint"] == COMPLAINT and state["confirmation"]["cp"] == "CP3"
    assert state["confirmed_requirements"][0]["id"] == "REQ-01"


def test_low_confidence_needs_a_person(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="m")
    ws, _, desk = completed_desk(repo_root, key_env, decision=choice("new_change", 0.4))
    complaint = desk.open_complaint(COMPLAINT)
    desk.check_complaint(complaint["id"])
    item = ws.get("complaints", complaint["id"])
    assert item["classification"] == "새 변경 요청" and item["needs_human"] is True


def test_guard_overrides_the_decision(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="m")
    ws, _, desk = completed_desk(repo_root, key_env, decision=choice("new_change", 0.95))
    complaint = desk.open_complaint(SAME_AS_CONFIRMED)
    desk.check_complaint(complaint["id"])
    item = ws.get("complaints", complaint["id"])
    assert item["decision"]["label"] == "새 변경 요청" and item["guard"]["applied"] is True
    assert item["classification"] == "합의 위반" and item["needs_human"] is False


def test_decision_unavailable_marks_needs_human(repo_root: Path, key_env: Path) -> None:
    ws, _, desk = completed_desk(repo_root, key_env)  # no LINER_DECISION_MODEL
    complaint = desk.open_complaint(COMPLAINT)
    desk.check_complaint(complaint["id"])
    item = ws.get("complaints", complaint["id"])
    assert item["classification"] == "새 변경 요청" and item["needs_human"] is True
    assert "LINER_DECISION_MODEL" in item["decision"]["error"]


def test_bad_threshold_setting_is_explained(repo_root: Path, key_env: Path) -> None:
    from app.decisions import min_confidence

    add_env(key_env, EXETHON_DECISION_MIN_CONFIDENCE="높게")
    with pytest.raises(ValueError, match="EXETHON_DECISION_MIN_CONFIDENCE"):
        min_confidence(key_env)


# --- 6. Visualization -----------------------------------------------------------------------------
def test_s5_flow_chart_is_stripped_and_exported(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    (flow,) = ws.items("flow_chart")
    assert "https://" not in flow["html"] and "<link" not in flow["html"]
    assert {v["code"] for v in flow["violations"]} >= {"external_link", "external_media"}
    assert flow["based_on"] == [s["id"] for s in ws.items("screens")]
    assert events(ws, "liner_visualization")[0]["actor"] == "designer"
    orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)
    orch.advance()
    orch.confirm("CP4", True, "발주사")
    names = zipfile.ZipFile(io.BytesIO(build_bundle(ws.source))).namelist()
    assert "user_flow.html" in names


def test_flow_chart_request_carries_roles_branches_and_the_wanted_shape(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    query = ws.items("flow_chart")[0]["query"]
    who = ws.items("problem_statement")[0]["who"]
    assert who and who in query  # who uses the service
    assert all(lane in query for lane in ("고객", "앱", "사장"))  # one band per role
    assert "결제 실패" in query and "다시 결제 누르기" in query  # the exception branch and where it leads
    assert "점선" in query and "역할" in query  # the shape asked for in words
    assert len(query) <= 1500


def test_flow_chart_failure_is_a_cp3_notice_only(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, viz_status=500)
    to_cp3(orch, ws)
    assert ws.pipeline["stage"] == "CP3" and ws.items("flow_chart") == ()
    review = client_todo(ws.source)["review"]
    assert any(n["code"] == "flow.failed" for n in review["notices"])
    assert not any(w["code"] == "flow.failed" for w in review["blocking"] + review["waivable"])


# --- 5. Credits -----------------------------------------------------------------------------------
def test_balance_recorded_at_start_and_after_each_stage(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    credits = [e["data"] for e in events(ws, "credits")]
    points = [c["point"] for c in credits]
    assert points[0] == "start" and {"after S2", "after S3", "after S4"} <= set(points)
    assert credits[-1]["spent_usd"] > 0 and all(e["actor"] == "system" for e in events(ws, "credits"))


def test_credits_failure_is_logged_and_work_goes_on(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, credits_status=500)
    orch.ingest(CHUNKS)
    orch.advance()
    assert ws.pipeline["stage"] == "CP1"
    assert all(e["data"]["error"] and e["data"]["balance_usd"] is None for e in events(ws, "credits"))


def test_cost_cap_stops_and_continue_grants_the_same_again(repo_root: Path, key_env: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.limits.STAGE_TYPICAL_COST_USD", {})  # the pre-stage prediction: test_budget_mode.py
    add_env(key_env, EXETHON_MAX_COST_USD="0.002")
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()  # S2 spends $0.003 (3 fake calls) → CP1 waits
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "stopped" and "비용" in ws.pipeline["error"]
    g7 = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G7"][-1]
    assert g7["limit"] == "cost"
    assert client_todo(ws.source)["limit"] == "cost"
    orch.continue_after_limit()
    orch.advance()
    assert ws.pipeline["status"] in ("awaiting_answers", "stopped")
    assert [e["data"]["limit"] for e in events(ws, "guardrail")
            if e["data"]["id"] == "G7" and e["data"]["outcome"] == "resumed"] == ["cost"]
