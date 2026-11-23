from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.agent_runner import AgentRunner
from app.definitions import load_definitions
from app.liner import LinerClient
from app.orchestrator import (
    FIRST_ROUND_MAX_CARDS,
    STAGE_TABLE,
    UNKNOWN_OPTION,
    ConfirmationRequiredError,
    Orchestrator,
    PipelineStateError,
)
from app.store import empty_source
from app.workspace import Workspace
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, card, final_requirements_for, flower_outputs, memo_chunks

CHUNKS = memo_chunks()


def build(repo_root: Path, env_file: Path, overrides: dict[str, list[Any]] | None = None,
          **fake_kwargs: Any) -> tuple[Orchestrator, Workspace, FakeLiner]:
    agents, teams = load_definitions(repo_root)
    fake = FakeLiner({**flower_outputs(CHUNKS), **(overrides or {})},
                     search_body=fake_kwargs.pop("search_body", SEARCH_BODY), **fake_kwargs)
    ws = Workspace(empty_source(), agents)
    runner = AgentRunner(LinerClient(env_file=env_file, transport=fake.transport()), agents, ws)
    return Orchestrator(ws, teams["default"], runner), ws, fake


def to_cp1(orch: Orchestrator) -> None:
    assert orch.ingest(CHUNKS).blocked is False
    orch.advance()


def to_cp2(orch: Orchestrator, ws: Workspace, unknown: bool = False) -> None:
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    for q in ws.items("questions"):
        orch.answer(q["id"], "unknown" if unknown else "choice", None if unknown else q["options"][1])
    orch.submit_answers()
    orch.advance()


def events(ws: Workspace, kind: str) -> list[dict[str, Any]]:
    return [e for e in ws.source["events"] if e["type"] == kind]


def test_stage_table_is_fixed_order() -> None:
    assert [s.id for s in STAGE_TABLE] == ["S1", "S2", "CP1", "S3", "S4", "CP2", "S5", "CP3", "S6", "CP4"]


