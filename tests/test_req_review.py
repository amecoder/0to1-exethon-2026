from __future__ import annotations
"""CP2 card review: 확정 or 고칠 점 per requirement, send the notes for rework, repeat until all are 확정."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.errors import PipelineStateError
from app.req_review import fixes_text, review_summary
from tests.pipeline_helpers import build, to_cp2
from tests.test_delivery_api import CHUNKS, client_for


def test_marks_count_and_unsent_fixes_block_approval(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    first, second = [r["id"] for r in ws.items("requirements")][:2]
    orch.review_requirement(first, "ok", None, "발주사")
    with pytest.raises(PipelineStateError):
        orch.review_requirement(second, "fix", "  ", "발주사")  # a fix needs words
    orch.review_requirement(second, "fix", "일시정지는 하루 전까지로 해 주세요", "발주사")
    summary = review_summary(ws.source)
    assert (summary["ok"], summary["fix"], summary["open"]) == (1, 1, summary["total"] - 2)
    assert f"{second} 「" in (fixes_text(ws.source) or "")
    with pytest.raises(PipelineStateError, match="고칠 점"):
        orch.confirm("CP2", True, "발주사")
    orch.review_requirement(second, "clear", None, "발주사")
    assert review_summary(ws.source)["fix"] == 0
    orch.confirm("CP2", True, "발주사")  # nothing unsent: the old one-click approval still works


def test_sending_fixes_reworks_s4_and_keeps_unchanged_ok_marks(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp2(orch, ws)
    first, second = [r["id"] for r in ws.items("requirements")][:2]
    with pytest.raises(PipelineStateError):
        orch.send_requirement_fixes("발주사")  # no notes yet
    orch.review_requirement(first, "ok", None, "발주사")
    orch.review_requirement(second, "fix", "일시정지는 하루 전까지로 해 주세요", "발주사")
    orch.send_requirement_fixes("발주사")
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S4", "running")
    assert "일시정지는 하루 전까지로" in ws.pipeline["feedback"]
    record = ws.items("confirmations")[-1]
    assert record["approved"] is False and record["reason"].startswith("요구사항 1건 고쳐 주세요")
    assert "문구를 바꾸지 마라" not in record["reason"]  # the PM instruction stays out of the client's record
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP2", "awaiting_confirmation")
    summary = review_summary(ws.source)
    assert summary["fix"] == 0  # the note was sent; the reworked card is open again
    # the scripted PM returns the same requirements, so the untouched one keeps its 확정
    assert next(i for i in summary["items"] if i["id"] == first)["verdict"] == "ok"


def test_a_changed_requirement_loses_its_old_mark(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    req = ws.items("requirements")[0]
    orch.review_requirement(req["id"], "ok", None, "발주사")
    ws.write("pm", "requirements", {**req, "statement": req["statement"] + " (고침)"})
    assert next(i for i in review_summary(ws.source)["items"] if i["id"] == req["id"])["verdict"] is None


def test_api_review_and_cp2_todo(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})
    client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True})
    for _ in range(2):
        q = client.get(base).json()["todo"]["question"]
        client.post(f"{base}/answers", json={"question_id": q["id"], "kind": "choice", "value": q["options"][0]})
    client.post(f"{base}/answers/submit")
    todo = client.get(base).json()["todo"]
    assert todo["cp"] == "CP2" and todo["req_reviews"]["open"] == todo["req_reviews"]["total"]
    rid = todo["req_reviews"]["items"][0]["id"]
    assert client.post(f"{base}/requirements/{rid}/review", json={"verdict": "ok"}).status_code == 200
    assert client.get(base).json()["todo"]["req_reviews"]["ok"] == 1
    assert client.post(f"{base}/requirements/{rid}/review", json={"verdict": "fix"}).status_code == 409
