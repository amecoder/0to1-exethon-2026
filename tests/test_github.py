from __future__ import annotations
"""GitHub 연동: per-browser device-flow sign-in, then the download bundle pushed as one commit (fake GitHub, no network)."""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.github import SESSION_COOKIE, SESSION_TTL, GitHubClient
from app.liner import LinerClient
from app.main import create_app
from app.routes_github import leaked
from tests.fake_github import TOKEN, FakeGitHub
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs
from tests.test_delivery_api import CHUNKS, to_cp4


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def gh_env(key_env: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    key_env.write_text(key_env.read_text(encoding="utf-8") + "GITHUB_CLIENT_ID=Iv1.fakeclient\n", encoding="utf-8")
    return key_env


def make_app(tmp_path: Path, env_file: Path, gh: FakeGitHub, clock: Clock | None = None) -> FastAPI:
    liner = LinerClient(env_file=env_file, transport=FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY).transport())
    github = GitHubClient(env_file=env_file, transport=gh.transport(), clock=clock or Clock())
    return create_app(Settings(db_path=tmp_path / "d.sqlite3", env_file=env_file), liner=liner, github=github)


def app_for(tmp_path: Path, env_file: Path, gh: FakeGitHub, clock: Clock | None = None) -> TestClient:
    return TestClient(make_app(tmp_path, env_file, gh, clock))


def sign_in(client: TestClient, clock: Clock) -> dict:
    started = client.post("/api/github/connect").json()
    assert started["pending"]["user_code"].startswith("ABCD-") and started["connected"] is False
    waiting = client.post("/api/github/poll").json()  # authorization_pending
    assert waiting["connected"] is False and waiting["pending"]
    clock.now += 5
    return client.post("/api/github/poll").json()


