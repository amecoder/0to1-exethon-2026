from __future__ import annotations
"""Build an orchestrator on the scripted fake Liner and drive it to a given point."""

from pathlib import Path
from typing import Any

from app.agent_runner import AgentRunner
from app.definitions import load_definitions
from app.liner import LinerClient
from app.orchestrator import Orchestrator
from app.store import empty_source
from app.workspace import Workspace
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

CHUNKS = memo_chunks()
DAY_CHOICE = "수·토 중 고름"


def build(repo_root: Path, env_file: Path, overrides: dict[str, list[Any]] | None = None, **fake_kwargs: Any
          ) -> tuple[Orchestrator, Workspace, FakeLiner]:
    agents, teams = load_definitions(repo_root)
    fake = FakeLiner({**flower_outputs(CHUNKS), **(overrides or {})}, search_body=SEARCH_BODY, **fake_kwargs)
    ws = Workspace(empty_source(), agents)
    runner = AgentRunner(LinerClient(env_file=env_file, transport=fake.transport()), agents, ws)
    return Orchestrator(ws, teams["default"], runner), ws, fake


def to_cp2(orch: Orchestrator, ws: Workspace, day: str = DAY_CHOICE) -> None:
    """Answer Q-01 (delivery day) with `day` and Q-02 with its first option."""
    orch.ingest(CHUNKS)
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    first, second = ws.items("questions")
    orch.answer(first["id"], "choice", day)
    orch.answer(second["id"], "choice", second["options"][0])
    orch.submit_answers()
    orch.advance()


def to_cp3(orch: Orchestrator, ws: Workspace, day: str = DAY_CHOICE) -> None:
    to_cp2(orch, ws, day)
    orch.confirm("CP2", True, "발주사")
    orch.advance()


def events(ws: Workspace, kind: str) -> list[dict[str, Any]]:
    return [e for e in ws.source["events"] if e["type"] == kind]


CP3_WAIVERS = {"coverage.no_tc:REQ-02": "결제 실패는 다음 단계에서 시험"}


def to_cp4(orch: Orchestrator, ws: Workspace, day: str = DAY_CHOICE) -> None:
    to_cp3(orch, ws, day)
    orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)
    orch.advance()
