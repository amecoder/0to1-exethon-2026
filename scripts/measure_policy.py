from __future__ import annotations
"""G9 purpose check: the golden requests (12 harmful, 16 legitimate with trap words or border cases) through Liner Decisions.

    uv run python scripts/measure_policy.py --runs 2    # needs LINER_API_KEY + LINER_DECISION_MODEL (about $0.005 a run)

Hypothesis (written before the first run, 2026-11-18): on every run at least 11 of 12 harmful requests are
blocked and at most 1 of 12 legitimate ones is blocked. Baseline before G9: nothing is checked, 0 of 12 blocked.
Reports per-case verdicts so a failure shows which category or trap word broke.
"""

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.config import KEY_MISSING_MESSAGE, read_env  # noqa: E402
from app.liner import LinerClient  # noqa: E402
from app.policy import check_purpose  # noqa: E402

GOLDEN = REPO_ROOT / "eval" / "golden" / "policy_cases.json"


class DirectRunner:
    """The one method check_purpose needs, straight to the client (no workspace, no event log)."""

    def __init__(self, client: LinerClient) -> None:
        self.client = client

    def decide(self, agent_id: str, purpose: str, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        return self.client.decide(state, questions)


def run_once(runner: DirectRunner, cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in cases:
        verdict = check_purpose(runner, "coordinator", [case["text"]])
        ok = (verdict.blocked and case["expected"] == "block") or (not verdict.blocked and case["expected"] == "pass")
        rows.append({"id": case["id"], "expected": case["expected"], "blocked": verdict.blocked,
                     "category": verdict.category, "harmful": verdict.harmful, "error": verdict.error, "ok": ok})
    blocked = sum(r["blocked"] for r in rows if r["expected"] == "block")
    false_blocks = sum(r["blocked"] for r in rows if r["expected"] == "pass")
    return {"block_recall": blocked, "false_blocks": false_blocks, "errors": sum(bool(r["error"]) for r in rows),
            "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    if read_env("LINER_API_KEY", None) is None:
        print(KEY_MISSING_MESSAGE, file=sys.stderr)
        return 2
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    crit = golden["pass_criteria"]
    runner = DirectRunner(LinerClient(None))
    passed = True
    for n in range(1, args.runs + 1):
        result = run_once(runner, golden["cases"])
        good = (result["block_recall"] >= crit["block_recall_min"] and result["false_blocks"] <= crit["false_block_max"]
                and result["errors"] == 0)
        passed = passed and good
        print(f"run {n}: 막음 {result['block_recall']}/{crit['block_total']} · 잘못 막음 {result['false_blocks']}/{crit['pass_total']} · 오류 {result['errors']} "
              f"→ {'합격' if good else '불합격'}")
        for r in result["rows"]:
            if not r["ok"] or r["error"]:
                print(f"  틀림 {r['id']} 기대 {r['expected']} · 막음 {r['blocked']} · {r['category']} · "
                      f"해로움 {r['harmful']} · {r['error'] or ''}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
