from __future__ import annotations
"""에이전트 OS 3단계 (D6 a, 11-20): every Liner tool is registered, an agent file may only name registered tools,
and an agent calls only the tools its file declares — a missing one is refused before any request (G4)."""

import json
import re
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.agent_runner import AgentRunner, ToolNotAllowedError
from app.definitions import DefinitionError, load_agents, load_definitions
from app.liner import DECISIONS_URL, IMAGES_URL, RERANK_URL, SEARCH_URL, VISUALIZATION_URL, LinerClient
from app.store import empty_source
from app.tools import TOOLS
from app.workspace import Workspace
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs
from tests.test_liner_features import add_env
from tests.test_orchestrator import CHUNKS


def test_every_liner_tool_is_registered() -> None:
    assert set(TOOLS) == {"liner_search", "liner_ai_search", "liner_visualization", "liner_decisions",
                          "liner_rerank", "liner_images"}


def test_an_agent_file_naming_an_unknown_tool_is_refused(repo_root: Path, tmp_path: Path) -> None:
    folder = tmp_path / "agents"
    shutil.copytree(repo_root / "agents", folder)
    pm = json.loads((folder / "pm.json").read_text(encoding="utf-8"))
    (folder / "pm.json").write_text(json.dumps({**pm, "tools": ["liner_teleport"]}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(DefinitionError, match="liner_teleport"):
        load_agents(folder)


def test_the_default_team_declares_the_tools_it_uses(repo_root: Path) -> None:
    agents, _ = load_definitions(repo_root)
    for agent in ("fde_lead", "qa", "coordinator"):
        assert "liner_decisions" in agents[agent].tools
    assert "liner_rerank" in agents["pm"].tools and "liner_images" in agents["developer"].tools
    assert {"liner_search", "liner_ai_search"} <= set(agents["researcher"].tools)
    assert "liner_visualization" in agents["designer"].tools


def runner_without(repo_root: Path, env: Path, agent: str, tool: str) -> tuple[AgentRunner, Workspace, FakeLiner]:
    agents, _ = load_definitions(repo_root)
    agents = {**agents, agent: replace(agents[agent], tools=tuple(t for t in agents[agent].tools if t != tool))}
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    ws = Workspace(empty_source(), agents)
    return AgentRunner(LinerClient(env_file=env, transport=fake.transport()), agents, ws), ws, fake


CALLS: list[tuple[str, str, str, Any]] = [
    ("coordinator", "liner_decisions", DECISIONS_URL, lambda r: r.decide("coordinator", "purpose", {"q": 1}, {"q": {}})),
    ("pm", "liner_rerank", RERANK_URL, lambda r: r.rerank("pm", "선물하기", ["가", "나"], 2)),
    ("developer", "liner_images", IMAGES_URL, lambda r: r.image("developer", "hero", "꽃다발")),
    ("researcher", "liner_search", SEARCH_URL, lambda r: r.search("researcher", "꽃 정기구독")),
    ("designer", "liner_visualization", VISUALIZATION_URL, lambda r: r.visualize("designer", "주문 흐름")),
]


@pytest.mark.parametrize("agent, tool, url, call", CALLS)
def test_a_tool_the_agent_lacks_is_never_called(repo_root: Path, key_env: Path, agent: str, tool: str, url: str,
                                               call: Any) -> None:
    add_env(key_env, LINER_DECISION_MODEL="typesafe/jev-1.13", LINER_RERANK_MODEL="cohere/rerank-5-fast",
            LINER_IMAGE_MODEL="qwen/qwen-image-2.1-turbo")
    runner, ws, fake = runner_without(repo_root, key_env, agent, tool)
    with pytest.raises(ToolNotAllowedError):
        call(runner)
    assert fake.payloads(url) == []
    blocked = [e["data"] for e in ws.source["events"] if e["type"] == "guardrail" and e["data"].get("id") == "G4"]
    assert len(blocked) == 1 and blocked[0]["outcome"] == "blocked" and blocked[0]["tool"] == tool


def test_rerank_without_the_tool_keeps_the_feature_order(repo_root: Path, key_env: Path) -> None:
    from app.bus import MessageBus
    from app.orchestrator import Orchestrator
    add_env(key_env, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    runner, ws, fake = runner_without(repo_root, key_env, "pm", "liner_rerank")
    _, teams = load_definitions(repo_root)
    orch = Orchestrator(ws, teams["default"], runner)
    feats = [{"id": f"REQ-{n:02d}", "title": f"기능 {n} " + "나" * 25} for n in range(14)]
    assert orch.ingest(CHUNKS, services=[{"name": "꽃님 정기구독", "features": feats}]).blocked is False
    assert fake.payloads(RERANK_URL) == []
    skipped = [e["data"] for e in ws.source["events"] if e["type"] == "check_result" and e["data"]["check"] == "rerank"]
    assert skipped and skipped[0]["outcome"] == "skipped"
    (system,) = ws.items("systems")
    assert [f["id"] for f in system["features"]] == [f"SYS-01/REQ-{n:02d}" for n in range(len(system["features"]))]
    assert MessageBus  # imported for the orchestrator's team wiring


def test_without_the_decision_tool_the_reason_is_the_tool_not_a_setting(repo_root: Path, key_env: Path) -> None:
    from types import SimpleNamespace
    from app.answer_desk import classify
    add_env(key_env, LINER_DECISION_MODEL="typesafe/jev-1.13")
    runner, ws, _ = runner_without(repo_root, key_env, "coordinator", "liner_decisions")
    result = classify(SimpleNamespace(runner=runner, ws=ws), "CP1", "이거 왜 이렇게 됐어요?")
    assert "LINER_DECISION_MODEL" not in result["fallback"] and "도구" in result["fallback"]


# --- E1 (11-21): one registry decides every Liner call and what G7 counts ----------------------------
def test_every_counted_call_event_comes_from_the_registry() -> None:
    from app import limits
    from app.tools import ALL_CALLS
    assert limits.CALL_EVENTS == {t.event for t in ALL_CALLS.values()}
    assert limits.CALL_EVENTS == {"liner_chat", "liner_search", "liner_decision", "liner_rerank", "liner_visualization",
                                  "liner_transcription", "liner_image", "liner_attachment"}


def test_every_event_the_runner_emits_is_registered(repo_root: Path, key_env: Path) -> None:
    from app.tools import call_of
    from tests.pipeline_helpers import build, to_cp4
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    calls = [e for e in ws.source["events"] if e["type"].startswith("liner_")]
    assert calls and all(call_of(e["type"], e["data"].get("api")) is not None for e in calls)
    assert call_of("liner_search", "ai_search") == "liner_ai_search" and call_of("liner_search", "search") == "liner_search"
    assert call_of("liner_chat", "model") == "liner_model" and call_of("liner_attachment", "model") == "liner_attachment"
    assert call_of("liner_teleport", None) is None


def test_an_agent_file_cannot_declare_a_built_in_call(repo_root: Path, tmp_path: Path) -> None:
    folder = tmp_path / "agents"
    shutil.copytree(repo_root / "agents", folder)
    pm = json.loads((folder / "pm.json").read_text(encoding="utf-8"))
    (folder / "pm.json").write_text(json.dumps({**pm, "tools": ["liner_model"]}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(DefinitionError, match="liner_model"):
        load_agents(folder)


LINER_CALL = re.compile(r"\b(?:liner|client|_client)\.(chat|search|ai_search|decide|rerank|visualize|generate_image|transcribe)\(")


def test_no_module_calls_liner_past_the_runner(repo_root: Path) -> None:
    """Every paid call goes through app/agent_runner.py (G4 tool gate, G7 caps, the call's event)."""
    files = [p for p in (repo_root / "app").rglob("*.py") if p.name not in ("agent_runner.py", "liner.py")]
    leaks = [f"{p.relative_to(repo_root)}: {m.group(0)}" for p in files
             for m in LINER_CALL.finditer(p.read_text(encoding="utf-8"))]
    assert leaks == []
    makers = [p.relative_to(repo_root).as_posix() for p in files if "LinerClient(" in p.read_text(encoding="utf-8")]
    assert makers == ["app/main.py"]


def test_the_tools_endpoint_lists_who_holds_each_tool(tmp_path: Path, key_env: Path) -> None:
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    client = TestClient(create_app(Settings(db_path=tmp_path / "t.sqlite3", env_file=key_env)))
    tools = {t["id"]: t for t in client.get("/api/tools").json()["tools"]}
    assert list(tools)[:6] == list(TOOLS) and len(tools) == 9
    assert tools["liner_decisions"]["agents"] == ["coordinator", "fde_lead", "qa"]
    assert tools["liner_decisions"]["declared"] is True and tools["liner_model"]["declared"] is False
    assert tools["liner_model"]["agents"] == [] and tools["liner_attachment"]["api"] == "model"


def test_the_guard_regex_catches_every_name_the_client_goes_by() -> None:
    """Fable review M4: the Liner client is `liner` in the routers and `_client` in the runner, not only `client`."""
    for leak in ("liner.chat(messages)", "liner.search(\"x\")", "self._client.rerank(q)", "ctx.runner.client.search(1)"):
        assert LINER_CALL.search(leak), leak
    assert not LINER_CALL.search("liner.credits_balance()")  # free balance reads are not paid calls
