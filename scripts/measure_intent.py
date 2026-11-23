from __future__ import annotations
"""확인 단계 의도 판정: eval/golden/client_intent_cases.json through Liner Decisions, routed the way the app does.

    uv run python scripts/measure_intent.py --runs 3    # real Decisions API: needs LINER_API_KEY + LINER_DECISION_MODEL

Hypothesis (fixed before the first real run): on every run missed_fix == 0 (a fix request is never handled as
question-only) and question_saved >= 0.7 (most plain questions skip the rework). The app's routing is applied:
a confidence under the threshold counts as `both` (app/answer_desk.classify).
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.answer_desk import INTENT_QUESTION, INTENTS, SEARCH_QUESTION  # noqa: E402
from app.decisions import min_confidence  # noqa: E402
from app.liner import LinerAPIError, LinerClient, LinerConfigError  # noqa: E402

CASES = REPO_ROOT / "eval" / "golden" / "client_intent_cases.json"
TARGET_MISSED_FIX = 0
TARGET_QUESTION_SAVED = 0.7


def routed(answer: Mapping[str, Any], threshold: float) -> tuple[str | None, str, float | None]:
    """(model choice, app route, confidence) — the same fallback as app/answer_desk.classify."""
    choice = answer.get("choice") if isinstance(answer, Mapping) else None
    confidence = answer.get("confidence") if isinstance(answer, Mapping) else None
    if choice not in INTENTS or not isinstance(confidence, (int, float)) or confidence < threshold:
        return choice, "both", confidence
    return choice, choice, float(confidence)


def run_once(client: LinerClient, cases: Sequence[Mapping[str, Any]], threshold: float) -> dict[str, Any]:
    rows = []
    for case in cases:
        try:
            body = client.decide({"확인 단계": case["cp"], "발주사의 말": case["text"]},
                                 {"intent": INTENT_QUESTION, "search": SEARCH_QUESTION})
            choice, route, confidence = routed((body.get("answers") or {}).get("intent") or {}, threshold)
            error = None
        except (LinerAPIError, LinerConfigError) as exc:
            choice, route, confidence, error = None, "both", None, str(exc)
        rows.append({"id": case["id"], "expected": case["expected"], "choice": choice, "route": route,
                     "confidence": confidence, "error": error})
    fixes = [r for r in rows if r["expected"] in ("change", "both")]
    questions = [r for r in rows if r["expected"] == "question"]
    return {
        "missed_fix": [r["id"] for r in fixes if r["route"] == "question"],
        "question_saved": sum(r["route"] == "question" for r in questions) / len(questions),
        "accuracy": sum(r["choice"] == r["expected"] for r in rows) / len(rows),
        "per_label": {label: f"{sum(r['choice'] == label for r in rows if r['expected'] == label)}/"
                             f"{sum(r['expected'] == label for r in rows)}" for label in INTENTS},
        "rows": rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="확인 단계 의도 판정 측정")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args(argv)
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    client = LinerClient()
    threshold = min_confidence(client.env_file)
    ok = True
    for n in range(1, args.runs + 1):
        result = run_once(client, cases, threshold)
        passed = len(result["missed_fix"]) <= TARGET_MISSED_FIX and result["question_saved"] >= TARGET_QUESTION_SAVED
        ok = ok and passed
        print(f"run {n}: missed_fix={result['missed_fix']} question_saved={result['question_saved']:.2f} "
              f"accuracy={result['accuracy']:.2f} per_label={result['per_label']} → {'통과' if passed else '불합격'}")
        for r in result["rows"]:
            if r["choice"] != r["expected"] or r["route"] != r["choice"]:
                print(f"   {r['id']} 정답 {r['expected']} · 판정 {r['choice']} · 처리 {r['route']} · 확신도 {r['confidence']}"
                      + (f" · 오류 {r['error']}" if r["error"] else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
