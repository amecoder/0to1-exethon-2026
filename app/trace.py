from __future__ import annotations
"""에이전트 OS 5단계 (E2, 11-21): the event log as an OTLP/JSON trace, computed — the log is not changed.

One root span per project, one span per stage run (a rework is a second span), and one CLIENT span per Liner call
(app/tools.py CALL_EVENTS) under the stage it ran in. Guardrails, confirmations and interruptions are span events.
Only who / what / how long / how much leaves: no instruction, query, model output, search result, reason or name
of a person, nor the project name. Attribute names follow the OpenTelemetry GenAI semantic conventions (still in development).
Shape only: no collector import was tested.
"""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.tools import CALL_EVENTS, call_of

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
CHAT_EVENTS = frozenset({"liner_chat", "liner_attachment"})
SPAN_EVENTS = frozenset({"guardrail", "confirmation", "run_interrupted", "run_retried"})
EVENT_FIELDS = {"guardrail": ("outcome", "tool", "limit"), "confirmation": ("cp", "approved", "version"),
                "run_interrupted": ("crash", "restored"), "run_retried": ()}
CALL_FIELDS = (("gen_ai.request.model", "model"), ("gen_ai.response.model", "answered_model"),
               ("gen_ai.usage.input_tokens", "prompt_tokens"), ("gen_ai.usage.output_tokens", "completion_tokens"),
               ("zerotoone.cost_usd", "cost"), ("zerotoone.schema", "schema"),
               ("zerotoone.routing_strategy", "routing_strategy"), ("zerotoone.budget_mode", "budget_mode"),
               ("zerotoone.result_count", "result_count"))


@dataclass(frozen=True)
class StageRun:
    stage: str
    start: Mapping[str, Any]  # its stage_started event
    end: Mapping[str, Any]  # its stage_completed event, else the last event before the next stage started
    completed: bool
    stopped: bool  # it cannot still be running: a later stage started, or the run was interrupted inside it


