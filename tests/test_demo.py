from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.definitions import load_definitions
from app.demo import FAKE_NOTICE, compared_bundles, load_recording, replay, write_recording
from app.liner import LinerClient
from app.main import create_app
from app.store import empty_source
from app.workspace import Workspace
from tests.fake_liner import FakeLiner
from tests.make_fake_demo import DEMO_FILE, record_fake


def test_committed_demo_file_is_a_real_run_and_replays_to_its_final() -> None:
    """2026-11-17: the committed demo is a real Liner run (client role typed by the dev team, said in the notice)."""
    rec = load_recording(DEMO_FILE)
    assert rec["kind"] == "real" and "대리 입력" in rec["notice"] and rec.get("operator_note")
    assert rec["models"] and rec["total_cost_usd"] and rec["duration_seconds"]
    assert compared_bundles(replay(rec["events"])) == rec["final"]
    final = replay(rec["events"])
    assert final["meta"]["pipeline"]["status"] == "completed" and final["prototype"][-1]["html"]
    approved = [c["cp"] for c in final["confirmations"] if c.get("approved", True)]
    assert approved[-3:] == ["CP5", "CP3", "CP4"] and "recheck" not in final["meta"]
    assert final["changes"][0]["status"] == "approved" and final["changes"][0].get("revision")
    assert {c["classification"] for c in final["complaints"]} == {"합의 위반", "새 변경 요청"}


def test_replay_rebuilds_the_same_source_as_the_original_run(tmp_path: Path) -> None:
    recording, ws = record_fake(tmp_path)
    rebuilt = replay(recording["events"])
    original = ws.source
    for kind in ("requirements", "screens", "tests", "questions", "decisions", "prototype", "qa_checklist", "sources"):
        assert rebuilt[kind] == original[kind], kind
    assert rebuilt["meta"]["pipeline"]["status"] == original["meta"]["pipeline"]["status"] == "completed"
    assert [v["version"] for v in rebuilt["versions"]] == ["v1", "v2", "v3", "v4"]  # v3 = CP5, v4 = CP3 again
    assert "recheck" not in rebuilt["meta"] and "recheck" not in original["meta"]


def test_replay_honours_bundle_rewrites(repo_root: Path) -> None:
    agents, _ = load_definitions(repo_root)
    ws = Workspace(empty_source(), agents)
    ws.write_all("designer", "screens", [{"id": "SCR-01"}, {"id": "SCR-02"}])
    ws.write_all("designer", "screens", [{"id": "SCR-01", "title": "다시"}])
    assert replay(ws.source["events"])["screens"] == [{"id": "SCR-01", "title": "다시"}]


def test_demo_api_replays_without_key_and_without_liner(tmp_path: Path, no_key_env: Path) -> None:
    recording, ws = record_fake(tmp_path)
    demo_file = tmp_path / "demo" / "run.json"
    write_recording(recording, demo_file)
    fake = FakeLiner({})
    settings = Settings(db_path=tmp_path / "x.sqlite3", env_file=no_key_env, demo_file=demo_file)
    client = TestClient(create_app(settings, liner=LinerClient(env_file=no_key_env, transport=fake.transport())))

    meta = client.get("/api/demo").json()
    assert meta["kind"] == "fake" and meta["notice"] == FAKE_NOTICE and meta["recorded_at"]
    assert meta["total"] == len(recording["events"])
    first = client.get("/api/demo/state", params={"step": 0}).json()
    assert first["event"] is None and first["source"]["requirements"] == []
    seen = set()
    for step in range(1, meta["total"] + 1):  # every step: a sampled stride misses short scenes when the log grows
        state = client.get("/api/demo/state", params={"step": step}).json()
        seen.add(state["todo"]["kind"])
    assert {"question", "confirmation"} <= seen
    last = client.get("/api/demo/state", params={"step": meta["total"]}).json()
    assert last["todo"]["kind"] == "download" and "decision_status" in last["todo"] and last["documents"]["screens"]["sections"]
    for kind in ("requirements", "screens", "tests"):
        assert last["source"][kind] == ws.source[kind]
    preview = client.get("/api/demo/prototype/preview")
    assert preview.status_code == 200 and 'sandbox="allow-scripts"' in preview.text
    step = {"step": meta["total"]}
    assert client.get("/api/demo/documents/prd.md", params=step).text.startswith("# PRD")
    assert client.get("/api/demo/documents/prd.docx", params=step).content[:2] == b"PK"
    assert client.get("/api/demo/documents/tests.pdf", params=step).content.startswith(b"%PDF")
    assert client.get("/api/demo/documents/prd.pdf", params={"step": 1}).status_code == 404  # no documents yet
    assert fake.requests == []  # replay never calls Liner


def test_missing_or_bad_demo_file_is_a_korean_404(tmp_path: Path, no_key_env: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "other", "events": []}), encoding="utf-8")
    for path in (tmp_path / "none.json", bad):
        settings = Settings(db_path=tmp_path / "y.sqlite3", env_file=no_key_env, demo_file=path)
        response = TestClient(create_app(settings)).get("/api/demo")
        assert response.status_code == 404 and "시연 녹화 파일" in response.json()["detail"]


def test_make_fake_demo_never_overwrites_the_committed_real_recording(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    import tests.make_fake_demo as maker

    before = DEMO_FILE.read_bytes()
    monkeypatch.setattr(maker, "FAKE_DEMO_FILE", tmp_path / "fake.json")
    assert maker.main() == 0
    assert DEMO_FILE.read_bytes() == before and load_recording(tmp_path / "fake.json")["kind"] == "fake"
