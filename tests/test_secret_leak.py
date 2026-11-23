from __future__ import annotations
"""Review fixes 3 and 6 + the leak check: a fake key and a fake phone number injected into Liner answers,
stream errors and HTTP errors never reach the event log, the demo recording or the zip export."""

import copy
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent_runner import AgentRunner
from app.config import Settings
from app.definitions import load_definitions
from app.demo import make_recording
from app.liner import AI_SEARCH_URL, LinerAPIError, LinerClient
from app.main import create_app
from app.store import empty_source
from app.workspace import Workspace
from tests.fake_liner import FakeLiner, sse
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

KEY = "zz-fake-key-LEAK77"  # short on purpose: only the configured-key rule (not a pattern) can catch it
PHONE = "010-9876-5432"
CHUNKS = memo_chunks()


@pytest.fixture
def leak_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("LINER_API_KEY", raising=False)
    monkeypatch.delenv("LINER_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f"LINER_API_KEY={KEY}\nLINER_MODEL=test-model\n", encoding="utf-8")
    return env_file


def leaks(text: str) -> list[str]:
    return [s for s in (KEY, PHONE) if s in text]


def poisoned_problem_scope() -> dict[str, Any]:
    out = copy.deepcopy(flower_outputs(CHUNKS)["problem_scope"][0])
    out["pain"] = f"{out['pain']} 담당 {PHONE} · 키 {KEY}"
    return out


def poisoned_search_body() -> dict[str, Any]:
    body = copy.deepcopy(SEARCH_BODY)
    body["results"][0]["snippet"] += f" 문의 {PHONE} ({KEY})"
    return body


def runner_on(handler: Any, env_file: Path, repo_root: Path) -> tuple[AgentRunner, Workspace]:
    agents, _ = load_definitions(repo_root)
    ws = Workspace(empty_source(), agents)
    client = LinerClient(env_file=env_file, transport=httpx.MockTransport(handler))
    return AgentRunner(client, agents, ws), ws


# --- fix 3: model answers are masked before they are recorded --------------------------------------
def test_chat_answer_is_masked_before_the_event_is_recorded(repo_root: Path, leak_env: Path) -> None:
    from tests.pipeline_helpers import build

    orch, ws, _ = build(repo_root, leak_env, {"problem_scope": [poisoned_problem_scope()]})
    orch.ingest(CHUNKS)
    orch.advance()
    chats = [e for e in ws.source["events"] if e["type"] == "liner_chat"]
    assert chats and leaks(json.dumps(chats, ensure_ascii=False)) == []
    assert leaks(json.dumps(ws.source, ensure_ascii=False)) == []


# --- fix 6: provider error text never becomes an event or an exception message -----------------------
def test_sse_error_text_is_not_recorded(repo_root: Path, leak_env: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == AI_SEARCH_URL:
            return httpx.Response(200, text=sse({"type": "error", "errorText": f"bad key {KEY} for {PHONE}"}))
        return httpx.Response(500, text=f"upstream said {KEY} {PHONE}")

    runner, ws = runner_on(handler, leak_env, repo_root)
    assert runner.research("researcher", "꽃 구독 결제 실패") == []
    recorded = json.dumps(ws.source["events"], ensure_ascii=False)
    assert leaks(recorded) == []
    errors = [e["data"]["error"] for e in ws.source["events"] if e["type"] == "liner_search"]
    assert errors and all(errors)


def test_stream_error_exception_carries_a_kind_and_a_fixed_message(leak_env: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse({"type": "error", "errorText": f"bad key {KEY} for {PHONE}"}))

    client = LinerClient(env_file=leak_env, transport=httpx.MockTransport(handler))
    with pytest.raises(LinerAPIError) as exc:
        client.ai_search("질문")
    assert leaks(str(exc.value)) == [] and exc.value.kind == "stream_error"


@pytest.mark.parametrize("status, kind", [(401, "auth"), (402, "credits"), (429, "rate_limit"), (503, "server")])
def test_http_errors_map_to_a_kind_without_the_body(leak_env: Path, status: int, kind: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=f"{KEY} {PHONE}")

    client = LinerClient(env_file=leak_env, transport=httpx.MockTransport(handler))
    with pytest.raises(LinerAPIError) as exc:
        client.search("질문")
    assert leaks(str(exc.value)) == [] and exc.value.kind == kind and f"HTTP {status}" in str(exc.value)


# --- the whole run: events, demo recording, zip ------------------------------------------------------
def test_events_recording_and_zip_hold_neither_key_nor_phone(tmp_path: Path, leak_env: Path,
                                                             repo_root: Path) -> None:
    fake = FakeLiner({**flower_outputs(CHUNKS), "problem_scope": [poisoned_problem_scope()]},
                     search_body=poisoned_search_body())
    settings = Settings(db_path=tmp_path / "l.sqlite3", env_file=leak_env)
    client = TestClient(create_app(settings, liner=LinerClient(env_file=leak_env, transport=fake.transport())))
    pid = client.post("/api/projects", json={"name": "누출 점검", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})
    refused = client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": False,
                                                         "reason": f"{PHONE} 로 연락 주세요"})
    assert refused.status_code == 409
    client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True})
    for kind in ("unknown", "choice"):
        q = client.get(base).json()["todo"]["question"]
        client.post(f"{base}/answers", json={"question_id": q["id"], "kind": kind, "value": q["options"][0]})
    client.post(f"{base}/answers/submit")
    client.post(f"{base}/confirmations", json={"cp": "CP2", "approved": True})
    client.post(f"{base}/confirmations", json={
        "cp": "CP3", "approved": True, "waivers": {"coverage.no_tc:REQ-02": "다음 단계에서 시험"}})
    assert client.post(f"{base}/confirmations", json={"cp": "CP4", "approved": True}).status_code == 202

    source = client.get(base).json()["source"]
    assert source["meta"]["pipeline"]["status"] == "completed"
    assert leaks(json.dumps(source["events"], ensure_ascii=False)) == []

    agents, _ = load_definitions(repo_root)
    recording = make_recording(Workspace(source, agents), "fake", "test-model", "누출 점검")
    assert leaks(json.dumps(recording, ensure_ascii=False)) == []

    response = client.get(f"{base}/download")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        for name in zf.namelist():
            assert leaks(zf.read(name).decode("utf-8", errors="ignore")) == [], name


def test_committed_demo_recording_holds_no_key_or_phone(repo_root: Path) -> None:
    text = (repo_root / "demo" / "flower-run.json").read_text(encoding="utf-8")
    assert "fake-key-for-recording" not in text and PHONE not in text
