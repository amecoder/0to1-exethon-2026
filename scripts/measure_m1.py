from __future__ import annotations
"""FR-24 · M1 (누락 탐지): score a run's question cards and warnings against eval/golden/seeded_defects.json.

    uv run python scripts/measure_m1.py --fake                 # scripted FakeLiner (CI) — NOT the metric
    uv run python scripts/measure_m1.py demo/flower-run.json   # score saved recordings (one per run)
    uv run python scripts/measure_m1.py --runs 3               # real runs: needs LINER_API_KEY (+ LINER_MODEL)

Rule (평가 설계 1절, fixed before implementation): a defect is detected when every word of one of its
`match_any` groups appears in the team's output. The script applies it per output unit (one question card,
one QA finding, one warning, one open item) — "함께 나온다" read strictly — and also prints the looser
whole-output count for reference. Ambiguous cases still need a human; the script says so.

Real runs go S1 → S2 → CP1 (auto-approved here; a measurement run, not a client decision) → S3 and stop
at the first question card, so no human answer is needed. The golden file is read ONLY by this script;
app code never loads it (tests/test_no_answer_leak.py).
"""

import argparse
import json
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.agent_runner import AgentRunner  # noqa: E402
from app.config import KEY_MISSING_MESSAGE, read_env  # noqa: E402
from app.definitions import load_definitions  # noqa: E402
from app.demo import load_recording, replay  # noqa: E402
from app.liner import LinerClient  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from app.store import empty_source  # noqa: E402
from app.workspace import Workspace  # noqa: E402

DEFECTS = REPO_ROOT / "eval" / "golden" / "seeded_defects.json"
MEMO = REPO_ROOT / "examples" / "flower-subscription" / "request_memo.md"
TARGET = 8
FAKE_NOTE = ("※ 가짜 모드(--fake): 손으로 쓴 FakeLiner 응답을 채점한 값입니다. 채점 배관 확인용이며 M1 지표가 아닙니다. "
             "지표는 실제 실행(키 필요) 3회의 최솟값으로 잽니다.")


