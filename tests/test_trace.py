from __future__ import annotations
"""E2 (11-21): the event log exported as an OTLP/JSON trace — one span per Liner call under the stage that made it,
computed from the log only, with nothing the client or a model wrote."""

import json
from pathlib import Path
from typing import Any

from app.limits import calls_used
from app.stage_problem import TASK_FDE
from app.trace import otlp_trace
from tests.pipeline_helpers import CHUNKS, build, to_cp4


def ev(seq: int, type_: str, stage: str | None, data: dict[str, Any], second: float = 0.0,
       actor: str = "system") -> dict[str, Any]:
    whole, frac = divmod(second, 1)
    ts = f"2026-11-21T00:00:{int(whole):02d}.{int(round(frac * 1_000_000)):06d}+00:00"
    return {"seq": seq, "ts": ts, "stage": stage, "type": type_, "actor": actor, "data": data}


def spans_of(trace: dict[str, Any]) -> list[dict[str, Any]]:
    return trace["resourceSpans"][0]["scopeSpans"][0]["spans"]


def attrs(span: dict[str, Any]) -> dict[str, Any]:
    return {a["key"]: next(iter(a["value"].values())) for a in span.get("attributes", [])}


def full_run(repo_root: Path, key_env: Path) -> list[dict[str, Any]]:
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    orch.confirm("CP4", True, "발주사")
    return list(ws.source["events"])


def test_every_liner_call_becomes_one_span(repo_root: Path, key_env: Path) -> None:
    events = full_run(repo_root, key_env)
    calls = [s for s in spans_of(otlp_trace("p1", events)) if "gen_ai.operation.name" in attrs(s)]
    assert len(calls) == calls_used(events) > 0
    assert all(s["kind"] == 3 for s in calls)


def test_call_spans_sit_under_the_stage_that_made_them(repo_root: Path, key_env: Path) -> None:
    spans = spans_of(otlp_trace("p1", full_run(repo_root, key_env)))
    by_id = {s["spanId"]: s for s in spans}
    (root,) = [s for s in spans if s["name"] == "project"]
    assert all(s["parentSpanId"] in by_id for s in spans if s is not root) and "parentSpanId" not in root
    s2 = {s["spanId"] for s in spans if s["name"] == "stage S2"}
    s2_calls = [s for s in spans if "gen_ai.operation.name" in attrs(s) and attrs(s).get("zerotoone.stage.id") == "S2"]
    assert s2_calls and all(s["parentSpanId"] in s2 for s in s2_calls)
    assert all(s["parentSpanId"] == root["spanId"] for s in spans if s["name"].startswith("stage "))
    assert len({s["traceId"] for s in spans}) == 1


def test_span_times_come_from_the_event() -> None:
    events = [ev(1, "stage_started", "S2", {"stage": "S2", "agents": ["fde_lead"]}, 0),
              ev(2, "liner_chat", "S2", {"api": "model", "model": "m", "duration_ms": 1500}, 2, "fde_lead"),
              ev(3, "stage_completed", "S2", {"stage": "S2"}, 3)]
    (call,) = [s for s in spans_of(otlp_trace("p", events)) if s["name"].startswith("chat")]
    assert isinstance(call["startTimeUnixNano"], str) and isinstance(call["endTimeUnixNano"], str)
    assert int(call["endTimeUnixNano"]) - int(call["startTimeUnixNano"]) == 1_500_000_000


