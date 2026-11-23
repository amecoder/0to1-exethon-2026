from __future__ import annotations
"""Answer consistency: a requirement citing DEC-xx must say what the client chose, not a rejected option."""

from pathlib import Path
from typing import Any

import pytest

from app.checks import answer_table, approval_problems, consistency_violations, normalize_key, review
from app.orchestrator import PipelineStateError
from app.quality import client_jargon
from app.views import client_todo
from tests.flower_script import final_requirements, final_requirements_for
from tests.pipeline_helpers import CHUNKS, DAY_CHOICE, build, events, to_cp2

OPTIONS = ["고객이 고름", "토요일 일괄", "수·토 중 고름"]


def decision(chosen: str, kind: str = "choice", options: list[str] = OPTIONS, status: str = "확정") -> dict[str, Any]:
    return {"id": "DEC-01", "question_id": "Q-01", "topic": "배송 요일", "chosen": chosen, "answer_kind": kind,
            "rejected": [o for o in options if o != chosen], "status": status, "answered_by": "client"}


def req(title: str, statement: str, status: str = "확정", refs: tuple[str, ...] = ("DEC-01",)) -> dict[str, Any]:
    return {"id": "REQ-01", "title": title, "statement": statement, "status": status,
            "acceptance": {"given": "고객이", "when": "신청하면", "then": "저장된다"},
            "decision_refs": list(refs), "screens": [], "tests": []}


def source(decisions: list[dict[str, Any]], reqs: list[dict[str, Any]]) -> dict[str, Any]:
    question = {"id": "Q-01", "question": "고객이 요일을 고르나요?", "options": OPTIONS, "status": "answered"}
    return {"questions": [question], "decisions": decisions, "requirements": reqs, "open_items": [],
            "findings": [], "screens": [], "tests": [], "confirmations": [], "versions": []}


def test_normalize_key_ignores_spaces_and_punctuation() -> None:
    assert normalize_key("수·토 중 고름") == normalize_key("수 토, 중고름!") == "수토중고름"


def test_observed_bug_saturday_batch_against_wed_sat_choice_is_flagged() -> None:
    src = source([decision(DAY_CHOICE)], [req("토요일 일괄 배송", "배송은 매주 토요일 일괄로 나간다")])
    (violation,) = consistency_violations(src)
    assert violation["severity"] == "block" and violation["target"] == "REQ-01"
    assert violation["decision_id"] == "DEC-01"
    assert violation["missing_chosen"] is True and violation["rejected_found"] == ["토요일 일괄"]
    assert approval_problems(src, "CP2", {}) and approval_problems(src, "CP3", {})


def test_requirement_quoting_the_chosen_answer_passes() -> None:
    src = source([decision(DAY_CHOICE)], [req("배송 요일", "배송 요일은 수·토 중 고름 방식으로 정한다")])
    assert consistency_violations(src) == []
    assert approval_problems(src, "CP2", {}) == []


def test_missing_chosen_text_alone_is_a_violation() -> None:
    (violation,) = consistency_violations(source([decision(DAY_CHOICE)], [req("배송 요일", "요일을 정한다")]))
    assert violation["missing_chosen"] is True and violation["rejected_found"] == []


def test_rejected_option_inside_chosen_text_is_not_flagged() -> None:
    options = ["토요일", "토요일 일괄"]
    src = source([decision("토요일 일괄", options=options)], [req("배송", "배송은 토요일 일괄로 나간다")])
    assert consistency_violations(src) == []


def test_free_text_answer_checks_only_rejected_options() -> None:
    free = decision("격주 금요일", kind="free_text")
    assert consistency_violations(source([free], [req("배송", "배송은 격주로 나간다")])) == []
    (violation,) = consistency_violations(source([free], [req("배송", "배송은 토요일 일괄로 나간다")]))
    assert violation["missing_chosen"] is False


def test_assumed_decision_must_match_the_default_too() -> None:
    assumed = decision("고객이 고름", kind="unknown", status="가정")
    assert consistency_violations(source([assumed], [req("배송", "토요일 일괄 배송", status="가정")]))


