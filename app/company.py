from __future__ import annotations
"""회사 작업 공간: what the client's company already settled, given to every new project of that company.

At S1 the company's notes (용어·사내 규칙·이미 정한 것, one per line) and the confirmed answers from its other
projects are copied into the project as `company` items (CMP-01 …). A copy, not a live link: editing the company
material later never changes a project that already started.

S3 uses them: a QA finding the company material already answers is not turned into a question card. The
coordinator names it in `settled` (finding · CMP item · the answer), and code keeps only entries that point at a
real finding and a real CMP item — those become decisions (kind company, 확정) instead of open items.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.config import LinerKeyMissingError, read_env
from app.limits import LimitReachedError
from app.liner import LinerAPIError, LinerConfigError
from app.naming import clean_name
from app.schemas import QUESTION_CARDS, STR, array, obj
from app.guardrails import mask_sensitive
from app.stage_common import StageContext
from app.systems import LINE_MAX, MAX_SERVICES

NOTE = "note"
COMPANY_DECISION = "decision"
NOTES_MAX = 6000
NAME_MAX = 60
MAX_ITEMS = 40  # 제안: enough for a company's rules and a few projects' answers, small enough for one prompt
DECIDED_BY = "회사 자료"

# A service the company built with 0to1: a project of the company confirmed at CP4. Its features are the
# requirements that were settled (확정) or filled with a default (가정) — what was handed over to be built.
SERVICE_NOTE = "0to1로 만든 서비스"
FEATURE_STATUSES = ("확정", "가정")
QUERY_MAX = 2000

_BULLET = re.compile(r"^(?:[-*•]|\d+[.)])\s*")
_NOT_KEY = re.compile(r"[^0-9a-z가-힣]")

# A settled answer must share wording with the company item it cites: the share of the answer's letter pairs
# found in the item. 0.20 kept 27/29 real (answer, cited item) pairs and rejected 317/348 mismatched ones
# in the 11-20 runs (scratchpad/settled_bench.py, design doc 6-4).
RELATED_MIN = 0.20

TASK_CARDS_COMPANY = (
    " 공유 원본의 company 는 발주사 회사가 이미 정해 둔 것이다(note: 회사 공통 자료, decision: 같은 회사의 지난 프로젝트에서 "
    "발주사가 확정한 답). 지적 중 company 항목으로 답이 정해지는 것은 카드로 만들지 말고 settled 에 지적 ID(finding_ref), "
    "그 company 항목 ID(company_ref), 그 항목에 따른 답(answer)을 적어라. 이번 요청과 주제가 다른 항목으로는 정하지 않는다 — "
    "애매하면 카드로 만든다. 해당하는 지적이 없으면 settled 는 빈 배열이다. company 의 decision 항목은 오래된 "
    "프로젝트부터 적혀 있다. decision 항목끼리 같은 일을 서로 다르게 정했으면 그것으로 정하지 말고 카드로 묻되, 뒤에 적힌"
    "(더 최근) 답을 default_option 으로 한다."
)
TASK_PM_COMPANY = (
    " decisions 중 answered_by 가 company 인 것은 회사 자료로 정한 답이다. 같은 일을 발주사가 직접 고른 답(answered_by "
    "client)이 다르게 정했으면 발주사 답을 따르고, 그 company 결정 ID 는 decision_refs 에 적지 않는다."
)
QUESTION_CARDS_COMPANY = {
    **QUESTION_CARDS,
    "properties": {**QUESTION_CARDS["properties"],
                   "settled": array(obj(finding_ref=STR, company_ref=STR, answer=STR))},
    "required": [*QUESTION_CARDS["required"], "settled"],
}


def company_enabled(env_file: Any = None) -> bool:
    """The company workspace runs only with EXETHON_COMPANY=on. Off (the default, so the contest submission runs
    실제 · 시연 as before): no company panel and nothing of a company copied into a project."""
    return (read_env("EXETHON_COMPANY", env_file) or "off").lower() in ("on", "1", "true", "yes")


def note_lines(notes: str) -> list[str]:
    """One note per non-empty line; '#' lines are headings and list bullets are dropped."""
    lines = []
    for line in notes.splitlines():
        line = _BULLET.sub("", line.strip()).strip()
        if line and not line.startswith("#"):
            lines.append(line[:LINE_MAX])
    return lines


def company_items(profile: Mapping[str, Any], past: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Notes first, then the past decisions (oldest project first), numbered CMP-01 … (at most MAX_ITEMS).
    Over the cap notes come first (only the first MAX_ITEMS of them if there are more) and the newest decisions
    fill what is left: a later project's answer is the current one."""
    rows: list[dict[str, Any]] = [{"kind": NOTE, "text": line} for line in note_lines(str(profile.get("notes", "")))]
    room = max(MAX_ITEMS - len(rows), 0)
    for d in list(past)[-room:] if room else []:
        text = f"{d.get('topic', '')} → {d.get('chosen', '')}"[:LINE_MAX]
        rows.append({"kind": COMPANY_DECISION, "text": text, "project": str(d.get("project", "")),
                     "decision_id": str(d.get("decision_id", ""))})
    return [{"id": f"CMP-{n:02d}", **row} for n, row in enumerate(rows[:MAX_ITEMS], start=1)]


