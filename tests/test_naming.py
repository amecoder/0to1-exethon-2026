from __future__ import annotations
"""D1 (11-20): a project's name — what the client sees and what a built service is called."""

from app.naming import NAME_MAX, clean_name


def test_clean_name_drops_what_the_systems_list_splits_on() -> None:
    assert clean_name(" 꽃님:  정기구독 — 앱 ") == "꽃님 정기구독-앱"
    assert len(clean_name("가" * 100)) == NAME_MAX == 40
    assert clean_name(" : ") == ""


from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from app.store import ProjectStore, empty_source
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, problem_scope
from tests.test_orchestrator import CHUNKS


def client_with(tmp_path: Path, key_env: Path, scopes: list[dict[str, Any]] | None = None) -> TestClient:
    outputs = flower_outputs(CHUNKS)
    if scopes is not None:
        outputs = {**outputs, "problem_scope": scopes}
    liner = LinerClient(env_file=key_env, transport=FakeLiner(outputs, search_body=SEARCH_BODY).transport())
    return TestClient(create_app(Settings(db_path=tmp_path / "name.sqlite3", env_file=key_env), liner=liner))


def named(name: str) -> dict[str, Any]:
    return {**problem_scope(CHUNKS), "service_name": name}


def started(client: TestClient) -> str:
    p = client.post("/api/projects", json={"name": "새 프로젝트", "mode": "real"}).json()
    client.post(f"/api/projects/{p['id']}/input", json={"chunks": CHUNKS})
    return p["id"]


def test_s2_names_the_project(tmp_path: Path, key_env: Path) -> None:
    client = client_with(tmp_path, key_env, [named("꽃님: 정기구독")])
    pid = started(client)
    project = client.get(f"/api/projects/{pid}").json()
    assert project["name"] == "꽃님 정기구독"
    assert client.get("/api/projects").json()["projects"][0]["name"] == "꽃님 정기구독"
    named_events = [e for e in project["source"]["events"] if e["type"] == "project_named"]
    assert len(named_events) == 1 and named_events[0]["actor"] == "fde_lead"


def test_without_a_proposed_name_the_placeholder_stays(tmp_path: Path, key_env: Path) -> None:
    client = client_with(tmp_path, key_env)
    pid = started(client)
    project = client.get(f"/api/projects/{pid}").json()
    assert project["name"] == "새 프로젝트"
    assert not [e for e in project["source"]["events"] if e["type"] == "project_named"]


def test_a_client_name_survives_an_s2_rework(tmp_path: Path, key_env: Path) -> None:
    client = client_with(tmp_path, key_env, [named("꽃님 정기구독"), named("다른 이름")])
    pid = started(client)
    assert client.put(f"/api/projects/{pid}/name", json={"name": "우리 꽃집 구독"}).json() == {"name": "우리 꽃집 구독"}
    client.post(f"/api/projects/{pid}/confirmations", json={"cp": "CP1", "approved": False, "reason": "범위를 다시 봐 주세요"})
    assert client.get(f"/api/projects/{pid}").json()["name"] == "우리 꽃집 구독"


def test_rename_refuses_personal_data_and_empty_names(tmp_path: Path, key_env: Path) -> None:
    client = client_with(tmp_path, key_env)
    pid = started(client)
    assert client.put(f"/api/projects/{pid}/name", json={"name": "김꽃님 010-1234-5678"}).status_code == 409
    assert client.put(f"/api/projects/{pid}/name", json={"name": " : "}).status_code == 422
    assert client.get(f"/api/projects/{pid}").json()["name"] == "새 프로젝트"


def test_services_carry_the_name_and_number_duplicates(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "svc.sqlite3")
    a = store.create_company("꽃집")
    for _ in range(2):
        source = {**empty_source(), "requirements": [{"id": "REQ-01", "title": "신청", "statement": "s", "status": "확정"}],
                  "confirmations": [{"cp": "CP4", "approved": True}]}
        source["meta"] = {**source.get("meta", {}), "name": {"value": "꽃님 정기구독", "by": "fde_lead"}}
        store.create("새 프로젝트", "real", source, company_id=a["id"])
    assert [s["name"] for s in store.services(a["id"])] == ["꽃님 정기구독", "꽃님 정기구독 (2)"]


def test_a_name_never_reaches_the_document_style_unescaped() -> None:
    from app.doc_html import page
    html = page("제목", "<p>본문</p>", "</style><script>alert(1)</script>")
    assert "<script>" not in html


def test_rename_refuses_text_that_is_not_valid_unicode(tmp_path: Path, key_env: Path) -> None:
    client = client_with(tmp_path, key_env)
    pid = started(client)
    response = client.put(f"/api/projects/{pid}/name", content='{"name": "\\ud83c 꽃"}',
                          headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_numbered_duplicates_keep_their_number_within_the_name_limit(tmp_path: Path) -> None:
    from app.naming import NAME_MAX, clean_name
    store = ProjectStore(tmp_path / "svc2.sqlite3")
    a = store.create_company("꽃집")
    long_name = "가" * NAME_MAX
    for _ in range(2):
        source = {**empty_source(), "requirements": [{"id": "REQ-01", "title": "신청", "statement": "s", "status": "확정"}],
                  "confirmations": [{"cp": "CP4", "approved": True}]}
        source["meta"] = {**source.get("meta", {}), "name": {"value": long_name, "by": "client"}}
        store.create("새 프로젝트", "real", source, company_id=a["id"])
    names = [clean_name(s["name"]) for s in store.services(a["id"])]
    assert len(set(names)) == 2 and names[1].endswith("(2)")


def test_a_name_kept_as_plain_text_still_reads(tmp_path: Path) -> None:
    from app.store import display_name
    assert display_name("새 프로젝트", {"meta": {"name": "꽃님 정기구독"}}) == "꽃님 정기구독"


def test_demo_replay_keeps_the_project_name() -> None:
    from app.demo import apply_event
    out = apply_event(empty_source(), {"type": "project_named", "actor": "fde_lead", "data": {"name": "꽃님 정기구독"}})
    assert out["meta"]["name"]["value"] == "꽃님 정기구독"
