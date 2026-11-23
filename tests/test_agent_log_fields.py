from __future__ import annotations
"""Fields the per-agent log reads from events: Liner call duration and the PM's change-mapping rationale."""

from pathlib import Path

from app.schemas import CHANGE_MAPPING
from tests.test_change_desk import completed
from tests.test_liner_features import PAUSE, add_env, completed_desk
from tests.pipeline_helpers import events

LINER_EVENTS = ("liner_chat", "liner_search", "liner_rerank")


def test_liner_events_record_call_duration(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    ws, _, desk = completed_desk(repo_root, key_env)
    desk.map_change(desk.open_change(PAUSE)["id"])
    for kind in LINER_EVENTS:
        found = events(ws, kind)
        assert found, kind
        for event in found:
            ms = event["data"]["duration_ms"]
            assert isinstance(ms, int) and ms >= 0, (kind, ms)


def test_failed_counted_call_still_records_duration(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    ws, _, desk = completed_desk(repo_root, key_env, rerank_status=500)
    desk.map_change(desk.open_change(PAUSE)["id"])
    failed = events(ws, "liner_rerank")[0]["data"]
    assert failed["error"] and isinstance(failed["duration_ms"], int)


def test_change_mapping_asks_for_and_keeps_a_rationale(repo_root: Path, key_env: Path) -> None:
    assert "rationale" in CHANGE_MAPPING["properties"]
    ws, fake, desk = completed_desk(repo_root, key_env)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["rationale"]  # the scripted PM gives one
    assert "rationale" in fake.chat_payloads("change_mapping")[0]["messages"][-1]["content"]


def test_change_mapping_without_rationale_still_works(repo_root: Path, key_env: Path) -> None:
    old = {"change_mapping": [{"target": "REQ-01", "after_statement": "토요일만 배송한다", "summary": "요일을 바꾼다"}]}
    _, ws, _, desk = completed(repo_root, key_env, old)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["status"] == "awaiting_cp5" and item["rationale"] == ""
