from __future__ import annotations
"""Honest counts (11-24): a blank in the text is open even when no item has the status 미결, an outside service
a requirement leans on is a link, and the 가정 list is shown once per item instead of on top of every file."""

from typing import Any

from app.export import bundle_files, count_lines, readme_text, status_banner
from app.handoff_docs import agents_md, proposal_md
from app.open_points import assumed_counts, blanks, integrations, open_counts
from app.scope_view import scope_view

ACC = {"given": "g", "when": "w", "then": "t"}


def source() -> dict[str, Any]:
    reqs = [
        {"id": "REQ-01", "title": "카드 자동결제", "statement": "결제대행사가 발급한 빌링키로 결제한다.", "acceptance": ACC,
         "exceptions": ["결제대행사 선정은 미정"], "status": "가정", "category": "SFR", "depends_on": []},
        {"id": "REQ-02", "title": "배송 전날 알림", "statement": "앱 푸시로 알리고, 푸시 실패 시 문자 발송은 하지 않는다.",
         "acceptance": ACC, "exceptions": [], "status": "확정", "category": "SFR", "depends_on": []},
        {"id": "REQ-03", "title": "환불", "statement": "환불한다.", "acceptance": ACC, "exceptions": [], "status": "미결",
         "category": "SFR", "depends_on": []},
    ]
    screens = [{"id": "SCR-01", "title": "신청", "status": "가정", "requirement_refs": ["REQ-01"], "states": {}, "elements": [
        {"no": 1, "name": "가격", "kind": "text", "description": "금액은 가격 미정이라 빈칸(PM 확인 필요).", "action": "",
         "input_rule": "", "requirement_refs": ["REQ-01"]},
        {"no": 2, "name": "배송지 주소", "kind": "input", "description": "'주소 검색' 버튼과 상세 주소.", "action": "", "input_rule": "",
         "requirement_refs": ["REQ-01"]}]}]
    tests = [{"id": "TC-01", "title": "결제", "requirement_refs": ["REQ-01"], "expected": "실제 가격 미정", "status": "가정"}]
    brd = [{"id": "BRD-01", "summary": [], "background": [], "non_goals": [], "constraints": [], "risks": [],
            "goals": [{"goal": "매출이 는다", "criterion": "수치 없음", "status": "미결"},
                      {"goal": "정시 도착", "criterion": "95% 이상", "status": "확정"}]}]
    return {"requirements": reqs, "screens": screens, "tests": tests, "brd": brd, "decisions": [], "confirmations": [],
            "versions": [], "open_items": [{"id": "OPEN-01", "title": "쿠폰 금액", "reason": "답이 없음"}]}


def test_blanks_goals_and_statuses_are_all_counted_as_open() -> None:
    view = scope_view(source())
    assert [(b["id"], b["doc"]) for b in blanks(view)] == [("REQ-01", "prd"), ("SCR-01#1", "screens")]
    assert blanks(view)[0]["text"] == "결제대행사 선정은 미정"  # the sentence, so a reader sees what is missing
    # status 미결 REQ-03 + open item + one goal without a number + two blanks; the test repeating 「미정」 is not counted again
    assert open_counts(view) == {"status": 1, "open_items": 1, "goals": 1, "blanks": 2, "total": 5}
    assert assumed_counts(view) == {"requirements": 1, "screens": 1, "tests": 1}


def test_outside_services_are_found_unless_negated() -> None:
    found = integrations(scope_view(source()))
    assert [(s["name"], s["refs"]) for s in found] == [("결제대행사(PG)", ["REQ-01"]), ("앱 푸시 알림", ["REQ-02"]),
                                                      ("주소 검색", ["SCR-01"])]  # 「문자 발송은 하지 않는다」 is not a link


def test_readme_states_the_real_numbers_and_what_they_are_made_of() -> None:
    text = readme_text(source(), "2026-11-24T00:00:00+00:00")
    assert "가정 3건 · 미결 5곳 · 미확인 0건" in text and "미결 0건" not in text
    lines = count_lines(source())
    assert "요구사항 1 · 화면 1 · 테스트 케이스 1건" in lines[1] and "발주사가 확인할 것은 요구사항 1건" in lines[1]
    assert "숫자 기준이 없는 목표 1" in lines[2] and "남은 곳 2" in lines[2] and "제안요약.md" in lines[2]


