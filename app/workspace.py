from __future__ import annotations
"""Shared source with a write gate (FR-07, G4) and the event log attached (FR-15)."""

import copy
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.definitions import AgentDef
from app.events import EventLog

SYSTEM = "system"
# What a version snapshot (CP2 → v1, CP3 → v2, CP5 → next) keeps.
SNAPSHOT_KINDS = ("sources", "systems", "company", "evidence", "alternatives", "problem_statement", "scope", "requirements", "questions",
                  "decisions", "open_items", "findings", "screens", "tests", "screen_spec", "test_plan", "brd", "prd", "feedback")
INITIAL_PIPELINE: dict[str, Any] = {
    "stage": "S1", "status": "awaiting_input", "active_agent": None, "error": None, "feedback": None,
}


class WriteRejectedError(RuntimeError):
    """Raised when the system itself attempts a forbidden write (e.g. sources after S1)."""


class Workspace:
    """Holds one project's shared source. Every change goes through write()/system methods and is logged."""

    def __init__(
        self,
        source: Mapping[str, Any],
        agents: Mapping[str, AgentDef],
        on_change: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        data = copy.deepcopy(dict(source))
        meta = data.get("meta", {})
        self._source = {**data, "meta": {**meta, "pipeline": {**INITIAL_PIPELINE, **meta.get("pipeline", {})}}}
        self._agents = agents
        self._on_change = on_change
        self.log = EventLog(data.get("events", []), on_append=lambda _event: self._changed())

    # --- reading -------------------------------------------------------------------------------
    @property
    def source(self) -> dict[str, Any]:
        return copy.deepcopy({**self._source, "events": list(self.log.events)})

    @property
    def pipeline(self) -> dict[str, Any]:
        return dict(self._source["meta"]["pipeline"])

    @property
    def meta(self) -> dict[str, Any]:
        return copy.deepcopy(self._source["meta"])

    def items(self, kind: str) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(self._source.get(kind, [])))

    def get(self, kind: str, item_id: str) -> dict[str, Any] | None:
        return next((i for i in self.items(kind) if i.get("id") == item_id), None)

    def next_id(self, kind: str, prefix: str) -> str:
        return f"{prefix}-{len(self._source.get(kind, [])) + 1:02d}"

    # --- events --------------------------------------------------------------------------------
    def emit(self, type_: str, actor: str, data: Mapping[str, Any]) -> dict[str, Any]:
        return self.log.append(type_, actor, data, stage=self.pipeline["stage"])

    def guardrail(self, gid: str, outcome: str, detail: str, actor: str = SYSTEM, **extra: Any) -> None:
        self.emit("guardrail", actor, {"id": gid, "outcome": outcome, "detail": detail, **extra})

    # --- gated writes --------------------------------------------------------------------------
    def write(self, actor: str, kind: str, item: Mapping[str, Any]) -> bool:
        """Upsert one item by id if `actor` may write `kind`; otherwise record the rejection."""
        if not self._allowed(actor, kind):
            return False
        new_item = copy.deepcopy(dict(item))
        current = self._source.get(kind, [])
        if any(i.get("id") == new_item.get("id") for i in current):
            updated = [new_item if i.get("id") == new_item.get("id") else i for i in current]
        else:
            updated = [*current, new_item]
        self._set(kind, updated)
        self.emit("item_written", actor, {"kind": kind, "item": new_item})
        return True

    def write_all(self, actor: str, kind: str, items: Sequence[Mapping[str, Any]]) -> bool:
        """Replace a whole bundle (one agent's rework). Each item is still logged for replay."""
        if not self._allowed(actor, kind):
            return False
        self._set(kind, [])
        self.emit("bundle_cleared", actor, {"kind": kind})
        for item in items:
            self.write(actor, kind, item)
        return True

    def _allowed(self, actor: str, kind: str) -> bool:
        if kind == "sources":
            self.guardrail("G4", "blocked", "원문(SRC-)은 S1 이후 누구도 수정할 수 없습니다", actor=actor)
            reason = "sources are immutable"
        elif actor not in self._agents:
            reason = "unknown agent"
        elif kind not in self._agents[actor].writes:
            reason = f"'{kind}' is not in writes of {actor}"
        else:
            return True
        self.emit("write_rejected", actor, {"kind": kind, "reason": reason})
        return False

    # --- system-only writes --------------------------------------------------------------------
    def add_sources(self, sources: Sequence[Mapping[str, Any]]) -> None:
        """S1 only: store original sentences once, then lock them (G4)."""
        if self._source["meta"].get("sources_locked"):
            self.guardrail("G4", "blocked", "원문(SRC-)은 이미 고정되었습니다")
            raise WriteRejectedError("원문은 S1 에서 한 번만 저장할 수 있습니다")
        self._set("sources", [copy.deepcopy(dict(s)) for s in sources])
        self._source = {**self._source, "meta": {**self._source["meta"], "sources_locked": True}}
        for item in sources:
            self.emit("item_written", SYSTEM, {"kind": "sources", "item": dict(item)})

    def add_systems(self, systems: Sequence[Mapping[str, Any]]) -> None:
        """S1 only, like the sources: the client's own system list (SYS-), never written by an agent."""
        self._set("systems", [copy.deepcopy(dict(s)) for s in systems])
        for item in systems:
            self.emit("item_written", SYSTEM, {"kind": "systems", "item": dict(item)})

    def add_company(self, items: Sequence[Mapping[str, Any]], company: Mapping[str, str]) -> None:
        """S1 only: the company material copied into this project (CMP-), never written by an agent."""
        self._set("company", [copy.deepcopy(dict(i)) for i in items])
        self._source = {**self._source, "meta": {**self._source.get("meta", {}), "company": dict(company)}}
        for item in items:
            self.emit("item_written", SYSTEM, {"kind": "company", "item": dict(item)})

    def add_confirmation(self, cp: str, approved: bool, who: str, reason: str | None,
                         version: str | None, waivers: Mapping[str, str] | None = None,
                         **extra: Any) -> dict[str, Any]:
        record = {
            "id": self.next_id("confirmations", "CF"), "cp": cp, "approved": approved, "who": who,
            "at": datetime.now(timezone.utc).isoformat(), "version": version, "reason": reason, **extra,
        }
        if waivers:
            record["waivers"] = dict(waivers)
        self._set("confirmations", [*self._source.get("confirmations", []), record])
        self.emit("confirmation", "client", record)
        return record

    def add_version(self, label: str, confirmation_id: str, kinds: Sequence[str]) -> dict[str, Any]:
        snapshot = {kind: list(self.items(kind)) for kind in kinds}
        record = {"version": label, "confirmation_id": confirmation_id,
                  "created_at": datetime.now(timezone.utc).isoformat(), "snapshot": snapshot}
        self._set("versions", [*self._source.get("versions", []), record])
        self.emit("version_created", SYSTEM, {"version": label, "confirmation_id": confirmation_id})
        return record

    def set_pipeline(self, **changes: Any) -> None:
        pipeline = {**self.pipeline, **changes}
        self._source = {**self._source, "meta": {**self._source["meta"], "pipeline": pipeline}}
        self.emit("pipeline", SYSTEM, {k: pipeline[k] for k in ("stage", "status", "active_agent", "error")})

    def set_name(self, value: str, by: str) -> None:
        """The project's name (D1): proposed by the FDE lead at S2 or set by the client; kept in meta.name."""
        if self._source.get("meta", {}).get("name") == {"value": value, "by": by}:
            return
        self._source = {**self._source, "meta": {**self._source["meta"], "name": {"value": value, "by": by}}}
        self.emit("project_named", by, {"name": value})

    def set_req_reviews(self, reviews: Mapping[str, Any]) -> None:
        """CP2 card review marks (system-owned: the client's verdicts, not an agent's write)."""
        self._source = {**self._source, "meta": {**self._source["meta"], "req_reviews": copy.deepcopy(dict(reviews))}}

    def set_recheck(self, recheck: Mapping[str, Any]) -> None:
        """A CP5 change made the delivered documents, screens, tests and prototype stale (download locked)."""
        self._source = {**self._source, "meta": {**self._source["meta"], "recheck": copy.deepcopy(dict(recheck))}}
        self.emit("recheck_required", SYSTEM, dict(recheck))

    def clear_recheck(self) -> None:
        """CP4 approved again on the new version: the deliverables are current."""
        meta = self._source["meta"]
        if "recheck" not in meta:
            return
        self._source = {**self._source, "meta": {k: v for k, v in meta.items() if k != "recheck"}}
        self.emit("recheck_cleared", SYSTEM, {"change_id": meta["recheck"].get("change_id")})

    def _set(self, kind: str, items: list[dict[str, Any]]) -> None:
        self._source = {**self._source, kind: items}

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change(self.source)
