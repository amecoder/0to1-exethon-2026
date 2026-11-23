from __future__ import annotations
"""BRD — why we build it (format spec section 1). No solutions in the problem section (C1)."""

from collections.abc import Mapping
from typing import Any

from app.documents.common import (
    NONE, DocContext, bullets, first, history_section, joined, make_doc, paragraph, section, table,
)
from app.quality import BRD_MAX_CHARS, brd_too_long, quote_interpretation_problem, solution_words, warning

STAKEHOLDER_ROWS = {
    "client": ("발주사", "사람", "요청한 결과물이 합의한 성공 기준대로 나오기를 바란다"),
    "consumer": ("소비자(최종 고객)", "에이전트", "실제로 쓰는 사람 입장에서 불편과 포기 지점이 없기를 바란다"),
}
OPEN_STATUSES = ("미결", "미확인")


def build_brd(source: Mapping[str, Any], ctx: DocContext) -> dict[str, Any]:
    brd, scope = first(source, "brd"), first(source, "scope")
    texts = {s["id"]: s["text"] for s in source.get("sources", [])}
    sections = [
        section("background", "1. 추진 배경과 문제", [
            paragraph("발주사가 한 말(원문)과 팀의 해석을 나란히 적습니다. 해결책은 이 칸에 쓰지 않습니다."),
            table(["원문 ID", "발주사 원문", "해석"],
                  [[b["src_id"], texts.get(b["src_id"], ""), b["interpretation"]] for b in brd.get("background", [])]),
        ]),
        section("goals", "2. 목표와 성공 기준", [table(
            ["목표", "성공 기준", "상태"], [[g["goal"], g["criterion"], g["status"]] for g in brd.get("goals", [])])]),
        section("scope", "3. 범위", [table(
            ["하는 것", "근거 원문"], [[c["text"], joined(c.get("refs", []))] for c in scope.get("in", [])])]),
        section("non_goals", "3-1. 하지 않는 것과 이유", [table(["하지 않는 것", "이유", "근거 원문"], non_goal_rows(brd, scope))]),
        section("stakeholders", "4. 이해관계자", [table(["누구", "구분", "관심"], stakeholder_rows(source, ctx))]),
        section("constraints", "5. 제약과 가정", constraint_blocks(source, brd)),
        section("risks", "6. 위험", [table(
            ["위험", "영향", "대응"], [[r["risk"], r["impact"], r["response"]] for r in brd.get("risks", [])])]),
        section("open_questions", "7. 열린 질문", [table(["ID", "질문", "누가 답하나"], open_rows(source, brd))]),
        history_section(source, "8", "pm", ctx),
    ]
    doc = make_doc("brd", "BRD — 왜 만드나", "pm", source, ctx, brd.get("summary", []), sections)
    return doc


def non_goal_rows(brd: Mapping[str, Any], scope: Mapping[str, Any]) -> list[list[str]]:
    rows = [[n["item"], n["reason"], joined(n.get("refs", []))] for n in brd.get("non_goals", [])]
    listed = {r[0] for r in rows}
    rows += [[c["text"], "이유가 아직 없습니다(미결)", joined(c.get("refs", []))]
             for c in scope.get("out", []) if c["text"] not in listed]
    return rows


def stakeholder_rows(source: Mapping[str, Any], ctx: DocContext) -> list[list[str]]:
    """The client's interest is the project's own 'done' line (problem statement); the fixed text is a fallback."""
    done = first(source, "problem_statement").get("done")
    rows = [list(STAKEHOLDER_ROWS[eid]) for eid, _ in ctx.externals if eid in STAKEHOLDER_ROWS]
    rows = [[r[0], r[1], done] if r[0] == "발주사" and done else r for r in rows]
    who = first(source, "problem_statement").get("who")
    if who:
        rows.append([who, "문제 진술의 대상", first(source, "problem_statement").get("pain", NONE)])
    return rows


def constraint_blocks(source: Mapping[str, Any], brd: Mapping[str, Any]) -> list[dict[str, Any]]:
    assumed = [[r["id"], r["title"], r["statement"]] for r in source.get("requirements", []) if r.get("status") == "가정"]
    return [bullets(brd.get("constraints", [])) if brd.get("constraints") else paragraph("적힌 제약이 없습니다."),
            paragraph(f"가정 모음 — 근거 없이 기본값으로 채운 요구사항 {len(assumed)}건"),
            table(["ID", "이름", "설명"], assumed)]


def open_rows(source: Mapping[str, Any], brd: Mapping[str, Any]) -> list[list[str]]:
    rows = [[o["id"], o.get("title", ""), "발주사"] for o in source.get("open_items", [])]
    rows += [[r["id"], r["title"], "발주사 · PM"] for r in source.get("requirements", []) if r.get("status") in OPEN_STATUSES]
    rows += [["—", f"목표 「{g['goal']}」: 숫자로 잴 기준이 필요합니다", "발주사"]
             for g in brd.get("goals", []) if g["status"] == "미결"]
    return rows


def brd_rule_warnings(doc: Mapping[str, Any], source: Mapping[str, Any], body_markdown: str) -> list[dict[str, Any]]:
    """BRD-only rules: length (P10), quote vs interpretation, no solutions in the problem section (C1)."""
    texts = {s["id"]: s["text"] for s in source.get("sources", [])}
    rows = next(b for b in doc["sections"][0]["blocks"] if b["type"] == "table")["rows"]
    out = []
    if brd_too_long(body_markdown):
        out.append(warning("quality.brd_length", "brd", "brd",
                           f"BRD 본문이 {len(body_markdown)}자로 A4 2쪽(약 {BRD_MAX_CHARS}자)을 넘습니다 — 문제가 덜 정리됐다는 신호입니다"))
    for row in rows:
        if quote_interpretation_problem(row, texts):
            out.append(warning("quality.quote_interpretation", row[0], "brd", f"{row[0]} 원문과 해석이 구분되지 않습니다"))
        words = solution_words(row[2])
        if words:
            out.append(warning("quality.solution_in_problem", row[0], "brd",
                               f"문제 칸에 해결책이 섞였습니다: {', '.join(words)}"))
    return out