def test_proposal_counts_links_and_lists_what_needs_a_decision() -> None:
    text = proposal_md(source())
    assert "요구사항 3건 · 화면 1개 · 연계 시스템 3개" in text and "**큼**" in text  # three links alone make it 큼
    for line in ("- 밖의 서비스 3개", "  - 결제대행사(PG):", "### 문서에 빈칸으로 남은 곳 2곳", "- 카드 자동결제: 결제대행사",
                 "### 숫자 기준이 없는 목표 1개", "- 매출이 는다", "### 팀이 기본값으로 채운 것(가정) 1건", "- 카드 자동결제\n",
                 "### 아직 정하지 않은 요구사항 2건", "- 환불\n", "- 쿠폰 금액: 답이 없음\n", "「큼」입니다"):
        assert line in text, line
    body, appendix = text.split("## 부록: 근거 번호")
    assert "REQ-" not in body and "OPEN-01" not in body  # the owner's page has no reference numbers in its sentences
    for row in ("| 카드 자동결제 | REQ-01 |", "| 환불 | REQ-03 · 미결 |", "| 밖의 서비스: 결제대행사(PG) | REQ-01 |"):
        assert row in appendix, row
    assert "BRD(왜 만드는지 적은 문서)" in text  # terms are explained once for the owner
    assert "외부 연동" in agents_md(source()) and "- 결제대행사(PG) (밖의 서비스" in agents_md(source())


def test_each_document_names_only_its_own_unconfirmed_items() -> None:
    src = source()
    brd, prd, screens, tests = (status_banner(src, d) for d in ("brd", "prd", "screens", "tests"))
    assert "가정으로 채운 요구사항 1건: 「5. 제약과 가정」" in brd and "숫자 기준이 없는 목표 1개" in brd and "REQ-01" not in brd
    assert "적었습니다" in brd and "적었다." in prd  # the BRD speaks to the owner (합니다체), the rest to developers (한다체)
    assert "가정 요구사항 1건" in prd and "상태가 미결·미확인인 요구사항 1건이다.\n  - REQ-03" in prd and "SCR-01" not in prd
    assert "가정 화면 1건이다." in screens and "  - SCR-01\n" in screens and "  - SCR-01#1 신청 화면의 가격" in screens and "TC-01" not in screens
    assert "가정 테스트 케이스 1건이다." in tests and "  - TC-01" in tests and "REQ-01" not in tests
    files = bundle_files({**src, "confirmations": [{"id": "CF-01", "cp": "CP4", "approved": True}]})
    for name in ("BRD.md", "PRD.md", "화면설계서.md", "테스트케이스.md"):
        assert str(files[name]).count("## 아직 확정되지 않은 것") == 1
    assert "| REQ-01 | 카드 자동결제 | 결제대행사 선정은 미정 |" in str(files["PRD.md"])  # the blank sits in the PRD's open table


def test_owner_documents_keep_reference_numbers_out_of_their_sentences() -> None:
    """11-24: the BRD and the summary are read by the owner — ID-only parentheses move to an appendix."""
    from app.documents import build_documents, to_markdown
    from app.owner_text import strip_refs

    assert strip_refs("중복 결제는 0건이어야 한다(DEC-02·09, TC-09·12). 꽃집 운영자 [SRC-01, SRC-02]") == (
        "중복 결제는 0건이어야 한다. 꽃집 운영자", ["DEC-02·09, TC-09·12", "SRC-01, SRC-02"])
    assert strip_refs("REQ-14가 빠져 측정 수단이 없습니다(가정)") == ("REQ-14가 빠져 측정 수단이 없습니다(가정)", [])  # part of the sentence
    src = source()
    src["brd"][0]["goals"][1]["criterion"] = "오후 6시 전 도착 95% 이상(DEC-08)"
    src["brd"][0]["risks"] = [{"risk": "가격이 정해지지 않았다(SRC-03).", "impact": "화면을 못 정한다", "response": "가격표를 받는다"}]
    brd = to_markdown(build_documents(src)["brd"])
    assert "| 정시 도착 | 오후 6시 전 도착 95% 이상 | 확정 |" in brd and "| 가격이 정해지지 않았다. |" in brd
    appendix = brd.split("## 7-1. 근거 번호")[1].split("\n## ")[0]
    assert "| 2. 목표와 성공 기준 | 오후 6시 전 도착 95% 이상 | DEC-08 |" in appendix and "| 6. 위험 | 가격이 정해지지 않았다. | SRC-03 |" in appendix
    proposal = proposal_md(src)
    assert "95% 이상 (확정)" in proposal.split("## 부록")[0] and "DEC-08" in proposal.split("## 부록")[1]
