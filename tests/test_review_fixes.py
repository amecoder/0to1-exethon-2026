from __future__ import annotations
"""Review fixes (2026-11-16): audio upload hardening, startup recovery isolation, catalog endpoints."""

import io
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import recovery
from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from app.store import ProjectStore, StaleRevisionError
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks
from tests.test_recovery import stuck_project

MP3 = b"ID3\x04\x00\x00" + b"\x00" * 64


def client_for(tmp_path: Path, env_file: Path, liner: LinerClient | None = None, **settings_kwargs) -> TestClient:
    fake = FakeLiner(flower_outputs(memo_chunks()), search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "rf.sqlite3", env_file=env_file, **settings_kwargs)
    return TestClient(create_app(settings, liner=liner or LinerClient(env_file=env_file, transport=fake.transport())))


def with_stt(env_file: Path) -> Path:
    env_file.write_text(env_file.read_text(encoding="utf-8") + "LINER_STT_MODEL=stt-test\n", encoding="utf-8")
    return env_file


# --- C1: a broken Content-Length header is ignored, the streamed limit still applies ---------------
def test_non_numeric_content_length_is_not_a_server_error(tmp_path: Path, key_env: Path) -> None:
    client = client_for(tmp_path, with_stt(key_env))
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    for bad in ("abc", "-5"):
        response = client.post(f"/api/projects/{pid}/input/audio?filename=a.mp3", content=MP3,
                               headers={"content-length": bad})
        assert response.status_code < 500, (bad, response.text)


# --- C4: the run lock is free while Liner transcribes; a slow call times out ----------------------
class SlowStt(LinerClient):
    def __init__(self, env_file: Path, store_path: Path, delay: float = 0.0) -> None:
        fake = FakeLiner(flower_outputs(memo_chunks()), search_body=SEARCH_BODY)
        super().__init__(env_file=env_file, transport=fake.transport())
        self.store_path, self.delay, self.lock_free = store_path, delay, []

    def transcribe(self, filename: str, data: bytes, **kwargs):  # type: ignore[override]
        store = ProjectStore(self.store_path)
        pid = store.ids()[0]
        token = store.acquire_run(pid)
        self.lock_free.append(token is not None)
        if token:
            store.release_run(pid, token)
        time.sleep(self.delay)
        return super().transcribe(filename, data, **kwargs)


def test_run_lock_is_not_held_during_transcription(tmp_path: Path, key_env: Path) -> None:
    env = with_stt(key_env)
    liner = SlowStt(env, tmp_path / "rf.sqlite3")
    client = client_for(tmp_path, env, liner=liner)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    response = client.post(f"/api/projects/{pid}/input/audio?filename=a.mp3", content=MP3)
    assert response.status_code == 200, response.text
    assert liner.lock_free == [True]


