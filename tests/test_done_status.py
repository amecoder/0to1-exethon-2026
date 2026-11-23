from __future__ import annotations
"""When is the planning really done: PRD 완료 조건, 결정 현황, 문제 진술 갱신 at CP2, 남은 카드 모두 확정."""

from pathlib import Path
from typing import Any

import pytest

from app.decision_status import decision_status
from app.documents import build_documents
from app.errors import PipelineStateError
from app.req_review import review_summary
from app.views import client_todo
from tests.pipeline_helpers import build, events, to_cp2, to_cp3, to_cp4
from tests.test_delivery_api import CHUNKS, client_for


def section(doc: dict[str, Any], sid: str) -> dict[str, Any]:
    return next(s for s in doc["sections"] if s["id"] == sid)


def tables(doc: dict[str, Any], sid: str) -> list[dict[str, Any]]:
    return [b for b in section(doc, sid)["blocks"] if b["type"] == "table"]


def problem_checks(ws: Any) -> list[str]:
    return [e["data"]["outcome"] for e in events(ws, "check_result") if e["data"]["check"] == "problem_done"]


# --- ① PRD 완료 조건 ---------------------------------------------------------------------------------
def test_prd_done_criteria_section_lists_tests_assumptions_open_and_goals(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    source = {**ws.source,
              "requirements": [*ws.source["requirements"],
                               {"id": "REQ-09", "title": "포장 방식", "status": "가정", "statement": "기본 포장"},
                               {"id": "REQ-10", "title": "해지 시점", "status": "미결", "statement": "?"}],
              "decisions": [*ws.source["decisions"],
                            {"id": "DEC-09", "topic": "배송 시간대", "chosen": "오전", "status": "가정"}],
              "open_items": [{"id": "OPEN-01", "title": "환불 규정", "reason": "답이 없음"}]}
    prd = build_documents(source)["prd"]
    assert [s["id"] for s in prd["sections"]][-2:] == ["done_criteria", "history"]
    must, assumed, open_, goals = tables(prd, "done_criteria")
    assert must["columns"] == ["TC ID", "이름", "기대 결과"]
    assert [r[0] for r in must["rows"]] == [t["id"] for t in source["tests"] if t["priority"] == "상"]
    assert must["rows"][0][2] == source["tests"][0]["expected"]
    assert [r[0] for r in assumed["rows"]] == ["REQ-09", "DEC-09"]
    assert [r[0] for r in open_["rows"]] == ["REQ-10", "OPEN-01"]
    assert goals["columns"] == ["목표", "성공 기준", "상태"]
    assert goals["rows"] == [[g["goal"], g["criterion"], g["status"]] for g in source["brd"][0]["goals"]]


# --- ② 결정 현황 -----------------------------------------------------------------------------------
def test_decision_status_counts_and_two_level_completion() -> None:
    source: dict[str, Any] = {
        "requirements": [{"id": "REQ-01", "title": "a", "status": "확정"}, {"id": "REQ-02", "title": "b", "status": "가정"},
                         {"id": "REQ-03", "title": "c", "status": "미확인"}],
        "decisions": [{"id": "DEC-01", "topic": "요일", "status": "확정"}, {"id": "DEC-02", "topic": "결제", "status": "가정"}],
        "open_items": [{"id": "OPEN-01", "title": "환불"}],
        "confirmations": [{"cp": "CP4", "approved": True}],
    }
    status = decision_status(source)
    assert status["counts"] == {"confirmed": 2, "assumed": 2, "open": 2}
    assert [i["id"] for i in status["items"]["assumed"]] == ["REQ-02", "DEC-02"]
    assert [i["id"] for i in status["items"]["open"]] == ["REQ-03", "OPEN-01"]
    assert status["items"]["assumed"][1]["title"] == "결제"
    assert (status["planning_done"], status["decision_done"], status["level"]) == (True, False, "기획 완료")
    settled = {**source, "requirements": source["requirements"][:1], "decisions": source["decisions"][:1],
               "open_items": []}
    assert decision_status(settled)["level"] == "결정 완료"
    assert decision_status({**settled, "confirmations": []})["level"] is None


def test_download_and_cp4_todo_carry_decision_status(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    cp4 = client_todo(ws.source)
    assert cp4["cp"] == "CP4" and cp4["decision_status"]["planning_done"] is False
    orch.confirm("CP4", True, "발주사")
    todo = client_todo(ws.source)
    assert todo["kind"] == "download"
    assert todo["decision_status"]["counts"] == {"confirmed": 4, "assumed": 0, "open": 0}
    assert todo["decision_status"]["level"] == "결정 완료"


# --- ③ 문제 진술 갱신 -------------------------------------------------------------------------------
def test_cp2_approval_rewrites_problem_done_once(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp2(orch, ws)
    before = ws.items("problem_statement")[0]["done"]
    orch.confirm("CP2", True, "발주사")
    orch.advance()
    ps = ws.items("problem_statement")[0]
    assert ps["done_before"] == before and ps["done"] != before and "잠정" not in ps["done"]
    assert fake.chat_names.count("problem_done") == 1
    assert fake.chat_names.index("problem_done") == fake.chat_names.index("screen_spec") - 1
    assert problem_checks(ws) == ["updated"]
    orch.confirm("CP3", False, "발주사", "결제 안내 화면 문구가 어려워요")
    orch.advance()
    assert fake.chat_names.count("screen_spec") == 2
    assert fake.chat_names.count("problem_done") == 1  # an S5 rework does not ask again


def test_problem_done_refresh_is_fail_open(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, {"problem_done": []})  # no scripted output → Liner 500
    to_cp3(orch, ws)
    ps = ws.items("problem_statement")[0]
    assert ps["done"] == "고객이 구독을 신청하고 매주 꽃을 받는다" and "done_before" not in ps
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    assert problem_checks(ws) == ["skipped"]


# --- ④ 남은 카드 모두 확정 ---------------------------------------------------------------------------
def test_confirm_remaining_cards_keeps_fix_notes(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    first, second = [r["id"] for r in ws.items("requirements")][:2]
    orch.review_requirement(first, "fix", "일시정지는 하루 전까지로 해 주세요", "발주사")
    assert orch.confirm_remaining_requirements("발주사") == 1
    items = {i["id"]: i for i in review_summary(ws.source)["items"]}
    assert items[first]["verdict"] == "fix" and items[first]["note"].startswith("일시정지")
    assert items[second]["verdict"] == "ok"
    with pytest.raises(PipelineStateError, match="남은"):
        orch.confirm_remaining_requirements("발주사")


def test_api_confirm_remaining_cards(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    assert client.post("/api/projects/nope/requirements/confirm-rest").status_code == 404
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})
    client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True})
    for _ in range(2):
        q = client.get(base).json()["todo"]["question"]
        client.post(f"{base}/answers", json={"question_id": q["id"], "kind": "choice", "value": q["options"][0]})
    client.post(f"{base}/answers/submit")
    reviews = client.get(base).json()["todo"]["req_reviews"]
    rid = reviews["items"][0]["id"]
    client.post(f"{base}/requirements/{rid}/review", json={"verdict": "fix", "note": "문구를 쉽게"})
    res = client.post(f"{base}/requirements/confirm-rest")
    assert res.status_code == 200 and res.json() == {"accepted": True, "count": reviews["total"] - 1}
    after = client.get(base).json()["todo"]["req_reviews"]
    assert (after["ok"], after["fix"], after["open"]) == (reviews["total"] - 1, 1, 0)
    assert client.post(f"{base}/requirements/confirm-rest").status_code == 409
