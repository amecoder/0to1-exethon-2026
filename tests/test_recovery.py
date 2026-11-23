from __future__ import annotations
"""A run left `running` by a server restart becomes `failed` on startup and can be retried."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.intake import split_sentences
from app.liner import LinerClient
from app.main import create_app
from app.store import ProjectStore, empty_source
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

CHUNKS = memo_chunks()


def app_for(tmp_path: Path, env_file: Path, overrides: dict | None = None) -> tuple[TestClient, FakeLiner]:
    fake = FakeLiner({**flower_outputs(CHUNKS), **(overrides or {})}, search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "r.sqlite3", env_file=env_file)
    return TestClient(create_app(settings, liner=LinerClient(env_file=env_file, transport=fake.transport()))), fake


def stuck_project(db_path: Path) -> str:
    source = {**empty_source(), "sources": split_sentences(CHUNKS),
              "meta": {"sources_locked": True, "pipeline": {"stage": "S2", "status": "running",
                                                             "active_agent": "fde_lead", "error": None}}}
    return ProjectStore(db_path).create("멈춘 프로젝트", "real", source)["id"]


def test_startup_marks_running_projects_failed_with_event(tmp_path: Path, key_env: Path) -> None:
    pid = stuck_project(tmp_path / "r.sqlite3")
    client, _ = app_for(tmp_path, key_env)
    source = client.get(f"/api/projects/{pid}").json()["source"]
    pipeline = source["meta"]["pipeline"]
    assert (pipeline["stage"], pipeline["status"]) == ("S2", "failed")
    assert "다시 시작" in pipeline["error"] and pipeline["active_agent"] is None
    assert [e["type"] for e in source["events"]][-2:] == ["run_interrupted", "pipeline"]


def test_retry_reruns_the_current_stage(tmp_path: Path, key_env: Path) -> None:
    pid = stuck_project(tmp_path / "r.sqlite3")
    client, fake = app_for(tmp_path, key_env)
    response = client.post(f"/api/projects/{pid}/retry")
    assert response.status_code == 202
    source = client.get(f"/api/projects/{pid}").json()["source"]
    assert source["meta"]["pipeline"]["stage"] == "CP1"
    assert source["meta"]["pipeline"]["error"] is None
    assert "run_retried" in [e["type"] for e in source["events"]]
    assert fake.chat_names[0] == "problem_scope"


def test_retry_after_agent_failure(tmp_path: Path, key_env: Path) -> None:
    good = flower_outputs(CHUNKS)["problem_scope"][0]
    client, _ = app_for(tmp_path, key_env, {"problem_scope": ["not json", good]})
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    client.post(f"/api/projects/{pid}/input", json={"chunks": CHUNKS})
    assert client.get(f"/api/projects/{pid}").json()["source"]["meta"]["pipeline"]["status"] == "failed"
    assert client.post(f"/api/projects/{pid}/retry").status_code == 202
    assert client.get(f"/api/projects/{pid}").json()["todo"]["cp"] == "CP1"


def test_retry_only_when_failed(tmp_path: Path, key_env: Path) -> None:
    client, _ = app_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    assert client.post(f"/api/projects/{pid}/retry").status_code == 409


def test_lane_item_left_working_is_marked_failed_on_startup(tmp_path, key_env, repo_root) -> None:
    from app.change_desk import ChangeDesk
    from app.config import Settings
    from app.definitions import load_definitions
    from app.liner import LinerClient
    from app.main import create_app
    from app.store import ProjectStore
    from tests.pipeline_helpers import build, to_cp4

    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    orch.confirm("CP4", True, "발주사")
    _, teams = load_definitions(repo_root)
    ChangeDesk(ws, teams["default"], orch._ctx.runner).open_change("일시정지는 배송 하루 전까지")
    store = ProjectStore(tmp_path / "r.sqlite3")
    pid = store.create("x", "real", ws.source)["id"]
    create_app(Settings(db_path=tmp_path / "r.sqlite3", env_file=key_env), liner=LinerClient(env_file=key_env))
    change = store.get(pid)["source"]["changes"][0]
    assert change["status"] == "failed" and "다시" in change["error"]


# --- review fix 5: confirmation stages are never stranded by a restart ------------------------------
def project_at(db_path: Path, stage: str, status: str, error: str | None = None) -> str:
    source = {**empty_source(), "sources": split_sentences(CHUNKS),
              "meta": {"sources_locked": True, "pipeline": {"stage": stage, "status": status,
                                                             "active_agent": None, "error": error}}}
    return ProjectStore(db_path).create("확인 단계", "real", source)["id"]


def test_confirmation_stage_left_running_is_restored_and_can_be_approved(tmp_path: Path, key_env: Path) -> None:
    pid = project_at(tmp_path / "r.sqlite3", "CP1", "running")
    client, _ = app_for(tmp_path, key_env)
    pipeline = client.get(f"/api/projects/{pid}").json()["source"]["meta"]["pipeline"]
    assert (pipeline["stage"], pipeline["status"], pipeline["error"]) == ("CP1", "awaiting_confirmation", None)
    assert client.post(f"/api/projects/{pid}/confirmations", json={"cp": "CP1", "approved": True}).status_code == 202


def test_confirmation_stage_marked_failed_by_an_older_restart_is_restored(tmp_path: Path, key_env: Path) -> None:
    pid = project_at(tmp_path / "r.sqlite3", "CP3", "failed", "서버가 다시 시작되어 작업이 중단되었습니다")
    client, _ = app_for(tmp_path, key_env)
    project = client.get(f"/api/projects/{pid}").json()
    assert project["source"]["meta"]["pipeline"]["status"] == "awaiting_confirmation"
    assert project["todo"]["kind"] == "confirmation" and project["todo"]["cp"] == "CP3"


def test_every_saved_state_pairs_stage_and_status(repo_root: Path, key_env: Path) -> None:
    """A crash can land between any two saves; no saved state may be a CP stage that is not waiting,
    or a work stage that waits for a confirmation."""
    from app.agent_runner import AgentRunner
    from app.definitions import load_definitions
    from app.orchestrator import STAGES, Orchestrator
    from app.workspace import Workspace
    from tests.pipeline_helpers import to_cp4

    agents, teams = load_definitions(repo_root)
    saved: list[tuple[str, str]] = []
    ws = Workspace(empty_source(), agents, on_change=lambda src: saved.append(
        (src["meta"]["pipeline"]["stage"], src["meta"]["pipeline"]["status"])))
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    orch = Orchestrator(ws, teams["default"], AgentRunner(LinerClient(env_file=key_env, transport=fake.transport()),
                                                          agents, ws))
    to_cp4(orch, ws)
    bad = [(stage, status) for stage, status in saved if STAGES.get(stage) is not None and (
        (STAGES[stage].kind == "confirm" and status != "awaiting_confirmation")
        or (STAGES[stage].kind == "work" and status == "awaiting_confirmation"))]
    assert bad == []


# --- X1 (11-21): a background crash must not leave the project `running` until a restart ---------------
def test_a_crashed_stage_becomes_failed_and_can_be_retried(tmp_path: Path, key_env: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    import app.orchestrator as orchestrator
    from app.recovery import CRASHED
    original = orchestrator.RUNS["problem"]

    def crash(ctx):  # noqa: ANN001, ANN202 - same shape as a run
        raise KeyError("비밀문장")

    monkeypatch.setitem(orchestrator.RUNS, "problem", crash)
    client, _ = app_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    client.post(f"/api/projects/{pid}/input", json={"chunks": CHUNKS})
    response = client.get(f"/api/projects/{pid}")
    pipeline = response.json()["source"]["meta"]["pipeline"]
    assert (pipeline["stage"], pipeline["status"], pipeline["error"]) == ("S2", "failed", CRASHED)
    assert "다시 시도" in pipeline["error"] and "비밀문장" not in response.text
    crashed = [e["data"] for e in response.json()["source"]["events"] if e["type"] == "run_interrupted"]
    assert crashed[-1]["crash"] == "KeyError"
    monkeypatch.setitem(orchestrator.RUNS, "problem", original)
    assert client.post(f"/api/projects/{pid}/retry").status_code == 202
    pipeline = client.get(f"/api/projects/{pid}").json()["source"]["meta"]["pipeline"]
    assert (pipeline["stage"], pipeline["status"]) == ("CP1", "awaiting_confirmation")


def test_a_crash_at_a_confirmation_returns_to_the_confirmation(tmp_path: Path, key_env: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    import app.orchestrator as orchestrator
    from app.recovery import CRASHED_CONFIRM
    client, _ = app_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    client.post(f"/api/projects/{pid}/input", json={"chunks": CHUNKS})

    def crash(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise KeyError("비밀문장")

    monkeypatch.setattr(orchestrator, "classify", crash)
    client.post(f"/api/projects/{pid}/confirmations", json={"cp": "CP1", "approved": False, "reason": "범위를 줄여 주세요"})
    response = client.get(f"/api/projects/{pid}")
    pipeline = response.json()["source"]["meta"]["pipeline"]
    assert (pipeline["stage"], pipeline["status"], pipeline["error"]) == ("CP1", "awaiting_confirmation", CRASHED_CONFIRM)
    assert "비밀문장" not in response.text and pipeline.get("asked") is None  # L2


def test_a_crashed_change_mapping_fails_the_item(tmp_path: Path, key_env: Path, repo_root: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    from app.change_desk import ChangeDesk
    from app.recovery import CRASHED_LANE
    from tests.pipeline_helpers import build, to_cp4
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    orch.confirm("CP4", True, "발주사")
    pid = ProjectStore(tmp_path / "r.sqlite3").create("x", "real", ws.source)["id"]
    client, _ = app_for(tmp_path, key_env)
    original = ChangeDesk.map_change

    def crash(self, change_id):  # noqa: ANN001, ANN202
        raise RuntimeError("비밀문장")

    monkeypatch.setattr(ChangeDesk, "map_change", crash)
    client.post(f"/api/projects/{pid}/changes", json={"utterance": "일시정지는 배송 하루 전까지"})
    response = client.get(f"/api/projects/{pid}")
    change = response.json()["source"]["changes"][-1]
    assert (change["status"], change["error"]) == ("failed", CRASHED_LANE) and "비밀문장" not in response.text
    monkeypatch.setattr(ChangeDesk, "map_change", original)
    assert client.post(f"/api/projects/{pid}/changes", json={"utterance": "일시정지는 배송 하루 전까지"}).status_code != 409


# --- Fable review (11-21) M1·L1: the call cap at the purpose check, and a project left running with no worker ---
def test_the_call_cap_at_the_purpose_check_is_a_409_not_a_500(tmp_path: Path, key_env: Path) -> None:
    from tests.test_liner_features import add_env
    add_env(key_env, LINER_DECISION_MODEL="typesafe/jev-1.13", EXETHON_MAX_LINER_CALLS="0")
    client, _ = app_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    response = client.post(f"/api/projects/{pid}/input", json={"chunks": CHUNKS})
    assert response.status_code == 409 and "상한" in response.json()["detail"]


def test_a_change_request_at_the_call_cap_is_a_409(tmp_path: Path, key_env: Path, repo_root: Path) -> None:
    from tests.pipeline_helpers import build, to_cp4
    from tests.test_liner_features import add_env
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    orch.confirm("CP4", True, "발주사")
    pid = ProjectStore(tmp_path / "r.sqlite3").create("x", "real", ws.source)["id"]
    add_env(key_env, LINER_DECISION_MODEL="typesafe/jev-1.13", EXETHON_MAX_LINER_CALLS="1")
    client, _ = app_for(tmp_path, key_env)
    response = client.post(f"/api/projects/{pid}/changes", json={"utterance": "일시정지는 배송 하루 전까지"})
    assert response.status_code == 409 and "상한" in response.json()["detail"]


def test_a_project_left_running_with_no_worker_recovers_on_the_next_request(tmp_path: Path, key_env: Path) -> None:
    client, _ = app_for(tmp_path, key_env)  # started first: startup recovery never sees this project
    pid = stuck_project(tmp_path / "r.sqlite3")
    assert client.post(f"/api/projects/{pid}/retry").status_code == 202
    pipeline = client.get(f"/api/projects/{pid}").json()["source"]["meta"]["pipeline"]
    assert (pipeline["stage"], pipeline["status"]) == ("CP1", "awaiting_confirmation")
