from __future__ import annotations
"""FR-09: four document views from one shared source, following the confirmed format spec."""

import re
from pathlib import Path
from typing import Any

import pytest

from app.documents import build_documents, to_markdown
from app.wireframe import render_wireframe
from tests.pipeline_helpers import build, to_cp3

WAIVER = {"coverage.no_tc:REQ-02": "결제 실패는 다음 단계에서 시험"}


@pytest.fixture
def source(repo_root: Path, key_env: Path) -> dict[str, Any]:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    orch.confirm("CP3", True, "발주사", waivers=WAIVER)
    return ws.source


def section(doc: dict[str, Any], sid: str) -> dict[str, Any]:
    return next(s for s in doc["sections"] if s["id"] == sid)


def table(doc: dict[str, Any], sid: str, index: int = 0) -> dict[str, Any]:
    return [b for b in section(doc, sid)["blocks"] if b["type"] == "table"][index]


def test_all_four_documents_have_two_layers_and_header(source: dict[str, Any]) -> None:
    docs = build_documents(source)
    assert list(docs) == ["brd", "prd", "screens", "tests"]
    owners = {k: d["header"]["owner_agent"] for k, d in docs.items()}
    assert owners == {"brd": "pm", "prd": "pm", "screens": "designer", "tests": "qa"}
    for doc in docs.values():
        assert 1 <= len(doc["summary"]) <= 5
        assert doc["sections"][-1]["id"] == "history"
        assert doc["header"]["version"] == "v2"
        assert [a["cp"] for a in doc["header"]["approvals"]] == ["CP2", "CP3"]
        assert all(a["id"].startswith("CF-") for a in doc["header"]["approvals"])


def test_brd_sections_follow_format_spec(source: dict[str, Any]) -> None:
    brd = build_documents(source)["brd"]
    assert [s["id"] for s in brd["sections"]] == [
        "background", "goals", "scope", "non_goals", "stakeholders", "constraints", "risks", "open_questions",
        "history"]
    assert "하지 않는 것과 이유" in section(brd, "non_goals")["title"]
    background = table(brd, "background")
    assert background["columns"] == ["원문 ID", "발주사 원문", "해석"]
    texts = {s["id"]: s["text"] for s in source["sources"]}
    for src_id, quote, interpretation in background["rows"]:
        assert quote == texts[src_id] and interpretation and interpretation != quote
    goals = table(brd, "goals")["rows"]
    assert [g[2] for g in goals] == ["확정", "미결"]
    assert table(brd, "non_goals")["rows"][0][:2] == ["서울 밖 배송", "가게가 직접 배송할 수 있는 곳만 먼저 한다"]
    assert table(brd, "history")["rows"][0][0] == "v1"


def test_prd_requirement_table_and_decisions(source: dict[str, Any]) -> None:
    prd = build_documents(source)["prd"]
    assert [s["id"] for s in prd["sections"]] == ["totals", "requirements", "decisions", "open_questions", "done_criteria", "history"]
    reqs = table(prd, "requirements")
    assert reqs["columns"] == ["ID", "분류", "이름", "설명", "인수 조건", "예외", "중요도", "상태", "근거",
                               "관련 요구사항", "관련 화면·테스트"]
    assert [r[0] for r in reqs["rows"]] == ["REQ-01", "REQ-02"]
    assert "SCR-01" in reqs["rows"][0][10] and "TC-01" in reqs["rows"][0][10]
    assert reqs["rows"][0][4].startswith("조건: ")  # 11-24: Korean labels (조건 / 동작 / 결과)
    decisions = table(prd, "decisions")
    assert decisions["columns"] == ["결정", "주제", "채택", "기각안과 이유", "누가 답했나"]
    first = decisions["rows"][0]
    assert first[0] == "DEC-01" and first[2] == "수·토 중 고름"
    assert "토요일 일괄" in first[3] and "발주사가 직접 골랐다" in first[3]
    assert "Q-01" in first[4]


def test_screen_spec_has_list_detail_wireframe_and_states(source: dict[str, Any]) -> None:
    doc = build_documents(source)["screens"]
    assert [s["id"] for s in doc["sections"]] == ["screen_list", "SCR-01", "SCR-02", "no_screen", "history"]
    assert table(doc, "screen_list")["columns"] == ["화면 ID", "화면명", "관련 요구사항", "상태"]
    (block,) = section(doc, "SCR-01")["blocks"]
    assert block["type"] == "screen" and block["id"] == "SCR-01"
    assert block["elements"]["columns"] == ["번호", "요소명", "설명", "동작과 결과", "입력 규칙(타입·필수·검증)", "관련 REQ"]
    assert [r[0] for r in block["elements"]["rows"]] == ["1", "2", "3", "4"]
    assert block["svg"].count('class="callout"') == 4
    assert [r[0] for r in block["states"]["rows"]] == ["빈 상태", "로딩", "오류"]
    assert "SCR-01" in doc["summary"][-1] and "→" in doc["summary"][-1]