def test_a_chat_span_names_agent_model_tokens_and_cost() -> None:
    data = {"api": "model", "model": "liner-claude-router", "answered_model": "anthropic/claude-x", "prompt_tokens": 120,
            "completion_tokens": 30, "cost": 0.0123, "duration_ms": 10, "task": "지시문", "output": {"a": 1}}
    (call,) = [s for s in spans_of(otlp_trace("p", [ev(1, "liner_chat", "S2", data, 1, "pm")]))
               if s["name"] != "project"]
    assert call["name"] == "chat liner-claude-router"
    a = attrs(call)
    assert (a["gen_ai.agent.id"], a["gen_ai.request.model"], a["gen_ai.response.model"]) == \
        ("pm", "liner-claude-router", "anthropic/claude-x")
    assert (a["gen_ai.usage.input_tokens"], a["gen_ai.usage.output_tokens"], a["zerotoone.cost_usd"]) == ("120", "30", 0.0123)
    assert a["gen_ai.provider.name"] == "liner" and a["gen_ai.operation.name"] == "chat"


def test_a_tool_span_names_the_registry_tool() -> None:
    data = {"api": "ai_search", "query": "꽃", "result_count": 3, "results": [], "error": None, "duration_ms": 5}
    (call,) = [s for s in spans_of(otlp_trace("p", [ev(1, "liner_search", "S2", data, 1, "researcher")]))
               if s["name"] != "project"]
    assert call["name"] == "execute_tool liner_ai_search"
    assert attrs(call)["gen_ai.tool.name"] == "liner_ai_search" and attrs(call)["zerotoone.result_count"] == "3"


def test_a_failed_call_is_an_error_span_without_its_message() -> None:
    data = {"api": "search", "query": "q", "result_count": 0, "results": [], "error": "키가 비밀이에요", "duration_ms": 5}
    trace = otlp_trace("p", [ev(1, "liner_search", "S2", data, 1, "researcher")])
    (call,) = [s for s in spans_of(trace) if s["name"] != "project"]
    assert call["status"]["code"] == 2 and "비밀" not in json.dumps(trace, ensure_ascii=False)


def test_a_rework_makes_a_second_stage_span() -> None:
    events = [ev(1, "stage_started", "S2", {"stage": "S2", "agents": ["fde_lead"]}, 0),
              ev(2, "stage_completed", "S2", {"stage": "S2"}, 1),
              ev(3, "stage_started", "CP1", {"stage": "CP1"}, 2),
              ev(4, "stage_started", "S2", {"stage": "S2", "agents": ["fde_lead"]}, 3),
              ev(5, "stage_completed", "S2", {"stage": "S2"}, 4)]
    s2 = [s for s in spans_of(otlp_trace("p", events)) if s["name"] == "stage S2"]
    assert len(s2) == 2 and s2[0]["spanId"] != s2[1]["spanId"]


def test_a_stage_that_never_completed_ends_at_the_last_event() -> None:
    events = [ev(1, "stage_started", "S2", {"stage": "S2", "agents": ["fde_lead"]}, 0),
              ev(2, "liner_chat", "S2", {"api": "model", "model": "m", "duration_ms": 1}, 4, "fde_lead"),
              ev(3, "run_interrupted", "S2", {"stage": "S2", "crash": "KeyError"}, 7)]
    spans = spans_of(otlp_trace("p", events))
    (stage,) = [s for s in spans if s["name"] == "stage S2"]
    (root,) = [s for s in spans if s["name"] == "project"]
    assert stage["status"]["code"] == 2 and stage["endTimeUnixNano"] == root["endTimeUnixNano"]
    assert [e["name"] for e in stage["events"]] == ["run_interrupted"]


def test_a_confirmation_stage_without_a_completion_is_not_an_error() -> None:
    events = [ev(1, "stage_started", "CP1", {"stage": "CP1"}, 0),
              ev(2, "confirmation", "CP1", {"cp": "CP1", "approved": True, "version": None, "who": "김", "reason": None}, 5)]
    (stage,) = [s for s in spans_of(otlp_trace("p", events)) if s["name"] == "stage CP1"]
    assert stage.get("status", {}).get("code", 0) != 2


