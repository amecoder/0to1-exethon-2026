from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.definitions import (
    DefinitionError,
    can_message,
    load_agents,
    load_definitions,
    load_team,
    parse_agent,
    parse_team,
)

AGENT_IDS = {"coordinator", "fde_lead", "researcher", "pm", "designer", "developer", "qa", "consumer"}

# Relationship doc (2026-11-13) section 2, as unordered pairs.
EXPECTED_RELATIONS = {
    frozenset({"client", "coordinator"}),
    frozenset({"consumer", "coordinator"}),
    frozenset({"coordinator", "fde_lead"}),
    frozenset({"coordinator", "researcher"}),
    frozenset({"coordinator", "pm"}),
    frozenset({"coordinator", "designer"}),
    frozenset({"coordinator", "developer"}),
    frozenset({"coordinator", "qa"}),
    frozenset({"fde_lead", "researcher"}),
    frozenset({"researcher", "pm"}),
    frozenset({"pm", "designer"}),
    frozenset({"pm", "qa"}),
    frozenset({"designer", "developer"}),
    frozenset({"qa", "developer"}),
}


def valid_agent(**overrides: object) -> dict:
    base = {
        "id": "tester",
        "name": "테스터",
        "persona": "꼼꼼하다",
        "role": "검사한다",
        "instructions": "검사하라",
        "tools": ["liner_search"],
        "writes": ["evidence"],
        "reads": ["sources"],
        "guardrails": ["G1"],
        "model": None,
        "version": 1,
    }
    return {**base, **overrides}


@pytest.fixture
def defs(repo_root: Path):
    return load_definitions(repo_root)


def test_all_eight_agents_load_and_are_drafts(defs) -> None:
    agents, _ = defs
    assert set(agents) == AGENT_IDS
    assert all(agent.draft for agent in agents.values())


def test_default_team_members_and_external(defs) -> None:
    _, teams = defs
    team = teams["default"]
    assert set(team.members) == AGENT_IDS - {"consumer"}
    assert team.coordinator == "coordinator"
    assert {(e.id, e.kind) for e in team.external} == {("client", "human"), ("consumer", "agent")}


def test_team_relations_equal_relationship_doc(defs) -> None:
    _, teams = defs
    relations = teams["default"].relations
    pairs = [frozenset({r.from_id, r.to_id}) for r in relations]
    assert len(pairs) == len(set(pairs)), "duplicate relation"
    assert set(pairs) == EXPECTED_RELATIONS
    assert all(r.carries.strip() for r in relations)


def test_researcher_matches_prd_example(defs) -> None:
    agents, _ = defs
    researcher = agents["researcher"]
    assert researcher.tools == ("liner_ai_search", "liner_search")
    assert researcher.writes == ("evidence", "alternatives")


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"persona": None}, "persona"),
        ({"tools": ["shell_exec"]}, "shell_exec"),
        ({"writes": ["salary"]}, "salary"),
        ({"writes": ["confirmations"]}, "confirmations"),
        ({"reads": ["nope"]}, "nope"),
        ({"guardrails": ["G10"]}, "G10"),  # G9 is a known guard since E3 (11-21)
        ({"version": "1"}, "version"),
    ],
)
def test_bad_agent_rejected(overrides: dict, fragment: str) -> None:
    with pytest.raises(DefinitionError) as exc:
        parse_agent(valid_agent(**overrides), "tester.json")
    assert fragment in str(exc.value)


def test_missing_field_rejected() -> None:
    data = valid_agent()
    del data["instructions"]
    with pytest.raises(DefinitionError, match="instructions"):
        parse_agent(data, "tester.json")


def test_bad_agent_file_rejected_by_loader(tmp_path: Path) -> None:
    (tmp_path / "tester.json").write_text(json.dumps(valid_agent(tools=["rm_rf"])), encoding="utf-8")
    with pytest.raises(DefinitionError, match="rm_rf"):
        load_agents(tmp_path)


def test_file_name_must_match_id(tmp_path: Path) -> None:
    (tmp_path / "other.json").write_text(json.dumps(valid_agent()), encoding="utf-8")
    with pytest.raises(DefinitionError, match="other.json"):
        load_agents(tmp_path)


def test_team_relation_to_non_member_rejected(tmp_path: Path, defs) -> None:
    agents, _ = defs
    team = {
        "id": "t",
        "name": "팀",
        "members": ["coordinator", "pm"],
        "coordinator": "coordinator",
        "external": [],
        "relations": [{"from": "pm", "to": "qa", "carries": "요구사항"}],
    }
    path = tmp_path / "t.json"
    path.write_text(json.dumps(team), encoding="utf-8")
    with pytest.raises(DefinitionError, match="qa"):
        load_team(path, agents)


