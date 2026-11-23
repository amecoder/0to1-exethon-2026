from __future__ import annotations
"""Deterministic checks shown on confirmation screens.

- answer consistency (user-approved addition): a requirement citing DEC-xx must contain the chosen
  answer's text and must not contain a rejected option's text → `block` (cannot be waived; reject instead)
- coverage (FR-10): REQ without TC, REQ without SCR and no reason, open items/미결 → `waivable` at CP3
- unresolved conflict findings (format spec 5, consistent) → `waivable` at CP3
- an approved change (CP5) being reworked: an affected requirement that still holds the superseded answer and
  not the new key phrase → `waivable` at CP3 (FR-21)
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.korean import josa
from app.flow_chart import flow_warnings
from app.prototype import prototype_warnings
from app.quality import client_jargon, quality_warnings
from app.waiver_help import help_for

_NOT_KEY = re.compile(r"[^0-9a-z가-힣]")
SEVERITIES = ("block", "waivable", "info")


def normalize_key(text: str) -> str:
    return _NOT_KEY.sub("", text.lower())


def warning(code: str, severity: str, target: str, doc: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"id": f"{code}:{target}", "code": code, "severity": severity, "target": target, "doc": doc,
            "message": message, **extra}


def requirement_text(req: Mapping[str, Any]) -> str:
    acceptance = req.get("acceptance") or {}
    parts = [req.get("title", ""), req.get("statement", ""), *(acceptance.get(k, "") for k in ("given", "when", "then"))]
    return " ".join(str(p) for p in parts)


def answer_decisions(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Decisions that answer question cards (G8 scope, CP1 build-or-buy and superseded ones are not compared)."""
    return [d for d in source.get("decisions", [])
            if d.get("kind") not in ("scope", "build_or_buy") and not d.get("superseded_by")]


def _citing(source: Mapping[str, Any], decision_id: str) -> list[dict[str, Any]]:
    return [r for r in source.get("requirements", []) if decision_id in r.get("decision_refs", [])]


def check_pair(decision: Mapping[str, Any], req: Mapping[str, Any]) -> dict[str, Any] | None:
    """Returns a block warning when `req` contradicts `decision`, else None."""
    text = normalize_key(requirement_text(req))
    chosen = normalize_key(str(decision.get("chosen", "")))
    # free text and the placement answer (which app) are not sentences a requirement repeats
    positive = decision.get("answer_kind", "choice") != "free_text" and decision.get("kind") != "placement" and bool(chosen)
    missing = positive and chosen not in text
    remainder = text.replace(chosen, " ") if chosen else text
    rejected = [o for o in decision.get("rejected", []) if normalize_key(o) and normalize_key(o) in remainder]
    if not missing and not rejected:
        return None
    detail = []
    if missing:
        detail.append(f"고른 답 「{decision['chosen']}」이 없습니다")
    if rejected:
        detail.append(f"고르지 않은 답 「{'」·「'.join(rejected)}」이 들어 있습니다")
    return warning("answer.inconsistent", "block", req["id"], "prd",
                   f"{josa(decision['id'], '와/과')} {josa(req['id'], '이/가')} 다릅니다: {' / '.join(detail)}",
                   decision_id=decision["id"], missing_chosen=missing, rejected_found=rejected)


