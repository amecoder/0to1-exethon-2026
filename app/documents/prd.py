from __future__ import annotations
"""PRD — what we build (format spec section 2). Decisions and alternatives come from DEC- records (C3)."""

from collections import Counter
from collections.abc import Mapping
from typing import Any

from app.documents.common import (
    NONE, OPEN_INTRO_DEV, DocContext, cut_of, first, history_section, joined, make_doc, paragraph, section, table,
)
from app.documents.brd import OPEN_STATUSES, open_rows
from app.open_points import blanks, open_goals
from app.schemas import CATEGORIES, REQ_STATUSES

CATEGORY_NAMES = {"SFR": "기능", "PER": "성능", "SER": "보안", "DAR": "데이터", "INR": "인터페이스", "COR": "제약"}
REQ_COLUMNS = ["ID", "분류", "이름", "설명", "인수 조건", "예외", "중요도", "상태", "근거", "관련 요구사항", "관련 화면·테스트"]
DEFAULT_REASON = {"choice": "발주사가 다른 답을 골랐다", "unknown": "발주사가 '잘 모르겠어요' → 기본값으로 채움(가정)",
                  "free_text": "발주사가 직접 입력했다"}


def acceptance_text(req: Mapping[str, Any]) -> str:
    a = req.get("acceptance") or {}
    return f"조건: {a.get('given', '')} / 동작: {a.get('when', '')} / 결과: {a.get('then', '')}"


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
    open_ += [[b["id"], b["title"], b["text"]] for b in blanks(source)]
    open_ += [[NONE, goal, "숫자로 잴 기준이 없는 목표"] for goal in open_goals(source)]
    goals = [[g["goal"], g["criterion"], g["status"]] for g in first(source, "brd").get("goals", [])]
    return [
        paragraph("반드시 통과해야 하는 테스트 — 중요도 「상」"), table(["TC ID", "이름", "기대 결과"], must),
        paragraph(f"개발 전에 확정할 가정 {len(assumed)}건 — 기본값으로 채운 것"), table(["ID", "이름", "내용"], assumed),
        paragraph(f"아직 정하지 않은 것(미결) {len(open_)}곳 — 상태가 미결인 항목, 본문에 미정·빈칸·확인 필요로 남은 곳, 숫자 기준이 없는 목표"),
        table(["ID", "이름", "내용"], open_),
        paragraph("성공 기준을 재는 법 — BRD 목표"), table(["목표", "성공 기준", "상태"], goals),
    ]


def cut_section(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """「이번 범위에서 뺀 것」: the one place that lists what the scope decision took out."""
    cut = cut_of(source)
    if not any(cut.values()):
        return []
    decision = (source.get("out_of_scope") or {}).get("decision") or NONE
    blocks = [paragraph(f"발주사가 화면 범위를 줄이면서({decision}) 이번 버전에서 뺀 것이다. 만들지 않지만 지우지 않고 여기에 한 번 적는다. "
                        "다른 곳에서 이 ID를 말할 때는 「(범위 밖)」을 붙였다."),
              table(["ID", "이름", "설명", "뺀 이유"],
                    [[r["id"], r.get("title", ""), r.get("statement", ""), "보여 주던 화면이 모두 빠짐"]
                     for r in cut["requirements"]]
                    + [[s["id"], s.get("title", ""), "화면", "먼저 만들 화면으로 고르지 않음"] for s in cut["screens"]])]
    return [section("out_of_scope", "2-1. 이번 범위에서 뺀 것", blocks)]


def build_prd(source: Mapping[str, Any], ctx: DocContext) -> dict[str, Any]:
    reqs = source.get("requirements", [])
    by_category, by_status = Counter(r.get("category") for r in reqs), Counter(r.get("status") for r in reqs)
    statuses = [*REQ_STATUSES, "미확인"]
    sections = [
        section("totals", "1. 요구사항 총괄표", [
            paragraph("요구사항을 분류와 상태로 센 표다. 분류 칸에는 영문 약어와 그 뜻을 함께 적었"
                      + (f"고, 이번 범위에서 뺀 요구사항 {len(cut_of(source)['requirements'])}건은 세지 않았다."
                         if cut_of(source)["requirements"] else "다.")),
            table(["분류", "개수"], [[f"{c} {CATEGORY_NAMES[c]}", by_category.get(c, 0)] for c in CATEGORIES]),
            table(["상태", "개수"], [[s, by_status.get(s, 0)] for s in statuses]),
        ]),
        section("requirements", "2. 요구사항 상세 표", [
            paragraph("요구사항마다 한 줄이다. 인수 조건(다 됐다고 볼 기준)은 「조건(어떤 상황에서) / 동작(무엇을 하면) / "
                      "결과(어떻게 된다)」 순서로 적었다."),
            table(REQ_COLUMNS, [requirement_row(r) for r in reqs])]),
        *cut_section(source),
        section("decisions", "3. 결정과 검토한 대안", [
            paragraph("질문마다 고른 답과 고르지 않은 답, 그 이유를 적었다. 「잘 모르겠어요」로 답한 질문은 팀이 기본값으로 채웠다."),
            table(["결정", "주제", "채택", "기각안과 이유", "누가 답했나"], decision_rows(source))]),
        section("open_questions", "4. 열린 질문", [
            paragraph(OPEN_INTRO_DEV), table(["ID", "질문", "누가 답하나"], open_rows(source, first(source, "brd")))]),
        section("done_criteria", "5. 완료 조건", done_criteria_blocks(source)),
        history_section(source, "6", "pm", ctx, polite=False),
    ]
    return make_doc("prd", "PRD — 무엇을 만드나", "pm", source, ctx, first(source, "prd").get("summary", []), sections)
