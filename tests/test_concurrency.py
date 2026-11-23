from __future__ import annotations
"""Review fix 1: concurrent requests must not overwrite each other's saves (revision + per-project run lock)."""

import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from app.orchestrator import Orchestrator
from app.store import ProjectStore, StaleRevisionError, empty_source
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

CHUNKS = memo_chunks()


def test_saving_twice_from_the_same_snapshot_rejects_the_second(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "c.sqlite3")
    project = store.create("x", "real")
    snapshot = store.get(project["id"])
    first = {**snapshot["source"], "meta": {"who": "first"}}
    second = {**snapshot["source"], "meta": {"who": "second"}}
    store.save_source(project["id"], first, snapshot["revision"])
    with pytest.raises(StaleRevisionError, match="새로 고쳐"):
        store.save_source(project["id"], second, snapshot["revision"])
    assert store.get(project["id"])["source"]["meta"] == {"who": "first"}


def test_run_lock_is_atomic_and_released_only_by_its_holder(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "c.sqlite3")
    pid = store.create("x", "real")["id"]
    token = store.acquire_run(pid)
    assert token and store.acquire_run(pid) is None
    store.release_run(pid, "someone-else")
    assert store.acquire_run(pid) is None
    store.release_run(pid, token)
    assert store.acquire_run(pid) is not None


def test_old_database_files_get_the_new_columns(tmp_path: Path) -> None:
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, "
                     "created_at TEXT NOT NULL, source_json TEXT NOT NULL)")
        conn.execute("INSERT INTO projects VALUES ('p1', 'x', 'real', '2026-11-15T00:00:00+00:00', '{}')")
    store = ProjectStore(db)
    assert store.get("p1")["revision"] == 0
    assert store.save_source("p1", empty_source(), 0) == 1
    assert store.acquire_run("p1") is not None


def test_two_approvals_at_once_apply_only_one(tmp_path: Path, key_env: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "c.sqlite3", env_file=key_env)
    client = TestClient(create_app(settings, liner=LinerClient(env_file=key_env, transport=fake.transport())))
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})
    assert client.get(base).json()["todo"]["cp"] == "CP1"

    entered, go = threading.Event(), threading.Event()
    original = Orchestrator.confirm

    def slow_confirm(self: Orchestrator, *args, **kwargs) -> None:
        if not entered.is_set():
            entered.set()
            go.wait(timeout=2)
        original(self, *args, **kwargs)

    monkeypatch.setattr(Orchestrator, "confirm", slow_confirm)
    results: dict[str, int] = {}
    first = threading.Thread(target=lambda: results.__setitem__(
        "first", client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True}).status_code))
    first.start()
    assert entered.wait(timeout=5)
    second = client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True})
    go.set()
    first.join(timeout=30)

    assert results["first"] == 202
    assert second.status_code == 409
    confirmations = [c for c in client.get(base).json()["source"]["confirmations"] if c["cp"] == "CP1"]
    assert len(confirmations) == 1