def test_test_case_view_fields_and_coverage(source: dict[str, Any]) -> None:
    doc = build_documents(source)["tests"]
    assert [s["id"] for s in doc["sections"]] == ["cases", "coverage", "history"]
    cases = table(doc, "cases")
    assert cases["columns"] == ["TC ID", "목적", "관련 요구사항·화면", "우선순위", "사전조건", "입력", "절차",
                                "기대 결과", "실제 결과·판정"]
    assert cases["rows"][0][0] == "TC-01" and cases["rows"][0][-1] == ""
    coverage = table(doc, "coverage")
    assert coverage["columns"] == ["요구사항 ID", "요구사항 설명", "테스트 케이스·운영 확인"]
    assert coverage["rows"][1][2] == "없음"


def test_same_id_same_text_across_views(source: dict[str, Any]) -> None:
    docs = build_documents(source)
    prd_rows = {r[0]: r[3] for r in table(docs["prd"], "requirements")["rows"]}
    tc_rows = {r[0]: r[1] for r in table(docs["tests"], "coverage")["rows"]}
    for req in source["requirements"]:
        assert prd_rows[req["id"]] == tc_rows[req["id"]] == req["statement"]
    screen_titles = {r[0]: r[1] for r in table(docs["screens"], "screen_list")["rows"]}
    assert screen_titles == {s["id"]: s["title"] for s in source["screens"]}


def test_markdown_export(source: dict[str, Any]) -> None:
    docs = build_documents(source)
    brd_md = to_markdown(docs["brd"])
    assert brd_md.startswith("# BRD")
    assert "## 한눈에 보기" in brd_md and "## 3-1. 하지 않는 것과 이유" in brd_md
    assert "작성 책임" in brd_md and "CF-" in brd_md
    assert "| 원문 ID | 발주사 원문 | 해석 |" in brd_md
    screens_md = to_markdown(docs["screens"])
    assert "![SCR-01 와이어프레임](wireframes/SCR-01.svg)" in screens_md
    assert "| 번호 | 요소명 |" in screens_md


def test_markdown_escapes_pipes_and_newlines() -> None:
    doc = {"title": "T", "header": {"owner_name": "PM", "version": "작업본", "approvals": []}, "summary": ["요약이다."],
           "sections": [{"id": "x", "title": "X", "blocks": [
               {"type": "table", "columns": ["a"], "rows": [["x|y\nz"]]}]}], "warnings": []}
    assert "| x\\|y z |" in to_markdown(doc)


def test_wireframe_has_one_numbered_callout_per_element() -> None:
    screen = {"id": "SCR-09", "title": "<테스트>", "elements": [
        {"no": i, "name": f"요소 {i}", "kind": kind} for i, kind in
        enumerate(["text", "input", "select", "list", "image", "button", "unknown"], start=1)]}
    svg = render_wireframe(screen)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert svg.count('class="callout"') == 7
    numbers = re.findall(r'<text class="callout-no"[^>]*>(\d+)</text>', svg)
    assert numbers == [str(i) for i in range(1, 8)]
    assert "<테스트>" not in svg and "&lt;테스트&gt;" in svg
    assert render_wireframe(screen) == svg


def test_draft_documents_before_any_version() -> None:
    docs = build_documents({"requirements": [], "screens": [], "tests": [], "sources": []})
    assert docs["brd"]["header"]["version"] == "작업본(미고정)"
    assert docs["brd"]["summary"] == []


def test_brd_stakeholders_and_open_questions_describe_the_project_not_the_tool(source: dict[str, Any]) -> None:
    """Review B: no tool self-description in the client's BRD; goal questions keep the ID column for IDs."""
    from app.documents import DocContext
    ctx = DocContext({}, (("client", "human"), ("consumer", "agent")))
    brd = build_documents(source, ctx)["brd"]
    rows = table(brd, "stakeholders")["rows"]
    client = next(r for r in rows if r[0] == "발주사")
    assert "컨펌" not in client[2] and "문서를 쓰지 않고" not in client[2]
    assert client[2] == source["problem_statement"][0]["done"]
    open_rows = table(brd, "open_questions")["rows"]
    assert open_rows and all(r[0] != "목표" for r in open_rows)
    goal_rows = [r for r in open_rows if "숫자로 잴 기준" in r[1]]
    assert goal_rows and all(r[0] == "—" and r[1].startswith("목표 「") for r in goal_rows)
