from __future__ import annotations
"""에이전트 OS 6단계 (E3, 11-21): the guardrails as a declared list (policies/guardrails.json), checked at startup.

Each entry says where the guard acts (input / output / tool / stage), whether a rule or a model judges, what
happens when it cannot judge (open: pass and record · closed: block · none: nothing can fail) and which agent's
tool it needs. Thresholds and switches stay in environment variables; this file does not move any call site.
A team whose agent lacks a needed tool does not start (G9 used to switch off silently when its tool was missing).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.definitions import KNOWN_GUARDRAILS, AgentDef, DefinitionError
from app.tools import TOOLS

POINTS = frozenset({"input", "output", "tool", "stage"})
METHODS = frozenset({"rule", "model", "rule+model"})
ON_ERROR = frozenset({"open", "closed", "none"})
KEYS = frozenset({"id", "title", "point", "method", "on_error", "requires"})
# The tools a guard's model check runs with, kept in code (a file line can be deleted): the file must say the same.
REQUIRED: Mapping[str, tuple[tuple[str, str], ...]] = {
    "G1": (("fde_lead", "liner_decisions"),),  # the model half of the citation check (stage_problem g1_support)
    "G9": (("coordinator", "liner_decisions"),),  # the purpose check (app/policy.py)
}


@dataclass(frozen=True)
class Guard:
    id: str
    title: str
    point: tuple[str, ...]
    method: str
    on_error: str
    requires: tuple[tuple[str, str], ...] = ()  # (agent id, tool id)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "point": list(self.point), "method": self.method,
                "on_error": self.on_error, "requires": [{"agent": a, "tool": t} for a, t in self.requires]}


def load_guards(path: Path, agents: Mapping[str, AgentDef]) -> tuple[Guard, ...]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DefinitionError(f"안전장치 목록을 읽지 못했어요: {path}: {exc}") from exc
    if not isinstance(data, Mapping) or set(data) != {"guardrails"} or not isinstance(data["guardrails"], list):
        raise DefinitionError(f"{path}: 안전장치 목록은 {{\"guardrails\": [...]}} 하나만 적어요")
    guards = tuple(_guard(item) for item in data["guardrails"])
    seen: set[str] = set()
    for g in guards:
        if g.id in seen:
            raise DefinitionError(f"안전장치 {g.id} 가 두 번 있어요")
        seen.add(g.id)
        _check_requires(g, agents)
    missing = sorted(KNOWN_GUARDRAILS - seen)
    if missing:
        raise DefinitionError(f"목록에 빠진 안전장치: {', '.join(missing)} (지우면 그 안전장치가 조용히 꺼질 수 있어요)")
    for agent in agents.values():
        unknown = sorted(set(agent.guardrails) - seen)
        if unknown:
            raise DefinitionError(f"{agent.id}: 목록에 없는 안전장치 {', '.join(unknown)}")
    return guards


def _guard(item: Any) -> Guard:
    if not isinstance(item, Mapping) or not isinstance(item.get("id"), str) or item["id"] not in KNOWN_GUARDRAILS:
        raise DefinitionError(f"안전장치 id 는 {', '.join(sorted(KNOWN_GUARDRAILS))} 중 하나여야 해요: {item!r}"[:200])
    gid = item["id"]
    extra = sorted(set(item) - KEYS)
    if extra:
        raise DefinitionError(f"{gid}: 모르는 키 「{extra[0]}」")
    point = item.get("point")
    if not isinstance(point, list) or not point or not all(isinstance(p, str) and p in POINTS for p in point):
        raise DefinitionError(f"{gid}: point {point!r} 는 {', '.join(sorted(POINTS))} 중에서 골라 목록으로 적어요")
    for key, allowed in (("method", METHODS), ("on_error", ON_ERROR)):
        value = item.get(key)
        if not isinstance(value, str) or value not in allowed:
            raise DefinitionError(f"{gid}: {key} 「{value}」 는 {', '.join(sorted(allowed))} 중 하나여야 해요")
    raw = item.get("requires", [])
    if not isinstance(raw, list) or not all(isinstance(r, Mapping) and isinstance(r.get("agent"), str)
                                            and isinstance(r.get("tool"), str) for r in raw):
        raise DefinitionError(f"{gid}: requires 는 [{{\"agent\": …, \"tool\": …}}] 목록으로 적어요")
    requires = tuple((r["agent"], r["tool"]) for r in raw)
    return Guard(gid, str(item.get("title", "")), tuple(point), item["method"], item["on_error"], requires)


def _check_requires(g: Guard, agents: Mapping[str, AgentDef]) -> None:
    if set(g.requires) != set(REQUIRED.get(g.id, ())):
        need = ", ".join(f"{a} 의 {t}" for a, t in REQUIRED.get(g.id, ())) or "없음"
        raise DefinitionError(f"{g.id}: requires 가 코드와 달라요 (코드가 쓰는 도구: {need})")
    for agent, tool in g.requires:
        if agent not in agents:
            raise DefinitionError(f"{g.id}: 정의되지 않은 에이전트 {agent}")
        if tool not in TOOLS:
            raise DefinitionError(f"{g.id}: 등록되지 않은 도구 {tool}")
        if tool not in agents[agent].tools:
            raise DefinitionError(f"{g.id} {g.title}: {agent} 에게 {tool} 도구가 있어야 합니다 "
                                  f"(agents/{agent}.json 의 tools)")
