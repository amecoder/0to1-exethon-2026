from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.bus import MessageBus
from app.definitions import load_definitions
from app.events import EventLog
from app.store import empty_source
from app.workspace import Workspace, WriteRejectedError


@pytest.fixture
def defs(repo_root: Path):
    return load_definitions(repo_root)


@pytest.fixture
def ws(defs) -> Workspace:
    agents, _ = defs
    return Workspace(empty_source(), agents)


def types(ws: Workspace) -> list[str]:
    return [e["type"] for e in ws.source["events"]]


def test_write_gate_rejects_kind_outside_writes(ws: Workspace) -> None:
    assert ws.write("designer", "requirements", {"id": "REQ-01", "title": "x"}) is False
    assert ws.items("requirements") == ()
    rejected = [e for e in ws.source["events"] if e["type"] == "write_rejected"]
    assert rejected[0]["actor"] == "designer"
    assert rejected[0]["data"]["kind"] == "requirements"


def test_write_gate_accepts_own_kind_and_records_item(ws: Workspace) -> None:
    assert ws.write("pm", "requirements", {"id": "REQ-01", "title": "x"}) is True
    assert ws.write("pm", "requirements", {"id": "REQ-01", "title": "y"}) is True  # upsert by id
    assert [r["title"] for r in ws.items("requirements")] == ["y"]
    assert types(ws).count("item_written") == 2


def test_write_gate_rejects_unknown_actor(ws: Workspace) -> None:
    assert ws.write("intruder", "requirements", {"id": "REQ-01"}) is False


def test_sources_immutable_after_s1(ws: Workspace) -> None:
    ws.add_sources([{"id": "SRC-01", "text": "원문", "chunk": 1}])
    with pytest.raises(WriteRejectedError):
        ws.add_sources([{"id": "SRC-02", "text": "추가", "chunk": 1}])
    assert ws.write("pm", "sources", {"id": "SRC-01", "text": "고친 원문"}) is False
    assert ws.items("sources")[0]["text"] == "원문"
    guardrails = [e for e in ws.source["events"] if e["type"] == "guardrail"]
    assert {g["data"]["id"] for g in guardrails} == {"G4"}


def test_events_are_sequenced_in_time_order(ws: Workspace) -> None:
    ws.write("pm", "requirements", {"id": "REQ-01"})
    ws.write("qa", "findings", {"id": "FND-01"})
    events = ws.source["events"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all({"seq", "ts", "stage", "type", "actor", "data"} <= set(e) for e in events)


def test_bus_direct_message_on_relation(defs, ws: Workspace) -> None:
    _, teams = defs
    MessageBus(teams["default"], ws).send("pm", "qa", "검토 부탁")
    messages = [e for e in ws.source["events"] if e["type"] == "agent_message"]
    assert [(m["data"]["from"], m["data"]["to"]) for m in messages] == [("pm", "qa")]


def test_bus_reroutes_disallowed_pair_via_coordinator(defs, ws: Workspace) -> None:
    _, teams = defs
    MessageBus(teams["default"], ws).send("pm", "developer", "바로 만들어 주세요")
    assert "message_rerouted" in types(ws)
    messages = [e for e in ws.source["events"] if e["type"] == "agent_message"]
    assert [(m["data"]["from"], m["data"]["to"]) for m in messages] == [
        ("pm", "coordinator"), ("coordinator", "developer"),
    ]


def test_event_log_refuses_message_types_outside_bus() -> None:
    log = EventLog([])
    for kind in ("agent_message", "message_rerouted"):
        with pytest.raises(ValueError):
            log.append(kind, "pm", {})


def test_no_other_path_sends_messages(repo_root: Path) -> None:
    """Only bus.py may emit message events; everything else must call MessageBus.send."""
    offenders = []
    for path in (repo_root / "app").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name not in {"bus.py", "events.py"} and re.search(r"_append_raw|agent_message|message_rerouted", text):
            offenders.append(path.name)
    assert offenders == []
    assert "can_message(" in (repo_root / "app" / "bus.py").read_text(encoding="utf-8")
