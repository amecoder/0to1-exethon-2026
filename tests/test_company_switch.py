from __future__ import annotations
"""EXETHON_COMPANY: the company workspace runs only when it is on. Without the setting (the contest submission)
the app runs 실제 · 시연 as before companies: no company panel, nothing of a company copied into a project."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from app.store import ProjectStore, empty_source
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs
from tests.test_orchestrator import CHUNKS


def make_client(tmp_path: Path, key_env: Path) -> TestClient:
    liner = LinerClient(env_file=key_env, transport=FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY).transport())
    return TestClient(create_app(Settings(db_path=tmp_path / "switch.sqlite3", env_file=key_env), liner=liner))


def built() -> dict:
    return {**empty_source(), "requirements": [{"id": "REQ-01", "title": "정기구독 신청", "statement": "신청한다",
                                                "status": "확정", "screens": []}],
            "confirmations": [{"cp": "CP4", "approved": True}]}


def test_without_the_setting_the_company_workspace_is_off(tmp_path: Path, key_env: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXETHON_COMPANY", raising=False)
    client = make_client(tmp_path, key_env)
    assert client.get("/api/features").json() == {"company": False}
    monkeypatch.setenv("EXETHON_COMPANY", "on")
    assert client.get("/api/features").json() == {"company": True}


def test_with_the_workspace_off_nothing_of_the_company_is_used(tmp_path: Path, key_env: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(tmp_path, key_env)  # conftest: on while the company material is set up
    a = client.post("/api/companies", json={"name": "꽃님 플라워"}).json()
    client.put(f"/api/companies/{a['id']}", json={"systems": "꽃집 POS", "notes": "회원 등급은 3단계다"})
    first = client.post("/api/projects", json={"name": "꽃님 정기구독", "mode": "real", "company_id": a["id"]}).json()
    ProjectStore(tmp_path / "switch.sqlite3").save_source(first["id"], built(), 0)
    monkeypatch.setenv("EXETHON_COMPANY", "off")
    p = client.post("/api/projects", json={"name": "선물하기", "mode": "real", "company_id": a["id"]}).json()
    client.post(f"/api/projects/{p['id']}/input", json={"chunks": CHUNKS})
    source = client.get(f"/api/projects/{p['id']}").json()["source"]
    assert source.get("company", []) == [] and source.get("systems", []) == [] and "company" not in source["meta"]
    text = json.dumps(source, ensure_ascii=False)
    assert "꽃님 플라워" not in text and "회원 등급" not in text and "꽃집 POS" not in text
