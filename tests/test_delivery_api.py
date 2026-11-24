from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from app.store import FIXTURE_BUNDLE_FIELDS, export_fixture
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

CHUNKS = memo_chunks()
FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "src"
ZIP_NAMES = {"README.txt", "prototype.html", "BRD.md", "PRD.md", "화면설계서.md", "테스트케이스.md", "source.json"}


def client_for(tmp_path: Path, env_file: Path) -> tuple[TestClient, FakeLiner]:
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "d.sqlite3", env_file=env_file)
    return TestClient(create_app(settings, liner=LinerClient(env_file=env_file, transport=fake.transport()))), fake


def to_cp4(client: TestClient) -> str:
    """S1 → CP4 through the API; the first card answered '잘 모르겠어요' so REQ-01 is 가정."""
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})
    client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True})
    for kind in ("unknown", "choice"):
        q = client.get(base).json()["todo"]["question"]
        client.post(f"{base}/answers", json={"question_id": q["id"], "kind": kind, "value": q["options"][0]})
    client.post(f"{base}/answers/submit")
    client.post(f"{base}/confirmations", json={"cp": "CP2", "approved": True})
    client.post(f"{base}/confirmations", json={
        "cp": "CP3", "approved": True, "waivers": {"coverage.no_tc:REQ-02": "다음 단계에서 시험"}})
    return base


def test_s1_to_cp4_then_download_end_to_end(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = to_cp4(client)
    project = client.get(base).json()
    todo = project["todo"]
    assert todo["kind"] == "confirmation" and todo["cp"] == "CP4" and todo["title"] == "프로토타입 인수"
    assert todo["review"]["can_approve"] is True and "프로토타입" in todo["review"]["summary"]
    assert project["source"]["qa_checklist"][0]["rows"][0]["tc_id"] == "TC-01"

    assert project["delivery"]["ready"] is True and project["delivery"]["final"] is False
    draft = zipfile.ZipFile(io.BytesIO(client.get(f"{base}/download").content))
    assert draft.read("README.txt").decode("utf-8").startswith("[작업본]")
    assert "**[작업본]" in draft.read("PRD.md").decode("utf-8") and "(작업본)" in draft.read("PRD.html").decode("utf-8")

    assert client.post(f"{base}/confirmations", json={"cp": "CP4", "approved": True}).status_code == 202
    project = client.get(base).json()
    assert project["todo"]["kind"] == "download" and project["todo"]["decision_status"]["planning_done"] is True
    assert project["delivery"]["final"] is True
    assert project["source"]["meta"]["pipeline"]["status"] == "completed"

    response = client.get(f"{base}/download")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(zf.namelist())
    assert ZIP_NAMES <= names and {"wireframes/SCR-01.svg", "wireframes/SCR-02.svg"} <= names
    for name in ("BRD.md", "PRD.md", "화면설계서.md", "테스트케이스.md"):
        text = zf.read(name).decode("utf-8")
        assert "## 아직 확정되지 않은 것" in text and text.index("## 아직 확정되지 않은 것") < text.index("## 한눈에 보기")
    assert "- 가정 요구사항" in zf.read("PRD.md").decode("utf-8")  # 11-24: each item is named in its own document only
    prototype = zf.read("prototype.html").decode("utf-8")
    assert "SCR-01" in prototype and "Content-Security-Policy" in prototype
    readme = zf.read("README.txt").decode("utf-8")
    assert "가짜 데이터" in readme and "source.json" in readme and "작업본" not in readme
    source = json.loads(zf.read("source.json"))
    assert "events" not in source and source["prototype"][0]["origin"] == "agent"
    fixture = export_fixture(source)
    for bundle, fields in FIXTURE_BUNDLE_FIELDS.items():
        assert fixture[bundle] and all(set(item) == set(fields) for item in fixture[bundle])
    assert "category" in source["requirements"][0]  # added fields are kept
    assert "test-key-123" not in response.content.decode("latin-1")
    assert fake.chat_names.count("prototype") == 1


def test_download_waits_for_the_documents(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})
    assert client.get(base).json()["delivery"]["ready"] is False
    refused = client.get(f"{base}/download")
    assert refused.status_code == 409 and "문서" in refused.json()["detail"]


def test_cp4_reject_goes_back_to_development(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = to_cp4(client)
    assert client.post(f"{base}/confirmations", json={"cp": "CP4", "approved": False}).status_code == 409
    rejected = client.post(f"{base}/confirmations", json={"cp": "CP4", "approved": False, "reason": "버튼이 작아요"})
    assert rejected.status_code == 202
    assert client.get(base).json()["todo"]["cp"] == "CP4"
    assert fake.chat_names.count("prototype") == 2
    draft = client.get(f"{base}/download")
    assert draft.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(draft.content)).read("README.txt").decode("utf-8").startswith("[작업본]")


def test_preview_is_sandboxed_without_same_origin(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    assert client.get(f"/api/projects/{pid}/prototype/preview").status_code == 404
    base = to_cp4(client)
    response = client.get(f"{base}/prototype/preview")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "connect-src 'none'" in csp
    assert 'sandbox="allow-scripts"' in response.text and "allow-same-origin" not in response.text
    assert "fonts.example.com" not in response.text  # stripped by G6 before it was stored


def test_frontend_iframes_never_allow_same_origin() -> None:
    sources = [p.read_text(encoding="utf-8") for p in FRONTEND.rglob("*.tsx")]
    iframes = [s for s in sources if "<iframe" in s]
    assert iframes, "the CP4 view must render the preview in an iframe"
    assert all("allow-same-origin" not in s for s in sources)
    assert all('sandbox="allow-scripts"' in s for s in iframes)


def test_the_trace_endpoint_returns_spans(tmp_path: Path, key_env: Path) -> None:
    """E2 (11-21): GET …/trace — the project's event log as OTLP/JSON spans."""
    client, _ = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    client.post(f"/api/projects/{pid}/input", json={"chunks": CHUNKS})
    response = client.get(f"/api/projects/{pid}/trace")
    assert response.status_code == 200
    spans = response.json()["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert spans and any(s["name"].startswith("chat ") for s in spans)
    assert client.get("/api/projects/nope/trace").status_code == 404
