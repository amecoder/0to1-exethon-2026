from __future__ import annotations
"""Turn a finished real web project (SQLite store) into a demo recording (kind "real").

    uv run python scripts/export_demo.py --project <id> [--db data/exethon.sqlite3] [--out demo/flower-run.json]

Refuses (exit 2) unless the project is a real-mode run approved through CP4 with no pending CP5 recheck.
The header carries the answering models, total cost and elapsed time for the demo banner. No Liner call.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.definitions import load_definitions  # noqa: E402
from app.demo import make_recording, write_recording  # noqa: E402
from app.export import cp4_approved  # noqa: E402
from app.store import ProjectStore  # noqa: E402
from app.workspace import Workspace  # noqa: E402

DEFAULT_DB = REPO_ROOT / "data" / "exethon.sqlite3"
DEFAULT_OUT = REPO_ROOT / "demo" / "flower-run.json"


class ExportRefused(RuntimeError):
    """The project cannot become a demo recording (missing, demo mode, or not approved through CP4)."""


def chat_model(events: list[dict]) -> str | None:
    """The configured model of the run (the first chat call's `model`)."""
    return next((e["data"].get("model") for e in events if e.get("type") == "liner_chat" and e["data"].get("model")),
                None)


def export_project(store: ProjectStore, project_id: str, note: str = "") -> dict:
    project = store.get(project_id)
    if project is None:
        raise ExportRefused(f"프로젝트가 없습니다: {project_id}")
    if project["mode"] != "real":
        raise ExportRefused("실제 모드로 실행한 프로젝트만 녹화본으로 내보낼 수 있습니다")
    source = project["source"]
    if not cp4_approved(source) or source.get("meta", {}).get("recheck"):
        raise ExportRefused("CP4 프로토타입 인수 승인까지 마친 프로젝트만 내보낼 수 있습니다 (다시 확인 중인 변경도 없어야 합니다)")
    agents, _ = load_definitions(REPO_ROOT)
    ws = Workspace(source, agents)
    recording = make_recording(ws, "real", chat_model(source.get("events", [])), project["name"])
    if note.strip():
        # Who played the client, shown in the demo banner next to the real-run notice.
        recording = {**recording, "notice": f"{recording['notice']} · {note.strip()}", "operator_note": note.strip()}
    return recording


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="실제 웹 실행 프로젝트를 시연 녹화본으로 내보낸다")
    parser.add_argument("--project", required=True, help="프로젝트 ID")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--note", default="", help="배너에 덧붙일 한 줄 (예: 발주사 역할 대리 입력)")
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(f"저장소 파일이 없습니다: {args.db}", file=sys.stderr)
        return 2
    try:
        recording = export_project(ProjectStore(args.db), args.project, args.note)
    except ExportRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_recording(recording, args.out)
    cost = recording["total_cost_usd"]
    print(f"녹화본을 썼습니다: {args.out} · 이벤트 {recording['event_count']}개 · 답한 모델 "
          f"{', '.join(recording['models']) or '없음'} · 비용 {'알 수 없음' if cost is None else f'${cost:.4f}'} · "
          f"걸린 시간 {recording['duration_seconds']}초")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