def test_team_coordinator_must_be_member(tmp_path: Path, defs) -> None:
    agents, _ = defs
    team = {
        "id": "t",
        "name": "팀",
        "members": ["pm"],
        "coordinator": "coordinator",
        "external": [],
        "relations": [],
    }
    path = tmp_path / "t.json"
    path.write_text(json.dumps(team), encoding="utf-8")
    with pytest.raises(DefinitionError, match="coordinator"):
        load_team(path, agents)


@pytest.mark.parametrize(
    "sender, receiver, allowed",
    [
        ("pm", "developer", False),
        ("developer", "pm", False),
        ("fde_lead", "pm", False),
        ("designer", "qa", False),
        ("client", "pm", False),
        ("consumer", "designer", False),
        ("pm", "qa", True),
        ("qa", "pm", True),
        ("fde_lead", "researcher", True),
        ("designer", "developer", True),
        ("developer", "qa", True),
        ("pm", "coordinator", True),
        ("coordinator", "developer", True),
        ("client", "coordinator", True),
        ("coordinator", "consumer", True),
        ("pm", "pm", False),
    ],
)
def test_can_message(defs, sender: str, receiver: str, allowed: bool) -> None:
    _, teams = defs
    assert can_message(teams["default"], sender, receiver) is allowed


def test_can_message_every_member_reaches_coordinator(defs) -> None:
    _, teams = defs
    team = teams["default"]
    for member in [*team.members, *(e.id for e in team.external)]:
        if member != team.coordinator:
            assert can_message(team, member, team.coordinator)
            assert can_message(team, team.coordinator, member)


def test_can_message_unknown_participant_raises(defs) -> None:
    _, teams = defs
    with pytest.raises(DefinitionError, match="ghost"):
        can_message(teams["default"], "ghost", "coordinator")


# --- review fixes (2026-11-14): relations are the only source of truth for direct messages


def _team_data(repo_root: Path) -> dict:
    return json.loads((repo_root / "teams" / "default.json").read_text(encoding="utf-8"))


def _agent_data(repo_root: Path, agent_id: str = "qa") -> dict:
    return json.loads((repo_root / "agents" / f"{agent_id}.json").read_text(encoding="utf-8"))


def test_can_message_has_no_coordinator_shortcut(defs, repo_root: Path) -> None:
    agents, _ = defs
    data = _team_data(repo_root)
    data["relations"] = [r for r in data["relations"] if {r["from"], r["to"]} != {"coordinator", "qa"}]
    team = parse_team(data, agents, "synthetic.json")
    assert can_message(team, "coordinator", "qa") is False
    assert can_message(team, "qa", "coordinator") is False


@pytest.mark.parametrize("field", ["tools", "writes", "reads", "guardrails"])
def test_non_string_list_item_is_definition_error(repo_root: Path, field: str) -> None:
    data = _agent_data(repo_root)
    data[field] = [["x"]]
    with pytest.raises(DefinitionError):
        parse_agent(data, "qa.json")


@pytest.mark.parametrize("version", [0, -5])
def test_version_must_be_positive(repo_root: Path, version: int) -> None:
    data = _agent_data(repo_root)
    data["version"] = version
    with pytest.raises(DefinitionError, match="version"):
        parse_agent(data, "qa.json")


def test_draft_must_be_boolean(repo_root: Path) -> None:
    data = _agent_data(repo_root)
    data["draft"] = "no"
    with pytest.raises(DefinitionError, match="draft"):
        parse_agent(data, "qa.json")


def test_duplicate_members_rejected(defs, repo_root: Path) -> None:
    agents, _ = defs
    data = _team_data(repo_root)
    data["members"] = [*data["members"], "qa"]
    with pytest.raises(DefinitionError, match="중복"):
        parse_team(data, agents, "synthetic.json")


def test_external_id_must_not_overlap_members(defs, repo_root: Path) -> None:
    agents, _ = defs
    data = _team_data(repo_root)
    data["external"] = [*data["external"], {"id": "pm", "kind": "human"}]
    with pytest.raises(DefinitionError):
        parse_team(data, agents, "synthetic.json")


def test_duplicate_relation_rejected(defs, repo_root: Path) -> None:
    agents, _ = defs
    data = _team_data(repo_root)
    first = data["relations"][0]
    data["relations"] = [*data["relations"], {"from": first["to"], "to": first["from"], "carries": "중복"}]
    with pytest.raises(DefinitionError, match="중복"):
        parse_team(data, agents, "synthetic.json")
