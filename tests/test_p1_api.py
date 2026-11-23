from __future__ import annotations
"""P1 endpoints end to end on the scripted FakeLiner: change → CP5, complaint, G8 scope, G7 continue."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks
from tests.test_scope_limit import six_screens

CHUNKS = memo_chunks()
WAIVER = {"coverage.no_tc:REQ-02": "결제 실패는 다음 단계에서 시험"}


def client_for(tmp_path: Path, env_file: Path, **overrides) -> TestClient:
    fake = FakeLiner({**flower_outputs(CHUNKS), **overrides}, search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "p1.sqlite3", env_file=env_file)
    return TestClient(create_app(settings, liner=LinerClient(env_file=env_file, transport=fake.transport())))


def to_cp3(client: TestClient) -> str:
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})
    client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True})
    for _ in range(2):
        q = client.get(base).json()["todo"]["question"]
        client.post(f"{base}/answers", json={"question_id": q["id"], "kind": "choice", "value": q["options"][0]})
    client.post(f"{base}/answers/submit")
    client.post(f"{base}/confirmations", json={"cp": "CP2", "approved": True})
    return base


def to_completed(client: TestClient) -> str:
    base = to_cp3(client)
    client.post(f"{base}/confirmations", json={"cp": "CP3", "approved": True, "waivers": WAIVER})
    client.post(f"{base}/confirmations", json={"cp": "CP4", "approved": True})
    assert client.get(base).json()["todo"]["kind"] == "download"
    return base


def test_change_request_to_cp5_over_http(tmp_path: Path, key_env: Path) -> None:
    client = client_for(tmp_path, key_env)
    base = to_completed(client)
    assert client.get(base).json()["lane"] == {"open": True, "busy": False, "reason": None}
    response = client.post(f"{base}/changes", json={"utterance": "일시정지는 배송 하루 전까지 되게 해 주세요"})
    assert response.status_code == 202
    cid = response.json()["id"]
    project = client.get(base).json()
    change = next(c for c in project["source"]["changes"] if c["id"] == cid)
    assert change["status"] == "awaiting_cp5" and change["impact"]["screens"] == ["SCR-01", "SCR-02"]
    assert project["lane"]["open"] is False
    assert client.post(f"{base}/complaints", json={"text": "이거 아닌데요"}).status_code == 409
    assert client.post(f"{base}/changes/{cid}/decision", json={"approved": True}).status_code == 202
    project = client.get(base).json()
    assert project["source"]["versions"][-1]["version"] == "v3"
    assert project["source"]["confirmations"][-1]["cp"] == "CP5"
    assert project["lane"]["open"] is True


def test_complaint_over_http(tmp_path: Path, key_env: Path) -> None:
    client = client_for(tmp_path, key_env)
    base = to_completed(client)
    cmp_id = client.post(f"{base}/complaints", json={"text": "일요일에도 받고 싶어요"}).json()["id"]
    item = next(c for c in client.get(base).json()["source"]["complaints"] if c["id"] == cmp_id)
    assert item["classification"] == "새 변경 요청" and item["evidence"][0]["confirmation"]["cp"] == "CP3"
    converted = client.post(f"{base}/changes", json={"utterance": item["text"], "complaint_ref": cmp_id})
    assert converted.status_code == 202


def test_lane_closed_before_cp2(tmp_path: Path, key_env: Path) -> None:
    client = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    response = client.post(f"/api/projects/{pid}/changes", json={"utterance": "바꿔 주세요"})
    assert response.status_code == 409 and "CP2" in response.json()["detail"]


def test_g8_scope_over_http(tmp_path: Path, key_env: Path) -> None:
    client = client_for(tmp_path, key_env, screen_spec=[six_screens()])
    base = to_cp3(client)
    todo = client.get(base).json()["todo"]
    assert todo["kind"] == "scope" and todo["max"] == 5
    assert client.post(f"{base}/scope", json={"keep": ["SCR-01"]}).status_code == 202
    project = client.get(base).json()
    assert project["todo"]["kind"] == "confirmation" and project["todo"]["cp"] == "CP3"
    assert [s["id"] for s in project["source"]["screens"]] == ["SCR-01"]


def test_g7_stop_and_continue_over_http(tmp_path: Path, key_env: Path) -> None:
    key_env.write_text(key_env.read_text(encoding="utf-8") + "EXETHON_MAX_LINER_CALLS=3\n", encoding="utf-8")
    client = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})  # S2 uses exactly 3 calls
    client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True})
    todo = client.get(base).json()["todo"]
    assert todo["kind"] == "limit" and todo["limit"] == "calls" and todo["max"] == 3 and todo["stage"] == "S3"
    assert "3회를 더" in todo["message"]
    # 「계속」 allows 3 more calls from here and restarts S3 (3 calls) → the question cards arrive.
    assert client.post(f"{base}/limits/continue").status_code == 202
    assert client.get(base).json()["todo"]["kind"] == "question"
