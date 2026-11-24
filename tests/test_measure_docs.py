from __future__ import annotations
"""Document-quality measurement scripts: readability (hanlint on a cell copy) and cross-document consistency.
hanlint itself is not run here (it needs the network to install); the pure parts are."""

from pathlib import Path
from types import ModuleType

from tests.test_measure_scripts import load

LONG = "주문 마감 직후 그 주 배송분의 수량과 배송지 목록을 한 번에 확인한다."


def readability(repo_root: Path) -> ModuleType:
    return load(repo_root, "measure_doc_readability")


def consistency(repo_root: Path) -> ModuleType:
    return load(repo_root, "measure_doc_consistency")


def test_cells_lists_and_quotes_become_paragraphs_with_a_map_back(repo_root: Path) -> None:
    m = readability(repo_root)
    md = "\n".join(["# 문서", "", "> 머리말 한 줄", "", "## 1. 표", "", "| ID | 설명 | 근거 |", "|---|---|---|",
                    f"| REQ-01 | {LONG} | SRC-01, SRC-02, SRC-03, SRC-04, SRC-05 |", "| REQ-02 | 짧다 | — |", "",
                    "- 목록 항목: 고정 문구입니다.", ""])
    segments, copy = m.extract("PRD.md", md, (LONG,))
    cell = next(s for s in segments if s.kind == "cell")
    assert (cell.section, cell.row, cell.column, cell.origin) == ("1. 표", 1, "설명", "model")
    assert copy.splitlines()[cell.line - 1] == LONG  # the map points at the line hanlint reports
    assert [s.kind for s in segments] == ["heading", "quote", "heading", "cell", "list"]  # short and ID-only cells are left out
    assert all(s.origin == "code" for s in segments if s.kind != "cell")
    assert "|" not in copy and "- " not in copy and "> " not in copy


def test_origin_survives_a_glossary_note_and_long_sentences_are_counted(repo_root: Path) -> None:
    m = readability(repo_root)
    strings = m.model_strings({"requirements": [{"statement": "매주 목요일에 자동결제를 실행한다."}], "events": [{"x": "기록에만 있는 긴 문장입니다."}]})
    assert strings == ("매주 목요일에 자동결제를 실행한다.",)
    assert m.origin_of("매주 목요일에 자동결제(정해진 날 돈이 나가는 것)를 실행한다.", strings) == "model"
    assert m.origin_of("기록에만 있는 긴 문장입니다.", strings) == "code"
    long_sentence = " ".join(["말"] * 31) + "."
    segs = [m.Segment("d", "s", "prose", 0, "", f"{long_sentence} 짧은 문장이다.", "model", 1)]
    assert m.long_share(segs) == (1, 2)
    summary = m.summarize(segs, [{"rule": "longSentence", "line": 1}, {"rule": "noQuestion", "line": 0}])
    assert summary["model"]["findings"] == 1 and summary["model"]["per_1000"] > 0 and summary["code"]["findings"] == 0
    assert summary["unplaced"] == {"noQuestion": 1}


def _source() -> dict[str, object]:
    return {
        "requirements": [{"id": "REQ-01", "title": "신청", "statement": "결제대행사 빌링키로 결제한다. 가격은 미정", "status": "가정"},
                         {"id": "REQ-02", "title": "집계", "statement": "운영자가 집계를 본다", "status": "확정"},
                         {"id": "REQ-03", "title": "알림", "statement": "앱 푸시를 보내고, 문자 발송은 하지 않는다", "status": "확정"}],
        "screens": [{"id": "SCR-01", "title": "신청", "elements": [
            {"no": 1, "name": "집계 보기 버튼", "action": "누르면 SCR-02로 이동한다", "description": ""}]}],
        "screen_spec": [{"id_map": {"a": "SCR-01", "b": "SCR-02"}, "swimlane": {"steps": [
            {"id": "S1", "label": "집계 확인", "screen_ref": "SCR-02"}]}}],
        "tests": [{"id": "TC-01", "status": "가정"}],
        "brd": [{"goals": [{"goal": "매출", "status": "미결"}]}],
        "decisions": [{"id": "DEC-01", "kind": "scope", "screens_kept": ["SCR-01"], "dropped_requirements": ["REQ-02"]}],
    }


def test_scope_leaks_are_found_outside_the_dropped_list_only(repo_root: Path) -> None:
    c = consistency(repo_root)
    assert c.scope_cut(_source()) == ({"REQ-02"}, {"SCR-02"})
    assert c.id_mentions("REQ-12·14(범위 밖)와 REQ-03, 11-22") == [("REQ-12", True), ("REQ-14", True), ("REQ-03", False)]
    files = {"AGENTS.md": "## 작업 순서\n\n### TASK-02 · REQ-02 집계\n\n- 먼저: REQ-02(범위 밖)\n\n## 이번 범위에서 뺀 것\n\n- REQ-02 집계\n",
             "화면설계서.md": "## 2-1. SCR-01\n\n| 1 | 버튼 | 누르면 SCR-02로 이동한다 |\n",
             "wireframes/SCR-01.svg": "<svg><text>집계 보기 버튼</text></svg>",
             "user_flow_lanes.html": '<g data-step="S1"><text>집계 확인</text></g>'}
    found = c.check_scope(_source(), files)
    assert [(v["where"].split(" · ")[0], v["what"]) for v in found] == [
        ("화면설계서.md", "SCR-02"), ("AGENTS.md", "REQ-02"), ("wireframes/SCR-01.svg", "#1 집계 보기 버튼"),
        ("user_flow_lanes.html", "SCR-02")]
    clean = {"AGENTS.md": "## 이번 범위에서 뺀 것\n\n- REQ-02 집계\n", "wireframes/SCR-01.svg": "<svg></svg>",
             "user_flow_lanes.html": '<g data-step="S1"><text>화면 없음(이번 범위 밖)</text></g>'}
    assert c.check_scope(_source(), clean) == []


def test_open_count_integrations_and_dangling_ids(repo_root: Path) -> None:
    c = consistency(repo_root)
    source = _source()
    points = c.open_points(source)
    assert points["goals"] == ["매출"] and points["blanks"] == ["REQ-01"]  # the dropped REQ-02 is not counted
    assert len(c.check_open_count(source, {"README.txt": "가정 2건 · 미결 0건"})) == 1
    assert c.check_open_count(source, {"README.txt": "미결 2건"}) == []
    assert c.integrations(source) == {"결제대행사(PG)": ["REQ-01"], "앱 푸시 알림": ["REQ-03"]}  # 문자 발송 is negated
    assert len(c.check_integrations(source, {"제안요약.md": "연계 시스템 0개"})) == 1
    assert c.check_integrations(source, {"제안요약.md": "연계 시스템 2개"}) == []
    dangling = c.check_dangling(source, {"PRD.md": "## 표\n\nREQ-01, TC-014, SCR-02, DEC-01"})
    assert [v["what"] for v in dangling] == ["TC-014"]  # SCR-02 is a dropped screen: counted by (a), not here
    result = c.measure(source, {"README.txt": "미결 2건", "제안요약.md": "연계 시스템 2개"})
    assert result["total"] == 0 and result["counts"] == {"a": 0, "b": 0, "c": 0, "d": 0}
