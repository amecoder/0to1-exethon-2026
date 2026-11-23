from __future__ import annotations
"""Startup recovery: runs (or change-lane items) left working by a restart cannot resume mid-call → failed.

Each project is recovered on its own under its run lock: one that fails (say a StaleRevisionError) is logged
and the rest still recover. A confirmation stage (CP1~CP4) left `running` or `failed` has no call to resume: it only waits for a person,
so it goes back to `awaiting_confirmation`. Run locks are cleared — no background work survives a restart.
"""

import logging
from collections.abc import Mapping

from app.agent_runner import AgentRunner
from app.change_desk import ChangeDesk, lane
from app.definitions import AgentDef, TeamDef
from app.liner import LinerClient
from app.orchestrator import STAGES, Orchestrator
from app.store import ProjectStore
from app.workspace import Workspace

log = logging.getLogger(__name__)

# X1 (11-21): a background task that dies on an unexpected exception goes the same way as a restart.
CRASHED = "예상하지 못한 오류로 작업이 멈췄어요. '다시 시도'를 누르면 이 단계를 처음부터 다시 합니다"
CRASHED_LANE = "예상하지 못한 오류로 처리가 멈췄어요. 같은 말을 다시 보내 주세요"
CRASHED_CONFIRM = "말씀을 처리하다 오류가 났어요. 다시 적어 주세요"


def recover_interrupted(store: ProjectStore, agents: Mapping[str, AgentDef], team: TeamDef,
                        liner: LinerClient) -> list[str]:
    store.release_all_runs()
    recovered = []
    for project_id in store.ids():
        token = store.acquire_run(project_id)
        if token is None:
            continue
        try:
            if recover_one(store, project_id, agents, team, liner):
                recovered.append(project_id)
        except Exception:  # one broken project must not keep the others stuck
            log.exception("프로젝트 %s 를 복구하지 못했습니다", project_id)
        finally:
            store.release_run(project_id, token)
    return recovered


def recover_one(store: ProjectStore, project_id: str, agents: Mapping[str, AgentDef], team: TeamDef,
                liner: LinerClient, crash: str | None = None) -> bool:
    """`crash` is only the exception's type name (never its message: it may quote the client's text)."""
    project = store.get(project_id)
    if project is None:
        return False
    pipeline = project["source"].get("meta", {}).get("pipeline", {})
    stranded = STAGES.get(pipeline.get("stage"), None) is not None and \
        STAGES[pipeline["stage"]].kind == "confirm" and pipeline.get("status") in ("running", "failed")
    running = pipeline.get("status") == "running"
    busy = lane(project["source"])["busy"]
    if not (running or busy or stranded):
        return False
    ws = Workspace(project["source"], agents, on_change=store.saver(project_id, project["revision"]))
    runner = AgentRunner(liner, agents, ws)
    if stranded:
        Orchestrator(ws, team, runner).restore_confirmation(error=CRASHED_CONFIRM if crash else None, crash=crash)
    elif running:
        if crash:
            Orchestrator(ws, team, runner).mark_interrupted(error=CRASHED, crash=crash)
        else:
            Orchestrator(ws, team, runner).mark_interrupted()
    if busy:
        if crash:
            ChangeDesk(ws, team, runner).mark_interrupted(error=CRASHED_LANE)
        else:
            ChangeDesk(ws, team, runner).mark_interrupted()
    return True
