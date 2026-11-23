from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

CHUNKS = memo_chunks()


def client_for(tmp_path: Path, env_file: Path) -> tuple[TestClient, FakeLiner]:
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "e2e.sqlite3", env_file=env_file)
    liner = LinerClient(env_file=env_file, transport=fake.transport())
    return TestClient(create_app(settings, liner=liner)), fake


def test_s1_to_cp3_end_to_end(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    assert client.get(base).json()["todo"]["kind"] == "input"

    response = client.post(f"{base}/input", json={"chunks": CHUNKS})
    assert response.status_code == 202 and response.json()["blocked"] is False
    project = client.get(base).json()
    assert project["source"]["meta"]["pipeline"]["stage"] == "CP1"
    assert project["todo"] == {"kind": "confirmation", "cp": "CP1", "title": "문제·범위 확인"}

    assert client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True}).status_code == 202
    todo = client.get(base).json()["todo"]
    assert todo["kind"] == "question" and todo["remaining"] == 2
    assert todo["question"]["options"] and todo["sources"]
    second = client.post(f"{base}/answers", json={"question_id": todo["question"]["id"], "kind": "unknown"})
    assert second.status_code == 202
    todo = client.get(base).json()["todo"]
    assert todo["remaining"] == 1 and todo["evidence"][0]["id"] == "EV-01"
    client.post(f"{base}/answers", json={"question_id": todo["question"]["id"], "kind": "choice",
                                         "value": todo["question"]["options"][0]})
    review = client.get(base).json()["todo"]
    assert review["kind"] == "answers_review" and [q["status"] for q in review["questions"]] == ["answered"] * 2
    assert client.post(f"{base}/answers/submit").status_code == 202

    project = client.get(base).json()
    assert project["todo"]["cp"] == "CP2"
    statuses = [r["status"] for r in project["source"]["requirements"]]
    assert statuses == ["가정", "확정"]

    review = project["todo"]["review"]
    assert review["can_approve"] is True and [r["decision_id"] for r in review["answers"]] == ["DEC-01", "DEC-02"]

    assert client.post(f"{base}/confirmations", json={"cp": "CP2", "approved": True}).status_code == 202
    project = client.get(base).json()
    source = project["source"]
    assert source["versions"][0]["version"] == "v1"
    assert source["confirmations"][-1]["who"] == "발주사"
    assert project["todo"]["cp"] == "CP3" and project["todo"]["title"] == "문서 4종 확인"
    cp3 = project["todo"]["review"]
    assert [w["id"] for w in cp3["waivable"]] == ["coverage.no_tc:REQ-02"] and cp3["can_approve"] is False
    assert cp3["answers"][0]["requirements"][0]["id"] == "REQ-01"

    docs = client.get(f"{base}/documents").json()
    assert list(docs["documents"]) == ["brd", "prd", "screens", "tests"]
    assert docs["documents"]["screens"]["sections"][1]["blocks"][0]["svg"].startswith("<svg")
    markdown = client.get(f"{base}/documents/prd.md")
    assert markdown.status_code == 200 and markdown.headers["content-type"].startswith("text/markdown")
    assert "REQ-01" in markdown.text
    word = client.get(f"{base}/documents/prd.docx")
    assert word.status_code == 200 and word.content[:2] == b"PK"  # a zip container
    assert word.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml")
    assert word.headers["content-disposition"].endswith("filename*=UTF-8''PRD.docx")
    pdf = client.get(f"{base}/documents/screens.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''%ED%99%94%EB%A9%B4%EC%84%A4%EA%B3%84%EC%84%9C.pdf" in pdf.headers["content-disposition"]
    assert client.get(f"{base}/documents/nope.pdf").status_code == 404
    svg = client.get(f"{base}/documents/wireframes/SCR-01.svg")
    assert svg.headers["content-type"].startswith("image/svg+xml") and svg.text.count('class="callout"') == 4
    assert client.get(f"{base}/documents/nope.md").status_code == 404
    assert client.get(f"{base}/documents/wireframes/SCR-99.svg").status_code == 404

    refused = client.post(f"{base}/confirmations", json={"cp": "CP3", "approved": True})
    assert refused.status_code == 409 and "REQ-02" in refused.json()["detail"]
    approved = client.post(f"{base}/confirmations", json={
        "cp": "CP3", "approved": True, "waivers": {"coverage.no_tc:REQ-02": "다음 단계에서 시험"}})
    assert approved.status_code == 202
    source = client.get(base).json()["source"]
    assert [v["version"] for v in source["versions"]] == ["v1", "v2"]
    assert (source["meta"]["pipeline"]["stage"], source["meta"]["pipeline"]["status"]) == ("CP4", "awaiting_confirmation")
    kinds = {e["type"] for e in source["events"]}
    assert {"agent_message", "liner_chat", "liner_search", "confirmation", "item_written"} <= kinds
    assert "test-key-123" not in json.dumps(source, ensure_ascii=False)
    # 11 team calls (incl. the PM's problem_done rewrite after CP2) + 2 consumer opinions (FR-20: before CP3 and CP4)
    assert len(fake.chat_names) == 13 and fake.chat_names[-2:] == ["prototype", "consumer_feedback"]


def test_input_blocked_by_g3_returns_korean_prompt(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    response = client.post(f"/api/projects/{pid}/input", json={"chunks": ["카드 1234-5678-9012-3456 로 결제"]})
    assert response.status_code == 200
    body = response.json()
    assert body["blocked"] is True and "가린 값" in body["message"] and body["kinds"] == ["카드번호"]
    assert client.get(f"/api/projects/{pid}").json()["source"]["sources"] == []


def test_wrong_state_requests_are_rejected(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    assert client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True}).status_code == 409
    assert client.post(f"{base}/answers", json={"question_id": "Q-01", "kind": "unknown"}).status_code == 409
    assert client.post("/api/projects/missing/input", json={"chunks": ["a"]}).status_code == 404


def test_demo_project_cannot_run_live_pipeline(tmp_path: Path, no_key_env: Path) -> None:
    client, _ = client_for(tmp_path, no_key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "demo"}).json()["id"]
    response = client.post(f"/api/projects/{pid}/input", json={"chunks": ["안녕하세요."]})
    assert response.status_code == 400
