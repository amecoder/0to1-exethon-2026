from __future__ import annotations
"""「같은 앱에 넣을까요?」 — a request built into a service the company already made with 0to1.

The 11-20 runs (design doc 6-1, H6) showed the team puts a request into the existing service even when the memo
never says which app (원데이 클래스 예약 → 정기구독 앱). So at S2 the FDE lead quotes the memo sentence that names
the service (`placement`, G1-checked like every quote), and at S3 code asks one card for each service that
requirements were built into without such a sentence. 「따로 새로 만든다」 unlinks that service from every
requirement (it becomes 신규); 「잘 모르겠어요」 keeps the team's choice as an assumption.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.guardrails import verify_quote
from app.schemas import PROBLEM_SCOPE, STR, STR_LIST, array, obj
from app.stage_common import UNKNOWN_OPTION, StageContext, citation_texts, str_list

KIND = "placement"
SEPARATE = "따로 새로 만든다"

TASK_FDE_PLACEMENT = (
    " systems 중 features 가 있는 것은 이 회사가 0to1로 이미 만든 서비스(앱)다. 원문이 이번 일을 그 서비스 안에 넣거나 "
    "그 서비스를 고쳐 달라고 직접 밝힌 경우에만(예: '지난번에 만든 정기구독 앱에 이어서') placement 에 system_ref, "
    "근거 원문 ID(refs), 원문에서 그대로 옮긴 인용문(quote)을 적어라. 원문이 어느 서비스·앱인지 말하지 않았으면 적지 않는다."
)
PROBLEM_SCOPE_SERVICES = {
    **PROBLEM_SCOPE,
    "properties": {**PROBLEM_SCOPE["properties"], "placement": array(obj(system_ref=STR, refs=STR_LIST, quote=STR))},
    "required": [*PROBLEM_SCOPE["required"], "placement"],
}


def services(systems: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Systems built with 0to1 (they carry their features)."""
    return {s["id"]: s for s in systems if s.get("features")}


def check_placement(ctx: StageContext, raw: Any) -> list[dict[str, Any]]:
    """Only built services; the quote must be in the cited memo sentence (G1)."""
    built = services(ctx.ws.items("systems"))
    texts = citation_texts(ctx.ws)
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, Mapping) or str(item.get("system_ref", "")) not in built:
            continue
        refs, quote = str_list(item.get("refs")), str(item.get("quote", ""))
        ok = verify_quote(quote, refs, texts)
        if not ok:
            ctx.ws.guardrail("G1", "flagged", "서비스에 넣으라는 근거 인용문이 원문에 그대로 없습니다", actor="fde_lead",
                             system=str(item["system_ref"]))
        out.append({"system_ref": str(item["system_ref"]), "refs": refs, "quote": quote,
                    "status": "확인" if ok else "미확인"})
    return out


def ask_placement(ctx: StageContext) -> int:
    """One card per built service the requirements use without a memo sentence naming it. Returns cards added."""
    built = services(ctx.ws.items("systems"))
    stated = {p["system_ref"] for s in ctx.ws.items("scope") for p in s.get("placement", []) if p.get("status") == "확인"}
    asked = {q.get("system_ref") for q in ctx.ws.items("questions") if q.get("kind") == KIND}
    added = 0
    for sid, system in built.items():
        linked = [r["id"] for r in ctx.ws.items("requirements") if sid in r.get("system_refs", [])]
        if not linked or sid in stated or sid in asked:
            continue
        name = system.get("name", sid)
        ctx.ws.write("coordinator", "questions", {
            "id": ctx.ws.next_id("questions", "Q"), "kind": KIND, "system_ref": sid,
            "question": f"이번 요청을 이미 만든 「{name}」 안에 넣을까요, 따로 새로 만들까요?",
            "why": (f"요청에 어느 앱에 넣을지 적혀 있지 않은데, 팀은 「{name}」에 기능을 더하는 쪽으로 요구사항 "
                    f"{len(linked)}건을 썼어요. 따로 만들면 「{name}」의 결제·알림 같은 기능을 함께 쓰지 않아요."),
            "options": [f"「{name}」 안에 넣는다", SEPARATE], "unknown_option": UNKNOWN_OPTION, "allow_free_text": False,
            "default_option": f"「{name}」 안에 넣는다", "source_refs": [], "evidence_refs": [], "finding_refs": [],
            "requirement_refs": linked, "status": "pending", "answer": None,
        })
        added += 1
    if added:
        ctx.bus.send("coordinator", "client", f"기존 서비스에 넣을지 {added}건을 먼저 여쭤봐요")
    return added


def separated(decisions: Sequence[Mapping[str, Any]]) -> set[str]:
    """Services the client chose to keep out of this request."""
    return {str(d.get("system_ref")) for d in decisions
            if d.get("kind") == KIND and d.get("chosen") == SEPARATE and not d.get("superseded_by")}
