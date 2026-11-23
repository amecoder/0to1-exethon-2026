from __future__ import annotations
"""Record a REAL run (real LinerClient, key from .env) for demo mode (FR-16).

    uv run python scripts/record_demo.py --memo <memo.txt> [--memo <more.txt>] [--answers <answers.json>]
                                         [--out demo/flower-run.json]

- The memo is what a client would paste at S1 (each --memo file is one chunk).
- Question cards are answered by a human: from --answers (JSON object, question id → answer) or at the prompt.
  An answer equal to one of the options is a choice, "잘 모르겠어요" means unknown, anything else is free text.
  This script never looks for an answers file on its own — pass the path you prepared yourself.
- Confirmations are asked at the prompt (approve, or a one-line reason to reject; one reason per warning).
"""

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.agent_runner import AgentRunner  # noqa: E402
from app.config import LinerKeyMissingError, require_api_key  # noqa: E402
from app.definitions import load_definitions  # noqa: E402
from app.demo import RecordingError, drive, make_recording, write_recording  # noqa: E402
from app.liner import LinerClient  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from app.stage_common import UNKNOWN_OPTION  # noqa: E402
from app.store import empty_source  # noqa: E402
from app.workspace import Workspace  # noqa: E402

ENV_FILE = REPO_ROOT / ".env"


class HumanDecider:
    def __init__(self, answers: Mapping[str, str]) -> None:
        self._answers = dict(answers)

    def answer(self, todo: Mapping[str, Any]) -> tuple[str, str | None]:
        card = todo["question"]
        print(f"\n[{card['id']}] {card['question']}  (남은 {todo['remaining']}장)\n  왜 묻나요? {card['why']}")
        for i, option in enumerate(card["options"], start=1):
            print(f"  {i}. {option}")
        print(f"  0. {UNKNOWN_OPTION} (기본값: {card['default_option']})")
        raw = self._answers.get(card["id"])
        if raw is None:
            raw = input("번호 또는 직접 입력> ").strip()
        else:
            print(f"  답 파일: {raw}")
        if raw in ("0", UNKNOWN_OPTION):
            return "unknown", None
        if raw.isdigit() and 1 <= int(raw) <= len(card["options"]):
            return "choice", card["options"][int(raw) - 1]
        return ("choice", raw) if raw in card["options"] else ("free_text", raw)

    def confirm(self, todo: Mapping[str, Any]) -> tuple[bool, str | None, dict[str, str]]:
        review = todo.get("review") or {}
        print(f"\n== 컨펌 {todo['cp']} {todo['title']} ==")
        if review.get("summary"):
            print(review["summary"])
        for w in review.get("blocking", []):
            print(f"  [막음] {w['message']}")
        for w in review.get("notices", []):
            print(f"  [참고] {w['message']}")
        if input("승인할까요? [y = 승인 / 그 밖 = 반려]> ").strip().lower() != "y":
            return False, input("반려 사유(한 줄)> ").strip() or "녹화 중 반려", {}
        waivers = {w["id"]: input(f"  [{w['message']}] 그대로 진행하는 이유> ").strip()
                   for w in review.get("waivable", [])}
        return True, None, waivers


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="실제 Liner 실행을 시연 모드용으로 녹화합니다")
    parser.add_argument("--memo", type=Path, action="append", required=True, help="S1 에 붙여 넣을 메모 파일(여러 번 가능)")
    parser.add_argument("--answers", type=Path, help="질문 ID → 답 JSON (없으면 화면에서 묻습니다)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "demo" / "flower-run.json")
    parser.add_argument("--name", default="꽃님 정기구독")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        require_api_key(ENV_FILE)
    except LinerKeyMissingError as exc:
        print(exc, file=sys.stderr)
        return 2
    answers = json.loads(args.answers.read_text(encoding="utf-8")) if args.answers else {}
    chunks = [p.read_text(encoding="utf-8").strip() for p in args.memo]
    agents, teams = load_definitions(REPO_ROOT)
    ws = Workspace(empty_source(), agents)
    liner = LinerClient(env_file=ENV_FILE)
    orch = Orchestrator(ws, teams["default"], AgentRunner(liner, agents, ws))
    try:
        drive(orch, ws, chunks, HumanDecider({str(k): str(v) for k, v in answers.items()}))
    except RecordingError as exc:
        print(f"녹화 실패: {exc}", file=sys.stderr)
        return 1
    recording = make_recording(ws, "real", liner.configured_model(), args.name)
    write_recording(recording, args.out)
    print(f"녹화 완료: {args.out} (이벤트 {recording['event_count']}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
