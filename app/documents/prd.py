from __future__ import annotations
"""PRD — what we build (format spec section 2). Decisions and alternatives come from DEC- records (C3)."""

from collections import Counter
from collections.abc import Mapping
from typing import Any

from app.documents.common import (
    NONE, DocContext, first, history_section, joined, make_doc, paragraph, section, table,
)
from app.documents.brd import OPEN_STATUSES, open_rows
from app.schemas import CATEGORIES, REQ_STATUSES

CATEGORY_NAMES = {"SFR": "기능", "PER": "성능", "SER": "보안", "DAR": "데이터", "INR": "인터페이스", "COR": "제약"}
REQ_COLUMNS = ["ID", "분류", "이름", "설명", "인수 조건", "예외", "중요도", "상태", "근거", "관련 요구사항", "관련 화면·테스트"]
DEFAULT_REASON = {"choice": "발주사가 다른 답을 골랐다", "unknown": "발주사가 '잘 모르겠어요' → 기본값으로 채움(가정)",
                  "free_text": "발주사가 직접 입력했다"}


def acceptance_text(req: Mapping[str, Any]) -> str:
    a = req.get("acceptance") or {}
    return f"Given {a.get('given', '')} / When {a.get('when', '')} / Then {a.get('then', '')}"


def links_text(req: Mapping[str, Any]) -> str:
    links = [*req.get("screens", []), *req.get("tests", [])]
    if req.get("screen_exemption"):
        links.append(f"화면 없음: {req['screen_exemption']}")
    return joined(links)


def requirement_row(req: Mapping[str, Any]) -> list[str]:
    category = req.get("category", "SFR")
    return [req["id"], f"{category} {CATEGORY_NAMES.get(category, '')}".strip(), req.get("title", ""),
            req.get("statement", ""), acceptance_text(req), joined(req.get("exceptions", []), " / "),
            req.get("priority", ""), req.get("status", ""),
            joined([*req.get("source_refs", []), *req.get("evidence_refs", []), *req.get("decision_refs", [])]),
            joined(req.get("depends_on", [])), links_text(req)]


def decision_rows(source: Mapping[str, Any]) -> list[list[str]]:
    notes = {n["decision_id"]: n["reason"] for n in first(source, "prd").get("decision_notes", [])}
    cp2 = [c["id"] for c in source.get("confirmations", []) if c.get("cp") == "CP2" and c.get("approved")]
    rows = []
    for d in source.get("decisions", []):
        reason = notes.get(d["id"]) or DEFAULT_REASON.get(d.get("answer_kind", "choice"), "")
        rejected = f"{joined(d.get('rejected', []))} — {reason}" if d.get("rejected") else f"{NONE} — {reason}"
        who = (f"회사 자료 {d.get('company_ref', NONE)}" if d.get("answered_by") == "company"
               else f"발주사 · 질문 카드 {d.get('question_id', NONE)}" + (f" · 확인 {cp2[-1]}" if cp2 else ""))
        rows.append([d["id"], d.get("topic", ""), d.get("chosen", ""), rejected, who])
    return rows


def done_criteria_blocks(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """When the planning is really done: must-pass tests, assumptions to settle, open items, how goals are measured."""
    reqs, decisions = source.get("requirements", []), source.get("decisions", [])
    must = [[t["id"], t.get("title", ""), t.get("expected", "")] for t in source.get("tests", []) if t.get("priority") == "상"]
    assumed = [[r["id"], r.get("title", ""), r.get("statement", "")] for r in reqs if r.get("status") == "가정"]
    assumed += [[d["id"], d.get("topic", ""), d.get("chosen", "")] for d in decisions if d.get("status") == "가정"]
    open_ = [[r["id"], r.get("title", ""), r.get("statement", "")] for r in reqs if r.get("status") in OPEN_STATUSES]
    open_ += [[o["id"], o.get("title", ""), o.get("reason", "")] for o in source.get("open_items", [])]
    goals = [[g["goal"], g["criterion"], g["status"]] for g in first(source, "brd").get("goals", [])]
    return [
        paragraph("반드시 통과해야 하는 테스트 — 중요도 「상」"), table(["TC ID", "이름", "기대 결과"], must),
        paragraph(f"개발 전에 확정할 가정 {len(assumed)}건 — 기본값으로 채운 것"), table(["ID", "이름", "내용"], assumed),
        paragraph(f"아직 정하지 않은 것(미결) {len(open_)}건"), table(["ID", "이름", "내용"], open_),
        paragraph("성공 기준을 재는 법 — BRD 목표"), table(["목표", "성공 기준", "상태"], goals),
    ]


def build_prd(source: Mapping[str, Any], ctx: DocContext) -> dict[str, Any]:
    reqs = source.get("requirements", [])
    by_category, by_status = Counter(r.get("category") for r in reqs), Counter(r.get("status") for r in reqs)
    statuses = [*REQ_STATUSES, "미확인"]
    sections = [
        section("totals", "1. 요구사항 총괄표", [
            table(["분류", "개수"], [[f"{c} {CATEGORY_NAMES[c]}", by_category.get(c, 0)] for c in CATEGORIES]),
            table(["상태", "개수"], [[s, by_status.get(s, 0)] for s in statuses]),
        ]),
        section("requirements", "2. 요구사항 상세 표", [table(REQ_COLUMNS, [requirement_row(r) for r in reqs])]),
        section("decisions", "3. 결정과 검토한 대안", [table(["결정", "주제", "채택", "기각안과 이유", "누가 답했나"],
                                                       decision_rows(source))]),
        section("open_questions", "4. 열린 질문", [table(["ID", "질문", "누가 답하나"], open_rows(source, first(source, "brd")))]),
        section("done_criteria", "5. 완료 조건", done_criteria_blocks(source)),
        history_section(source, "6", "pm", ctx),
    ]
    return make_doc("prd", "PRD — 무엇을 만드나", "pm", source, ctx, first(source, "prd").get("summary", []), sections)
