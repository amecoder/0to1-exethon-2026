from __future__ import annotations
"""FR-24 measurement scripts: fake mode runs in CI, real mode refuses without a key (exit 2)."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


def load(repo_root: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, repo_root / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run(repo_root: Path, *args: str, env_file: Path | None = None) -> subprocess.CompletedProcess[str]:
    extra = ["--env-file", str(env_file)] if env_file else []
    env = {"PATH": "/usr/bin:/bin", "HOME": str(repo_root)}
    return subprocess.run([sys.executable, *args, *extra], cwd=repo_root, capture_output=True, text=True, env=env)


def test_m1_rule_needs_all_words_of_one_group_in_one_unit(repo_root: Path) -> None:
    m1 = load(repo_root, "measure_m1")
    defects = [{"id": "D01", "match_any": [["요일", "토요일"]]}, {"id": "D05", "match_any": [["배송", "실패"]]}]
    units = [("질문 Q-01", "요일을 고르나요, 토요일 일괄인가요?"), ("질문 Q-02", "배송 주소"), ("지적", "결제 실패")]
    result = m1.score(units, defects)
    assert result["detected"] == ["D01"] and result["where"]["D01"] == "질문 Q-01"
    assert result["loose"] == ["D01", "D05"]  # whole-output reading also finds D05


def test_m1_units_cover_cards_findings_open_items_and_checks(repo_root: Path) -> None:
    m1 = load(repo_root, "measure_m1")
    source = {"questions": [{"id": "Q-01", "question": "a", "why": "b", "options": ["c"]}],
              "findings": [{"id": "FND-01", "note": "d"}], "open_items": [{"id": "OPEN-01", "title": "e", "reason": ""}],
              "events": [{"type": "check_result", "data": {"check": "coverage", "details": ["f"]}}]}
    assert [label for label, _ in m1.output_units(source)] == ["질문 Q-01", "QA 지적 FND-01", "미결 OPEN-01", "검사 coverage"]


def test_m1_fake_mode_prints_runs_minimum_and_disclaimer(repo_root: Path) -> None:
    result = run(repo_root, "scripts/measure_m1.py", "--fake")
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("[가짜 실행") == 3 and "최솟값" in result.stdout and "지표가 아닙니다" in result.stdout


def test_m1_scores_a_recording(repo_root: Path) -> None:
    result = run(repo_root, "scripts/measure_m1.py", "demo/flower-run.json")
    assert result.returncode == 0, result.stderr
    assert "[녹화 1]" in result.stdout


def test_decisions_fake_mode_reports_per_label_and_threshold(repo_root: Path) -> None:
    result = run(repo_root, "scripts/measure_decisions.py", "--fake")
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("[가짜") == 3 and "violation 10/10" in result.stdout and "new_change 10/10" in result.stdout
    assert "사람 판단 필요" in result.stdout and "지표가 아닙니다" in result.stdout


def test_decisions_score_counts_wrong_and_low_confidence(repo_root: Path) -> None:
    md = load(repo_root, "measure_decisions")
    cases = [{"id": "A", "expected": "violation"}, {"id": "B", "expected": "new_change"}]
    preds = {"A": {"choice": "violation", "confidence": 0.9}, "B": {"choice": "violation", "confidence": 0.3}}
    s = md.score(cases, preds, 0.6)
    assert s["accuracy"] == 0.5 and s["per_label"]["new_change"] == {"right": 0, "total": 1}
    assert s["low_confidence"] == ["B"] and md.TARGET_ACCURACY == 0.90


@pytest.mark.parametrize("script", ["scripts/measure_m1.py", "scripts/measure_m2.py", "scripts/measure_decisions.py"])
def test_real_mode_without_key_exits_2_in_korean(repo_root: Path, tmp_path: Path, script: str) -> None:
    result = run(repo_root, script, env_file=tmp_path / "missing.env")
    assert result.returncode == 2
    assert "LINER_API_KEY" in result.stderr and "--fake" in result.stderr


def test_m2_score_counts_target_recall_precision(repo_root: Path) -> None:
    m2 = load(repo_root, "measure_m2")
    cases = [{"id": "A", "target": "REQ-01", "expected": {"requirements": ["REQ-01"], "screens": ["SCR-01"], "tests": []}},
             {"id": "B", "target": "REQ-02", "expected": {"requirements": ["REQ-02"], "screens": [], "tests": ["TC-02"]}}]
    preds = {"A": {"target": "REQ-01", "impact": {"requirements": ["REQ-01"], "screens": ["SCR-01"], "tests": []}},
             "B": {"target": "REQ-03", "impact": {"requirements": ["REQ-03"], "screens": [], "tests": ["TC-02"]}}}
    s = m2.score(cases, preds)
    assert s["target_accuracy"] == 0.5 and s["impact_recall"] == 0.75 and s["impact_precision"] == 0.75
    assert s["recall_when_target_right"] == 1.0


def test_m2_fake_mode_verifies_the_deterministic_impact(repo_root: Path) -> None:
    result = run(repo_root, "scripts/measure_m2.py", "--fake")
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("대상이 맞을 때 재현율 1.000") == 3
    assert "지표가 아닙니다" in result.stdout
