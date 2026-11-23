from __future__ import annotations
"""FR-16 demo mode: record a run's events to a file, and rebuild the shared source by replaying them.

Replay is pure data processing — it never touches Liner. Recording drives a real Orchestrator; who
answers the question cards and confirmations is a `Decider` (a human at a prompt, or a test script).
"""

import copy
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.orchestrator import COMPLETED, Orchestrator
from app.store import empty_source
from app.views import client_todo
from app.workspace import Workspace

DEMO_FORMAT = "exethon-demo-run/1"
FAKE_NOTICE = "가짜 응답으로 만든 임시 녹화본 — 실제 실행 기록으로 교체 예정"
REAL_NOTICE = "실제 실행 기록 — Liner API 를 실제로 호출한 실행을 녹화했습니다"
CLIENT_NAME = "발주사"
COMPARED = ("requirements", "screens", "tests")
MAX_ROUNDS = 60


class DemoFileError(RuntimeError):
    """The demo recording is missing or not in the expected format."""


class RecordingError(RuntimeError):
    """The run being recorded could not reach CP4 approval."""


# --- replay -------------------------------------------------------------------------------------
def _upsert(items: list[dict[str, Any]], item: Mapping[str, Any]) -> list[dict[str, Any]]:
    new = copy.deepcopy(dict(item))
    if any(i.get("id") == new.get("id") for i in items):
        return [new if i.get("id") == new.get("id") else i for i in items]
    return [*items, new]