# --- scoring (pure) -----------------------------------------------------------------------------
def output_units(source: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The team's question cards and warnings, one text per unit: (label, text)."""
    units: list[tuple[str, str]] = []
    for q in source.get("questions", []):
        units.append((f"질문 {q.get('id')}", " ".join([str(q.get("question", "")), str(q.get("why", "")),
                                                       *map(str, q.get("options", []))])))
    for f in source.get("findings", []):
        units.append((f"QA 지적 {f.get('id')}", str(f.get("note", ""))))
    for o in source.get("open_items", []):
        units.append((f"미결 {o.get('id')}", f"{o.get('title', '')} {o.get('reason', '')}"))
    for e in source.get("events", []):
        if e.get("type") == "check_result":
            units.extend((f"검사 {e['data'].get('check')}", str(d)) for d in e["data"].get("details", []))
    return [(label, text) for label, text in units if text.strip()]


def matches(text: str, groups: Sequence[Sequence[str]]) -> bool:
    return any(all(word in text for word in group) for group in groups)


def score(units: Sequence[tuple[str, str]], defects: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    strict: dict[str, str] = {}
    for d in defects:
        hit = next((label for label, text in units if matches(text, d["match_any"])), None)
        if hit is not None:
            strict[d["id"]] = hit
    whole = " ".join(text for _, text in units)
    loose = [d["id"] for d in defects if matches(whole, d["match_any"])]
    return {"detected": sorted(strict), "where": strict, "loose": sorted(loose), "units": len(units)}


# --- runs ---------------------------------------------------------------------------------------
def memo_chunks() -> list[str]:
    """What a client pastes at S1: the messages after the memo's separator (same as the fake tests)."""
    body = MEMO.read_text(encoding="utf-8").split("\n---\n", 1)[1].strip()
    monday, tuesday = body.split("**[화", 1)
    return [monday.strip(), "**[화" + tuesday.strip()]


def run_to_cards(client: LinerClient) -> dict[str, Any]:
    agents, teams = load_definitions(REPO_ROOT)
    ws = Workspace(empty_source(), agents)
    orch = Orchestrator(ws, teams["default"], AgentRunner(client, agents, ws))
    if orch.ingest(memo_chunks()).blocked:
        raise RuntimeError("메모에서 민감 정보가 발견되어 진행하지 않았습니다")
    orch.advance()
    if ws.pipeline["stage"] == "CP1":
        orch.confirm("CP1", True, "측정 스크립트")
        orch.advance()
    if ws.pipeline["status"] not in ("awaiting_answers", "awaiting_confirmation"):
        raise RuntimeError(f"질문 카드까지 가지 못했습니다: {ws.pipeline['stage']} · {ws.pipeline['status']} "
                           f"{ws.pipeline.get('error') or ''}")
    return ws.source


def fake_client(env_dir: Path) -> LinerClient:
    from tests.fake_liner import FakeLiner
    from tests.flower_script import SEARCH_BODY, flower_outputs

    env_file = env_dir / ".env"
    env_file.write_text("LINER_API_KEY=fake-key-for-measurement\nLINER_MODEL=fake-model\n", encoding="utf-8")
    fake = FakeLiner(flower_outputs(memo_chunks()), search_body=SEARCH_BODY)
    return LinerClient(env_file=env_file, transport=fake.transport())


def report(label: str, results: Iterable[dict[str, Any]], defects: Sequence[Mapping[str, Any]]) -> list[int]:
    counts = []
    for i, r in enumerate(results, start=1):
        counts.append(len(r["detected"]))
        print(f"[{label} {i}] 탐지 {len(r['detected'])}/{len(defects)} (같은 항목 안 기준) · "
              f"출력 전체 기준 {len(r['loose'])}/{len(defects)} · 채점한 출력 {r['units']}개")
        for d in defects:
            where = r["where"].get(d["id"])
            mark = f"탐지 — {where}" if where else ("출력 전체로는 탐지(사람 판정 필요)" if d["id"] in r["loose"] else "못 찾음")
            print(f"    {d['id']} {d['type']:<18} {mark}")
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M1 누락 탐지 채점")
    parser.add_argument("recordings", nargs="*", type=Path, help="채점할 시연 녹화 파일(회차마다 하나)")
    parser.add_argument("--fake", action="store_true", help="가짜 Liner 응답으로 실행(CI용, 지표 아님)")
    parser.add_argument("--runs", type=int, default=3, help="실제·가짜 실행 횟수 (기본 3)")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    args = parser.parse_args(argv)
    defects = json.loads(DEFECTS.read_text(encoding="utf-8"))["defects"]

    if args.recordings:
        sources = [replay(load_recording(p)["events"]) for p in args.recordings]
        label = "녹화"
    elif args.fake:
        with tempfile.TemporaryDirectory() as tmp:
            sources = [run_to_cards(fake_client(Path(tmp))) for _ in range(args.runs)]
        label = "가짜 실행"
    else:
        if read_env("LINER_API_KEY", args.env_file) is None:
            print(f"실제 측정에는 Liner API 키가 필요합니다. {KEY_MISSING_MESSAGE}", file=sys.stderr)
            print("키 없이 채점 배관만 확인하려면 --fake 를 붙이세요.", file=sys.stderr)
            return 2
        client = LinerClient(env_file=args.env_file)
        sources = [run_to_cards(client) for _ in range(args.runs)]
        label = "실제 실행"

    counts = report(label, [score(output_units(s), defects) for s in sources], defects)
    lowest = min(counts)
    verdict = "채택" if lowest >= TARGET else "기각"
    print(f"\nM1 회차별 탐지 수 {counts} · 최솟값 {lowest}/{len(defects)} · 목표 {TARGET} 이상 → {verdict}"
          + (" (가짜 모드라 판정에 쓰지 않음)" if args.fake else ""))
    if args.fake:
        print(FAKE_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