def test_answer_table_lists_question_answer_decision_and_requirement_text() -> None:
    src = source([decision(DAY_CHOICE)], [req("토요일 일괄 배송", "배송은 토요일 일괄로 나간다")])
    (row,) = answer_table(src)
    assert row["question_id"] == "Q-01" and row["question"] == "고객이 요일을 고르나요?"
    assert row["answer"] == DAY_CHOICE and row["decision_id"] == "DEC-01" and row["status"] == "확정"
    assert row["requirements"] == [{"id": "REQ-01", "title": "토요일 일괄 배송",
                                    "statement": "배송은 토요일 일괄로 나간다", "status": "확정"}]
    assert row["consistent"] is False


def test_decision_reflected_nowhere_is_a_notice_not_a_block() -> None:
    src = source([decision(DAY_CHOICE)], [req("배송", "배송한다", refs=())])
    result = review(src, "CP2")
    assert result["blocking"] == []
    assert any(n["code"] == "answer.unreflected" for n in result["notices"])
    assert answer_table(src)[0]["requirements"] == []


# --- pipeline reproduction ------------------------------------------------------------------------
def wrong_pm() -> dict[str, list[Any]]:
    return {"requirements_final": [final_requirements_for(CHUNKS, "토요일 일괄", "3일 안에 다시 결제")]}


def test_bug_reproduction_blocks_cp2_approval(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, wrong_pm())
    to_cp2(orch, ws, day=DAY_CHOICE)
    assert ws.items("decisions")[0]["chosen"] == DAY_CHOICE
    assert ws.items("requirements")[0]["status"] == "확정"
    flagged = [e for e in events(ws, "check_result") if e["data"]["check"] == "answer_consistency"]
    assert flagged and flagged[0]["data"]["outcome"] == "flagged" and flagged[0]["stage"] == "S4"
    todo = client_todo(ws.source)
    assert todo["cp"] == "CP2" and todo["review"]["blocking"][0]["target"] == "REQ-01"
    assert todo["review"]["can_approve"] is False
    with pytest.raises(PipelineStateError, match="DEC-01"):
        orch.confirm("CP2", True, "발주사")
    assert ws.items("versions") == ()
    orch.confirm("CP2", False, "발주사", "요일은 수·토 중에 고르기로 했어요")
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP2", "running")  # sorted in the background


def test_consistent_pm_passes_cp2(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    todo = client_todo(ws.source)
    assert todo["review"]["blocking"] == [] and todo["review"]["can_approve"] is True
    assert client_jargon(todo["review"]["summary"]) == []
    rows = todo["review"]["answers"]
    assert [r["decision_id"] for r in rows] == ["DEC-01", "DEC-02"]
    assert rows[0]["answer"] == DAY_CHOICE and rows[0]["requirements"][0]["id"] == "REQ-01"
    assert DAY_CHOICE in rows[0]["requirements"][0]["statement"]


def test_decisions_record_answer_kind(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    assert [d["answer_kind"] for d in ws.items("decisions")] == ["choice", "choice"]


def fix_events(ws: Any) -> list[dict[str, Any]]:
    return [e["data"] for e in events(ws, "check_result") if e["data"]["check"] == "answer_fix"]


def test_pm_repairs_answer_mismatch_once_before_cp2(repo_root: Path, key_env: Path) -> None:
    fixed = final_requirements(CHUNKS)
    orch, ws, fake = build(repo_root, key_env, {**wrong_pm(), "requirements_fix": [fixed]})
    to_cp2(orch, ws, day=DAY_CHOICE)
    assert fake.chat_names.count("requirements_fix") == 1
    assert "고른 답과 다른 요구사항" in fake.chat_payloads("requirements_fix")[0]["messages"][-1]["content"]
    [fix] = fix_events(ws)
    assert fix["outcome"] == "passed" and "→ 0건" in fix["details"][0]
    assert client_todo(ws.source)["review"]["can_approve"] is True


def test_worse_repair_is_discarded(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, {**wrong_pm(), "requirements_fix": wrong_pm()["requirements_final"]})
    to_cp2(orch, ws, day=DAY_CHOICE)
    [fix] = fix_events(ws)
    assert fix["outcome"] == "flagged" and "고치기 전으로 둠" in fix["details"][0]
    assert client_todo(ws.source)["review"]["can_approve"] is False


def test_failed_repair_still_blocks_at_cp2(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, wrong_pm())  # no scripted requirements_fix → the fake answers 500
    to_cp2(orch, ws, day=DAY_CHOICE)
    assert fix_events(ws)[0]["outcome"] == "skipped" and ws.pipeline["stage"] == "CP2"