def test_not_configured_speaks_to_the_user_not_the_operator(tmp_path: Path, key_env: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    client = app_for(tmp_path, key_env, FakeGitHub())
    assert client.get("/api/github/status").json()["configured"] is False
    refused = client.post("/api/github/connect")
    detail = refused.json()["detail"]
    assert refused.status_code == 409 and "운영자" in detail and "zip" in detail
    assert ".env" not in detail and "GITHUB_" not in detail


def test_first_request_sets_an_opaque_session_cookie(tmp_path: Path, gh_env: Path) -> None:
    client = app_for(tmp_path, gh_env, FakeGitHub())
    res = client.get("/api/github/status")
    cookie = res.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=") and "HttpOnly" in cookie and "Path=/api/github" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "set-cookie" not in client.get("/api/github/status").headers  # the same browser keeps its session


def test_device_flow_signs_in_without_leaking_the_token(tmp_path: Path, gh_env: Path) -> None:
    gh, clock = FakeGitHub(), Clock()
    client = app_for(tmp_path, gh_env, gh, clock)
    status = sign_in(client, clock)
    assert status == {**status, "connected": True, "login": "kim", "pending": None}
    assert "via" not in status and "can_sign_in" not in status
    assert TOKEN not in client.get("/api/github/status").text
    assert client.post("/api/github/disconnect").json()["connected"] is False


def test_poll_waits_for_the_interval_github_gave(tmp_path: Path, gh_env: Path) -> None:
    gh, clock = FakeGitHub(pending_polls=5), Clock()
    client = app_for(tmp_path, gh_env, gh, clock)
    client.post("/api/github/connect")
    for _ in range(3):
        client.post("/api/github/poll")
    assert len(gh.calls("POST", "access_token")) == 1


def test_denied_sign_in_is_reported(tmp_path: Path, gh_env: Path) -> None:
    client = app_for(tmp_path, gh_env, FakeGitHub(deny=True))
    client.post("/api/github/connect")
    denied = client.post("/api/github/poll")
    assert denied.status_code == 409 and "취소" in denied.json()["detail"]


def test_push_creates_a_private_repo_with_exactly_the_zip_files(tmp_path: Path, gh_env: Path) -> None:
    gh, clock = FakeGitHub(), Clock()
    client = app_for(tmp_path, gh_env, gh, clock)
    base = to_cp4(client)
    client.post(f"{base}/confirmations", json={"cp": "CP4", "approved": True})
    sign_in(client, clock)
    pid = base.rsplit("/", 1)[1]

    res = client.post(f"/api/github/projects/{pid}/push", json={"repo": "flower-plan"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["repo"] == "kim/flower-plan" and out["created"] is True and out["final"] is True
    assert out["commit_url"] == f"https://github.com/kim/flower-plan/commit/{out['commit']}"
    repo = gh.repos["kim/flower-plan"]
    assert repo["private"] is True and "확정본" in repo["message"]
    zip_names = set(zipfile.ZipFile(io.BytesIO(client.get(f"{base}/download").content)).namelist())
    assert set(repo["files"]) == zip_names  # the init README is replaced, nothing else
    assert TOKEN.encode() not in b"".join(repo["files"].values())

    again = client.post(f"/api/github/projects/{pid}/push", json={"repo": "kim/flower-plan"}).json()
    assert again["created"] is False and again["commit"] != out["commit"]


def test_two_browsers_each_push_with_their_own_account(tmp_path: Path, gh_env: Path) -> None:
    gh, clock = FakeGitHub(logins=("kim", "lee")), Clock()
    app = make_app(tmp_path, gh_env, gh, clock)
    kim, lee = TestClient(app), TestClient(app)  # separate cookie jars = separate browsers
    pid = to_cp4(kim).rsplit("/", 1)[1]
    bodies = [sign_in(kim, clock), sign_in(lee, clock)]
    assert (bodies[0]["login"], bodies[1]["login"]) == ("kim", "lee")
    bodies += [kim.get("/api/github/status").json(), lee.get("/api/github/status").json()]
    assert (bodies[2]["login"], bodies[3]["login"]) == ("kim", "lee")

    pushed = [c.post(f"/api/github/projects/{pid}/push", json={"repo": "plan"}) for c in (kim, lee)]
    assert [p.json()["repo"] for p in pushed] == ["kim/plan", "lee/plan"]
    assert gh.repos["kim/plan"]["pushed_by"] == "kim" and gh.repos["lee/plan"]["pushed_by"] == "lee"

    bodies += [p.text for p in pushed] + [lee.post("/api/github/disconnect").text]
    assert kim.get("/api/github/status").json()["login"] == "kim"  # lee leaving does not sign kim out
    for token in gh.tokens.values():
        assert all(token not in str(b) for b in bodies)


def test_a_fresh_browser_is_not_connected_and_cannot_push(tmp_path: Path, gh_env: Path) -> None:
    gh, clock = FakeGitHub(), Clock()
    app = make_app(tmp_path, gh_env, gh, clock)
    first = TestClient(app)
    pid = to_cp4(first).rsplit("/", 1)[1]
    sign_in(first, clock)
    fresh = TestClient(app)
    assert fresh.get("/api/github/status").json() == {**fresh.get("/api/github/status").json(),
                                                      "connected": False, "login": None, "pending": None}
    refused = fresh.post(f"/api/github/projects/{pid}/push", json={"repo": "x"})
    assert refused.status_code == 401 and "연결" in refused.json()["detail"]
    assert not gh.calls("POST", "git/blobs")


def test_an_unknown_cookie_gets_a_new_session(tmp_path: Path, gh_env: Path) -> None:
    client = app_for(tmp_path, gh_env, FakeGitHub())
    client.cookies.set(SESSION_COOKIE, "made-up-by-the-client", path="/api/github")
    res = client.get("/api/github/status")
    assert res.json()["connected"] is False and "made-up-by-the-client" not in res.headers["set-cookie"]


def test_server_github_token_is_ignored(tmp_path: Path, key_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    gh = FakeGitHub()
    client = app_for(tmp_path, key_env, gh)
    status = client.get("/api/github/status").json()
    assert status["connected"] is False and status["configured"] is False and status["login"] is None
    pid = to_cp4(client).rsplit("/", 1)[1]
    assert client.post(f"/api/github/projects/{pid}/push", json={"repo": "x"}).status_code == 409
    assert not [r for r in gh.requests if "api.github.com" in r[1]]


def test_idle_sessions_expire(tmp_path: Path, gh_env: Path) -> None:
    gh, clock = FakeGitHub(), Clock()
    client = app_for(tmp_path, gh_env, gh, clock)
    sign_in(client, clock)
    clock.now += SESSION_TTL - 1
    assert client.get("/api/github/status").json()["connected"] is True  # use keeps it alive
    clock.now += SESSION_TTL + 1
    res = client.get("/api/github/status")
    assert res.json()["connected"] is False and SESSION_COOKIE in res.headers["set-cookie"]


def test_sessions_are_capped_dropping_the_least_recently_used() -> None:
    github = GitHubClient(max_sessions=2)
    a = github.session(None)
    b = github.session(None)
    assert github.session(a) == a  # a is now the most recently used
    github.session(None)
    assert github.session(a) == a and github.session(b) != b


def test_push_to_an_existing_empty_repo_starts_it_first(tmp_path: Path, gh_env: Path) -> None:
    gh = FakeGitHub(repos={"team-x/plan": {"private": True, "head": None, "files": {}, "default_branch": "main"}})
    clock = Clock()
    client = app_for(tmp_path, gh_env, gh, clock)
    base = to_cp4(client)
    sign_in(client, clock)
    res = client.post(f"/api/github/projects/{base.rsplit('/', 1)[1]}/push", json={"repo": "team-x/plan"})
    assert res.status_code == 200, res.text
    assert res.json()["final"] is False and "작업본" in gh.repos["team-x/plan"]["message"]
    assert gh.calls("PUT", "contents/.gitkeep")


def test_push_refuses_bad_names_missing_org_repos_and_signed_out(tmp_path: Path, gh_env: Path) -> None:
    gh, clock = FakeGitHub(), Clock()
    client = app_for(tmp_path, gh_env, gh, clock)
    pid = to_cp4(client).rsplit("/", 1)[1]
    url = f"/api/github/projects/{pid}/push"
    assert "연결" in client.post(url, json={"repo": "x"}).json()["detail"]
    sign_in(client, clock)
    assert "영문" in client.post(url, json={"repo": "꽃님 기획"}).json()["detail"]
    assert "먼저 만들어" in client.post(url, json={"repo": "other-org/x"}).json()["detail"]
    gh.revoked = True
    signed_out = client.post(url, json={"repo": "x"})
    assert signed_out.status_code == 401 and "다시 연결" in signed_out.json()["detail"]
    assert client.get("/api/github/status").json()["connected"] is False


def test_push_without_documents_is_refused(tmp_path: Path, gh_env: Path) -> None:
    gh, clock = FakeGitHub(), Clock()
    client = app_for(tmp_path, gh_env, gh, clock)
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    sign_in(client, clock)
    refused = client.post(f"/api/github/projects/{pid}/push", json={"repo": "x"})
    assert refused.status_code == 409 and "문서" in refused.json()["detail"]
    assert not gh.calls("POST", "git/blobs")


def test_g3_blocks_files_holding_a_configured_secret() -> None:
    files = {"README.txt": "hello", "source.json": '{"note": "key test-key-123"}', "a.jpg": b"\x00\x01"}
    assert leaked(files, ("test-key-123",)) == ["source.json"]
    assert leaked(files, ()) == []
