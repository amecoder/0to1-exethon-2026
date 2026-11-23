from __future__ import annotations
"""FR-22 판정 정확도: the 20 golden complaint cases through Liner Decisions (`choice` violation/new_change).

    uv run python scripts/measure_decisions.py --fake      # scripted answers (CI) — NOT the metric
    uv run python scripts/measure_decisions.py --runs 3    # real Decisions API: needs LINER_API_KEY + LINER_DECISION_MODEL

Each case gives the decision model the confirmed requirement text(s) from the fixture, the confirmation that
fixed them and the client's complaint — the same state app/change_desk.py sends (app/decisions.py). Reports
accuracy per label and how many answers fall under the confidence threshold (「사람 판단 필요」).

Hypothesis (written before the first real run): accuracy ≥ TARGET_ACCURACY on every run. The code guard
(app/change_desk.complaint_guard) is NOT applied here — this measures the decision model alone.
"""

import argparse
import json
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.config import KEY_MISSING_MESSAGE, read_env  # noqa: E402
from app.decisions import COMPLAINT_QUESTION, complaint_state, min_confidence, read_choice  # noqa: E402
from app.liner import LinerAPIError, LinerClient, LinerConfigError  # noqa: E402

FIXTURE = REPO_ROOT / "examples" / "flower-subscription" / "requirements_fixture.json"
CASES = REPO_ROOT / "eval" / "golden" / "complaint_cases.json"
TARGET_ACCURACY = 0.90  # 판정 기준 (실행 전에 고정)
CONFIRMATION = {"cp": "CP3", "who": "발주사", "at": "2026-11-16T09:00:00+00:00", "version": "v2"}
LABELS = ("violation", "new_change")
FAKE_NOTE = ("※ 가짜 모드(--fake): 정답표의 라벨을 그대로 돌려주는 스크립트 응답입니다. 배관 확인용이며 "
             "판정 정확도 지표가 아닙니다. 지표는 실제 Decisions API 로 잽니다.")


def run_cases(client: LinerClient, cases: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    reqs = {r["id"]: r for r in json.loads(FIXTURE.read_text(encoding="utf-8"))["requirements"]}
    out: dict[str, dict[str, Any]] = {}
    for case in cases:
        state = complaint_state([reqs[i] for i in case["confirmed"]], CONFIRMATION, case["complaint"])
        try:
            body = client.decide(state, {"kind": COMPLAINT_QUESTION})
            out[case["id"]] = read_choice((body.get("answers") or {}).get("kind"))
        except (LinerAPIError, LinerConfigError, ValueError) as exc:
            out[case["id"]] = {"choice": None, "confidence": None, "error": str(exc)}
    return out


def score(cases: Sequence[Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]],
          threshold: float) -> dict[str, Any]:
    per = {label: {"right": 0, "total": 0} for label in LABELS}
    low = []
    for case in cases:
        pred = predictions.get(case["id"], {})
        per[case["expected"]]["total"] += 1
        if pred.get("choice") == case["expected"]:
            per[case["expected"]]["right"] += 1
        confidence = pred.get("confidence")
        if confidence is None or confidence < threshold:
            low.append(case["id"])
    right = sum(v["right"] for v in per.values())
    return {"accuracy": right / len(cases), "right": right, "per_label": per, "low_confidence": low}


def fake_client(env_dir: Path, cases: Sequence[Mapping[str, Any]]) -> LinerClient:
    from tests.fake_liner import FakeLiner

    expected = {c["complaint"]: c["expected"] for c in cases}

    def answer(payload: Mapping[str, Any]) -> dict[str, Any]:
        choice = expected.get(payload["state"]["complaint"], "new_change")
        other = "new_change" if choice == "violation" else "violation"
        return {"kind": {"type": "choice", "choice": choice, "confidence": 0.9,
                         "probabilities": {choice: 0.95, other: 0.05}}}

    env_file = env_dir / ".env"
    env_file.write_text("LINER_API_KEY=fake-key-for-measurement\nLINER_DECISION_MODEL=fake-decision\n",
                        encoding="utf-8")
    return LinerClient(env_file=env_file, transport=FakeLiner({}, decision=answer).transport())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FR-22 판정 정확도 (Liner Decisions)")
    parser.add_argument("--fake", action="store_true", help="정답 라벨을 돌려주는 가짜 판정(CI용, 지표 아님)")
    parser.add_argument("--runs", type=int, default=3, help="반복 횟수 (기본 3)")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    args = parser.parse_args(argv)
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]

    if args.fake:
        with tempfile.TemporaryDirectory() as tmp:
            client = fake_client(Path(tmp), cases)
            threshold = min_confidence(Path(tmp) / ".env")
            runs = [run_cases(client, cases) for _ in range(args.runs)]
    else:
        if read_env("LINER_API_KEY", args.env_file) is None:
            print(f"실제 측정에는 Liner API 키가 필요합니다. {KEY_MISSING_MESSAGE}", file=sys.stderr)
            print("키 없이 배관만 확인하려면 --fake 를 붙이세요.", file=sys.stderr)
            return 2
        if read_env("LINER_DECISION_MODEL", args.env_file) is None:
            print("LINER_DECISION_MODEL 이 없습니다. .env 에 넣으세요 (제안: typesafe/jev-1.13). "
                  "키 없이 배관만 확인하려면 --fake 를 붙이세요.", file=sys.stderr)
            return 2
        client = LinerClient(env_file=args.env_file)
        threshold = min_confidence(args.env_file)
        runs = [run_cases(client, cases) for _ in range(args.runs)]

    scores = []
    for i, predictions in enumerate(runs, start=1):
        s = score(cases, predictions, threshold)
        scores.append(s)
        per = " · ".join(f"{k} {v['right']}/{v['total']}" for k, v in s["per_label"].items())
        print(f"[{'가짜' if args.fake else '실제'} {i}] 정확도 {s['right']}/{len(cases)} ({s['accuracy']:.2f}) · {per} "
              f"· 확신도 {threshold} 미만(사람 판단 필요) {len(s['low_confidence'])}건")
        for case in cases:
            pred = predictions[case["id"]]
            if pred.get("choice") != case["expected"]:
                print(f"    {case['id']} 틀림: 정답 {case['expected']} · 낸 값 {pred.get('choice')} "
                      f"(확신도 {pred.get('confidence')}) {pred.get('error', '')}")
    lowest = min(s["accuracy"] for s in scores)
    verdict = "채택" if lowest >= TARGET_ACCURACY else "기각"
    print(f"\n판정 정확도 최솟값 {lowest:.2f} · 최댓값 {max(s['accuracy'] for s in scores):.2f} · "
          f"목표 {TARGET_ACCURACY} 이상 → {verdict}" + (" (가짜 모드라 판정에 쓰지 않음)" if args.fake else ""))
    if args.fake:
        print(FAKE_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
