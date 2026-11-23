from __future__ import annotations
"""Make a demo recording from the scripted FakeLiner. Test data, not app code.

    uv run python -m tests.make_fake_demo            # writes $TMPDIR/flower-run.fake.json

The file is marked kind="fake" and shows "가짜 응답으로 만든 임시 녹화본" on screen. Since 2026-11-17 the
committed demo/flower-run.json (DEMO_FILE) is a REAL Liner run, so this never writes there.
"""

import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.change_desk import ChangeDesk
from app.definitions import load_definitions
from app.demo import drive, drive_to_completion, make_recording, write_recording
from app.workspace import Workspace
from tests.pipeline_helpers import CHUNKS, DAY_CHOICE, build

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_FILE = REPO_ROOT / "demo" / "flower-run.json"  # the committed real recording — read only
FAKE_DEMO_FILE = Path(tempfile.gettempdir()) / "flower-run.fake.json"
FAKE_MODEL = "fake-model(가짜 응답)"
WAIVER = "가짜 응답 녹화 — 다음 단계에서 처리"


class ScriptedDecider:
    """Q-01 → DAY_CHOICE, other cards → '잘 모르겠어요'; approve every CP with a reason per warning."""

    def answer(self, todo: Mapping[str, Any]) -> tuple[str, str | None]:
        card = todo["question"]
        if DAY_CHOICE in card["options"]:
            return "choice", DAY_CHOICE
        return "unknown", None

    def confirm(self, todo: Mapping[str, Any]) -> tuple[bool, str | None, dict[str, str]]:
        waivable = (todo.get("review") or {}).get("waivable", [])
        return True, None, {w["id"]: WAIVER for w in waivable}


def record_fake(env_dir: Path) -> tuple[dict[str, Any], Workspace]:
    env_file = env_dir / ".env"
    env_file.write_text(f"LINER_API_KEY=fake-key-for-recording\nLINER_MODEL={FAKE_MODEL}\n"
                        "LINER_DECISION_MODEL=fake-decision\nLINER_RERANK_MODEL=fake-rerank\n", encoding="utf-8")
    orch, ws, _ = build(REPO_ROOT, env_file, decision=demo_decision)
    drive(orch, ws, CHUNKS, ScriptedDecider())
    play_p1(orch, ws)
    return make_recording(ws, "fake", FAKE_MODEL, "꽃님 정기구독"), ws


def demo_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The complaint (Sunday delivery) is a new change at 0.92; every G1 support question is a clear yes."""
    answers: dict[str, Any] = {}
    for name, q in payload["questions"].items():
        if q["type"] == "choice":
            answers[name] = {"type": "choice", "choice": "new_change", "confidence": 0.92,
                             "probabilities": {"violation": 0.04, "new_change": 0.96}}
        else:
            answers[name] = {"type": "noul", "noul": 0.93}
    return answers


CHANGE = "일시정지는 배송 하루 전까지 되게 해 주세요"
COMPLAINT = "일요일에도 받고 싶은데 왜 안 되죠?"


def play_p1(orch: Any, ws: Workspace) -> None:
    """After CP4: one change request approved at CP5 — the team redoes S5 → CP3 → S6 → CP4 and the client
    confirms again — then one 「아 이거 아닌데?」 (FR-21 · FR-22)."""
    _, teams = load_definitions(REPO_ROOT)
    desk = ChangeDesk(ws, teams["default"], orch._ctx.runner)
    change = desk.open_change(CHANGE)
    desk.map_change(change["id"])
    desk.decide(change["id"], True, "발주사")
    drive_to_completion(orch, ws, ScriptedDecider())
    complaint = desk.open_complaint(COMPLAINT)
    desk.check_complaint(complaint["id"])


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        recording, _ = record_fake(Path(tmp))
    write_recording(recording, FAKE_DEMO_FILE)
    print(f"wrote {FAKE_DEMO_FILE} ({recording['event_count']} events, kind=fake)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