def otlp_trace(project_id: str, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    trace_id = hashlib.sha256(project_id.encode()).hexdigest()[:32]

    def span_id(key: str) -> str:
        return hashlib.sha256(f"{project_id}:{key}".encode()).hexdigest()[:16]

    spans: list[dict[str, Any]] = []
    if events:
        runs = stage_runs(events)
        root = _span(trace_id, span_id("root"), None, "project", events[0], events[-1], [])
        stage_spans = [_stage_span(trace_id, span_id(f"stage:{r.start['seq']}"), root["spanId"], r) for r in runs]
        for e in events:
            owner = _owner(e, runs, stage_spans) or root
            if e["type"] in CALL_EVENTS:
                spans.append(_inside(_call_span(trace_id, span_id(f"call:{e['seq']}"), owner["spanId"], e), owner))
            elif e["type"] in SPAN_EVENTS:
                owner["events"].append(_span_event(e))
        spans = [root, *stage_spans, *spans]
    # No project name: the client or the FDE lead (a model) wrote it (Fable review M6).
    resource = {"attributes": _attributes({"service.name": "0to1", "zerotoone.project.id": project_id})}
    return {"resourceSpans": [{"resource": resource,
                               "scopeSpans": [{"scope": {"name": "0to1.events"}, "spans": spans}]}]}


def stage_runs(events: Sequence[Mapping[str, Any]]) -> list[StageRun]:
    starts = [i for i, e in enumerate(events) if e["type"] == "stage_started"]
    runs = []
    for n, i in enumerate(starts):
        stage = events[i]["data"].get("stage")
        limit = starts[n + 1] if n + 1 < len(starts) else len(events)
        done = next((e for e in events[i + 1:limit] if e["type"] == "stage_completed"
                     and e["data"].get("stage") == stage), None)
        interrupted = any(e["type"] == "run_interrupted" for e in events[i + 1:limit])
        runs.append(StageRun(stage, events[i], done or events[limit - 1], done is not None,
                             limit < len(events) or interrupted))
    return runs


def _owner(e: Mapping[str, Any], runs: Sequence[StageRun], spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The stage span open at this event for the event's own stage."""
    for run, span in zip(runs, spans):
        if run.stage == e.get("stage") and run.start["seq"] <= e["seq"] <= run.end["seq"]:
            return span
    return None


def _stage_span(trace_id: str, sid: str, parent: str, run: StageRun) -> dict[str, Any]:
    agents = run.start["data"].get("agents")
    span = _span(trace_id, sid, parent, f"stage {run.stage}", run.start, run.end,
                 _attributes({"zerotoone.stage.id": run.stage, "zerotoone.stage.agents": ",".join(agents or []) or None}))
    if not run.completed and run.stopped and agents:  # a work stage that ended unfinished (not one still running)
        span["status"] = {"code": 2, "message": "not completed"}
    return span


def _inside(span: dict[str, Any], parent: Mapping[str, Any]) -> dict[str, Any]:
    """Keep a call inside its stage: `ts` is wall clock, `duration_ms` monotonic, so the computed start can fall a
    few milliseconds before the stage started (Jaeger then reports clock skew)."""
    low, high = int(parent["startTimeUnixNano"]), int(parent["endTimeUnixNano"])
    start = min(max(int(span["startTimeUnixNano"]), low), high)
    end = min(max(int(span["endTimeUnixNano"]), start), high)
    return {**span, "startTimeUnixNano": str(start), "endTimeUnixNano": str(end)}


def _call_span(trace_id: str, sid: str, parent: str, e: Mapping[str, Any]) -> dict[str, Any]:
    data = e["data"]
    chat = e["type"] in CHAT_EVENTS
    tool = call_of(e["type"], data.get("api"))
    end = _nanos(e["ts"])
    duration = data.get("duration_ms")
    start = end - int(duration) * 1_000_000 if isinstance(duration, (int, float)) else end
    values: dict[str, Any] = {"gen_ai.operation.name": "chat" if chat else "execute_tool", "gen_ai.provider.name": "liner",
                              "gen_ai.agent.id": e.get("actor"), "gen_ai.tool.name": tool,
                              "zerotoone.stage.id": e.get("stage"), "zerotoone.seq": e["seq"]}
    values.update({key: data.get(field) for key, field in CALL_FIELDS})
    cost = data.get("cost")
    values["zerotoone.cost_usd"] = float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None
    span = {"traceId": trace_id, "spanId": sid, "parentSpanId": parent,
            "name": (f"chat {data['model']}" if data.get("model") else "chat") if chat else f"execute_tool {tool}",
            "kind": 3,
            "startTimeUnixNano": str(start), "endTimeUnixNano": str(end), "attributes": _attributes(values),
            "events": []}
    if data.get("error"):
        span["status"] = {"code": 2, "message": "error"}
    return span


def _span(trace_id: str, sid: str, parent: str | None, name: str, first: Mapping[str, Any], last: Mapping[str, Any],
          attributes: list[dict[str, Any]]) -> dict[str, Any]:
    span = {"traceId": trace_id, "spanId": sid, "name": name, "kind": 1,
            "startTimeUnixNano": str(_nanos(first["ts"])), "endTimeUnixNano": str(_nanos(last["ts"])),
            "attributes": attributes, "events": []}
    return {**span, "parentSpanId": parent} if parent else span


def _span_event(e: Mapping[str, Any]) -> dict[str, Any]:
    data = e["data"]
    name = {"guardrail": f"guardrail.{data.get('id')}", "confirmation": "human.confirmation"}.get(e["type"], e["type"])
    return {"timeUnixNano": str(_nanos(e["ts"])), "name": name,
            "attributes": _attributes({k: data.get(k) for k in EVENT_FIELDS[e["type"]]})}


def _attributes(values: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"key": k, "value": _value(v)} for k, v in values.items() if v is not None]


def _value(v: Any) -> dict[str, Any]:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def _nanos(ts: str) -> int:
    moment = datetime.fromisoformat(ts)
    delta = moment - EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000
