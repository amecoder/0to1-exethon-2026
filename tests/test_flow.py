from __future__ import annotations
"""에이전트 OS 1단계: the business flow (stage order, kinds, agents, rework, the work each stage runs) is a file
(flows/*.json) the engine reads, not code. A broken flow file is refused before anything runs."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.agent_runner import AgentRunner
from app.definitions import load_definitions
from app.flow import DEFAULT_FLOW, FlowError, load_flow
from app.liner import LinerClient
from app.orchestrator import STAGE_TABLE, Orchestrator
from app.store import empty_source
from app.workspace import Workspace
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs
from tests.pipeline_helpers import CHUNKS, to_cp2

LITE = [
    {"id": "S1", "kind": "input", "title": "요구 입력"},
    {"id": "S2", "kind": "work", "title": "문제 인식", "agents": ["fde_lead", "researcher"], "run": "problem"},
    {"id": "CP1", "kind": "confirm", "title": "문제·범위 확인", "rework": "S2"},
    {"id": "S3", "kind": "work", "title": "구체화", "agents": ["pm", "qa", "coordinator"], "run": "requirements"},
    {"id": "S4", "kind": "work", "title": "원본 확정", "agents": ["pm"], "run": "finalize"},
    {"id": "CP2", "kind": "confirm", "title": "요구사항 원본 확인", "rework": "S3"},
]


def write(tmp_path: Path, stages: list[dict[str, Any]]) -> Path:
    path = tmp_path / "flow.json"
    path.write_text(json.dumps({"id": "lite", "title": "요구사항까지만", "stages": stages}, ensure_ascii=False))
    return path


def test_the_default_flow_file_is_the_stage_table(repo_root: Path) -> None:
    agents, _ = load_definitions(repo_root)
    flow = load_flow(DEFAULT_FLOW, agents)
    assert [s.id for s in flow.stages] == ["S1", "S2", "CP1", "S3", "S4", "CP2", "S5", "CP3", "S6", "CP4"]
    assert flow.stages == STAGE_TABLE
    assert flow.stage("CP3").rework == "S5" and flow.stage("S6").run == "prototype"
    assert flow.stage("CP2").on_approve == ("snapshot", "refresh_problem")
    assert flow.stage("CP4").on_approve == ("bind_version", "clear_recheck")
    assert flow.stage("CP1").features == ("build_or_buy",) and flow.stage("CP2").features == ("requirement_review",)


def test_a_flow_written_as_a_file_runs_without_engine_changes(repo_root: Path, key_env: Path, tmp_path: Path) -> None:
    agents, teams = load_definitions(repo_root)
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    ws = Workspace(empty_source(), agents)
    runner = AgentRunner(LinerClient(env_file=key_env, transport=fake.transport()), agents, ws)
    orch = Orchestrator(ws, teams["default"], runner, flow=load_flow(write(tmp_path, LITE), agents))
    to_cp2(orch, ws)
    assert ws.pipeline["stage"] == "CP2" and ws.pipeline["status"] == "awaiting_confirmation"
    orch.confirm("CP2", True, "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "completed"
    assert "screen_spec" not in fake.chat_names and "test_cases" not in fake.chat_names  # S5·S6 never ran


@pytest.mark.parametrize("change, message", [
    (lambda s: [*s[:3], {**s[3], "run": "없는 일"}, *s[4:]], "없는 일"),
    (lambda s: [*s, {**s[2]}], "CP1"),
    (lambda s: [*s[:2], {**s[2], "rework": "S4"}, *s[3:]], "rework"),
    (lambda s: [*s[:1], {**s[1], "agents": ["ghost"]}, *s[2:]], "ghost"),
    (lambda s: s[1:], "input"),
    (lambda s: [*s[:1], {**s[1], "kind": "wait"}, *s[2:]], "wait"),
    (lambda s: [*s[:2], {"id": "S1b", "kind": "input", "title": "또 입력"}, *s[2:]], "S1b"),
    (lambda s: [*s[:1], {**s[1], "agents": "pm"}, *s[2:]], "agents"),
    (lambda s: [*s[:5], {**s[5], "on_approve": ["fireworks"]}], "fireworks"),
    (lambda s: [*s[:5], {**s[5], "features": ["teleport"]}], "teleport"),
    (lambda s: [*s[:1], {**s[1], "on_approve": ["snapshot"]}, *s[2:]], "on_approve"),
    (lambda s: [*s[:2], {**s[2], "features": ["requirement_review"]}, *s[3:]], "finalize"),
    (lambda s: [*s[:4], s[5]], "finalize"),  # cards are asked (requirements) but nothing fixes them afterwards
    (lambda s: [*s[:5], {**s[5], "on_approve": ["snapshot", "snapshot"]}], "두 번"),
    # X3 (11-21): holes the Fable review found — each used to load without a word
    (lambda s: [*s[:5], {**s[5], "on_aprove": ["snapshot"]}], "on_aprove"),
    (lambda s: [*s[:1], {**s[1], "id": 2}, *s[2:]], "id"),
    (lambda s: [*s[:1], {**s[1], "id": " S2 "}, *s[2:]], "id"),
    (lambda s: [*s[:2], {**s[2], "run": "problem"}, *s[3:]], "run"),
    (lambda s: [*s[:1], {**s[1], "rework": "S1"}, *s[2:]], "rework"),
    (lambda s: [*s[:4], {"id": "S3b", "kind": "work", "agents": ["pm"], "run": "requirements"}, *s[4:]], "S3b"),
    (lambda s: [*s[:2], {**s[2], "features": ["build_or_buy"]}, *s[3:5], {**s[5], "features": ["build_or_buy"]}],
     "build_or_buy"),
    (lambda s: [*s[:2], {"id": "S5", "kind": "work", "agents": ["pm"], "run": "documents"}], "finalize"),
    (lambda s: [s[0], {"id": "S6", "kind": "work", "agents": ["developer"], "run": "prototype"}], "documents"),
])
def test_a_broken_flow_is_refused_before_it_runs(repo_root: Path, tmp_path: Path, change: Any, message: str) -> None:
    agents, _ = load_definitions(repo_root)
    with pytest.raises(FlowError, match=message):
        load_flow(write(tmp_path, change(LITE)), agents)


def test_an_unknown_top_level_key_is_refused(repo_root: Path, tmp_path: Path) -> None:
    agents, _ = load_definitions(repo_root)
    path = tmp_path / "flow.json"
    path.write_text(json.dumps({"id": "lite", "stagez": LITE, "stages": LITE}, ensure_ascii=False))
    with pytest.raises(FlowError, match="stagez"):
        load_flow(path, agents)



# --- 2단계 (D6 c): the engine names no stage ---------------------------------------------------------
RENAMED = {"S1": "IN", "S2": "W1", "CP1": "OK1", "S3": "W2", "S4": "W3", "CP2": "OK2", "S5": "W4", "CP3": "OK3",
           "S6": "W5", "CP4": "OK4"}


def test_the_engine_names_no_stage(repo_root: Path) -> None:
    import re
    text = (repo_root / "app" / "orchestrator.py").read_text(encoding="utf-8")
    assert re.findall(r'"(S[1-7]|CP[1-5])"', text) == []


def test_a_flow_with_other_stage_ids_runs_to_the_end(repo_root: Path, key_env: Path, tmp_path: Path) -> None:
    from tests.pipeline_helpers import CP3_WAIVERS
    data = json.loads(DEFAULT_FLOW.read_text(encoding="utf-8"))
    for stage in data["stages"]:
        stage["id"] = RENAMED[stage["id"]]
        if stage.get("rework"):
            stage["rework"] = RENAMED[stage["rework"]]
    path = tmp_path / "renamed.json"
    path.write_text(json.dumps(data, ensure_ascii=False))
    agents, teams = load_definitions(repo_root)
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    flow = load_flow(path, agents)
    ws = Workspace(empty_source(flow.first.id), agents)  # a new project starts at its flow's input stage
    runner = AgentRunner(LinerClient(env_file=key_env, transport=fake.transport()), agents, ws)
    orch = Orchestrator(ws, teams["default"], runner, flow=flow)
    orch.ingest(CHUNKS)
    orch.advance()
    orch.confirm("OK1", True, "발주사")
    orch.advance()
    assert ws.pipeline["stage"] == "W2"
    for q in ws.items("questions"):
        orch.answer(q["id"], "choice", q["options"][0])
    orch.submit_answers()
    orch.advance()
    orch.confirm("OK2", True, "발주사")
    orch.advance()
    orch.confirm("OK3", True, "발주사", waivers=CP3_WAIVERS)
    orch.advance()
    orch.confirm("OK4", True, "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "completed"
    assert [v["version"] for v in ws.items("versions")] == ["v1", "v2"]
    assert ws.items("confirmations")[-1]["based_on"] == "v2"


def test_a_flow_without_the_step_refuses_the_action(repo_root: Path, key_env: Path, tmp_path: Path) -> None:
    from app.errors import PipelineStateError
    agents, teams = load_definitions(repo_root)
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    ws = Workspace(empty_source(), agents)
    runner = AgentRunner(LinerClient(env_file=key_env, transport=fake.transport()), agents, ws)
    orch = Orchestrator(ws, teams["default"], runner, flow=load_flow(write(tmp_path, LITE), agents))
    with pytest.raises(PipelineStateError, match="흐름"):
        orch.narrow_scope(["SCR-01"], "발주사")


def test_the_server_refuses_a_flow_naming_an_unknown_agent(tmp_path: Path, key_env: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main
    from app.config import Settings
    from app.main import create_app
    broken = [*LITE[:1], {**LITE[1], "agents": ["ghost"]}, *LITE[2:]]
    monkeypatch.setattr(app.main, "DEFAULT_FLOW", write(tmp_path, broken))
    with pytest.raises(FlowError, match="ghost"):
        create_app(Settings(db_path=tmp_path / "f.sqlite3", env_file=key_env))


# --- E4 (11-21): a second flow ships as a file, and one command checks any flow file -------------------
FLOWS = sorted((Path(__file__).resolve().parents[1] / "flows").glob("*.json"))


@pytest.mark.parametrize("path", FLOWS, ids=lambda p: p.stem)
def test_every_shipped_flow_file_is_valid(repo_root: Path, path: Path) -> None:
    agents, _ = load_definitions(repo_root)
    assert load_flow(path, agents).id == path.stem


def test_the_shipped_lite_flow_stops_after_the_requirements(repo_root: Path, key_env: Path) -> None:
    agents, teams = load_definitions(repo_root)
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    ws = Workspace(empty_source(), agents)
    runner = AgentRunner(LinerClient(env_file=key_env, transport=fake.transport()), agents, ws)
    flow = load_flow(repo_root / "flows" / "requirements_lite.json", agents)
    orch = Orchestrator(ws, teams["default"], runner, flow=flow)
    to_cp2(orch, ws)
    orch.confirm("CP2", True, "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "completed" and [v["version"] for v in ws.items("versions")] == ["v1"]
    assert "screen_spec" not in fake.chat_names and "test_cases" not in fake.chat_names


def test_the_flow_command_reports_a_broken_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from app.flow import main
    broken = write(tmp_path, [*LITE[:3], {**LITE[3], "run": "없는 일"}, *LITE[4:]])
    assert main([str(broken)]) == 1
    assert "없는 일" in capsys.readouterr().out
    assert main([str(DEFAULT_FLOW)]) == 0
    assert "CP4" in capsys.readouterr().out



# --- Fable review (11-21) L4·L5 --------------------------------------------------------------------------------
@pytest.mark.parametrize("data", [
    {"id": "lite", "title": "x", "stages": [{**LITE[0], "rework": "S2"}, *LITE[1:]]},
    {"id": 7, "title": "x", "stages": LITE},
    {"id": "lite", "title": {"a": 1}, "stages": LITE},
])
def test_more_broken_flows_are_refused(repo_root: Path, tmp_path: Path, data: dict[str, Any]) -> None:
    agents, _ = load_definitions(repo_root)
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(FlowError):
        load_flow(path, agents)


def test_a_flow_file_that_is_not_utf8_is_a_flow_error(repo_root: Path, tmp_path: Path) -> None:
    path = tmp_path / "flow.json"
    path.write_bytes(b"\xff\xfe{}")
    with pytest.raises(FlowError):
        load_flow(path, None)


def test_the_flow_command_survives_a_korean_windows_console(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys
    from app.flow import main
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp949"))
    assert main([str(DEFAULT_FLOW)]) == 0  # used to raise UnicodeEncodeError on ✓ and the titles' —
    sys.stdout.flush()
    assert "requirements".encode("cp949") in raw.getvalue()
