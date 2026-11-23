from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from app.tools import TOOLS

KNOWN_TOOLS = frozenset(TOOLS)  # app/tools.py — the one registry of Liner tools
# Router models only (app/liner.py is_router); liner-mark answers 400 unsupported_parameter.
ROUTING_STRATEGIES = ("cost", "balanced", "quality")
REASONING_EFFORTS = ("low", "medium", "high")  # what Liner's chat accepted on 2026-11-22 (anything else: 400)
KNOWN_GUARDRAILS = frozenset(f"G{i}" for i in range(1, 10))  # policies/guardrails.json lists the same (E3)
# Bundles of the shared source (PRD 2-6) plus the document-level items from PRD 2-5 `writes`.
ITEM_KINDS = frozenset({
    "sources", "evidence", "requirements", "screens", "tests", "questions", "decisions",
    "open_items", "confirmations", "versions", "events",
    "problem_statement", "scope", "brd", "prd", "findings", "prototype", "feedback", "screen_spec", "test_plan",
    "qa_checklist", "changes", "complaints", "flow_chart", "alternatives", "replies", "systems", "company",
})
# Original text, human confirmations, snapshots and the event log are written by the system only.
AGENT_WRITABLE_KINDS = ITEM_KINDS - {"sources", "systems", "company", "confirmations", "versions", "events"}
EXTERNAL_KINDS = frozenset({"human", "agent"})

AGENT_FIELDS: dict[str, type | tuple[type, ...]] = {
    "id": str, "name": str, "persona": str, "role": str, "instructions": str,
    "tools": list, "writes": list, "reads": list, "guardrails": list,
    "model": (str, type(None)), "version": int,
}
TEAM_FIELDS: dict[str, type] = {
    "id": str, "name": str, "members": list, "relations": list, "coordinator": str, "external": list,
}


class DefinitionError(ValueError):
    """An agent or team definition file is invalid."""


@dataclass(frozen=True)
class AgentDef:
    id: str
    name: str
    persona: str
    role: str
    instructions: str
    tools: tuple[str, ...]
    writes: tuple[str, ...]
    reads: tuple[str, ...]
    guardrails: tuple[str, ...]
    model: str | None
    version: int
    draft: bool
    routing_strategy: str | None = None
    reasoning_effort: str | None = None  # None: the model's own default


@dataclass(frozen=True)
class Relation:
    from_id: str
    to_id: str
    carries: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.from_id, "to": self.to_id, "carries": self.carries}


@dataclass(frozen=True)
class ExternalParty:
    id: str
    kind: str


@dataclass(frozen=True)
class TeamDef:
    id: str
    name: str
    members: tuple[str, ...]
    relations: tuple[Relation, ...]
    coordinator: str
    external: tuple[ExternalParty, ...]

    @property
    def participants(self) -> frozenset[str]:
        return frozenset(self.members) | {e.id for e in self.external}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "members": list(self.members),
            "coordinator": self.coordinator,
            "external": [{"id": e.id, "kind": e.kind} for e in self.external],
            "relations": [r.to_dict() for r in self.relations],
        }


def _check_fields(data: Any, fields: Mapping[str, type | tuple[type, ...]], source: str) -> None:
    if not isinstance(data, dict):
        raise DefinitionError(f"{source}: JSON 객체가 아닙니다")
    for name, expected in fields.items():
        if name not in data:
            raise DefinitionError(f"{source}: 필수 필드 '{name}' 가 없습니다")
        value = data[name]
        if isinstance(value, bool) or not isinstance(value, expected):
            raise DefinitionError(f"{source}: 필드 '{name}' 의 형식이 잘못됐습니다")


def _check_names(values: list[Any], allowed: frozenset[str], label: str, source: str) -> tuple[str, ...]:
    if not all(isinstance(v, str) for v in values):
        raise DefinitionError(f"{source}: {label} 목록에는 문자열만 올 수 있습니다")
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise DefinitionError(f"{source}: 알 수 없는 {label} {unknown}")
    return tuple(values)


def parse_agent(data: Any, source: str) -> AgentDef:
    _check_fields(data, AGENT_FIELDS, source)
    for name in ("id", "name", "persona", "role", "instructions"):
        if not data[name].strip():
            raise DefinitionError(f"{source}: 필드 '{name}' 가 비어 있습니다")
    if data["version"] < 1:
        raise DefinitionError(f"{source}: version 은 1 이상이어야 합니다")
    if not isinstance(data.get("draft", False), bool):
        raise DefinitionError(f"{source}: draft 는 true/false 여야 합니다")
    strategy = data.get("routing_strategy")
    if strategy is not None and strategy not in ROUTING_STRATEGIES:
        raise DefinitionError(f"{source}: routing_strategy 는 {'/'.join(ROUTING_STRATEGIES)} 중 하나여야 합니다")
    effort = data.get("reasoning_effort")
    if effort is not None and effort not in REASONING_EFFORTS:
        raise DefinitionError(f"{source}: reasoning_effort 는 {'/'.join(REASONING_EFFORTS)} 중 하나여야 합니다")
    return AgentDef(
        id=data["id"],
        name=data["name"],
        persona=data["persona"],
        role=data["role"],
        instructions=data["instructions"],
        tools=_check_names(data["tools"], KNOWN_TOOLS, "도구", source),
        writes=_check_names(data["writes"], AGENT_WRITABLE_KINDS, "쓰기 항목", source),
        reads=_check_names(data["reads"], ITEM_KINDS, "읽기 항목", source),
        guardrails=_check_names(data["guardrails"], KNOWN_GUARDRAILS, "가드레일", source),
        model=data["model"],
        version=data["version"],
        draft=data.get("draft", False),
        routing_strategy=strategy,
        reasoning_effort=effort,
    )


