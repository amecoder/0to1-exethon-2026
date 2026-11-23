from __future__ import annotations
"""The work a flow stage can run (flows/*.json `run`): name → function of the stage context.

Each returns the waiting status when a person is needed mid-stage (answers, a scope choice), else None.
A flow file may only name work registered here (app/flow.py checks it before anything runs).
"""

from collections.abc import Callable, Mapping

from app.problem_refresh import refresh_problem_done
from app.stage_common import StageContext
from app.stage_development import run_s6
from app.stage_documents import run_s5
from app.stage_problem import run_s2
from app.stage_requirements import run_s3, run_s4


def problem(ctx: StageContext) -> str | None:
    run_s2(ctx)
    return None


def requirements(ctx: StageContext) -> str | None:
    return "awaiting_answers" if run_s3(ctx) else None


def finalize(ctx: StageContext) -> str | None:
    run_s4(ctx)
    return None


def documents(ctx: StageContext) -> str | None:
    if ctx.ws.pipeline.get("refresh_problem"):  # once per CP2 approval, not on an S5 rework
        refresh_problem_done(ctx)
        ctx.ws.set_pipeline(refresh_problem=None)
    return "awaiting_scope" if run_s5(ctx) else None


def prototype(ctx: StageContext) -> str | None:
    run_s6(ctx)
    return None


RUNS: Mapping[str, Callable[[StageContext], str | None]] = {
    "problem": problem, "requirements": requirements, "finalize": finalize,
    "documents": documents, "prototype": prototype,
}

# What each job reads from an earlier job (X3): a flow that runs a job before its input exists is refused.
REQUIRES: Mapping[str, tuple[str, ...]] = {
    "requirements": ("problem",), "finalize": ("requirements",), "documents": ("finalize",),
    "prototype": ("documents",),
}


def _cards_answered(ctx: StageContext, stage_id: str) -> str | None:
    if any(q["status"] == "pending" for q in ctx.ws.items("questions")):
        return f"답하지 않은 질문 카드가 있어 {stage_id} 를 시작할 수 없습니다"
    return None


# What must hold before a job starts (G2), by job name: the reason it cannot start, or None.
PRECHECKS: Mapping[str, Callable[[StageContext, str], str | None]] = {"finalize": _cards_answered}
