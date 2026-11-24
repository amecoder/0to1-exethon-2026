from __future__ import annotations
"""제안요약.md: one page for a decision maker, built from the shared source by code (no model call, no new facts).

Problem, scope (with what the client cut when narrowing the screens), size (a rule over counts — requirements,
screens, and the outside services the product has to connect to), expected effect (BRD goals), risks, and what
still needs a decision: blanks left in the text, goals without a number, and defaults the team filled in.
The reader is the business owner: fixed text is in plain polite Korean (합니다체), terms are explained once, and
reference numbers (REQ-, DEC-, TC- …) are taken out of the sentences and listed once in an appendix at the end.
"""

from collections.abc import Mapping
from typing import Any

from app.open_points import blanks, integrations, open_goals
from app.owner_text import excerpt, strip_refs
from app.quality import annotate_terms
from app.scope_view import MARK, scope_view


def _first(source: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    items = source.get(kind) or [{}]
    return items[0] if isinstance(items[0], Mapping) else {}


def size_class(requirements: int, screens: int, systems: int) -> tuple[str, str]:
    """작음 / 보통 / 큼 by a fixed rule over counts — never a made-up schedule or price."""
    basis = f"요구사항 {requirements}건 · 화면 {screens}개 · 연계 시스템 {systems}개"
    if requirements >= 20 or screens >= 8 or systems >= 3:
        return "큼", basis
    if requirements <= 6 and screens <= 3 and systems == 0:
        return "작음", basis
    return "보통", basis


class Refs:
    """Collects the reference numbers taken out of the owner's sentences, for the appendix."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str]] = []

    def clean(self, text: Any) -> str:
        plain, found = strip_refs(str(text or ""))
        self.rows += [(excerpt(plain), ref) for ref in found]
        return plain

    def note(self, what: str, ids: str) -> None:
        self.rows.append((excerpt(what), ids))


def _problem_lines(view: Mapping[str, Any], refs: Refs) -> list[str]:
    """The BRD summary (written for the owner); the raw problem statement only when there is no summary yet."""
    ps, brd = _first(view, "problem_statement"), _first(view, "brd")
    summary = [f"- {refs.clean(s)}" for s in brd.get("summary", [])]
    if summary:
        return summary
    return [f"- 누가: {refs.clean(ps.get('who'))}", f"- 무엇이 불편한가: {refs.clean(ps.get('pain'))}",
            f"- 성공 기준: {refs.clean(ps.get('done'))}"]


def _scope_lines(view: Mapping[str, Any], refs: Refs) -> list[str]:
    scope = _first(view, "scope")
    out = ["## 범위", "", "이번에 하는 것", *[f"- {refs.clean(c.get('text'))}" for c in scope.get("in", [])], "",
           "이번에 하지 않는 것", *[f"- {refs.clean(c.get('text'))}" for c in scope.get("out", [])], ""]
    cut = view.get("out_of_scope") or {}
    names = [f"화면: {s.get('title') or s['id']}" for s in cut.get("screens", [])]
    names += [f"기능: {r.get('title') or r['id']}" for r in cut.get("requirements", [])]
    for r in cut.get("requirements", []):
        refs.note(f"뺀 기능: {r.get('title', '')}", r["id"] + MARK)
    if names:
        out += ["화면 범위를 줄이면서 이번에 뺀 것 (다음 버전 후보)", *[f"- {name}" for name in names], ""]
    fits = scope.get("systems", [])
    if fits:
        out += ["이미 있는 시스템 활용", *[f"- {f['name']} · {f['fit']}: {refs.clean(f.get('what'))}" for f in fits], ""]
    return out


def _size_lines(view: Mapping[str, Any], refs: Refs) -> list[str]:
    listed = {f["system_ref"] for f in _first(view, "scope").get("systems", [])}
    outside = integrations(view)
    label, basis = size_class(len(view.get("requirements", [])), len(view.get("screens", [])), len(listed) + len(outside))
    out = ["## 규모", "", f"- 규모: **{label}** ({basis})",
           "- 판단 기준: 요구사항 20건, 화면 8개, 연계 시스템 3개 가운데 하나라도 넘으면 「큼」입니다. "
           "요구사항 6건 이하, 화면 3개 이하이면서 연계 시스템이 없으면 「작음」이고, 그 사이는 「보통」입니다.",
           "- 연계 시스템은 이 제품이 직접 만들지 않고 연결해서 쓰는 밖의 서비스와 이미 있는 시스템을 합친 수입니다."]
    out += [f"- 밖의 서비스 {len(outside)}개: 어느 회사 것을 쓸지 정하고 계약해야 합니다."] if outside else []
    out += [f"  - {s['name']}: {s['what']}" for s in outside]
    for s in outside:
        refs.note(f"밖의 서비스: {s['name']}", ", ".join(s["refs"]))
    return [*out, "- 기간과 비용은 이 규모와 작업 지시서(AGENTS.md)의 작업 수를 보고 개발팀이 정합니다. 이 문서는 숫자를 추정하지 않습니다.", ""]


def _decision_lines(view: Mapping[str, Any], refs: Refs) -> list[str]:
    """What the owner still has to answer: blanks, goals without a number, open items, and team defaults."""
    reqs = view.get("requirements", [])
    blank, goals = blanks(view), open_goals(view)
    opened = [(r.get("title", ""), f"{r['id']} · {r['status']}") for r in reqs if r.get("status") in ("미결", "미확인")]
    opened += [(f"{o.get('title', '')}: {o.get('reason', '')}", str(o.get("id", ""))) for o in view.get("open_items", [])]
    assumed = [(r.get("title", ""), r["id"]) for r in reqs if r.get("status") == "가정"]
    out = ["## 결정이 필요한 것", ""]
    if not (blank or goals or opened or assumed):
        return [*out, "- 없음", ""]
    out += ["아직 정해지지 않아 발주사가 답해야 하는 것입니다. 답이 없으면 개발자가 빈 곳을 짐작으로 채우게 됩니다.", ""]

    def listed(title: str, items: list[tuple[str, str]], intro: str = "") -> list[str]:
        for what, ids in items:
            refs.note(what, ids)
        return [f"### {title}", "", *([intro, ""] if intro else []), *[f"- {refs.clean(what)}" for what, _ in items], ""]

    if opened:
        out += listed(f"아직 정하지 않은 요구사항 {len(opened)}건", opened)
    if blank:
        out += listed(f"문서에 빈칸으로 남은 곳 {len(blank)}곳", [(f"{b['title']}: {b['text']}", b["id"]) for b in blank])
    if goals:
        out += [f"### 숫자 기준이 없는 목표 {len(goals)}개", "", *[f"- {refs.clean(goal)}" for goal in goals], ""]
    if assumed:
        out += listed(f"팀이 기본값으로 채운 것(가정) {len(assumed)}건", assumed,
                      "발주사가 확인하지 않아 팀이 흔한 방식으로 채웠습니다. 틀린 것이 있으면 알려 주세요.")
    return out


def _appendix(refs: Refs) -> list[str]:
    if not refs.rows:
        return []
    rows = list(dict.fromkeys(refs.rows))
    return ["## 부록: 근거 번호 (개발팀이 찾아볼 때)", "",
            "본문에서 뺀 근거 번호입니다. 번호는 PRD와 source.json에서 찾을 수 있습니다.", "",
            "| 본문의 문장 | 근거 번호 |", "|---|---|", *[f"| {what.replace('|', '/')} | {ids} |" for what, ids in rows], ""]


def proposal_md(source: Mapping[str, Any]) -> str:
    view = scope_view(source)
    brd, refs = _first(view, "brd"), Refs()
    out = ["# 제안 요약", "", "> 0to1(영일)이 확정한 공유 원본에서 자동으로 만든 한 장 요약입니다. 자세한 내용은 BRD·PRD 문서에 있습니다.", "",
           "## 문제", "", *_problem_lines(view, refs), "", *_scope_lines(view, refs), *_size_lines(view, refs), "## 기대 효과", ""]
    goals = brd.get("goals", [])
    out += [f"- {refs.clean(g.get('goal'))} — 기준: {refs.clean(g.get('criterion'))} ({g.get('status', '')})"
            for g in goals] or ["- (BRD 목표 없음)"]
    out += ["", "## 위험", ""]
    out += [f"- {refs.clean(r.get('risk'))} → {refs.clean(r.get('response'))}" for r in brd.get("risks", [])] or ["- (BRD 위험 없음)"]
    out += ["", *_decision_lines(view, refs), *_appendix(refs)]
    return "\n".join(annotate_terms(out))
