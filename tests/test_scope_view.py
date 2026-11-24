from __future__ import annotations
"""Scope cut → every hand-off output (11-24): what the client dropped when narrowing the screens is not a task,
a constant, a test, a wireframe box or a navigation target any more — it is listed once, and still named."""

import json
from pathlib import Path
from typing import Any

from app.documents import build_documents, to_markdown
from app.export import bundle_files, export_source
from app.handoff_docs import agents_md, proposal_md
from app.scope_view import MARK, fix_ids, scope_view
from app.swimlane import swimlane_svg
from app.wireframe import render_wireframe
from tests.test_measure_scripts import load
from tests.test_scope_limit import to_scope

ACC = {"given": "g", "when": "w", "then": "t"}


def req(rid: str, title: str, **extra: Any) -> dict[str, Any]:
    return {"id": rid, "title": title, "statement": f"{title} 진술", "acceptance": ACC, "exceptions": [], "status": "확정",
            "category": "SFR", "depends_on": [], "screens": [], "tests": [], **extra}


def element(no: int, name: str, action: str, kind: str = "button") -> dict[str, Any]:
    return {"no": no, "name": name, "kind": kind, "description": name, "action": action, "input_rule": "",
            "requirement_refs": ["REQ-01"]}


def cut_source() -> dict[str, Any]:
    """REQ-02 lost its only screen (SCR-02); REQ-03 leans on it; SCR-01 has a button that led to SCR-02."""
    return {
        "requirements": [req("REQ-01", "신청", tests=["TC-01", "TC-03"], screens=["SCR-01"]),
                         req("REQ-02", "운영자 집계", status="가정", tests=["TC-02"]),
                         req("REQ-03", "알림", depends_on=["REQ-02"], exceptions=["대상은 REQ-02를 따른다"], tests=["TC-04"])],
        "screens": [{"id": "SCR-01", "title": "신청", "purpose": "신청한다", "status": "확정", "requirement_refs": ["REQ-01"],
                     "states": {}, "elements": [element(1, "신청 버튼", "누르면 신청된다"),
                                                element(2, "집계 보기 버튼", "누르면 SCR-02로 이동한다")]}],
        "screen_spec": [{"id": "SCRDOC-01", "id_map": {"a": "SCR-01", "b": "SCR-02"}, "flow": ["SCR-01"], "no_screen": {},
                         "swimlane": {"lanes": ["고객", "운영자"], "steps": [
                             {"id": "S1", "lane": "고객", "label": "신청", "screen_ref": "SCR-01", "after": [], "kind": "normal", "note": ""},
                             {"id": "S2", "lane": "운영자", "label": "집계 확인", "screen_ref": "SCR-02", "after": ["S1"],
                              "kind": "normal", "note": ""}]}}],
        "tests": [{"id": "TC-01", "title": "신청", "requirement_refs": ["REQ-01"], "screen_refs": ["SCR-01"], "expected": "e",
                   "priority": "상", "status": "확정"},
                  {"id": "TC-02", "title": "집계", "requirement_refs": ["REQ-02"], "expected": "e", "status": "가정"},
                  {"id": "TC-03", "title": "집계 화면 이동", "requirement_refs": ["REQ-01"], "expected": "e", "status": "확정",
                   "preconditions": "집계 화면(SCR-02)이 있어야 한다. TC-001 뒤에 한다."},
                  {"id": "TC-04", "title": "알림", "requirement_refs": ["REQ-03", "REQ-02"], "expected": "e", "status": "확정"}],
        "decisions": [{"id": "DEC-01", "kind": "scope", "topic": "화면 범위 줄이기 (G8)", "chosen": "신청", "rejected": ["운영자 집계 화면"],
                       "status": "확정", "screens_kept": ["SCR-01"], "dropped_requirements": ["REQ-02"]}],
        "brd": [{"id": "BRD-01", "summary": [], "goals": [], "non_goals": [], "constraints": [],
                 "risks": [{"risk": "집계(REQ-02)가 빠졌다", "impact": "i", "response": "r"}], "background": []}],
        "confirmations": [], "versions": [],
    }


def test_fix_ids_marks_dropped_ids_and_reads_short_forms() -> None:
    dropped, known = {"REQ-12", "REQ-14", "SCR-06"}, {"REQ-10", "TC-14", "TC-15"}
    assert fix_ids("REQ-12·14가 빠졌다", dropped, known) == f"REQ-12·14{MARK}가 빠졌다"
    assert fix_ids("REQ-10·12는", dropped, known) == f"REQ-10·REQ-12{MARK}는"
    assert fix_ids("누르면 SCR-06으로 이동, 2026-11-22", dropped, known) == f"누르면 SCR-06{MARK}으로 이동, 2026-11-22"
    assert fix_ids("TC-014·015의 기대 금액", dropped, known) == "TC-14·15의 기대 금액"  # zero-padded → the ID the source has
    once = fix_ids("REQ-12와 REQ-10", dropped, known)
    assert fix_ids(once, dropped, known) == once == f"REQ-12{MARK}와 REQ-10"


