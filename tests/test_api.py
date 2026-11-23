from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client(tmp_path: Path, env_file: Path) -> TestClient:
    settings = Settings(db_path=tmp_path / "api.sqlite3", env_file=env_file)
    return TestClient(create_app(settings))


@pytest.fixture
def client_no_key(tmp_path: Path, no_key_env: Path) -> TestClient:
    return make_client(tmp_path, no_key_env)


@pytest.fixture
def client_with_key(tmp_path: Path, key_env: Path) -> TestClient:
    return make_client(tmp_path, key_env)


def test_health(client_no_key: TestClient) -> None:
    response = client_no_key.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_key_status_absent(client_no_key: TestClient) -> None:
    assert client_no_key.get("/api/liner/key-status").json() == {"present": False}


def test_key_added_after_start_works_without_restart(client_no_key: TestClient, no_key_env: Path) -> None:
    missing = client_no_key.post("/api/projects", json={"name": "p", "mode": "real"})
    assert missing.status_code == 400 and "다시 시작" not in missing.json()["detail"]  # README: no restart needed
    no_key_env.write_text("LINER_API_KEY=fake-key-after-start\n", encoding="utf-8")  # .env made after start
    assert client_no_key.get("/api/liner/key-status").json() == {"present": True}


def test_key_status_present_never_echoes_key(client_with_key: TestClient) -> None:
    response = client_with_key.get("/api/liner/key-status")
    assert response.json() == {"present": True}
    assert "test-key-123" not in response.text


def test_list_agents(client_no_key: TestClient) -> None:
    agents = client_no_key.get("/api/agents").json()["agents"]
    assert {a["id"] for a in agents} == {
        "coordinator", "fde_lead", "researcher", "pm", "designer", "developer", "qa", "consumer",
    }
    researcher = next(a for a in agents if a["id"] == "researcher")
    assert researcher["tools"] == ["liner_ai_search", "liner_search"]
    assert researcher["draft"] is True


def test_get_team(client_no_key: TestClient) -> None:
    team = client_no_key.get("/api/teams/default").json()
    assert team["coordinator"] == "coordinator"
    assert len(team["relations"]) == 14
    assert {"from", "to", "carries"} <= set(team["relations"][0])


def test_get_unknown_team_404(client_no_key: TestClient) -> None:
    assert client_no_key.get("/api/teams/nope").status_code == 404


def test_create_and_get_demo_project(client_no_key: TestClient) -> None:
    created = client_no_key.post("/api/projects", json={"name": "꽃님 구독", "mode": "demo"})
    assert created.status_code == 201
    project = created.json()
    fetched = client_no_key.get(f"/api/projects/{project['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "꽃님 구독"
    assert fetched.json()["source"]["requirements"] == []


def test_real_mode_without_key_fails_fast(client_no_key: TestClient) -> None:
    response = client_no_key.post("/api/projects", json={"name": "x", "mode": "real"})
    assert response.status_code == 400
    assert "LINER_API_KEY" in response.json()["detail"]


def test_real_mode_with_key_created(client_with_key: TestClient) -> None:
    response = client_with_key.post("/api/projects", json={"name": "x", "mode": "real"})
    assert response.status_code == 201
    assert response.json()["mode"] == "real"


def test_invalid_mode_422(client_no_key: TestClient) -> None:
    assert client_no_key.post("/api/projects", json={"name": "x", "mode": "turbo"}).status_code == 422


def test_unknown_project_404(client_no_key: TestClient) -> None:
    assert client_no_key.get("/api/projects/missing").status_code == 404
