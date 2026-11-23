from __future__ import annotations
"""FR-20 consumer feedback: before CP3 on the screen specs, before CP4 on the prototype.

The coordinator asks over the bus (relation consumer ↔ coordinator only). The consumer writes `feedback`
items linked to SCR ids. Opinion only (PRD Q8 → "의견만, PM 이 정한다"): nothing here blocks approval
or touches requirements, and a failed consumer call does not stop the stage.
"""

import re
from typing import Any

from app.agent_runner import AgentOutputError
from app.liner import LinerAPIError
from app.schemas import CONSUMER_FEEDBACK, FEEDBACK_KINDS
from app.stage_common import StageContext, masked_output

TASK = {
    "CP3": ("화면설계서(screens)를 처음 이 서비스를 쓰는 고객처럼 화면 순서대로 따라가 보고, 헷갈리는 곳·불편한 곳·"
            "그만두고 싶어지는 곳을 쉬운 말로 남겨라. 의견마다 어느 화면인지 screen_id(예: SCR-01)를 적는다. "
            "해결책을 설계하지 말고 겪은 느낌만 말한다. 의견은 5개 이하."),
    "CP4": ("프로토타입(prototype 의 html)을 처음 쓰는 고객처럼 눌러 본다고 생각하고, 헷갈리는 곳·불편한 곳·"
            "그만두고 싶어지는 곳을 쉬운 말로 남겨라. 의견마다 그 화면의 screen_id(예: SCR-01)를 적는다. "
            "해결책을 설계하지 말고 겪은 느낌만 말한다. 의견은 5개 이하."),
}
TARGET = {"CP3": "screens", "CP4": "prototype"}
ASK = {"CP3": "화면설계서를 고객 입장에서 봐 주세요", "CP4": "프로토타입을 고객 입장에서 눌러 봐 주세요"}
MAX_ITEMS = 5
_NUM = re.compile(r"(\d+)$")


def collect_feedback(ctx: StageContext, cp: str) -> int:
    """Ask the consumer for feedback for `cp` (CP3/CP4). Returns how many items were stored."""
    ctx.ws.set_pipeline(active_agent="coordinator")
    ctx.bus.send("coordinator", "consumer", ASK[cp])
    try:
        out = masked_output(ctx, "consumer", ctx.runner.ask(
            "consumer", TASK[cp], "consumer_feedback", CONSUMER_FEEDBACK))
    except (AgentOutputError, LinerAPIError) as exc:
        ctx.ws.emit("check_result", "coordinator", {"check": "consumer_feedback", "outcome": "failed",
                                                    "items": [], "details": [str(exc)]})
        ctx.bus.send("coordinator", "consumer", "의견을 받지 못했어요 — 이번 확인은 의견 없이 진행합니다")
        return 0
    items = _items(ctx, out.get("items"), cp)
    kept = [i for i in ctx.ws.items("feedback") if i.get("cp") != cp]
    ctx.ws.write_all("consumer", "feedback", [*kept, *items])
    ctx.bus.send("consumer", "coordinator", f"고객 의견 {len(items)}건")
    return len(items)


def _items(ctx: StageContext, raw: Any, cp: str) -> list[dict[str, Any]]:
    screens = {s["id"] for s in ctx.ws.items("screens")}
    start = max((int(m.group(1)) for i in ctx.ws.items("feedback") if (m := _NUM.search(str(i.get("id", ""))))),
                default=0)
    out: list[dict[str, Any]] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict) or len(out) >= MAX_ITEMS:
            continue
        screen = str(entry.get("screen_id", ""))
        comment = str(entry.get("comment", "")).strip()
        if screen not in screens:
            ctx.ws.emit("ref_dropped", "consumer", {"item": "feedback", "ref": screen, "reason": "공유 원본에 없는 ID"})
            continue
        if not comment:
            continue
        out.append({
            "id": f"FB-{start + len(out) + 1:02d}", "cp": cp, "target": TARGET[cp], "screen_id": screen,
            "kind": entry.get("kind") if entry.get("kind") in FEEDBACK_KINDS else "불편", "comment": comment,
            "status": "의견", "owner_agent": "consumer",
        })
    return out


def feedback_for(source: dict[str, Any], cp: str) -> list[dict[str, Any]]:
    return [f for f in source.get("feedback", []) if f.get("cp") == cp]
