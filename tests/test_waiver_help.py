from __future__ import annotations
"""11-22 (user): a 빈칸 card at CP3/CP4 is hard to read and hard to answer, so each one comes with a plain
explanation and a reason already filled in (code rules, no Liner call) that the client may edit. A screen the
client dropped at the G8 scope question gives its requirements the scope reason."""

from pathlib import Path

from app.checks import approval_problems, review, warning
from app.waiver_help import help_for
from tests.pipeline_helpers import build, to_cp3
from tests.test_scope_limit import to_scope


def source_with(**parts: object) -> dict[str, object]:
    return {"requirements": [], "open_items": [], "decisions": [], "screens": [], **parts}


def test_every_waivable_at_cp3_is_explained_and_prefilled(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    waivable = review(ws.source, "CP3")["waivable"]
    assert waivable and all(w["explain"] and w["suggested"] for w in waivable)
    reasons = {w["id"]: w["suggested"] for w in waivable}
    assert approval_problems(ws.source, "CP3", reasons) == []  # the filled reasons are enough to approve


def test_the_scope_question_records_which_requirements_lost_their_screen(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = to_scope(repo_root, key_env)
    screens = {s["id"]: set(s["requirement_refs"]) for s in ws.items("screens")}
    orch.narrow_scope(["SCR-03"], "발주사")
    scope = next(d for d in ws.items("decisions") if d.get("kind") == "scope")
    lost = set().union(*(refs for sid, refs in screens.items() if sid != "SCR-03")) - screens["SCR-03"]
    assert lost and scope["dropped_requirements"] == sorted(lost)


def test_a_requirement_whose_screen_was_dropped_gets_the_scope_reason(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = to_scope(repo_root, key_env)
    orch.narrow_scope(["SCR-03"], "발주사")
    orch.advance()
    no_screen = [w for w in review(ws.source, "CP3")["waivable"] if w["code"] == "coverage.no_scr"]
    assert no_screen
    for w in no_screen:
        assert "화면 범위" in w["suggested"] and "1개" in w["suggested"]
        assert "화면을 고를 때" in w["explain"]


def test_a_requirement_without_a_screen_and_no_scope_question() -> None:
    req = {"id": "REQ-03", "title": "결제 실패 재시도", "status": "확정", "statement": "실패하면 다음 날 다시 결제한다"}
    w = warning("coverage.no_scr", "waivable", "REQ-03", "screens", "REQ-03 에 연결된 화면이 없고, 화면이 없는 이유도 없습니다")
    out = help_for(w, source_with(requirements=[req]))
    assert "「결제 실패 재시도」" in out["explain"] and "REQ-03" not in out["explain"]
    assert "화면 범위" not in out["suggested"] and out["suggested"]


def test_an_open_item_that_missed_the_card_limit_says_so() -> None:
    item = {"id": "OPEN-02", "title": "카드가 만료되면 어떻게 바꾸는지 없다.", "reason": "질문 카드에 들어가지 못한 지적",
            "requirement_refs": ["REQ-04"]}
    req = {"id": "REQ-04", "title": "카드 등록", "status": "확정"}
    w = warning("coverage.open", "waivable", "OPEN-02", "prd", "OPEN-02 미결: 카드가 만료되면 어떻게 바꾸는지 없다.")
    out = help_for(w, source_with(requirements=[req], open_items=[item]))
    # 11-22: with the cap at 30, a finding without a card was one the team judged it need not ask — not the cap
    assert "카드가 만료되면" in out["explain"] and "「카드 등록」" in out["explain"]
    assert "따로 묻지 않았어요" in out["explain"] and "장까지만" not in out["explain"]
    assert out["suggested"]


def test_an_open_item_over_the_card_cap_says_so() -> None:
    from app.stage_common import FIRST_ROUND_MAX_CARDS
    item = {"id": "OPEN-03", "title": "포장지 색을 고르나요?", "reason": "이번 회차 카드 수 상한 초과", "requirement_refs": []}
    w = warning("coverage.open", "waivable", "OPEN-03", "prd", "OPEN-03 미결: 포장지 색을 고르나요?")
    out = help_for(w, source_with(open_items=[item]))
    assert f"{FIRST_ROUND_MAX_CARDS}장까지만" in out["explain"]


def test_an_unknown_warning_still_gets_a_reason() -> None:
    w = warning("something.new", "waivable", "X-1", "prd", "새 경고")
    out = help_for(w, source_with())
    assert out["explain"] == "" and out["suggested"]


def test_particles_follow_the_last_sound() -> None:
    reqs = [{"id": "REQ-01", "title": "카드 정보 보호", "status": "미결"}, {"id": "REQ-02", "title": "배송 알림", "status": "확정"}]
    item = {"id": "OPEN-01", "title": "만료 처리가 없다.", "reason": "질문 카드에 들어가지 못한 지적", "requirement_refs": ["REQ-01"]}
    out = help_for(warning("coverage.open", "waivable", "OPEN-01", "prd", "x"), source_with(requirements=reqs, open_items=[item]))
    assert "「카드 정보 보호」예요" in out["explain"]
    out = help_for(warning("coverage.open", "waivable", "REQ-01", "prd", "x"), source_with(requirements=reqs))
    assert out["explain"].startswith("「카드 정보 보호」는 아직")
    out = help_for(warning("coverage.no_tc", "waivable", "REQ-02", "tests", "x"), source_with(requirements=reqs))
    assert out["explain"].startswith("「배송 알림」이 제대로")
