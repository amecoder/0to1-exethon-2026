from __future__ import annotations
"""scripts/export_demo.py: a finished real web project → a demo recording (kind real) with run totals."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import load_recording, make_recording, run_summary
from app.main import create_app
from app.store import ProjectStore
from scripts.export_demo import ExportRefused, export_project, main
from tests.pipeline_helpers import build, to_cp3, to_cp4


def finished_project(repo_root: Path, key_env: Path, db: Path, through_cp4: bool = True) -> str:
    orch, ws, _ = build(repo_root, key_env)
    if through_cp4:
        to_cp4(orch, ws)
        orch.confirm("CP4", True, "발주사")
        orch.advance()
    else:
        to_cp3(orch, ws)
    return ProjectStore(db).create("꽃님 실제", "real", ws.source)["id"]


def test_run_summary_reads_models_cost_and_time() -> None:
    events = [
        {"type": "credits", "ts": "2026-11-16T10:00:00+00:00", "data": {"balance_usd": 200.0}},
        {"type": "liner_chat", "ts": "2026-11-16T10:00:05+00:00",
         "data": {"model": "liner-claude-router", "answered_model": "anthropic/claude-x", "cost": 0.01}},
        {"type": "liner_chat", "ts": "2026-11-16T10:01:00+00:00", "data": {"model": "liner-mark-1.3", "cost": 0.02}},
        {"type": "credits", "ts": "2026-11-16T10:02:30+00:00", "data": {"balance_usd": 199.5}},
    ]
    assert run_summary(events) == {"models": ["anthropic/claude-x", "liner-mark-1.3"],
                                   "total_cost_usd": 0.5, "duration_seconds": 150}
    no_credits = run_summary(events[1:3])
    assert no_credits["total_cost_usd"] == pytest.approx(0.03) and no_credits["duration_seconds"] == 55
    assert run_summary([]) == {"models": [], "total_cost_usd": None, "duration_seconds": None}


def test_export_writes_a_real_recording_with_header_totals(tmp_path: Path, repo_root: Path, key_env: Path) -> None:
    db, out = tmp_path / "e.sqlite3", tmp_path / "out" / "run.json"
    pid = finished_project(repo_root, key_env, db)
    assert main(["--project", pid, "--db", str(db), "--out", str(out)]) == 0
    rec = load_recording(out)
    assert rec["kind"] == "real" and rec["project_name"] == "꽃님 실제"
    assert rec["models"] and rec["duration_seconds"] is not None and "total_cost_usd" in rec
    assert rec["event_count"] == len(rec["events"])

    settings = Settings(db_path=tmp_path / "x.sqlite3", env_file=key_env, demo_file=out)
    meta = TestClient(create_app(settings)).get("/api/demo").json()
    assert meta["kind"] == "real" and meta["models"] == rec["models"]
    assert {"total_cost_usd", "duration_seconds"} <= set(meta)


def test_export_refuses_unfinished_demo_and_unknown_projects(tmp_path: Path, repo_root: Path, key_env: Path,
                                                             capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "e.sqlite3"
    unfinished = finished_project(repo_root, key_env, db, through_cp4=False)
    demo = ProjectStore(db).create("시연", "demo")["id"]
    for pid in (unfinished, demo, "없는-id"):
        with pytest.raises(ExportRefused):
            export_project(ProjectStore(db), pid)
        assert main(["--project", pid, "--db", str(db), "--out", str(tmp_path / "no.json")]) == 2
    assert "CP4" in capsys.readouterr().err
    assert not (tmp_path / "no.json").exists()


def test_old_recordings_without_totals_still_load(tmp_path: Path) -> None:
    old = {"format": "exethon-demo-run/1", "kind": "fake", "recorded_at": "2026-11-15T00:00:00+00:00",
           "events": []}
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    assert load_recording(path)["events"] == []
    assert callable(make_recording)


def test_note_is_added_to_the_banner_notice(tmp_path: Path, repo_root: Path, key_env: Path) -> None:
    db = tmp_path / "n.sqlite3"
    pid = finished_project(repo_root, key_env, db)
    rec = export_project(ProjectStore(db), pid, "발주사 역할은 개발팀이 대리 입력")
    assert rec["notice"].endswith("· 발주사 역할은 개발팀이 대리 입력")
    assert rec["operator_note"] == "발주사 역할은 개발팀이 대리 입력"
    assert "operator_note" not in export_project(ProjectStore(db), pid)
