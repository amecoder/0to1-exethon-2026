from __future__ import annotations
"""CP1 「이 제품을 쓰고 모자란 부분만 만들기」: take an existing product and build only what it lacks."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.checks import answer_decisions
from app.config import Settings
from app.main import create_app
from app.orchestrator import PipelineStateError
from app.stage_common import GAP_KEY, gap_instruction
from tests.flower_script import extra_input
from tests.pipeline_helpers import CHUNKS, build
from tests.test_build_or_buy import at_cp1, with_alternative

INSTRUCTION = gap_instruction("꽃배달 앱", "정기 배송", "요일 선택")


def test_gap_instruction_names_product_covers_and_lacks() -> None:
    assert INSTRUCTION == ("발주사가 꽃배달 앱을(를) 쓰기로 했다. 그 제품이 해 주는 것(정기 배송)은 만들지 말고, "
                           "모자란 것(요일 선택)과 그 제품과 연결하는 부분만 요구사항으로 만든다")


def test_build_gap_records_decision_scope_and_continues(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = at_cp1(repo_root, key_env)
    orch.build_gap("ALT-01", "발주사")
    [dec] = ws.items("decisions")
    assert dec["kind"] == "build_or_buy" and dec["chosen"] == "꽃배달 앱 + 모자란 부분만"
    assert dec["alternative_ref"] == "ALT-01" and dec["evidence_refs"] == ["EV-01"]
    assert dec["rejected"] == ["새로 만들기", "제품만 쓰고 끝내기"]
    out = ws.items("scope")[0]["out"]
    assert out[-1]["text"] == "꽃배달 앱이(가) 이미 해 주는 것: 정기 배송"
    assert out[-1]["decided_by"] == "client" and out[-1]["status"] == "확인"
    assert ws.items("confirmations")[-1]["cp"] == "CP1" and ws.items("confirmations")[-1]["approved"] is True
    assert ws.pipeline["stage"] == "S3" and ws.pipeline["status"] == "running"
    orch.advance()
    assert ws.pipeline["stage"] == "S3" and ws.pipeline["status"] == "awaiting_answers"
    [pm] = fake.chat_payloads("requirement_candidates")
    assert extra_input(pm)[GAP_KEY] == INSTRUCTION
    assert extra_input(fake.chat_payloads("qa_findings")[0])[GAP_KEY] == INSTRUCTION


def test_gap_instruction_reaches_s4_and_stays_out_of_answer_checks(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = at_cp1(repo_root, key_env)
    orch.build_gap("ALT-01", "발주사")
    orch.advance()
    first, second = ws.items("questions")
    orch.answer(first["id"], "choice", first["options"][0])
    orch.answer(second["id"], "choice", second["options"][0])
    orch.submit_answers()
    orch.advance()
    assert extra_input(fake.chat_payloads("requirements_final")[0])[GAP_KEY] == INSTRUCTION
    assert all(d.get("kind") != "build_or_buy" for d in answer_decisions(ws.source))
    assert ws.pipeline.get("feedback") is None


def test_build_gap_lists_other_products_as_rejected(repo_root: Path, key_env: Path) -> None:
    two = {**with_alternative(), "alternatives": [
        *with_alternative()["alternatives"],
        {"name": "다른 앱", "covers": "꽃", "lacks": "배송", "result_id": "R1-1", "quote": "없는 문장"}]}
    orch, ws, _ = at_cp1(repo_root, key_env, research_evidence=[two])
    orch.build_gap("ALT-01", "발주사")
    assert ws.items("decisions")[0]["rejected"] == ["새로 만들기", "다른 앱", "제품만 쓰고 끝내기"]


def test_build_gap_rejects_unknown_id_and_wrong_stage(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = at_cp1(repo_root, key_env)
    with pytest.raises(PipelineStateError, match="기존 제품"):
        orch.build_gap("ALT-99", "발주사")
    assert not ws.items("decisions") and ws.pipeline["stage"] == "CP1"
    fresh, _, _ = build(repo_root, key_env)
    fresh.ingest(CHUNKS)
    with pytest.raises(PipelineStateError):
        fresh.build_gap("ALT-01", "발주사")
    orch.build_gap("ALT-01", "발주사")
    with pytest.raises(PipelineStateError):
        orch.build_gap("ALT-01", "발주사")


def test_gap_route_refuses_outside_cp1(tmp_path: Path, key_env: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "t.sqlite3", env_file=key_env)))
    pid = client.post("/api/projects", json={"name": "t", "mode": "real"}).json()["id"]
    res = client.post(f"/api/projects/{pid}/alternatives/ALT-01/gap")
    assert res.status_code == 409
    assert res.json()["detail"]