def _pairs(text: str) -> set[str]:
    key = _NOT_KEY.sub("", text.lower())
    return {key[i:i + 2] for i in range(len(key) - 1)}


def relatedness(answer: str, item_text: str) -> float:
    pairs = _pairs(answer)
    return len(pairs & _pairs(item_text)) / len(pairs) if pairs else 0.0


def same_answer(a: str, b: str) -> bool:
    """The same answer: equal letters and digits once spacing and punctuation are dropped. Not a similarity score —
    「환불 가능」 and 「환불 불가능」 share most letter pairs yet say the opposite (review 11-21)."""
    return bool(_NOT_KEY.sub("", a.lower())) and _NOT_KEY.sub("", a.lower()) == _NOT_KEY.sub("", b.lower())


def settled_candidates(ctx: StageContext, findings: Sequence[Mapping[str, Any]], raw: Any) -> dict[str, tuple[str, str]]:
    """The settled entries that name a real finding and a real company item and whose answer shares wording with
    that item (RELATED_MIN): {finding id: (company item id, answer)}. Nothing is written yet — a finding the round
    also asks on a card is the client's to answer (D2: the client's own answer wins)."""
    known = {f["id"] for f in findings}
    company = {c["id"]: c for c in ctx.ws.items("company")}
    found: dict[str, tuple[str, str]] = {}
    unrelated: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, Mapping):
            continue
        ref, cmp_ref, answer = (str(item.get(k, "")).strip() for k in ("finding_ref", "company_ref", "answer"))
        if ref not in known or cmp_ref not in company or not answer or ref in found:
            continue
        if relatedness(answer, str(company[cmp_ref].get("text", ""))) < RELATED_MIN:
            unrelated.append(f"{ref} — {cmp_ref}: 「{answer[:60]}」")
            continue
        found[ref] = (cmp_ref, answer)
    if unrelated:  # left as open items by keep_uncarded: the client still sees them
        ctx.ws.emit("check_result", "coordinator", {
            "check": "company_settled", "outcome": "flagged", "items": [],
            "details": [f"회사 자료와 겹치는 말이 없어 정한 것으로 받지 않음: {u}" for u in unrelated]})
    return found


def write_settled(ctx: StageContext, findings: Sequence[Mapping[str, Any]],
                  candidates: Mapping[str, tuple[str, str]]) -> set[str]:
    """Record each settled finding as a company decision (kind company, 확정). The same company item settling the
    same answer again (an S3 rework numbers its findings anew) joins the decision already there. Returns the IDs."""
    known = {f["id"]: f for f in findings}
    earlier = {d["id"] for d in ctx.ws.items("decisions")}  # only an earlier round's decision is joined
    done: set[str] = set()
    for ref, (cmp_ref, answer) in candidates.items():
        finding = known[ref]
        same = next((d for d in ctx.ws.items("decisions") if d["id"] in earlier and d.get("kind") == "company"
                     and not d.get("superseded_by")
                     and d.get("company_ref") == cmp_ref and same_answer(answer, str(d.get("chosen", "")))), None)
        if same is not None:
            ctx.ws.write("coordinator", "decisions", {
                **same, "finding_refs": list(dict.fromkeys([*same.get("finding_refs", []), ref])),
                "requirement_refs": list(dict.fromkeys([*same.get("requirement_refs", []), *finding["requirement_ids"]])),
                "source_refs": list(dict.fromkeys([*same.get("source_refs", []), *finding["source_refs"]]))})
        else:
            ctx.ws.write("coordinator", "decisions", {
                "id": ctx.ws.next_id("decisions", "DEC"), "kind": "company", "topic": finding["note"] or ref,
                "chosen": answer, "answer_kind": "free_text", "status": "확정", "answered_by": "company",
                "who": DECIDED_BY, "company_ref": cmp_ref, "finding_refs": [ref],
                "requirement_refs": list(finding["requirement_ids"]), "source_refs": list(finding["source_refs"])})
        done.add(ref)
    return done


