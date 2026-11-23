from __future__ import annotations
"""11-22 user decision 「기본값 목록 한 화면」: a finding the cards do not ask about gets the team's default answer
right at the question stage (one PM call), shown on the answer review; 「이대로 진행」 keeps it or the client's
change, and it no longer reaches CP3 as a blank."""

from pathlib import Path
from typing import Any

import pytest

from app.checks import coverage_warnings
from app.errors import PipelineStateError
from app.views import question_todo
from tests.flower_script import card
from tests.test_orchestrator import build, events, to_cp1

ONLY_FIRST = [card("고객이 요일을 고르나요?", ["고객이 고름", "토요일 일괄"], [])]  # FND-02 (결제 실패) gets no card
DEFAULT = "결제가 실패하면 다음 날 한 번 더 결제하고, 그래도 안 되면 이번 회차는 건너뛰어요"
WHY = "정기결제 서비스에서 흔한 방식이라 팀이 이렇게 정했어요"


def team_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    from tests.flower_script import extra_input
    return {"defaults": [{"id": i["id"], "default": DEFAULT, "why": WHY} for i in extra_input(payload)["open_items"]]}


def to_review(repo_root: Path, key_env: Path, defaults: Any = team_defaults) -> tuple[Any, Any, Any]:
    orch, ws, fake = build(repo_root, key_env, {"question_cards": [{"cards": ONLY_FIRST}], "team_defaults": [defaults]})
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    for q in ws.items("questions"):
        orch.answer(q["id"], "choice", q["options"][0])
    return orch, ws, fake


def test_an_uncarded_finding_gets_the_teams_default_and_why(repo_root: Path, key_env: Path) -> None:
    _, ws, fake = to_review(repo_root, key_env)
    assert fake.chat_names.count("team_defaults") == 1
    (item,) = ws.items("open_items")
    assert item["team_default"] == DEFAULT and item["team_why"] == WHY
    todo = question_todo(ws.source)
    assert todo["kind"] == "answers_review" and [d["id"] for d in todo["defaults"]] == [item["id"]]


def test_no_call_when_every_finding_has_a_card(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    assert "team_defaults" not in fake.chat_names
    assert question_todo(ws.source).get("defaults", []) == []


def test_keeping_the_default_makes_an_assumed_team_decision_and_no_blank(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = to_review(repo_root, key_env)
    (item,) = ws.items("open_items")
    orch.submit_answers()
    assert not ws.items("open_items")
    (dec,) = [d for d in ws.items("decisions") if d.get("kind") == "team_default"]
    assert dec["chosen"] == DEFAULT and dec["status"] == "가정" and dec["answered_by"] == "team"
    assert dec["topic"] == item["title"] and dec["finding_refs"] == item["finding_refs"]
    assert not [w for w in coverage_warnings(ws.source) if w["target"] == item["id"]]
    (done,) = events(ws, "team_defaults_confirmed")
    assert done["data"] == {"count": 1, "changed": 0}


def test_a_changed_line_is_the_clients_answer(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = to_review(repo_root, key_env)
    (item,) = ws.items("open_items")
    orch.submit_answers({item["id"]: "결제가 실패하면 사장님에게 알림만 보내요"})
    (dec,) = [d for d in ws.items("decisions") if d.get("kind") == "team_default"]
    assert dec["chosen"] == "결제가 실패하면 사장님에게 알림만 보내요"
    assert dec["status"] == "확정" and dec["answered_by"] == "client" and dec["answer_kind"] == "free_text"


def test_a_change_with_personal_data_is_blocked_before_anything_is_stored(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = to_review(repo_root, key_env)
    (item,) = ws.items("open_items")
    with pytest.raises(PipelineStateError):
        orch.submit_answers({item["id"]: "실패하면 010-1234-5678 로 연락"})
    assert ws.items("open_items") and not [d for d in ws.items("decisions") if d.get("kind") == "team_default"]
    assert ws.pipeline["status"] == "awaiting_answers"


def test_a_failed_defaults_call_leaves_the_open_item_as_before(repo_root: Path, key_env: Path) -> None:
    _, ws, _ = to_review(repo_root, key_env, defaults="이건 JSON 이 아님")
    (item,) = ws.items("open_items")
    assert "team_default" not in item
    assert question_todo(ws.source)["defaults"] == []
