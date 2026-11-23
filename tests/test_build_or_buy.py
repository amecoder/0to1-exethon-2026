from __future__ import annotations
"""CP1 build-or-buy: existing products found by the researcher and the client ending the project with one."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.orchestrator import PipelineStateError
from app.views import client_todo
from tests.flower_script import SNIPPET, extra_input, research_evidence
from tests.pipeline_helpers import CHUNKS, build

QUOTE = "3일 안에 한 번 더 결제를 시도한다"
ASKED = "이런 기능을 제공하는 앱이 이미 있는지 먼저 알려 주세요"


def with_alternative(name: str = "꽃배달 앱", quote: str = QUOTE) -> dict[str, Any]:
    return {**research_evidence(CHUNKS), "alternatives": [
        {"name": name, "covers": "정기 배송", "lacks": "요일 선택", "result_id": "R1-1", "quote": quote}]}


def at_cp1(repo_root: Path, key_env: Path, **overrides: list[Any]) -> tuple[Any, Any, Any]:
    orch, ws, fake = build(repo_root, key_env, {"research_evidence": [with_alternative()], **overrides})
    orch.ingest(CHUNKS)
    orch.advance()
    return orch, ws, fake


def test_researcher_stores_existing_products_with_g1(repo_root: Path, key_env: Path) -> None:
    _, ws, fake = at_cp1(repo_root, key_env)
    [alt] = ws.items("alternatives")
    assert alt["id"] == "ALT-01" and alt["name"] == "꽃배달 앱" and alt["status"] == "확인"
    assert alt["evidence_refs"] == ["EV-01"] and alt["lacks"] == "요일 선택"
    assert QUOTE in SNIPPET
    assert "이미 해 주는 제품" in fake.chat_payloads("problem_scope")[0]["messages"][-1]["content"]


def test_alternative_quote_not_in_hit_is_unverified(repo_root: Path, key_env: Path) -> None:
    _, ws, _ = at_cp1(repo_root, key_env, research_evidence=[with_alternative(quote="지어낸 문장")])
    assert ws.items("alternatives")[0]["status"] == "미확인"
    assert any(e["data"].get("detail", "").startswith("기존 제품") for e in ws.source["events"]
               if e["type"] == "guardrail")


def test_client_can_end_with_an_existing_product(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = at_cp1(repo_root, key_env)
    with pytest.raises(PipelineStateError):
        orch.use_existing("ALT-99", "발주사")
    orch.use_existing("ALT-01", "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "closed" and ws.pipeline["stage"] == "CP1"
    [dec] = ws.items("decisions")
    assert dec["kind"] == "build_or_buy" and dec["chosen"] == "꽃배달 앱" and "새로 만들기" in dec["rejected"]
    todo = client_todo(ws.source)
    assert todo["kind"] == "closed" and todo["chosen"] == "꽃배달 앱" and todo["alternative"]["id"] == "ALT-01"
    with pytest.raises(PipelineStateError):
        orch.use_existing("ALT-01", "발주사")


def test_use_existing_route_refuses_outside_cp1(tmp_path: Path, key_env: Path) -> None:
    client = TestClient(create_app(Settings(db_path=tmp_path / "t.sqlite3", env_file=key_env)))
    pid = client.post("/api/projects", json={"name": "t", "mode": "real"}).json()["id"]
    res = client.post(f"/api/projects/{pid}/use-existing", json={"alternative_id": "ALT-01"})
    assert res.status_code == 409


def test_rerun_research_gets_known_product_names(repo_root: Path, key_env: Path) -> None:
    orch, _, fake = at_cp1(repo_root, key_env)
    assert "known_products" not in extra_input(fake.chat_payloads("research_evidence")[0])
    orch.confirm("CP1", False, "발주사", ASKED)
    orch.advance()
    assert extra_input(fake.chat_payloads("research_evidence")[1])["known_products"] == ["꽃배달 앱"]