def test_guardrails_and_confirmations_are_span_events() -> None:
    events = [ev(1, "stage_started", "CP1", {"stage": "CP1"}, 0),
              ev(2, "guardrail", "CP1", {"id": "G7", "outcome": "blocked", "detail": "비밀 사유", "limit": "calls"}, 1),
              ev(3, "confirmation", "CP1", {"cp": "CP1", "approved": True, "version": "v1", "who": "김비밀",
                                            "reason": "비밀 이유"}, 2)]
    trace = otlp_trace("p", events)
    (stage,) = [s for s in spans_of(trace) if s["name"] == "stage CP1"]
    names = {e["name"]: {a["key"]: a["value"] for a in e["attributes"]} for e in stage["events"]}
    assert names["guardrail.G7"]["outcome"] == {"stringValue": "blocked"} and "limit" in names["guardrail.G7"]
    assert names["human.confirmation"]["approved"] == {"boolValue": True}
    assert "비밀" not in json.dumps(trace, ensure_ascii=False)


def test_nothing_the_client_or_a_model_wrote_leaves(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    text = json.dumps(otlp_trace("p1", ws.source["events"]), ensure_ascii=False)
    lines = [line.strip() for chunk in CHUNKS for line in chunk.splitlines() if len(line.strip()) > 8]
    assert lines and not [line for line in lines if line in text]
    assert TASK_FDE[:20] not in text
    assert not [r["statement"] for r in ws.items("requirements") if r["statement"] in text]


def test_the_same_log_gives_the_same_trace(repo_root: Path, key_env: Path) -> None:
    events = full_run(repo_root, key_env)
    assert otlp_trace("p1", events) == otlp_trace("p1", events)
    assert spans_of(otlp_trace("p1", [])) == []


def test_a_call_span_stays_inside_its_stage() -> None:
    """Jaeger (11-21) warned of clock skew: wall-clock `ts` minus a monotonic `duration_ms` can start a call a few
    milliseconds before its stage. A child span is kept inside its parent."""
    events = [ev(1, "stage_started", "S3", {"stage": "S3", "agents": ["pm"]}, 10.0),
              ev(2, "liner_chat", "S3", {"api": "model", "model": "m", "duration_ms": 10_050}, 20.0, "pm"),
              ev(3, "stage_completed", "S3", {"stage": "S3"}, 21.0)]
    spans = spans_of(otlp_trace("p", events))
    (stage,) = [s for s in spans if s["name"] == "stage S3"]
    (call,) = [s for s in spans if s["name"].startswith("chat")]
    assert int(call["startTimeUnixNano"]) == int(stage["startTimeUnixNano"])
    assert int(call["endTimeUnixNano"]) <= int(stage["endTimeUnixNano"])



# --- Fable review (11-21) M6·L6 -------------------------------------------------------------------------------
def test_the_project_name_does_not_leave(repo_root: Path, key_env: Path) -> None:
    events = [ev(1, "liner_chat", "S2", {"api": "model", "model": "m", "duration_ms": 1}, 1, "pm")]
    text = json.dumps(otlp_trace("p", events), ensure_ascii=False)
    assert "zerotoone.project.name" not in text


def test_a_stage_still_running_is_not_an_error() -> None:
    events = [ev(1, "stage_started", "S2", {"stage": "S2", "agents": ["fde_lead"]}, 0),
              ev(2, "liner_chat", "S2", {"api": "model", "model": "m", "duration_ms": 1}, 4, "fde_lead")]
    (stage,) = [s for s in spans_of(otlp_trace("p", events)) if s["name"] == "stage S2"]
    assert "status" not in stage


def test_a_chat_without_a_model_and_an_integer_cost() -> None:
    events = [ev(1, "liner_chat", "S1", {"api": "model", "cost": 0, "duration_ms": 1}, 1, "system")]
    (call,) = [s for s in spans_of(otlp_trace("p", events)) if s["name"] != "project"]
    assert call["name"] == "chat" and attrs(call)["zerotoone.cost_usd"] == 0.0
    assert next(a for a in call["attributes"] if a["key"] == "zerotoone.cost_usd")["value"] == {"doubleValue": 0.0}
