from __future__ import annotations
"""After CP2: one PM call rewrites the problem statement's "done" line so it matches the client's answers.

Fail-open: if the agent or Liner fails, the old line stays and the pipeline goes on (a G7 limit still stops it).
"""

from collections.abc import Mapping
from typing import Any

from app.agent_runner import AgentOutputError
from app.config import LinerKeyMissingError
from app.liner import LinerAPIError, LinerConfigError
from app.schemas import PROBLEM_DONE
from app.stage_common import StageContext, masked_output

TASK_PROBLEM_DONE = (
    "발주사가 요구사항 원본을 확인했다. 문제 진술(problem_statement)의 done(언제 끝났다고 보나)을 발주사가 고른 답"
    "(decisions)에 맞게 한두 문장으로 다시 써라. 답으로 정해진 부분에서는 「잠정」, 「[상태: 가정]」 같은 임시 표시를 "
    "빼고, 답이 아직 '가정'인 부분은 그대로 둔다. 새 기능이나 해결책을 더하지 마라."
)
FAILURES = (AgentOutputError, LinerAPIError, LinerConfigError, LinerKeyMissingError)


def refresh_problem_done(ctx: StageContext) -> None:
    ps = (ctx.ws.items("problem_statement") or [None])[0]
    if ps is None:
        return
    before = str(ps.get("done", ""))
    try:
        out = masked_output(ctx, "pm", ctx.runner.ask("pm", TASK_PROBLEM_DONE, "problem_done", PROBLEM_DONE))
    except FAILURES as exc:
        _report(ctx, ps, "skipped", f"성공 기준을 다시 쓰지 못해 그대로 둠: {exc}")
        return
    after = " ".join(str(out.get("done", "")).split())
    if not after or after == before:
        _report(ctx, ps, "unchanged", "성공 기준이 답과 맞아 그대로 둠")
        return
    ctx.ws.write("pm", "problem_statement", {**ps, "done": after, "done_before": before})
    _report(ctx, ps, "updated", f"「{before}」 → 「{after}」")


def _report(ctx: StageContext, ps: Mapping[str, Any], outcome: str, detail: str) -> None:
    ctx.ws.emit("check_result", "pm", {"check": "problem_done", "outcome": outcome, "items": [ps.get("id", "")],
                                       "details": [detail]})
