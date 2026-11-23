from __future__ import annotations
"""FR-24 · M2 (변경 영향 재현율): run the 20 golden change cases through the FR-21 pipeline.

    uv run python scripts/measure_m2.py --fake        # scripted mapping (CI) — NOT the metric
    uv run python scripts/measure_m2.py --runs 3      # real PM agent on Liner: needs LINER_API_KEY (+ LINER_MODEL)

Each case: utterance → PM agent picks the target REQ (Liner Model, `change_mapping`) → code computes the
impact from the fixture links (app/impact.py, the rule of eval/validate_golden.sh). Scores (change_cases.json
`scoring`): target accuracy, impact recall and precision over all REQ/SCR/TC ids, summed over the 20 cases.

Because the impact is deterministic, M2 really measures the utterance → target mapping (평가 설계 2절).
In --fake mode the mapping is scripted to answer the golden target, so it only proves the impact part:
impact recall must be 1.0 whenever the target is right. Fake numbers are NOT the metric.
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

from app.agent_runner import AgentRunner  # noqa: E402
from app.bus import MessageBus  # noqa: E402
from app.change_desk import UnmappedChangeError, propose_change  # noqa: E402
from app.config import KEY_MISSING_MESSAGE, read_env  # noqa: E402
from app.definitions import load_definitions  # noqa: E402
from app.liner import LinerAPIError, LinerClient  # noqa: E402
from app.agent_runner import AgentOutputError  # noqa: E402
from app.stage_common import StageContext  # noqa: E402
from app.store import source_from_fixture  # noqa: E402
from app.workspace import Workspace  # noqa: E402

FIXTURE = REPO_ROOT / "examples" / "flower-subscription" / "requirements_fixture.json"
CASES = REPO_ROOT / "eval" / "golden" / "change_cases.json"
TARGET_RECALL = 0.90
KINDS = ("requirements", "screens", "tests")
FAKE_NOTE = ("※ 가짜 모드(--fake): 대상 REQ 매핑을 정답표에서 그대로 돌려주는 스크립트 응답입니다. "
             "영향 계산(링크 규칙) 배관 확인용이며 M2 지표가 아닙니다. 지표는 실제 PM 에이전트로 3회 잽니다.")


def predicted_ids(impact: Mapping[str, Sequence[str]] | None) -> set[str]:
    return {i for k in KINDS for i in (impact or {}).get(k, [])}


def score(cases: Sequence[Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    hit_target = hit = expected_n = predicted_n = 0
    right_hit = right_expected = 0
    for case in cases:
        pred = predictions.get(case["id"], {})
        exp = predicted_ids(case["expected"])
        got = predicted_ids(pred.get("impact"))
        overlap = len(exp & got)
        hit, expected_n, predicted_n = hit + overlap, expected_n + len(exp), predicted_n + len(got)
        if pred.get("target") == case["target"]:
            hit_target += 1
            right_hit, right_expected = right_hit + overlap, right_expected + len(exp)
    return {
        "target_accuracy": hit_target / len(cases),
        "impact_recall": hit / expected_n if expected_n else 0.0,
        "impact_precision": hit / predicted_n if predicted_n else 0.0,
        "recall_when_target_right": right_hit / right_expected if right_expected else 0.0,
        "targets_right": hit_target,
    }


def run_cases(client: LinerClient, cases: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    agents, teams = load_definitions(REPO_ROOT)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for case in cases:
        ws = Workspace(source_from_fixture(fixture), agents)
        ctx = StageContext(ws, MessageBus(teams["default"], ws), AgentRunner(client, agents, ws))
        try:
            proposal = propose_change(ctx, case["utterance"])
            out[case["id"]] = {"target": proposal["target"], "impact": proposal["impact"]}
        except (UnmappedChangeError, AgentOutputError, LinerAPIError) as exc:
            out[case["id"]] = {"target": None, "impact": None, "error": str(exc)}
    return out


def fake_client(env_dir: Path, cases: Sequence[Mapping[str, Any]]) -> LinerClient:
    from tests.fake_liner import FakeLiner

    targets = {c["utterance"]: c["target"] for c in cases}

    def mapping(payload: dict[str, Any]) -> dict[str, Any]:
        content = payload["messages"][-1]["content"]
        utterance = json.loads(content.split("[추가 입력]\n", 1)[1])["변경 요청"]
        return {"target": targets.get(utterance, ""), "after_statement": utterance, "summary": "가짜 매핑"}

    env_file = env_dir / ".env"
    env_file.write_text("LINER_API_KEY=fake-key-for-measurement\nLINER_MODEL=fake-model\n", encoding="utf-8")
    return LinerClient(env_file=env_file, transport=FakeLiner({"change_mapping": [mapping]}).transport())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M2 변경 영향 재현율")
    parser.add_argument("--fake", action="store_true", help="정답 대상을 돌려주는 가짜 매핑(CI용, 지표 아님)")
    parser.add_argument("--runs", type=int, default=3, help="반복 횟수 (기본 3)")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    args = parser.parse_args(argv)
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]

    if args.fake:
        with tempfile.TemporaryDirectory() as tmp:
            client = fake_client(Path(tmp), cases)
            runs = [run_cases(client, cases) for _ in range(args.runs)]
    else:
        if read_env("LINER_API_KEY", args.env_file) is None:
            print(f"실제 측정에는 Liner API 키가 필요합니다. {KEY_MISSING_MESSAGE}", file=sys.stderr)
            print("키 없이 영향 계산만 확인하려면 --fake 를 붙이세요.", file=sys.stderr)
            return 2
        client = LinerClient(env_file=args.env_file)
        runs = [run_cases(client, cases) for _ in range(args.runs)]

    scores = []
    for i, predictions in enumerate(runs, start=1):
        s = score(cases, predictions)
        scores.append(s)
        print(f"[{'가짜' if args.fake else '실제'} {i}] 대상 적중 {s['targets_right']}/{len(cases)} "
              f"({s['target_accuracy']:.2f}) · 영향 재현율 {s['impact_recall']:.3f} · 정밀도 {s['impact_precision']:.3f} "
              f"· 대상이 맞을 때 재현율 {s['recall_when_target_right']:.3f}")
        for case in cases:
            pred = predictions[case["id"]]
            if pred.get("target") != case["target"]:
                print(f"    {case['id']} 대상 틀림: 정답 {case['target']} · 낸 값 {pred.get('target')} {pred.get('error', '')}")
    lowest = min(s["impact_recall"] for s in scores)
    verdict = "채택" if lowest >= TARGET_RECALL else "기각"
    print(f"\nM2 영향 재현율 최솟값 {lowest:.3f} · 최댓값 {max(s['impact_recall'] for s in scores):.3f} · "
          f"대상 적중률 최솟값 {min(s['target_accuracy'] for s in scores):.2f} · 목표 {TARGET_RECALL} 이상 → {verdict}"
          + (" (가짜 모드라 판정에 쓰지 않음)" if args.fake else ""))
    if args.fake:
        print(FAKE_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