def test_slow_transcription_times_out_in_korean(tmp_path: Path, key_env: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from app import routes_pipeline
    monkeypatch.setattr(routes_pipeline, "TRANSCRIBE_TIMEOUT_S", 0.05)
    env = with_stt(key_env)
    client = client_for(tmp_path, env, liner=SlowStt(env, tmp_path / "rf.sqlite3", delay=0.5))
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    response = client.post(f"/api/projects/{pid}/input/audio?filename=a.mp3", content=MP3)
    assert response.status_code == 504 and "시간" in response.json()["detail"]


# --- C3: one project failing recovery does not stop the others; the lock is released after ---------
def test_recovery_keeps_going_after_one_project_fails(tmp_path: Path, key_env: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "rf.sqlite3"
    first, second = stuck_project(db), stuck_project(db)
    original = recovery.Orchestrator.mark_interrupted
    calls: list[str] = []

    def flaky(self) -> None:
        calls.append("x")
        if len(calls) == 1:
            raise StaleRevisionError("다른 요청이 먼저 반영됐어요")
        original(self)

    monkeypatch.setattr(recovery.Orchestrator, "mark_interrupted", flaky)
    client = client_for(tmp_path, key_env)
    statuses = [client.get(f"/api/projects/{pid}").json()["source"]["meta"]["pipeline"]["status"]
                for pid in (first, second)]
    assert len(calls) == 2 and statuses.count("failed") == 1 and statuses.count("running") == 1
    store = ProjectStore(db)
    assert all(store.acquire_run(pid) for pid in (first, second))  # no lock left behind


# --- A5: example memo and recent projects -----------------------------------------------------------
def test_example_memo_drops_the_header_block(tmp_path: Path, no_key_env: Path) -> None:
    examples = tmp_path / "ex"
    examples.mkdir()
    (examples / "request_memo.md").write_text("# 머리\n- 설명\n\n---\n\n본문 첫 줄\n둘째 줄\n", encoding="utf-8")
    body = client_for(tmp_path, no_key_env, examples_root=examples).get("/api/sample-memo").json()
    assert body == {"name": "request_memo.md", "text": "본문 첫 줄\n둘째 줄"}


def test_real_example_memo_is_served_and_missing_is_korean_404(tmp_path: Path, no_key_env: Path) -> None:
    text = client_for(tmp_path, no_key_env).get("/api/sample-memo").json()["text"]
    assert text and not text.startswith("#") and "---" not in text.splitlines()[0]
    missing = client_for(tmp_path, no_key_env, examples_root=tmp_path / "none").get("/api/sample-memo")
    assert missing.status_code == 404 and "예제" in missing.json()["detail"]


def test_project_list_shows_real_projects_newest_first(tmp_path: Path, key_env: Path) -> None:
    client = client_for(tmp_path, key_env)
    store = ProjectStore(tmp_path / "rf.sqlite3")
    store.create("시연", "demo")
    old = client.post("/api/projects", json={"name": "옛것", "mode": "real"}).json()["id"]
    stuck = stuck_project(tmp_path / "rf.sqlite3")
    projects = client.get("/api/projects").json()["projects"]
    assert [p["id"] for p in projects] == [stuck, old]
    assert set(projects[0]) >= {"id", "name", "mode", "created_at", "stage", "status", "completed"}
    assert projects[0]["stage"] == "S2" and projects[0]["completed"] is False
    assert projects[1]["stage"] is None and projects[1]["status"] is None


def test_project_list_limit_and_total(tmp_path: Path, key_env: Path) -> None:
    client = client_for(tmp_path, key_env)
    for i in range(23):
        client.post("/api/projects", json={"name": f"p{i}", "mode": "real"})
    body = client.get("/api/projects").json()
    assert len(body["projects"]) == 20 and body["total"] == 23  # default: the 20 newest
    every = client.get("/api/projects", params={"limit": 1000}).json()
    assert len(every["projects"]) == 23 and every["projects"][0]["name"] == "p22"
    assert client.get("/api/projects", params={"limit": 0}).status_code == 422


# --- A6 · B: demo download from the recording ---------------------------------------------------------
def test_demo_download_builds_the_zip_from_the_recording(tmp_path: Path, no_key_env: Path) -> None:
    from app.demo import write_recording
    from tests.make_fake_demo import record_fake
    recording, _ = record_fake(tmp_path)
    demo_file = tmp_path / "demo.json"
    write_recording(recording, demo_file)
    response = client_for(tmp_path, no_key_env, demo_file=demo_file).get("/api/demo/download")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert "%EC%8B%9C%EC%97%B0" in response.headers["content-disposition"]  # 시연_결과물.zip
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    readme = zf.read("README.txt").decode("utf-8")
    assert readme.startswith("[시연 녹화본") and "가짜 응답" in readme.splitlines()[0]
    assert {"prototype.html", "BRD.md", "source.json"} <= set(zf.namelist())


def test_demo_download_marks_a_recording_without_cp4_as_draft(tmp_path: Path, no_key_env: Path) -> None:
    from app.demo import write_recording
    from tests.make_fake_demo import record_fake
    recording, _ = record_fake(tmp_path)
    cut = next(i for i, e in enumerate(recording["events"])
               if e["type"] == "confirmation" and e["data"].get("cp") == "CP4")
    demo_file = tmp_path / "short.json"
    write_recording({**recording, "events": recording["events"][:cut]}, demo_file)
    response = client_for(tmp_path, no_key_env, demo_file=demo_file).get("/api/demo/download")
    assert response.status_code == 200
    lines = zipfile.ZipFile(io.BytesIO(response.content)).read("README.txt").decode("utf-8").splitlines()
    assert lines[0].startswith("[시연 녹화본") and lines[1].startswith("[작업본]")
