from __future__ import annotations
"""What the client writes instead of approving is sorted first (Liner Decisions): a question is answered in
place without reworking the stage; a fix (or anything unsure) is reworked as before."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tests.pipeline_helpers import CHUNKS, build, to_cp3

ANSWER = {"answer": "네, 있어요. 「꽃배달 앱」이 가장 가까워요.", "refs": ["EV-01"]}
QUESTION = "이런 기능을 하는 앱이 이미 있나요?"


def decision(intent: str, confidence: float = 0.9, search: float = 0.9) -> Callable[[Mapping[str, Any]], dict]:
    def answer(_: Mapping[str, Any]) -> dict[str, Any]:
        return {"intent": {"type": "choice", "choice": intent, "confidence": confidence, "probabilities": {}},
                "search": {"type": "noul", "noul": search}}
    return answer


def at_cp1(repo_root: Path, key_env: Path, **fake: Any) -> tuple[Any, Any, Any]:
    key_env.write_text(key_env.read_text(encoding="utf-8") + "LINER_DECISION_MODEL=fake-decision\n", encoding="utf-8")
    orch, ws, liner = build(repo_root, key_env, {"client_reply": [ANSWER]}, **fake)
    orch.ingest(CHUNKS)
    orch.advance()
    return orch, ws, liner


def intent_check(ws: Any) -> dict[str, Any]:
    return [e["data"] for e in ws.source["events"] if e["type"] == "check_result"
            and e["data"]["check"] == "client_intent"][-1]


def test_question_is_answered_without_rework(repo_root: Path, key_env: Path) -> None:
    orch, ws, liner = at_cp1(repo_root, key_env, decision=decision("question"))
    orch.confirm("CP1", False, "발주사", QUESTION)
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP1", "awaiting_confirmation")
    assert liner.chat_names.count("problem_scope") == 1  # S2 did not rerun
    assert liner.chat_names.count("research_evidence") == 2  # one search for the question
    [reply] = ws.items("replies")
    assert reply["question"] == QUESTION and reply["answer"] == ANSWER["answer"] and reply["searched"] is True
    assert ws.items("confirmations") == ()  # a question is not a rejection
    assert intent_check(ws)["outcome"] == "question"
    assert any(e["type"] == "credits" and e["data"]["point"] == "after CP1 말씀 처리" for e in ws.source["events"])
    orch.confirm("CP1", True, "발주사")  # the client can approve right after the answer


def test_question_answerable_from_own_material_skips_search(repo_root: Path, key_env: Path) -> None:
    orch, ws, liner = at_cp1(repo_root, key_env, decision=decision("question", search=0.1))
    orch.confirm("CP1", False, "발주사", "범위에서 빠진 게 뭐예요?")
    orch.advance()
    assert liner.chat_names.count("research_evidence") == 1 and ws.items("replies")[0]["searched"] is False


def test_change_reworks_the_stage_without_answer(repo_root: Path, key_env: Path) -> None:
    orch, ws, liner = at_cp1(repo_root, key_env, decision=decision("change"))
    orch.confirm("CP1", False, "발주사", "범위에 쿠폰도 넣어 주세요")
    orch.advance()
    assert liner.chat_names.count("problem_scope") == 2 and ws.items("replies") == ()
    assert [c["approved"] for c in ws.items("confirmations")] == [False]
    assert "범위에 쿠폰도 넣어 주세요" in liner.chat_payloads("problem_scope")[1]["messages"][-1]["content"]


def test_both_answers_then_reworks(repo_root: Path, key_env: Path) -> None:
    orch, ws, liner = at_cp1(repo_root, key_env, decision=decision("both"))
    orch.confirm("CP1", False, "발주사", "기존 앱 있나요? 없으면 읽음 확인을 꼭 넣어 주세요")
    orch.advance()
    assert len(ws.items("replies")) == 1 and liner.chat_names.count("problem_scope") == 2
    assert ws.pipeline["stage"] == "CP1"


def test_low_confidence_question_is_also_reworked(repo_root: Path, key_env: Path) -> None:
    orch, ws, liner = at_cp1(repo_root, key_env, decision=decision("question", confidence=0.3))
    orch.confirm("CP1", False, "발주사", "쿠폰은요?")
    orch.advance()
    assert len(ws.items("replies")) == 1 and liner.chat_names.count("problem_scope") == 2
    check = intent_check(ws)
    assert check["outcome"] == "both" and "확신도가 낮아요" in check["details"][0]


def test_failed_answer_returns_to_the_confirmation_unchanged(repo_root: Path, key_env: Path) -> None:
    orch, ws, liner = at_cp1(repo_root, key_env, decision=decision("question", search=0.1))
    liner._outputs["client_reply"] = []  # the fake answers 500 → LinerAPIError
    orch.confirm("CP1", False, "발주사", QUESTION)
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP1", "awaiting_confirmation")
    assert "답하지 못했어요" in ws.pipeline["error"] and ws.items("replies") == ()
    assert liner.chat_names.count("problem_scope") == 1
    orch.confirm("CP1", True, "발주사")
    assert ws.pipeline["error"] is None


def test_question_at_cp3_does_not_rewrite_the_documents(repo_root: Path, key_env: Path) -> None:
    key_env.write_text(key_env.read_text(encoding="utf-8") + "LINER_DECISION_MODEL=fake-decision\n", encoding="utf-8")
    orch, ws, liner = build(repo_root, key_env, {"client_reply": [ANSWER]}, decision=decision("question", search=0.1))
    to_cp3(orch, ws)
    before = liner.chat_names.count("screen_spec")
    orch.confirm("CP3", False, "발주사", "결제가 실패하면 고객은 무엇을 보게 되나요?")
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    assert liner.chat_names.count("screen_spec") == before and ws.items("replies")[0]["cp"] == "CP3"
