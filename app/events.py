from __future__ import annotations
"""FR-15 activity log. Events are append-only and time-ordered; demo mode will replay them.

Event shape (JSON):
    {"seq": 1, "ts": "<UTC ISO>", "stage": "S2", "type": "<type>", "actor": "<agent|client|system>",
     "data": {...}}
Types: stage_started, stage_completed, pipeline, agent_message, message_rerouted, liner_chat,
liner_search, guardrail, item_written, write_rejected, question_answered, confirmation, version_created,
liner_image (S6 prototype picture: model, slot, prompt, usage — never the image), check_result (answer consistency / coverage), ref_dropped, run_interrupted, run_retried, bundle_cleared
(write_all empties a bundle before rewriting it), prototype_built (S6 origin/attempts).
intake_triage (S1, before ingest: case, missing slots, by code|model — never the client's text).
P1 adds no new types: check_result carries `consumer_feedback` (failed), `change_impact`, `complaint_guard`;
guardrail carries G7 blocked/resumed and G8 flagged/resolved; the change lane is `changes`/`complaints` items.
`item_written` carries the full item, so replaying events in order rebuilds the shared source (app/demo.py).
"""

import copy
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

# Only app/bus.py may emit these (via _append_raw), so every handoff passes can_message.
MESSAGE_TYPES = frozenset({"agent_message", "message_rerouted"})


class EventLog:
    def __init__(
        self,
        events: list[dict[str, Any]],
        on_append: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._events: tuple[dict[str, Any], ...] = tuple(copy.deepcopy(events))
        self._on_append = on_append

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return self._events

    def append(self, type_: str, actor: str, data: Mapping[str, Any], stage: str | None = None) -> dict[str, Any]:
        if type_ in MESSAGE_TYPES:
            raise ValueError(f"'{type_}' 이벤트는 메시지 버스(MessageBus.send)로만 남길 수 있습니다")
        return self._append_raw(type_, actor, data, stage)

    def _append_raw(self, type_: str, actor: str, data: Mapping[str, Any], stage: str | None) -> dict[str, Any]:
        event = {
            "seq": len(self._events) + 1,
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "type": type_,
            "actor": actor,
            "data": copy.deepcopy(dict(data)),
        }
        self._events = (*self._events, event)
        if self._on_append is not None:
            self._on_append(event)
        return event
