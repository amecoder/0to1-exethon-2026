from __future__ import annotations
"""에이전트 OS 1단계: a business flow is a file (flows/*.json), not code.

A flow lists its stages in order — input (the client's request), work (agents run a registered job, app/runs.py)
and confirm (a person approves or sends it back to an earlier work stage). The engine (app/orchestrator.py) walks
the list. A flow file is checked when it is read, so a broken one never starts.
"""

import json
import re
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT

DEFAULT_FLOW = REPO_ROOT / "flows" / "requirements.json"
KINDS = ("input", "work", "confirm")
FLOW_KEYS = frozenset({"id", "title", "stages"})
STAGE_KEYS = frozenset({"id", "kind", "title", "agents", "rework", "run", "on_approve", "features"})
STAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,20}")


class FlowError(ValueError):
    """A flow file that cannot run; the message says which stage and why."""


@dataclass(frozen=True)
class StageSpec:
    id: str
    kind: str  # input | work | confirm
    agents: tuple[str, ...] = ()
    title: str = ""
    rework: str | None = None  # confirm: the work stage a rejection returns to
    run: str | None = None  # work: the registered job (app/runs.py)
    on_approve: tuple[str, ...] = ()  # confirm: what approving does, in order (app/hooks.py)
    features: tuple[str, ...] = ()  # confirm: what a person can do there besides approve/reject (app/hooks.py)


@dataclass(frozen=True)
class Flow:
    id: str
    title: str
    stages: tuple[StageSpec, ...]

    def stage(self, stage_id: str) -> StageSpec:
        found = next((s for s in self.stages if s.id == stage_id), None)
        if found is None:
            raise FlowError(f"이 흐름에 없는 단계: {stage_id}")
        return found

    @property
    def first(self) -> StageSpec:
        return self.stages[0]

    def running(self, run: str) -> StageSpec | None:
        """The work stage that runs this registered job, if the flow has one."""
        return next((s for s in self.stages if s.kind == "work" and s.run == run), None)

    def with_feature(self, feature: str) -> StageSpec | None:
        return next((s for s in self.stages if feature in s.features), None)

    def has(self, stage_id: str) -> bool:
        return any(s.id == stage_id for s in self.stages)

    def next(self, stage_id: str) -> StageSpec | None:
        ids = [s.id for s in self.stages]
        index = ids.index(stage_id)
        return self.stages[index + 1] if index + 1 < len(self.stages) else None

    def before(self, stage_id: str) -> tuple[StageSpec, ...]:
        return self.stages[:[s.id for s in self.stages].index(stage_id)]


def load_flow(path: Path, agents: Collection[str] | None = None) -> Flow:
    """Read and check a flow file. `agents`: the defined agent ids (unchecked when None)."""
    from app.hooks import APPROVE_HOOKS, FEATURES  # registries import the workspace; read lazily
    from app.runs import REQUIRES, RUNS  # the registry imports the stage modules; read lazily

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlowError(f"흐름 파일을 읽지 못했어요: {path}: {exc}") from exc
    raw = data.get("stages") if isinstance(data, Mapping) else None
    if not isinstance(raw, list) or not raw:
        raise FlowError(f"{path}: stages 가 비어 있어요")
    for key in ("id", "title"):
        if key in data and not isinstance(data[key], str):
            raise FlowError(f"{path}: {key} 는 글자로 적어요")
    extra = sorted(set(data) - FLOW_KEYS)
    if extra:
        raise FlowError(f"{path}: 모르는 키 「{extra[0]}」 (쓸 수 있는 키: {', '.join(sorted(FLOW_KEYS))})")
    stages = tuple(_stage(item, n) for n, item in enumerate(raw, start=1))
    _check(stages, Registries(set(RUNS), REQUIRES, set(APPROVE_HOOKS), set(FEATURES)), agents)
    return Flow(str(data.get("id", Path(path).stem)), str(data.get("title", "")), stages)


@dataclass(frozen=True)
class Registries:
    """What a flow file may name: jobs (and what each needs before it), approve hooks, confirm features."""
    runs: Collection[str]
    requires: Mapping[str, tuple[str, ...]]
    hooks: Collection[str]
    features: Collection[str]


def _stage(item: Any, n: int) -> StageSpec:
    if not isinstance(item, Mapping) or not str(item.get("id", "")).strip():
        raise FlowError(f"{n}번째 단계에 id 가 없어요")
    if not isinstance(item["id"], str) or not STAGE_ID.fullmatch(item["id"]):
        raise FlowError(f"{n}번째 단계의 id 「{item['id']}」 는 영문·숫자·-·_ 20자 이내여야 해요")
    extra = sorted(set(item) - STAGE_KEYS)
    if extra:
        raise FlowError(f"{item['id']}: 모르는 키 「{extra[0]}」 (쓸 수 있는 키: {', '.join(sorted(STAGE_KEYS))})")
    lists = {k: item.get(k, []) for k in ("agents", "on_approve", "features")}
    for key, value in lists.items():
        if not isinstance(value, list):
            raise FlowError(f"{item['id']}: {key} 는 목록이어야 해요 (예: [\"pm\"])")
    return StageSpec(id=item["id"], kind=str(item.get("kind", "")), title=str(item.get("title", "")),
                     agents=tuple(str(a) for a in lists["agents"]),
                     on_approve=tuple(str(h) for h in lists["on_approve"]),
                     features=tuple(str(f) for f in lists["features"]),
                     rework=str(item["rework"]) if item.get("rework") else None,
                     run=str(item["run"]) if item.get("run") else None)