def _parse_external(items: list[Any], agents: Mapping[str, AgentDef], source: str) -> tuple[ExternalParty, ...]:
    parties = []
    for item in items:
        _check_fields(item, {"id": str, "kind": str}, f"{source} external")
        if item["kind"] not in EXTERNAL_KINDS:
            raise DefinitionError(f"{source}: external '{item['id']}' 의 kind 는 human/agent 여야 합니다")
        if item["kind"] == "agent" and item["id"] not in agents:
            raise DefinitionError(f"{source}: external 에이전트 '{item['id']}' 의 정의 파일이 없습니다")
        parties.append(ExternalParty(id=item["id"], kind=item["kind"]))
    return tuple(parties)


def _parse_relations(items: list[Any], participants: frozenset[str], source: str) -> tuple[Relation, ...]:
    relations = []
    for item in items:
        _check_fields(item, {"from": str, "to": str, "carries": str}, f"{source} relation")
        for end in (item["from"], item["to"]):
            if end not in participants:
                raise DefinitionError(f"{source}: 관계 끝점 '{end}' 가 팀 구성원이 아닙니다")
        if item["from"] == item["to"]:
            raise DefinitionError(f"{source}: 자기 자신과의 관계 '{item['from']}'")
        pair = {item["from"], item["to"]}
        if any({r.from_id, r.to_id} == pair for r in relations):
            raise DefinitionError(f"{source}: 중복된 관계 {item['from']} ↔ {item['to']}")
        relations.append(Relation(item["from"], item["to"], item["carries"]))
    return tuple(relations)


def parse_team(data: Any, agents: Mapping[str, AgentDef], source: str) -> TeamDef:
    _check_fields(data, TEAM_FIELDS, source)
    members = _check_names(data["members"], frozenset(agents), "구성원", source)
    if len(set(members)) != len(members):
        raise DefinitionError(f"{source}: members 에 중복된 구성원이 있습니다")
    if data["coordinator"] not in members:
        raise DefinitionError(f"{source}: coordinator '{data['coordinator']}' 가 members 에 없습니다")
    external = _parse_external(data["external"], agents, source)
    external_ids = [e.id for e in external]
    if len(set(external_ids)) != len(external_ids) or set(external_ids) & set(members):
        raise DefinitionError(f"{source}: external id 가 중복되거나 members 와 겹칩니다")
    participants = frozenset(members) | {e.id for e in external}
    return TeamDef(
        id=data["id"],
        name=data["name"],
        members=members,
        relations=_parse_relations(data["relations"], participants, source),
        coordinator=data["coordinator"],
        external=external,
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DefinitionError(f"{path.name}: JSON 을 읽을 수 없습니다 ({exc})") from exc


def load_agents(directory: Path) -> dict[str, AgentDef]:
    agents: dict[str, AgentDef] = {}
    for path in sorted(directory.glob("*.json")):
        agent = parse_agent(_read_json(path), path.name)
        if agent.id != path.stem:
            raise DefinitionError(f"{path.name}: 파일 이름과 id '{agent.id}' 가 다릅니다")
        agents[agent.id] = agent
    return agents


def load_team(path: Path, agents: Mapping[str, AgentDef]) -> TeamDef:
    team = parse_team(_read_json(path), agents, path.name)
    if team.id != path.stem:
        raise DefinitionError(f"{path.name}: 파일 이름과 id '{team.id}' 가 다릅니다")
    return team


def load_definitions(root: Path) -> tuple[dict[str, AgentDef], dict[str, TeamDef]]:
    agents = load_agents(root / "agents")
    teams = {p.stem: load_team(p, agents) for p in sorted((root / "teams").glob("*.json"))}
    return agents, teams


def can_message(team: TeamDef, from_id: str, to_id: str) -> bool:
    """FR-03: direct message only along a declared relation; callers route other traffic via the coordinator."""
    for end in (from_id, to_id):
        if end not in team.participants:
            raise DefinitionError(f"'{end}' 는 팀 '{team.id}' 의 참여자가 아닙니다")
    if from_id == to_id:
        return False
    return any({r.from_id, r.to_id} == {from_id, to_id} for r in team.relations)
