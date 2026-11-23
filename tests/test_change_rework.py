from __future__ import annotations
"""Review fix 4: a CP5 approval after delivery sends the work back through S5 → CP3 → S6 → CP4.
Nothing is confirmed automatically: until the new CP4 the zip can still be taken, but only as a 작업본."""

import io
import json
import zipfile
from pathlib import Path

from app.views import client_todo
from tests.test_delivery_api import client_for, to_cp4

PAUSE = "일시정지는 배송 하루 전까지 되게 해 주세요"
WAIVERS = {"coverage.no_tc:REQ-02": "다음 단계에서 시험"}


def readme(body: bytes) -> str:
    return zipfile.ZipFile(io.BytesIO(body)).read("README.txt").decode("utf-8")


def test_change_after_delivery_makes_download_a_draft_until_cp3_and_cp4_again(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = to_cp4(client)
    assert client.post(f"{base}/confirmations", json={"cp": "CP4", "approved": True}).status_code == 202
    assert client.get(f"{base}/download").status_code == 200

    change_id = client.post(f"{base}/changes", json={"utterance": PAUSE}).json()["id"]
    assert client.post(f"{base}/changes/{change_id}/decision", json={"approved": True}).status_code == 202

    project = client.get(base).json()
    assert project["delivery"]["ready"] is True and project["delivery"]["final"] is False
    assert change_id in project["delivery"]["note"]
    assert readme(client.get(f"{base}/download").content).startswith(f"[작업본] 변경 {change_id}")
    source = project["source"]
    recheck = source["meta"]["recheck"]
    assert recheck["change_id"] == change_id and recheck["version"] == "v3"
    assert {"documents", "screens", "tests", "prototype"} <= set(recheck["kinds"])
    # the team redid S5 by itself and now waits for a person at CP3 — never auto-approved
    assert (source["meta"]["pipeline"]["stage"], source["meta"]["pipeline"]["status"]) == ("CP3", "awaiting_confirmation")
    assert project["todo"]["kind"] == "confirmation" and project["todo"]["cp"] == "CP3"
    assert project["todo"]["recheck"]["change_id"] == change_id

    assert client.post(f"{base}/confirmations", json={"cp": "CP3", "approved": True, "waivers": WAIVERS}).status_code == 202
    assert client.get(base).json()["todo"]["cp"] == "CP4"
    assert readme(client.get(f"{base}/download").content).startswith("[작업본]")
    assert fake.chat_names.count("prototype") == 2

    assert client.post(f"{base}/confirmations", json={"cp": "CP4", "approved": True}).status_code == 202
    project = client.get(base).json()
    assert project["todo"]["kind"] == "download" and "recheck" not in project["source"]["meta"]
    response = client.get(f"{base}/download")
    assert response.status_code == 200 and "작업본" not in readme(response.content)
    assert project["delivery"]["final"] is True
    exported = json.loads(zipfile.ZipFile(io.BytesIO(response.content)).read("source.json"))
    req = next(r for r in exported["requirements"] if r["id"] == "REQ-01")
    assert change_id in req["change_refs"]
    cp4 = [c for c in exported["confirmations"] if c["cp"] == "CP4"][-1]
    assert cp4["based_on"] == exported["versions"][-1]["version"]


def test_todo_explains_the_lock_while_the_team_is_reworking() -> None:
    source = {"meta": {"pipeline": {"stage": "S5", "status": "running"},
                       "recheck": {"change_id": "CHG-01", "version": "v3", "kinds": ["documents"], "items": []}}}
    todo = client_todo(source)
    assert todo["kind"] == "none" and todo["recheck"]["change_id"] == "CHG-01"
