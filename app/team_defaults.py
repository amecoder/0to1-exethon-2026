from __future__ import annotations
"""11-22 user decision 「기본값 목록 한 화면」: the points the question cards do not ask about.

Right after the cards (S3), one PM call gives each such open item the team's default answer and a plain why.
The answer review shows them as one list; 「이대로 진행」 keeps each default (a 가정 decision by the team) or the
client's one-line change (확정), and the open item is gone — it does not reach CP3 as a blank. Without the call's
answer (bad output, Liner trouble) the open items stay as before and CP3 explains them (app/waiver_help.py).
"""

from collections.abc import Mapping
from typing import Any

from app.agent_runner import AgentOutputError
from app.errors import PipelineStateError
from app.liner import LinerAPIError
from app.schemas import TEAM_DEFAULTS
from app.stage_common import StageContext, g3_check
from app.workspace import Workspace

TASK = (
    "질문 카드로 묻지 않은 점(추가 입력의 open_items)마다 팀이 정할 기본값을 적어라. default 는 발주사가 읽고 바로 "
    "받아들이거나 고칠 수 있는 완전한 문장 하나(예: '결제가 실패하면 다음 날 한 번 더 결제해요'), why 는 그렇게 정한 "
    "이유를 쉬운 말 한 문장으로(원문·업계에서 흔한 방식 등 근거). 원문과 발주사가 고른 답(decisions)과 어긋나지 않게, "
    "가장 흔하고 안전한 쪽으로 정한다. id 는 open_items 의 id 를 그대로 쓴다."
)
READS = ("sources", "requirements", "decisions")
MAX_CHANGE = 500


def propose(ctx: StageContext) -> int:
    """One PM call for the open items without a default yet. Returns how many got one."""
    items = [i for i in ctx.ws.items("open_items") if not i.get("team_default")]
    if not items:
        return 0
    ctx.bus.send("coordinator", "pm", f"카드로 묻지 않은 점 {len(items)}개 — 팀 기본값을 정해 주세요")
    extra = {"open_items": [{k: i.get(k) for k in ("id", "title", "requirement_refs")} for i in items]}
    try:
        out = ctx.runner.ask("pm", TASK, "team_defaults", TEAM_DEFAULTS, extra, reads=READS)
    except (AgentOutputError, LinerAPIError):
        return 0  # the open items stay; CP3 explains each one
    given = {str(d.get("id")): d for d in out.get("defaults", []) if isinstance(d, Mapping)}
    done = 0
    for item in items:
        d = given.get(item["id"], {})
        default, why = str(d.get("default", "")).strip(), str(d.get("why", "")).strip()
        if default:
            ctx.ws.write("coordinator", "open_items", {**item, "team_default": default, "team_why": why})
            done += 1
    if done:
        ctx.bus.send("pm", "client", f"카드로 묻지 않은 점 {done}개는 팀이 기본값을 정했어요. 답 확인 화면에서 바꿀 수 있어요")
    return done


def pending(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """What the answer review lists: open items that carry a team default."""
    return [{k: i.get(k) for k in ("id", "title", "team_default", "team_why", "requirement_refs")}
            for i in source.get("open_items", []) if i.get("team_default")]


def confirm(ws: Workspace, changes: Mapping[str, str] | None) -> None:
    """「이대로 진행」: every listed default becomes a decision — the client's change where given. All or nothing:
    a change with personal data or more than one line stops here before anything is stored."""
    changes = {k: v.strip() for k, v in (changes or {}).items() if v and v.strip()}
    listed = [i for i in ws.items("open_items") if i.get("team_default")]
    picked = {i["id"]: changes[i["id"]] for i in listed if changes.get(i["id"], i["team_default"]) != i["team_default"]}
    g3_check(ws, list(picked.values()), "팀 기본값 수정")
    if any(len(v) > MAX_CHANGE or "\n" in v for v in picked.values()):
        raise PipelineStateError(f"기본값을 고칠 때는 한 줄, {MAX_CHANGE}자 안으로 적어 주세요")
    if not listed:
        return
    for item in listed:
        mine = item["id"] in picked
        ws.write("coordinator", "decisions", {
            "id": ws.next_id("decisions", "DEC"), "kind": "team_default", "topic": item.get("title", ""),
            "chosen": picked.get(item["id"], item["team_default"]), "why": item.get("team_why", ""),
            "answer_kind": "free_text" if mine else "team_default", "status": "확정" if mine else "가정",
            "answered_by": "client" if mine else "team", "finding_refs": list(item.get("finding_refs", [])),
            "requirement_refs": list(item.get("requirement_refs", [])), "source_refs": list(item.get("source_refs", []))})
    ws.write_all("coordinator", "open_items", [i for i in ws.items("open_items") if not i.get("team_default")])
    ws.emit("team_defaults_confirmed", "client", {"count": len(listed), "changed": len(picked)})
