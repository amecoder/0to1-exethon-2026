from __future__ import annotations
"""Liner usage in events (tokens + cost per call) and the read-only budget (G7 EXETHON_MAX_COST_USD) for the header."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent_runner import usage_fields
from app.config import Settings
from app.demo import load_recording, write_recording
from app.main import create_app
from tests.make_fake_demo import DEMO_FILE
from tests.pipeline_helpers import CHUNKS, events
from tests.test_liner_features import PAUSE, add_env, build, completed_desk


def test_usage_fields_maps_chat_and_input_output_shapes() -> None:
    chat = {"usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13, "cost": 0.0001}}
    assert usage_fields(chat) == {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13, "cost": 0.0001}
    audio = {"usage": {"input_tokens": 7, "output_tokens": 2}}
    assert usage_fields(audio) == {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9, "cost": None}
    assert usage_fields({}) == {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cost": None}


def test_chat_event_records_tokens_and_cost(repo_root: Path, key_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINER_MODEL", "liner-claude-router")
    orch, ws, _ = build(repo_root, key_env, answered_model="claude-sonnet-5.5")
    orch.ingest(CHUNKS)
    orch.advance()
    chat = events(ws, "liner_chat")[0]["data"]
    assert (chat["prompt_tokens"], chat["completion_tokens"], chat["total_tokens"], chat["cost"]) == (10, 5, 15, 0.0021)


def test_rerank_event_records_usage(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    ws, _, desk = completed_desk(repo_root, key_env)
    desk.map_change(desk.open_change(PAUSE)["id"])
    rerank = events(ws, "liner_rerank")[0]["data"]
    assert (rerank["total_tokens"], rerank["cost"]) == (10, 6.6e-07)


def test_project_payload_carries_budget(tmp_path: Path, key_env: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "a.sqlite3", env_file=key_env)))
    pid = client.post("/api/projects", json={"name": "p", "mode": "real"}).json()["id"]
    assert client.get(f"/api/projects/{pid}").json()["budget_usd"] is None
    add_env(key_env, EXETHON_MAX_COST_USD="5")
    assert client.get(f"/api/projects/{pid}").json()["budget_usd"] == 5.0


def test_demo_meta_passes_recording_budget(tmp_path: Path, no_key_env: Path) -> None:
    recording = {**load_recording(DEMO_FILE), "max_cost_usd": 5.0}
    demo_file = tmp_path / "run.json"
    write_recording(recording, demo_file)
    settings = Settings(db_path=tmp_path / "d.sqlite3", env_file=no_key_env, demo_file=demo_file)
    assert TestClient(create_app(settings)).get("/api/demo").json()["max_cost_usd"] == 5.0
