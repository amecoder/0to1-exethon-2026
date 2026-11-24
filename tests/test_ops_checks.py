from __future__ import annotations
"""운영 확인 항목: decisions, people's work steps and after-launch measures are written by QA as OPS- items
(checked by a person, not by clicking a screen). They count as coverage, so no 「테스트 케이스 없음」 warning."""

from pathlib import Path
from typing import Any

from app.checks import coverage_warnings
from app.documents import build_documents
from tests.flower_script import qa_test_cases
from tests.pipeline_helpers import CHUNKS, build, to_cp3

OPS = [
    {"title": "결제 실패 재시도 규칙을 결제 대행사와 맞춰 봤는지", "requirement_refs": ["REQ-02", "REQ-99"],
     "how": "출시 전 운영자가 대행사 설정 화면을 캡처해 남긴다"},
    {"title": "빈 항목", "requirement_refs": [], "how": ""},
]


def with_ops(payload: dict[str, Any]) -> dict[str, Any]:
    out = qa_test_cases(CHUNKS)
    out = out(payload) if callable(out) else out
    return {**out, "ops_checks": OPS}


def test_ops_checks_are_stored_and_count_as_coverage(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env, {"test_cases": [with_ops]})
    to_cp3(orch, ws)
    plan = ws.items("test_plan")[0]
    assert plan["ops_checks"] == [{"id": "OPS-01", "title": OPS[0]["title"], "requirement_refs": ["REQ-02"],
                                   "how": OPS[0]["how"]}]
    assert "coverage.no_tc:REQ-02" not in {w["id"] for w in coverage_warnings(ws.source)}
    assert "ops_checks" in fake.chat_payloads("test_cases")[0]["messages"][-1]["content"]
    doc = build_documents(ws.source)["tests"]
    ops = next(s for s in doc["sections"] if s["id"] == "ops")
    assert ops["blocks"][-1]["rows"][0][:3] == ["OPS-01", OPS[0]["title"], "REQ-02"]  # 11-24: an intro line comes first
    coverage = next(s for s in doc["sections"] if s["id"] == "coverage")
    assert any("OPS-01" in row[2] for row in coverage["blocks"][-1]["rows"])


def test_without_ops_checks_the_warning_stays(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    assert ws.items("test_plan")[0]["ops_checks"] == []
    assert "coverage.no_tc:REQ-02" in {w["id"] for w in coverage_warnings(ws.source)}
    assert all(s["id"] != "ops" for s in build_documents(ws.source)["tests"]["sections"])