def apply_event(source: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    data, kind = event.get("data", {}), event.get("type")
    out = {**source, "events": [*source.get("events", []), copy.deepcopy(dict(event))]}
    if kind == "item_written":
        out[data["kind"]] = _upsert(list(source.get(data["kind"], [])), data["item"])
    elif kind == "bundle_cleared":
        out[data["kind"]] = []
    elif kind == "confirmation":
        out["confirmations"] = [*source.get("confirmations", []), copy.deepcopy(dict(data))]
    elif kind == "version_created":
        out["versions"] = [*source.get("versions", []), {
            "version": data["version"], "confirmation_id": data["confirmation_id"], "created_at": event.get("ts"),
            "snapshot": {}}]
    elif kind == "pipeline":
        out["meta"] = {**source.get("meta", {}), "pipeline": {**dict(data), "feedback": None}}
    elif kind == "recheck_required":
        out["meta"] = {**source.get("meta", {}), "recheck": copy.deepcopy(dict(data))}
    elif kind == "project_named":
        out["meta"] = {**source.get("meta", {}), "name": {"value": data.get("name"), "by": event.get("actor")}}
    elif kind == "recheck_cleared":
        out["meta"] = {k: v for k, v in source.get("meta", {}).items() if k != "recheck"}
    return out


def replay(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    source: dict[str, Any] = empty_source()
    for event in events:
        source = apply_event(source, event)
    return source


def compared_bundles(source: Mapping[str, Any]) -> dict[str, Any]:
    return {kind: copy.deepcopy(list(source.get(kind, []))) for kind in COMPARED}


# --- recording file -------------------------------------------------------------------------------
SUMMARY_FIELDS = ("models", "total_cost_usd", "duration_seconds")


def _ts(event: Mapping[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.get("ts")))
    except ValueError:
        return None


def run_summary(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Header totals for the demo banner: who answered, what it cost, how long it took.

    models: the model that actually answered each chat call (`answered_model` from the router, else `model`).
    total_cost_usd: first credit balance minus the last (same rule as the header and G7) when two readings
    exist, else the sum of per-call `usage.cost`, else None. duration_seconds: last event time − first.
    """
    chats = [e.get("data", {}) for e in events if e.get("type") == "liner_chat"]
    models = sorted({str(d.get("answered_model") or d.get("model")) for d in chats
                     if d.get("answered_model") or d.get("model")})
    readings = [e["data"]["balance_usd"] for e in events if e.get("type") == "credits"
                and isinstance(e.get("data", {}).get("balance_usd"), (int, float))]
    costs = [e["data"]["cost"] for e in events if str(e.get("type", "")).startswith("liner_")
             and isinstance(e.get("data", {}).get("cost"), (int, float))]
    if len(readings) >= 2:
        cost: float | None = round(max(0.0, readings[0] - readings[-1]), 6)
    else:
        cost = round(sum(costs), 6) if costs else None
    times = [t for t in (_ts(e) for e in events) if t is not None]
    duration = int((times[-1] - times[0]).total_seconds()) if len(times) >= 2 else None
    return {"models": models, "total_cost_usd": cost, "duration_seconds": duration}


def make_recording(ws: Workspace, kind: str, model: str | None, project_name: str) -> dict[str, Any]:
    if kind not in ("fake", "real"):
        raise ValueError(f"kind 는 fake/real 중 하나여야 합니다: {kind!r}")
    source = ws.source
    return {
        "format": DEMO_FORMAT, "kind": kind, "notice": FAKE_NOTICE if kind == "fake" else REAL_NOTICE,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model,
        "project_name": project_name, "event_count": len(source["events"]), **run_summary(source["events"]),
        "final": compared_bundles(source), "events": source["events"],
    }


def write_recording(recording: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recording, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_recording(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DemoFileError(f"시연 녹화 파일이 없습니다: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DemoFileError(f"시연 녹화 파일을 읽을 수 없습니다: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != DEMO_FORMAT or not isinstance(data.get("events"), list):
        raise DemoFileError(f"시연 녹화 파일 형식이 {DEMO_FORMAT} 가 아닙니다")
    if data.get("kind") not in ("fake", "real") or not data.get("recorded_at"):
        raise DemoFileError("시연 녹화 파일에 kind(fake/real) 또는 recorded_at 이 없습니다")
    return data


# --- driving a run to record ----------------------------------------------------------------------
class Decider(Protocol):
    def answer(self, todo: Mapping[str, Any]) -> tuple[str, str | None]:
        """Return (kind, value) for the question card in `todo` (kind: choice | unknown | free_text)."""

    def confirm(self, todo: Mapping[str, Any]) -> tuple[bool, str | None, dict[str, str]]:
        """Return (approved, reject reason, waivers) for the confirmation in `todo`."""


def drive(orch: Orchestrator, ws: Workspace, chunks: list[str], decider: Decider) -> None:
    """S1 → … → CP4 approval. Raises RecordingError on G3 block, a failed stage or an unexpected state."""
    if orch.ingest(chunks).blocked:
        raise RecordingError("입력에 민감 정보가 있어 저장하지 않았습니다. 가린 메모로 다시 실행하세요")
    drive_to_completion(orch, ws, decider)


def drive_to_completion(orch: Orchestrator, ws: Workspace, decider: Decider) -> None:
    """Run and answer until completed (also used after a CP5 change sends the work back to S5)."""
    orch.advance()
    for _ in range(MAX_ROUNDS):
        status = ws.pipeline["status"]
        if status == COMPLETED:
            return
        if status == "failed":
            raise RecordingError(f"{ws.pipeline['stage']} 실패: {ws.pipeline['error']}")
        todo = client_todo(ws.source)
        if todo["kind"] == "question":
            kind, value = decider.answer(todo)
            orch.answer(todo["question"]["id"], kind, value)
        elif todo["kind"] == "answers_review":
            orch.submit_answers()
        elif todo["kind"] == "confirmation":
            approved, reason, waivers = decider.confirm(todo)
            orch.confirm(todo["cp"], approved, CLIENT_NAME, reason, waivers)
        else:
            raise RecordingError(f"예상하지 못한 상태입니다: {ws.pipeline['stage']} · {status}")
        orch.advance()
    raise RecordingError(f"{MAX_ROUNDS}번 주고받아도 CP4 승인까지 가지 못했습니다")