def test_view_moves_dropped_items_out_and_keeps_them_listed() -> None:
    source = cut_source()
    before = json.dumps(source, ensure_ascii=False)
    view = scope_view(source)
    assert json.dumps(source, ensure_ascii=False) == before  # the record is not changed
    assert [r["id"] for r in view["requirements"]] == ["REQ-01", "REQ-03"]
    assert [t["id"] for t in view["tests"]] == ["TC-01", "TC-04"]
    out = view["out_of_scope"]
    assert [r["id"] for r in out["requirements"]] == ["REQ-02"] and out["screens"] == [{"id": "SCR-02", "title": "운영자 집계 화면"}]
    assert [(t["id"], "REQ-02" in t["reason"] or "SCR-02" in t["reason"]) for t in out["tests"]] == [("TC-02", True), ("TC-03", True)]
    assert out["elements"][0]["name"] == "집계 보기 버튼"
    kept = {r["id"]: r for r in view["requirements"]}
    assert kept["REQ-01"]["tests"] == ["TC-01"]  # the parked TC-03 is no longer a test of REQ-01
    assert kept["REQ-03"]["depends_on"] == [f"REQ-02{MARK}"] and kept["REQ-03"]["exceptions"] == [f"대상은 REQ-02{MARK}를 따른다"]
    button = view["screens"][0]["elements"][1]
    assert button["out_of_scope"] is True and "이번 버전에서는 이 요소를 넣지 않는다" in button["action"]
    assert scope_view(view)["out_of_scope"] == out  # a view of a view is the same view


def test_a_scope_decision_for_older_screens_is_ignored() -> None:
    source = cut_source()
    source["screens"].append({"id": "SCR-03", "title": "새 화면", "elements": [], "requirement_refs": []})  # redrawn after a change
    view = scope_view(source)
    assert [r["id"] for r in view["requirements"]] == ["REQ-01", "REQ-02", "REQ-03"]
    assert view["out_of_scope"]["requirements"] == [] and view["out_of_scope"]["screens"] == []


def test_agents_md_has_no_task_constant_or_test_for_what_was_cut() -> None:
    text = agents_md(cut_source())
    tasks = [line for line in text.splitlines() if line.startswith("### TASK-")]
    assert tasks == ["### TASK-01 · REQ-01 신청", "### TASK-02 · REQ-03 알림"]
    assert "REQ_02" not in text and "TC-02 집계\n" not in text.split("## 작업 순서")[1]
    cut = text.split("## 이번 범위에서 뺀 것 (만들지 않는다)")[1].split("\n## ")[0]
    for named in ("요구사항 REQ-02 운영자 집계", "화면 SCR-02 운영자 집계 화면", "화면 요소 SCR-01 #2 집계 보기 버튼", "테스트 TC-02", "테스트 TC-03"):
        assert named in cut
    assert "먼저 끝나야 하는 것: REQ-02" not in text and f"REQ-03, REQ-02{MARK}" not in text.split("## 작업 순서")[0]


def test_documents_list_the_cut_once_and_mark_other_mentions() -> None:
    docs = build_documents(cut_source())
    prd, screens, tests = (to_markdown(docs[d]) for d in ("prd", "screens", "tests"))
    assert "## 2-1. 이번 범위에서 뺀 것" in prd and "| REQ-02 | 운영자 집계 |" in prd.split("## 2-1.")[1].split("\n## ")[0]
    assert "| REQ-02 |" not in prd.split("## 2. 요구사항 상세 표")[1].split("\n## ")[0]
    assert f"REQ-02{MARK}" in prd  # REQ-03 still says what it leans on
    assert "## 3-1. 이번 범위에서 뺀 화면과 요소" in screens and "SCR-02로 이동한다" not in screens
    assert "## 1-1. 이번 범위 밖 테스트 (보류)" in tests
    cases = tests.split("## 1. 테스트 케이스 표")[1].split("\n## ")[0]
    assert "| TC-02 |" not in cases and "| TC-03 |" not in cases and "| TC-01 |" in cases
    assert "(보류: TC-03)" in tests.split("커버리지 표")[1]
    assert "화면 범위를 줄이면서 뺀 요구사항 1건과 화면 1개" in to_markdown(docs["brd"])
    assert not [w for d in docs.values() for w in d["warnings"] if w["target"] == "REQ-02"]


def test_wireframe_lane_chart_summary_and_exported_source() -> None:
    source = cut_source()
    view = scope_view(source)
    svg = render_wireframe(view["screens"][0])
    assert "신청 버튼" in svg and "집계 보기 버튼" not in svg
    lanes = swimlane_svg(view["screen_spec"][0]["swimlane"], view["screens"])
    assert "화면: 이번 범위 밖" in lanes and "화면: 신청" in lanes
    proposal = proposal_md(source)
    assert "화면 범위를 줄이면서 이번에 뺀 것" in proposal and "- 화면: 운영자 집계 화면" in proposal and "- 기능: 운영자 집계" in proposal and "요구사항 2건" in proposal
    exported = export_source(source, "2026-11-24T00:00:00+00:00")
    assert exported["meta"]["out_of_scope"] == {"decision": "DEC-01", "requirements": ["REQ-02"], "screens": ["SCR-02"],
                                               "tests": ["TC-02", "TC-03"]}
    assert len(exported["requirements"]) == 3 and "out_of_scope" not in exported  # the items themselves stay


def test_a_narrowed_run_leaves_no_scope_leak_in_the_bundle(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = to_scope(repo_root, key_env)
    orch.narrow_scope(["SCR-01", "SCR-02"], "발주사")
    orch.advance()
    files = {k: v for k, v in bundle_files(ws.source).items() if isinstance(v, str)}
    consistency = load(repo_root, "measure_doc_consistency")
    result = consistency.measure(ws.source, files)
    assert result["counts"]["a"] == 0 and result["counts"]["d"] == 0, result["violations"]
    assert "(범위 밖)" not in files["AGENTS.md"] or "## 이번 범위에서 뺀 것" in files["AGENTS.md"]
