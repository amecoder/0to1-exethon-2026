from __future__ import annotations
"""FR-21 rework step 1: after CP5 the PM rewrites the requirements the approved change contradicts.

Runs once per change at the start of S5 while meta.recheck names it (no CP2 again — CP5 was the client's
confirmation). The PM may only rewrite title/statement/acceptance/exceptions of requirements inside the
impact set; ids, links and statuses stay. The target keeps the approved after-text word for word (G2).
Code records the before/after diff and runs the stale-text check that CP3 shows as a waivable warning.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.change_brief import change_brief
from app.checks import normalize_key, stale_requirements
from app.korean import josa
from app.schemas import REQUIREMENTS_REVISION
from app.stage_common import StageContext, masked_output, str_list

REVISABLE = ("title", "statement", "acceptance", "exceptions")
TASK_REVISE = (
    "발주사가 CP5 에서 변경을 승인했다(추가 입력의 '변경'). '고칠 수 있는 요구사항'(바뀌는 요구사항과 그것에 직접·간접으로 "
    "기대는 요구사항) 중 '바뀐 뒤' 내용과 어긋나는 것을 모두 고쳐라. 바뀌는 요구사항은 진술은 승인된 문장 그대로 두고 "
    "인수 조건(given/when/then)·예외를 그에 맞게 고친다. 기대는 요구사항은 '바뀌기 전'·'대체된 결정'의 내용이 남아 있으면 "
    "'바뀐 뒤'에 맞게 제목·진술·인수 조건·예외를 고친다. 고친 요구사항만 돌려주고 ID 는 그대로, 새로 만들거나 지우지 않는다. "
    "다른 결정(decisions)의 고른 답 문구는 그대로 둔다. after_key 에는 고친 요구사항에 들어가야 할 바뀐 뒤의 핵심 말을 "
    "짧게(예: '수요일 또는 토요일') 적어라."
)


def revision_pending(ctx: StageContext) -> bool:
    """An approved change is being reworked and its requirements were not revised yet (once per change)."""
    recheck = ctx.ws.meta.get("recheck") or {}
    item = ctx.ws.get("changes", recheck["change_id"]) if recheck.get("change_id") else None
    return item is not None and "revision" not in item


def before_keys(ctx: StageContext, item: Mapping[str, Any]) -> list[str]:
    """The superseded answers' texts (S4 writes chosen answers verbatim), unless the after-text keeps them."""
    after = normalize_key(str(item.get("after", "")))
    chosen = [str(d.get("chosen", "")) for d in ctx.ws.items("decisions")
              if d.get("superseded_by") == item["id"] and d.get("answer_kind") != "free_text"]
    return [c for c in dict.fromkeys(chosen) if normalize_key(c) and normalize_key(c) not in after]


def direct_ids(reqs: Sequence[Mapping[str, Any]], target: str) -> list[str]:
    """The target and the requirements that depend on it directly (the rest of the impact is transitive)."""
    return sorted({target} | {str(r["id"]) for r in reqs if target in str_list(r.get("depends_on"))})


def _view(req: Mapping[str, Any]) -> dict[str, Any]:
    return {k: req.get(k) for k in REVISABLE}


def _revised(old: Mapping[str, Any], raw: Mapping[str, Any], pinned: str | None) -> dict[str, Any]:
    acceptance = raw.get("acceptance") if isinstance(raw.get("acceptance"), Mapping) else {}
    new = {
        "title": str(raw.get("title") or old.get("title", "")),
        "statement": pinned if pinned is not None else str(raw.get("statement") or old.get("statement", "")),
        "acceptance": {k: str(acceptance.get(k) or (old.get("acceptance") or {}).get(k, "")) for k in ("given", "when", "then")},
        "exceptions": str_list(raw.get("exceptions")) if isinstance(raw.get("exceptions"), list) else list(old.get("exceptions", [])),
    }
    return {**old, **new}


def revise_requirements(ctx: StageContext) -> None:
    recheck = ctx.ws.meta["recheck"]
    item = ctx.ws.get("changes", recheck["change_id"])
    reqs = list(ctx.ws.items("requirements"))
    scope = list(item.get("impact", {}).get("requirements", [])) or [item["target"]]
    direct = item.get("direct") or direct_ids(reqs, item["target"])
    affected = [{**_view(r), "id": r["id"], "decision_refs": r.get("decision_refs", []),
                 "관계": "바뀌는 곳" if r["id"] == item["target"] else ("직접 기댐" if r["id"] in direct else "간접 기댐")}
                for r in reqs if r["id"] in scope]
    ctx.bus.send("coordinator", "pm", f"{item['id']} 승인 — 바뀐 뒤 내용과 어긋나는 요구사항을 먼저 고쳐 주세요")
    out = masked_output(ctx, "pm", ctx.runner.ask("pm", TASK_REVISE, "requirements_revision", REQUIREMENTS_REVISION,
                                                  {"변경": change_brief(ctx.ws.source), "고칠 수 있는 요구사항": affected}))
    by_id = {r["id"]: r for r in reqs}
    returned = {}
    for raw in out.get("requirements") or []:
        rid = str(raw.get("id", "")) if isinstance(raw, Mapping) else ""
        if rid not in scope or rid not in by_id:
            ctx.ws.emit("ref_dropped", "pm", {"item": item["id"], "ref": rid, "reason": "영향 범위 밖이거나 없는 요구사항"})
            continue
        returned[rid] = raw
    diff = []
    for rid in [r for r in scope if r in by_id]:
        old = by_id[rid]
        # the target's statement was already set to the approved text at CP5: show it against the old one
        shown = {**_view(old), "statement": item["before"]} if rid == item["target"] else _view(old)
        new = _revised(old, returned[rid], item["after"] if rid == item["target"] else None) if rid in returned else old
        if _view(new) == shown:
            continue
        if _view(new) != _view(old):
            new = {**new, "change_refs": list(dict.fromkeys([*old.get("change_refs", []), item["id"]]))}
            ctx.ws.write("pm", "requirements", new)
            by_id[rid] = new
        diff.append({"id": rid, "fields": [k for k in REVISABLE if _view(new)[k] != shown[k]],
                     "before": shown, "after": _view(new)})
    record(ctx, item, scope, direct, diff, str(out.get("after_key", "")).strip(), [by_id[r] for r in scope if r in by_id])

def record(ctx: StageContext, item: Mapping[str, Any], scope: list[str], direct: list[str],
           diff: list[dict[str, Any]], after_key: str, current: list[Mapping[str, Any]]) -> None:
    keys = before_keys(ctx, item)
    revision = {"requirements": diff, "scope": scope, "before_keys": keys, "after_key": after_key}
    ctx.ws.write("coordinator", "changes", {**ctx.ws.get("changes", item["id"]), "direct": direct, "revision": revision})
    ctx.ws.emit("change_revised", "pm", {"change_id": item["id"], "requirements": diff})
    stale = stale_requirements(current, keys, after_key)
    ctx.ws.emit("check_result", "coordinator", {
        "check": "change_consistency", "outcome": "flagged" if stale else "passed", "items": stale,
        "details": [f"{josa(r, '이/가')} 바뀌기 전 내용을 아직 담고 있습니다" for r in stale]})
    ctx.bus.send("pm", "coordinator", f"{item['id']} 반영: 요구사항 {len(diff)}건 고침"
                                      + (f", 아직 어긋남 {', '.join(stale)}" if stale else ""))