def test_runs_s2_then_stops_at_cp1(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp1(orch)
    assert ws.pipeline["stage"] == "CP1"
    assert ws.pipeline["status"] == "awaiting_confirmation"
    assert fake.chat_names == ["problem_scope", "research_evidence"]
    assert fake.search_queries == ["정기구독 결제 실패 처리 관행"]
    orch.advance()  # nothing happens without a confirmation record
    assert fake.chat_names == ["problem_scope", "research_evidence"]
    started = [e["data"]["stage"] for e in events(ws, "stage_started")]
    assert started == ["S1", "S2", "CP1"]


def test_entering_s3_without_cp1_record_is_blocked(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp1(orch)
    with pytest.raises(ConfirmationRequiredError):
        orch.run_stage("S3")
    assert any(g["data"]["id"] == "G2" for g in events(ws, "guardrail"))


def test_cp1_rejection_reruns_s2_with_reason(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp1(orch)
    orch.confirm("CP1", False, "발주사", "범위에 쿠폰도 넣어 주세요")
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP1", "running")  # sorted in the background
    orch.advance()
    assert fake.chat_names.count("problem_scope") == 2
    second = fake.chat_payloads("problem_scope")[1]
    assert "범위에 쿠폰도 넣어 주세요" in second["messages"][-1]["content"]
    assert ws.pipeline["stage"] == "CP1"
    assert [c["approved"] for c in ws.items("confirmations")] == [False]


@pytest.mark.parametrize("reason", ["", "  ", "두 줄\n사유"])
def test_rejection_needs_one_line_reason(repo_root: Path, key_env: Path, reason: str) -> None:
    orch, _, _ = build(repo_root, key_env)
    to_cp1(orch)
    with pytest.raises(PipelineStateError):
        orch.confirm("CP1", False, "발주사", reason)


def test_confirm_only_at_waiting_cp(repo_root: Path, key_env: Path) -> None:
    orch, _, _ = build(repo_root, key_env)
    to_cp1(orch)
    with pytest.raises(PipelineStateError):
        orch.confirm("CP2", True, "발주사")


def test_s2_g1_marks_claims_and_evidence(repo_root: Path, key_env: Path) -> None:
    bad = flower_outputs(CHUNKS)["problem_scope"][0]
    bad = {**bad, "claims": [*bad["claims"], {"text": "꽃 구독은 보통 월 2회다", "refs": [], "quote": "월 2회"}]}
    bad_ev = {"evidence": [{"result_id": "R1-1", "quote": "3일 안에 한 번 더 결제를 시도한다", "fact": "ok"},
                           {"result_id": "R1-1", "quote": "7일 안에 재시도한다", "fact": "지어낸 말"}],
              "not_found": []}
    orch, ws, _ = build(repo_root, key_env, {"problem_scope": [bad], "research_evidence": [bad_ev]})
    to_cp1(orch)
    claims = ws.items("problem_statement")[0]["claims"]
    assert [c["status"] for c in claims] == ["확인", "미확인"]
    evidence = ws.items("evidence")
    assert [e["status"] for e in evidence] == ["확인", "미확인"]
    assert {"query", "url", "quote", "raw_snippet"} <= set(evidence[0])
    assert evidence[0]["query"] == "정기구독 결제 실패 처리 관행"


def test_search_failure_continues_without_evidence(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, search_status=503)
    to_cp1(orch)
    assert ws.pipeline["stage"] == "CP1"
    assert ws.items("evidence") == ()
    assert events(ws, "liner_search")[0]["data"]["error"]


def test_s3_produces_question_cards_within_constraints(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "awaiting_answers"
    assert fake.chat_names[2:] == ["requirement_candidates", "qa_findings", "question_cards"]
    cards = ws.items("questions")
    assert 0 < len(cards) <= FIRST_ROUND_MAX_CARDS == 30
    for c in cards:
        assert 2 <= len(c["options"]) <= 4
        assert c["unknown_option"] == UNKNOWN_OPTION == "잘 모르겠어요"
        assert c["allow_free_text"] is True and c["why"] and c["status"] == "pending"
    assert cards[0]["source_refs"]
    assert cards[1]["evidence_refs"] == ["EV-01"]
    assert len(ws.items("findings")) == 2
    assert all(r["status"] == "미결" for r in ws.items("requirements"))


def test_first_round_is_capped_and_bad_cards_become_open_items(repo_root: Path, key_env: Path) -> None:
    many = [card(f"질문 {i}", ["가", "나"], []) for i in range(FIRST_ROUND_MAX_CARDS + 2)]
    many.append(card("선택지 하나", ["가"], []))
    orch, ws, _ = build(repo_root, key_env, {"question_cards": [{"cards": many}]})
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    assert len(ws.items("questions")) == FIRST_ROUND_MAX_CARDS
    # 3 past the cap (the one-option card comes after it); FND-02 is in no card, so it is kept too
    assert [o["reason"] for o in ws.items("open_items")] == [
        *["이번 회차 카드 수 상한 초과"] * 3, "질문 카드에 들어가지 못한 지적"]
    assert ws.items("open_items")[0]["finding_refs"] == ["FND-01"]  # an overflow card keeps the findings it carried


def test_a_finding_no_card_mentions_is_kept_as_an_open_item(repo_root: Path, key_env: Path) -> None:
    only_first = [card("고객이 요일을 고르나요?", ["고객이 고름", "토요일 일괄"], [])]
    orch, ws, _ = build(repo_root, key_env, {"question_cards": [{"cards": only_first}]})
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    fnd2 = ws.items("findings")[1]
    (kept,) = ws.items("open_items")
    assert kept["title"] == fnd2["note"] == "결제 실패 시 처리가 없다"
    assert kept["reason"] == "질문 카드에 들어가지 못한 지적"
    assert kept["source_refs"] == fnd2["source_refs"] and kept["finding_refs"] == [fnd2["id"]]
    assert kept["requirement_refs"] == ["REQ-02"]


def test_no_open_item_when_every_finding_has_a_card(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    assert not ws.items("open_items")


def test_answers_choice_and_unknown(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    first, second = ws.items("questions")
    with pytest.raises(PipelineStateError):
        orch.answer(first["id"], "choice", "없는 선택지")
    orch.answer(first["id"], "unknown", None)
    assert ws.pipeline["status"] == "awaiting_answers"
    orch.answer(second["id"], "free_text", "카드사 재시도 기본값으로")
    q1, q2 = ws.items("questions")
    assert q1["answer"] == {"kind": "unknown", "value": first["default_option"], "status": "가정"}
    assert q2["answer"]["status"] == "확정"
    assert [d["status"] for d in ws.items("decisions")] == ["가정", "확정"]
    # every card answered, yet nothing moves until the client checks the answers
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S3", "awaiting_answers")
    orch.submit_answers()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S4", "running")


def test_an_answer_can_be_changed_until_submitted(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    first, second = ws.items("questions")
    orch.answer(first["id"], "unknown", None)
    with pytest.raises(PipelineStateError):
        orch.submit_answers()  # Q-02 still open
    orch.answer(first["id"], "choice", first["options"][1])  # back to Q-01: change the answer
    orch.answer(second["id"], "choice", second["options"][0])
    orch.answer(second["id"], "choice", second["options"][1])  # change the last one too
    decisions = ws.items("decisions")
    assert [d["id"] for d in decisions] == ["DEC-01", "DEC-02"]  # replaced, not added
    assert [d["chosen"] for d in decisions] == [first["options"][1], second["options"][1]]
    assert [d["status"] for d in decisions] == ["확정", "확정"]
    assert [e["data"]["changed"] for e in events(ws, "question_answered")] == [False, True, False, True]
    orch.submit_answers()
    with pytest.raises(PipelineStateError):
        orch.answer(first["id"], "unknown", None)  # after submitting, CP2 is the place to object


def test_s4_blocked_while_questions_pending(repo_root: Path, key_env: Path) -> None:
    orch, _, _ = build(repo_root, key_env)
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    with pytest.raises(ConfirmationRequiredError):
        orch.run_stage("S4")


def test_s4_requirements_follow_data_model_and_status_rules(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws, unknown=True)
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP2", "awaiting_confirmation")
    reqs = ws.items("requirements")
    assert [r["id"] for r in reqs] == ["REQ-01", "REQ-02"]
    fields = {"id", "title", "statement", "category", "priority", "acceptance", "exceptions", "status",
              "source_refs", "evidence_refs", "decision_refs", "depends_on", "screens", "tests"}
    assert fields <= set(reqs[0])
    assert set(reqs[0]["acceptance"]) == {"given", "when", "then"}
    assert reqs[1]["depends_on"] == ["REQ-01"]
    assert [r["status"] for r in reqs] == ["가정", "가정"]  # both rest on "잘 모르겠어요" decisions


def test_s4_marks_unverified_evidence_and_missing_refs(repo_root: Path, key_env: Path) -> None:
    scripted = final_requirements_for(CHUNKS, "토요일 일괄", "3일 안에 다시 결제")["requirements"]
    final = {"requirements": [
        {**scripted[0], "decision_refs": [], "source_refs": [], "evidence_refs": []},
        {**scripted[1], "decision_refs": [], "evidence_refs": ["EV-77"]},
    ]}
    orch, ws, _ = build(repo_root, key_env, {"requirements_final": [final]})
    to_cp2(orch, ws)
    assert [r["status"] for r in ws.items("requirements")] == ["가정", "미확인"]
    assert ws.items("requirements")[1]["evidence_refs"] == ["EV-77"]


def test_cp2_approval_snapshots_v1(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    orch.confirm("CP2", True, "발주사")
    (version,) = ws.items("versions")
    cf = ws.items("confirmations")[-1]
    assert version["version"] == "v1" and version["confirmation_id"] == cf["id"]
    assert version["snapshot"]["requirements"] == list(ws.items("requirements"))
    assert {cf["cp"], cf["who"], cf["version"], cf["approved"]} == {"CP2", "발주사", "v1", True}
    assert cf["at"]
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S5", "running")  # S5 is next (was "done")


def test_cp2_rejection_returns_to_s3(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp2(orch, ws)
    orch.confirm("CP2", False, "발주사", "해지 요구사항이 빠졌어요")
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP2", "running")  # sorted in the background
    orch.advance()
    assert fake.chat_names.count("requirement_candidates") == 2
    assert "해지 요구사항이 빠졌어요" in fake.chat_payloads("requirement_candidates")[1]["messages"][-1]["content"]
    assert ws.items("versions") == ()


def test_liner_calls_are_events_without_key(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp2(orch, ws)
    chats, searches = events(ws, "liner_chat"), events(ws, "liner_search")
    assert len(chats) == len(fake.chat_names) == 6
    assert len(searches) == 1 and searches[0]["data"]["query"] == "정기구독 결제 실패 처리 관행"
    assert all(c["data"]["model"] == "test-model" for c in chats)
    assert {c["actor"] for c in chats} == {"fde_lead", "researcher", "pm", "qa", "coordinator"}
    assert "test-key-123" not in json.dumps(ws.source, ensure_ascii=False)


def test_agent_system_prompt_comes_from_definition(repo_root: Path, key_env: Path) -> None:
    agents, _ = load_definitions(repo_root)
    orch, _, fake = build(repo_root, key_env)
    to_cp1(orch)
    payload = fake.chat_payloads("problem_scope")[0]
    assert agents["fde_lead"].instructions in payload["messages"][0]["content"]
    assert payload["response_format"]["type"] == "json_schema"


def test_invalid_agent_json_fails_pipeline(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, {"problem_scope": ["not json"]})
    orch.ingest(CHUNKS)
    orch.advance()
    assert ws.pipeline["status"] == "failed"
    assert "fde_lead" in ws.pipeline["error"] or "FDE" in ws.pipeline["error"]


@pytest.mark.parametrize("secret", ["900101-1234567", "1234 5678 9012 3456", "010-9876-5432",
                                    "api_key_ABCDEFGHijklmnop1234"])
def test_ingest_blocks_sensitive_input_until_masked(repo_root: Path, key_env: Path, secret: str) -> None:
    orch, ws, _ = build(repo_root, key_env)
    result = orch.ingest([CHUNKS[0], f"참고로 {secret} 입니다."])
    assert result.blocked is True and "가린 값" in result.message
    assert ws.items("sources") == ()
    assert secret not in json.dumps(ws.source, ensure_ascii=False)
    masked = orch.ingest([CHUNKS[0], f"참고로 {secret} 입니다."], mask=True)
    assert masked.blocked is False
    assert secret not in json.dumps(ws.source, ensure_ascii=False)
    assert ws.items("sources")
