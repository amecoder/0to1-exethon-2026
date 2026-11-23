from __future__ import annotations
"""E3 (11-21): the guardrails G1~G9 are declared in policies/guardrails.json — where each acts, rule or model, what
happens when it cannot judge, and which agent's tool it needs. The server refuses to start when a needed tool is
missing (G9 used to switch off silently), and the code and the file cannot drift apart."""

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.definitions import KNOWN_GUARDRAILS, DefinitionError, load_definitions, parse_agent
from app.guard_catalog import load_guards
from app.main import create_app

GUARD_CALL = re.compile(r'guardrail\(\s*"(G\d)"')
ALL = {f"G{i}" for i in range(1, 10)}


def catalog(repo_root: Path) -> list[dict[str, Any]]:
    return json.loads((repo_root / "policies" / "guardrails.json").read_text(encoding="utf-8"))["guardrails"]


def test_the_catalog_lists_every_guardrail_the_code_records(repo_root: Path) -> None:
    recorded = {m.group(1) for p in (repo_root / "app").rglob("*.py") for m in GUARD_CALL.finditer(p.read_text("utf-8"))}
    agents, _ = load_definitions(repo_root)
    listed = {g.id for g in load_guards(repo_root / "policies" / "guardrails.json", agents)}
    assert recorded == listed == set(KNOWN_GUARDRAILS) == ALL


def copy_definitions(repo_root: Path, tmp_path: Path) -> Path:
    root = tmp_path / "defs"
    for name in ("agents", "teams", "policies"):
        shutil.copytree(repo_root / name, root / name)
    return root


def test_a_guard_whose_agent_lacks_its_tool_stops_the_server(repo_root: Path, tmp_path: Path, key_env: Path) -> None:
    root = copy_definitions(repo_root, tmp_path)
    path = root / "agents" / "coordinator.json"
    path.write_text(json.dumps({**json.loads(path.read_text("utf-8")), "tools": []}, ensure_ascii=False), "utf-8")
    with pytest.raises(DefinitionError, match="G9.*coordinator.*liner_decisions"):
        create_app(Settings(db_path=tmp_path / "g.sqlite3", env_file=key_env, definitions_root=root))


@pytest.mark.parametrize("change, message", [
    (lambda g: [*g, {**g[0]}], "G1"),
    (lambda g: [{**g[0], "point": ["everywhere"]}, *g[1:]], "everywhere"),
    (lambda g: [{**g[0], "on_error": "maybe"}, *g[1:]], "maybe"),
    (lambda g: [{**g[0], "severity": "high"}, *g[1:]], "severity"),
    (lambda g: [*g[:8], {**g[8], "requires": [{"agent": "ghost", "tool": "liner_decisions"}]}], "requires"),
    (lambda g: [*g[:8], {**g[8], "requires": [{"agent": "coordinator", "tool": "liner_teleport"}]}], "requires"),
])
def test_a_broken_catalog_is_refused(repo_root: Path, tmp_path: Path, change: Any, message: str) -> None:
    path = tmp_path / "guardrails.json"
    path.write_text(json.dumps({"guardrails": change(catalog(repo_root))}, ensure_ascii=False), encoding="utf-8")
    agents, _ = load_definitions(repo_root)
    with pytest.raises(DefinitionError, match=message):
        load_guards(path, agents)


def test_an_agent_file_may_name_g9(repo_root: Path) -> None:
    data = json.loads((repo_root / "agents" / "coordinator.json").read_text("utf-8"))
    assert "G9" in parse_agent({**data, "guardrails": ["G9"]}, "coordinator.json").guardrails


def test_the_guardrails_endpoint_returns_the_catalog(tmp_path: Path, key_env: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "g.sqlite3", env_file=key_env)))
    guards = {g["id"]: g for g in client.get("/api/guardrails").json()["guardrails"]}
    assert set(guards) == ALL and guards["G9"]["on_error"] == "open"
    assert guards["G9"]["requires"] == [{"agent": "coordinator", "tool": "liner_decisions"}]  # same shape as the file (L7)
    assert guards["G1"]["requires"] == [{"agent": "fde_lead", "tool": "liner_decisions"}] and guards["G7"]["on_error"] == "open"


# --- Fable review (11-21) M2·M3·L3: the list cannot drop a guard or its tool, and a broken file says why ---------
@pytest.mark.parametrize("change, message", [
    (lambda g: g[:8], "G9"),  # the G9 line removed: it would switch off silently again
    (lambda g: [*g[:8], {k: v for k, v in g[8].items() if k != "requires"}], "G9"),
    (lambda g: [{k: v for k, v in g[0].items() if k != "requires"}, *g[1:]], "G1"),
])
def test_the_list_cannot_drop_a_guard_or_the_tool_it_needs(repo_root: Path, tmp_path: Path, change: Any,
                                                           message: str) -> None:
    path = tmp_path / "guardrails.json"
    path.write_text(json.dumps({"guardrails": change(catalog(repo_root))}, ensure_ascii=False), encoding="utf-8")
    agents, _ = load_definitions(repo_root)
    with pytest.raises(DefinitionError, match=message):
        load_guards(path, agents)


def test_the_g1_model_check_needs_the_fde_leads_decision_tool(repo_root: Path, tmp_path: Path, key_env: Path) -> None:
    root = copy_definitions(repo_root, tmp_path)
    path = root / "agents" / "fde_lead.json"
    data = json.loads(path.read_text("utf-8"))
    path.write_text(json.dumps({**data, "tools": [t for t in data["tools"] if t != "liner_decisions"]},
                               ensure_ascii=False), "utf-8")
    with pytest.raises(DefinitionError, match="G1.*fde_lead.*liner_decisions"):
        create_app(Settings(db_path=tmp_path / "g.sqlite3", env_file=key_env, definitions_root=root))


@pytest.mark.parametrize("body", [
    {"guardrails": 5}, {"guardrails": None}, {"guardrails": [{"id": ["G1"]}]},
    {"guardrails": [{"id": "G1", "title": "x", "point": 3, "method": "rule", "on_error": "none"}]},
    {"guardrails": [{"id": "G1", "title": "x", "point": [["input"]], "method": "rule", "on_error": "none"}]},
    {"guardrails": [{"id": "G1", "title": "x", "point": ["input"], "method": ["rule"], "on_error": "none"}]},
    {"guardrails": [{"id": "G1", "title": "x", "point": ["input"], "method": "rule", "on_error": "none",
                     "requires": "coordinator"}]},
    {"guardrails": [{"id": "G1", "title": "x", "point": ["input"], "method": "rule", "on_error": "none",
                     "requires": ["coordinator"]}]},
    {"guardrails": [], "version": 2},
])
def test_a_malformed_list_is_a_definition_error(repo_root: Path, tmp_path: Path, body: Any) -> None:
    path = tmp_path / "guardrails.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    agents, _ = load_definitions(repo_root)
    with pytest.raises(DefinitionError):
        load_guards(path, agents)


def test_a_list_that_is_not_utf8_is_a_definition_error(repo_root: Path, tmp_path: Path) -> None:
    path = tmp_path / "guardrails.json"
    path.write_bytes("{\"guardrails\": []}".encode("utf-8") + b"\xff\xfe")
    agents, _ = load_definitions(repo_root)
    with pytest.raises(DefinitionError):
        load_guards(path, agents)