def _check(stages: tuple[StageSpec, ...], reg: Registries, agents: Collection[str] | None) -> None:
    if stages[0].kind != "input":
        raise FlowError(f"첫 단계는 input 이어야 해요 (지금 {stages[0].id}: {stages[0].kind})")
    seen: dict[str, StageSpec] = {}
    for s in stages:
        if s.id in seen:
            raise FlowError(f"단계 id {s.id} 가 두 번 있어요")
        if s.kind == "input" and seen:
            raise FlowError(f"{s.id}: input 은 첫 단계 하나뿐이어야 해요")
        if s.kind not in KINDS:
            raise FlowError(f"{s.id}: 종류 {s.kind} 는 없어요 ({' / '.join(KINDS)} 중 하나)")
        _check_work(s, seen, reg)
        _check_confirm(s, seen, reg)
        unknown = [a for a in s.agents if agents is not None and a not in agents]
        if unknown:
            raise FlowError(f"{s.id}: 정의되지 않은 에이전트 {', '.join(unknown)}")
        seen[s.id] = s
    runs = [s.run for s in stages if s.kind == "work"]
    if "requirements" in runs and "finalize" not in runs[runs.index("requirements"):]:
        raise FlowError("requirements(질문 카드) 단계 뒤에는 답을 반영할 finalize 단계가 있어야 해요")


def _check_work(s: StageSpec, seen: Mapping[str, StageSpec], reg: Registries) -> None:
    if s.kind != "work":
        if s.run:
            raise FlowError(f"{s.id}: run 은 work 단계에만 적어요")
        if s.kind == "input" and s.rework:
            raise FlowError(f"{s.id}: rework 는 confirm 단계에만 적어요")
        return
    if s.run not in reg.runs:
        raise FlowError(f"{s.id}: 등록되지 않은 일 「{s.run}」 (등록된 일: {', '.join(sorted(reg.runs))})")
    if s.rework:
        raise FlowError(f"{s.id}: rework 는 confirm 단계에만 적어요")
    first = next((p for p in seen.values() if p.run == s.run), None)
    if first is not None:
        raise FlowError(f"{s.id}: 일 「{s.run}」 은 이미 {first.id} 가 돌려요 (한 흐름에 한 번)")
    done = {p.run for p in seen.values()}
    for need in reg.requires.get(s.run, ()):
        if need not in done:
            raise FlowError(f"{s.id}: 「{s.run}」 앞에는 「{need}」 단계가 있어야 해요")


def _check_confirm(s: StageSpec, seen: Mapping[str, StageSpec], reg: Registries) -> None:
    if s.kind == "confirm" and (s.rework not in seen or seen[s.rework].kind != "work"):
        raise FlowError(f"{s.id}: rework 「{s.rework}」 는 이 확인보다 앞의 work 단계여야 해요")
    if (s.on_approve or s.features) and s.kind != "confirm":
        raise FlowError(f"{s.id}: on_approve·features 는 confirm 단계에만 적어요")
    if len(set(s.on_approve)) != len(s.on_approve):
        raise FlowError(f"{s.id}: 같은 승인 동작을 두 번 적었어요")
    for name in s.on_approve:
        if name not in reg.hooks:
            raise FlowError(f"{s.id}: 등록되지 않은 승인 동작 「{name}」 (등록된 것: {', '.join(sorted(reg.hooks))})")
    for name in s.features:
        if name not in reg.features:
            raise FlowError(f"{s.id}: 모르는 기능 「{name}」 (있는 것: {', '.join(sorted(reg.features))})")
        first = next((p for p in seen.values() if name in p.features), None)
        if first is not None:
            raise FlowError(f"{s.id}: 기능 「{name}」 은 이미 {first.id} 에 있어요")
    if "requirement_review" in s.features and not any(p.run == "finalize" for p in seen.values()):
        raise FlowError(f"{s.id}: requirement_review 는 그 앞에 finalize 단계가 있어야 해요")


def main(argv: Sequence[str]) -> int:
    """`python -m app.flow [file…]`: check flow files (default flows/*.json) and print each one's stages."""
    from app.definitions import load_definitions  # only the command needs the team files
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a cp949 console cannot show every character of a title
    agents, _ = load_definitions(REPO_ROOT)
    failed = 0
    for path in [Path(a) for a in argv] or sorted((REPO_ROOT / "flows").glob("*.json")):
        try:
            flow = load_flow(path, agents)
        except FlowError as exc:
            print(f"X {exc}")
            failed = 1
            continue
        print(f"OK {flow.id} - 단계 {len(flow.stages)}개 - {flow.title}")
        for s in flow.stages:
            print(f"  {s.id:<5} {s.kind:<8} {s.run or s.rework or '':<13} {','.join(s.on_approve):<28} {','.join(s.features)}")
    return failed


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