def consistency_violations(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for decision in answer_decisions(source):
        for req in _citing(source, decision["id"]):
            found = check_pair(decision, req)
            if found is not None:
                out.append({**found, "id": f"answer.inconsistent:{req['id']}:{decision['id']}"})
    return out


def unreflected_decisions(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [warning("answer.unreflected", "info", d["id"], "prd", f"{d['id']} 답을 반영한 요구사항이 없습니다")
            for d in answer_decisions(source) if not _citing(source, d["id"])]


def answer_table(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """CP2/CP3 table: 내가 고른 답 → 반영된 요구사항."""
    questions = {q["id"]: q for q in source.get("questions", [])}
    rows = []
    for d in answer_decisions(source):
        reqs = _citing(source, d["id"])
        rows.append({
            "question_id": d.get("question_id"), "question": questions.get(d.get("question_id"), {}).get("question", d.get("topic", "")),
            "answer": d.get("chosen"), "answer_kind": d.get("answer_kind", "choice"), "status": d.get("status"),
            "decision_id": d["id"], "answered_by": d.get("answered_by", "client"), "company_ref": d.get("company_ref"),
            "requirements": [{k: r.get(k) for k in ("id", "title", "statement", "status")} for r in reqs],
            "consistent": all(check_pair(d, r) is None for r in reqs),
        })
    return rows


def coverage_warnings(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    ops = [o for p in source.get("test_plan", []) for o in p.get("ops_checks", [])]
    tested = {ref for t in [*source.get("tests", []), *ops] for ref in t.get("requirement_refs", [])}
    drawn = {ref for s in source.get("screens", []) for ref in s.get("requirement_refs", [])}
    out = []
    for r in source.get("requirements", []):
        if r["id"] not in tested:
            out.append(warning("coverage.no_tc", "waivable", r["id"], "tests", f"{josa(r['id'], '을/를')} 확인할 테스트 케이스가 없습니다"))
        if r["id"] not in drawn and not str(r.get("screen_exemption") or "").strip():
            out.append(warning("coverage.no_scr", "waivable", r["id"], "screens",
                               f"{r['id']} 에 연결된 화면이 없고, 화면이 없는 이유도 없습니다"))
        if r.get("status") in ("미결", "미확인"):
            out.append(warning("coverage.open", "waivable", r["id"], "prd", f"{josa(r['id'], '이/가')} 아직 {r['status']} 상태입니다"))
    for item in source.get("open_items", []):
        out.append(warning("coverage.open", "waivable", item["id"], "prd", f"{item['id']} 미결: {item.get('title', '')}"))
    return out


def unresolved_conflicts(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    answered = {ref for q in source.get("questions", []) if q.get("status") == "answered"
                for ref in q.get("finding_refs", [])}
    return [warning("consistency.conflict", "waivable", f["id"], "prd", f"풀리지 않은 충돌 지적 {f['id']}: {f.get('note', '')}")
            for f in source.get("findings", []) if f.get("type") == "conflict" and f["id"] not in answered]


def change_text(req: Mapping[str, Any]) -> str:
    """What a change revision rewrites: the statement and the acceptance (titles stay short labels)."""
    acceptance = req.get("acceptance") or {}
    return " ".join(str(p) for p in [req.get("statement", ""), *(acceptance.get(k, "") for k in ("given", "when", "then"))])


def stale_requirements(reqs: Sequence[Mapping[str, Any]], before_keys: Sequence[str], after_key: str) -> list[str]:
    """IDs whose text still has a superseded phrase while the new key phrase is missing."""
    before = [k for k in (normalize_key(b) for b in before_keys) if k]
    after = normalize_key(after_key)
    out = []
    for req in reqs:
        text = normalize_key(change_text(req))
        if any(k in text for k in before) and not (after and after in text):
            out.append(str(req["id"]))
    return out


def change_warnings(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    recheck = source.get("meta", {}).get("recheck") or {}
    item = next((c for c in source.get("changes", []) if c.get("id") == recheck.get("change_id")), None)
    revision = (item or {}).get("revision")
    if not revision:
        return []
    scope = set(revision.get("scope", []))
    reqs = [r for r in source.get("requirements", []) if r["id"] in scope]
    keys = revision.get("before_keys", [])
    return [warning("change.stale", "waivable", rid, "prd",
                    f"{josa(rid, '이/가')} {item['id']} 전 내용(「{'」·「'.join(keys)}」)을 아직 담고 있습니다")
            for rid in stale_requirements(reqs, keys, revision.get("after_key", ""))]


def cp_warnings(source: Mapping[str, Any], cp: str, docs: Mapping[str, Mapping[str, Any]] | None = None
                ) -> list[dict[str, Any]]:
    out = consistency_violations(source) + unreflected_decisions(source)
    if cp == "CP3":
        out += coverage_warnings(source) + unresolved_conflicts(source) + change_warnings(source)
        out += quality_warnings(source, docs or {}) + flow_warnings(source)
    if cp == "CP4":
        out += prototype_warnings(source)
    return out


def review(source: Mapping[str, Any], cp: str, docs: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    warnings = cp_warnings(source, cp, docs)
    by = {s: [w for w in warnings if w["severity"] == s] for s in SEVERITIES}
    summary = review_summary(source, cp)
    if client_jargon(summary):
        by["info"].append(warning("quality.client_jargon", "info", cp, "client", f"확인 요약에 전문 용어: {', '.join(client_jargon(summary))}"))
    # 11-22: a plain explanation and a reason filled in for each 빈칸 (app/waiver_help.py)
    waivable = [{**w, **help_for(w, source)} for w in by["waivable"]]
    return {"cp": cp, "summary": summary, "answers": answer_table(source), "blocking": by["block"],
            "waivable": waivable, "notices": by["info"], "can_approve": not by["block"] and not by["waivable"],
            # FR-20: the consumer's opinions (info only — never part of can_approve)
            "consumer_feedback": [f for f in source.get("feedback", []) if f.get("cp") == cp]}


def review_summary(source: Mapping[str, Any], cp: str) -> str:
    screens, tests = len(source.get("screens", [])), len(source.get("tests", []))
    if cp == "CP2":
        return f"요구사항 {len(source.get('requirements', []))}건과 고른 답 {len(source.get('decisions', []))}개를 확인해 주세요."
    if cp == "CP4":
        return f"프로토타입(화면 {screens}개)을 미리보기로 열어 보고, 시험 항목 {tests}개의 화면 대조표를 확인해 주세요."
    return f"문서 4종(화면 {screens}개, 시험 항목 {tests}개)을 확인해 주세요."


def approval_problems(source: Mapping[str, Any], cp: str, waivers: Mapping[str, str]) -> list[str]:
    """Why approval must be refused: blocking warnings, or waivable ones without a one-line reason."""
    problems = []
    for w in cp_warnings(source, cp):
        reason = str(waivers.get(w["id"], "")).strip()
        if w["severity"] == "block":
            problems.append(w["message"])
        elif w["severity"] == "waivable" and (not reason or "\n" in reason):
            problems.append(f"{w['message']} — 해소하거나 사유를 한 줄로 적어 주세요")
    return problems