def _name(service: Mapping[str, Any]) -> str:
    return clean_name(str(service.get("name", "")))


def line_features(service: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The features that fit on the service's line, in the given order, until LINE_MAX is reached."""
    size, kept = len(f"{_name(service)}: {SERVICE_NOTE} · 기능"), []
    for n, feature in enumerate(service.get("features", [])):
        size += len(" " if n == 0 else ", ") + len(str(feature.get("title", "")))
        if size > LINE_MAX:
            break
        kept.append(feature)
    return kept


def service_line(service: Mapping[str, Any]) -> str:
    """「이름: 0to1로 만든 서비스 · 기능 A, B, …」 — how the service reads in the systems list."""
    return f"{_name(service)}: {SERVICE_NOTE} · 기능 " + ", ".join(str(f.get("title", ""))
                                                              for f in line_features(service)).rstrip()


def masked_service(service: Mapping[str, Any]) -> dict[str, Any]:
    """G3 mask: the service name and feature titles as they would be stored."""
    return {**service, "name": mask_sensitive(str(service.get("name", ""))),
            "features": [{**f, "title": mask_sensitive(str(f.get("title", "")))} for f in service.get("features", [])]}


def service_items(services: Sequence[Mapping[str, Any]], start: int) -> list[dict[str, Any]]:
    """SYS items made straight from the services (D4: never re-read from a joined text that a cap could cut), numbered
    after the client's list. Feature ids carry the SYS id (SYS-03/REQ-02) so they never read as this project's REQ."""
    items = []
    for n, service in enumerate(services, start=start):
        sid, line = f"SYS-{n:02d}", service_line(service)
        feats = [{"id": f"{sid}/{f['id']}", "title": str(f.get("title", ""))} for f in line_features(service) if f.get("id")]
        item = {"id": sid, "name": _name(service), "about": line.split(": ", 1)[1], "raw": line}
        items.append({**item, "features": feats} if feats else item)
    return items


def report_systems_list(ws: Any, listed: int, kept: int, dropped: Sequence[str],
                        services: Sequence[Mapping[str, Any]]) -> None:
    """D4: say what the systems list left out — client lines over MAX_SYSTEMS, services over MAX_SERVICES, features
    that did not fit on a service's line. Flagged when a system or a service was left out; nothing when all fit."""
    details, flagged = [], False
    if listed > kept:
        details.append(f"우리 시스템 목록 {listed}줄 중 {kept}줄만 담았어요")
        flagged = True
    if dropped:
        details.append(f"0to1로 만든 서비스 {len(dropped) + MAX_SERVICES}개 중 최근 {MAX_SERVICES}개만 담았어요 "
                       f"(빠짐: {', '.join(dropped)})")
        flagged = True
    for service in services:
        total, fit = len(service.get("features", [])), len(line_features(service))
        if fit < total:
            details.append(f"「{_name(service)}」 기능 {total}개 중 {fit}개만 한 줄에 담았어요")
    if details:
        ws.emit("check_result", "coordinator", {"check": "systems_list", "outcome": "flagged" if flagged else "passed",
                                                "items": [], "details": details})


def ranked_service(ctx: StageContext, request: str, service: Mapping[str, Any]) -> dict[str, Any]:
    """When not every feature fits on the line, Liner Rerank puts the ones closest to the request first.
    Fail-open: on an error the features keep their order and a note is left."""
    feats = list(service.get("features", []))
    full = f"{_name(service)}: {SERVICE_NOTE} · 기능 " + ", ".join(str(f.get("title", "")) for f in feats)
    if len(full) <= LINE_MAX:
        return dict(service)
    try:
        body = ctx.runner.rerank("pm", request[:QUERY_MAX], [str(f.get("title", "")) for f in feats], len(feats))
    except (LinerAPIError, LinerConfigError, LinerKeyMissingError, LimitReachedError) as exc:
        ctx.ws.emit("check_result", "coordinator", {"check": "rerank", "outcome": "skipped", "items": [],
                                                    "details": [f"기능 순서를 정하지 못해 앞쪽 기능만 담았어요: {exc}"]})
        return dict(service)
    order = [r["index"] for r in body.get("results") or []
             if isinstance(r, Mapping) and isinstance(r.get("index"), int) and 0 <= r["index"] < len(feats)]
    order = list(dict.fromkeys(order)) + [i for i in range(len(feats)) if i not in order]
    return {**service, "features": [feats[i] for i in order]}
