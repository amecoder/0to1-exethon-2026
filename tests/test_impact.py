from __future__ import annotations
"""FR-21 impact rule: the Python port must agree with eval/validate_golden.sh on all 20 golden cases."""

import json
import subprocess
from pathlib import Path

import pytest

from app.impact import impacted, owners_of

FIXTURE = "examples/flower-subscription/requirements_fixture.json"
CASES = "eval/golden/change_cases.json"


def load(repo_root: Path, rel: str) -> dict:
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def test_python_rule_matches_all_golden_cases(repo_root: Path) -> None:
    reqs = load(repo_root, FIXTURE)["requirements"]
    for case in load(repo_root, CASES)["cases"]:
        got = impacted(reqs, case["target"])
        expected = {k: sorted(v) for k, v in case["expected"].items()}
        assert got == expected, case["id"]


def test_transitive_closure_follows_reverse_depends_on() -> None:
    reqs = [
        {"id": "REQ-01", "depends_on": [], "screens": ["SCR-01"], "tests": ["TC-01"]},
        {"id": "REQ-02", "depends_on": ["REQ-01"], "screens": ["SCR-02"], "tests": []},
        {"id": "REQ-03", "depends_on": ["REQ-02"], "screens": ["SCR-02"], "tests": ["TC-03"]},
        {"id": "REQ-04", "depends_on": [], "screens": ["SCR-04"], "tests": ["TC-04"]},
    ]
    assert impacted(reqs, "REQ-01") == {"requirements": ["REQ-01", "REQ-02", "REQ-03"],
                                        "screens": ["SCR-01", "SCR-02"], "tests": ["TC-01", "TC-03"]}
    assert impacted(reqs, "REQ-03") == {"requirements": ["REQ-03"], "screens": ["SCR-02"], "tests": ["TC-03"]}


def test_unknown_target_raises() -> None:
    with pytest.raises(KeyError):
        impacted([{"id": "REQ-01", "depends_on": [], "screens": [], "tests": []}], "REQ-99")


def test_cycles_terminate() -> None:
    reqs = [{"id": "REQ-01", "depends_on": ["REQ-02"], "screens": [], "tests": []},
            {"id": "REQ-02", "depends_on": ["REQ-01"], "screens": [], "tests": []}]
    assert impacted(reqs, "REQ-01")["requirements"] == ["REQ-01", "REQ-02"]


def test_only_roles_owning_impacted_items_are_listed() -> None:
    impact = {"requirements": ["REQ-02"], "screens": ["SCR-01"], "tests": []}
    assert owners_of(impact) == [{"agent": "pm", "items": ["REQ-02"]}, {"agent": "designer", "items": ["SCR-01"]}]
    full = {"requirements": ["REQ-01"], "screens": ["SCR-01"], "tests": ["TC-01", "TC-02"]}
    assert [o["agent"] for o in owners_of(full)] == ["pm", "designer", "qa"]


def test_validate_golden_script_still_passes(repo_root: Path) -> None:
    result = subprocess.run(["bash", str(repo_root / "eval" / "validate_golden.sh")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
