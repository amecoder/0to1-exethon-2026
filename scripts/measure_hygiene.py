from __future__ import annotations
"""Small talk after confirmation: does the real PM answer NONE, does the real QA say 무관 — and do real
complaints still get compared (not thrown away as 무관)? Run on the flower fixture.

    uv run python scripts/measure_hygiene.py      # needs LINER_API_KEY + LINER_MODEL (about $0.6)

Hypothesis (written before the first run, 2026-11-18): at least 9/10 small-talk change lines get NONE, at least
5/6 small-talk complaint lines get 무관, and at most 1/20 real complaints (eval/golden/complaint_cases.json) is
called 무관. Real change requests are checked by scripts/measure_m2.py (target accuracy must not drop).
"""

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.agent_runner import AgentOutputError, AgentRunner  # noqa: E402
from app.bus import MessageBus  # noqa: E402
from app.change_desk import TASK_COMPLAINT, UnmappedChangeError, UnrelatedChangeError, propose_change  # noqa: E402
from app.config import KEY_MISSING_MESSAGE, read_env  # noqa: E402
from app.definitions import load_definitions  # noqa: E402
from app.liner import LinerAPIError, LinerClient  # noqa: E402
from app.request_hygiene import UNRELATED_CLASS  # noqa: E402
from app.schemas import COMPLAINT_CHECK  # noqa: E402
from app.stage_common import StageContext  # noqa: E402
from app.store import source_from_fixture  # noqa: E402
from app.workspace import Workspace  # noqa: E402

FIXTURE = REPO_ROOT / "examples" / "flower-subscription" / "requirements_fixture.json"
HYGIENE = REPO_ROOT / "eval" / "golden" / "hygiene_cases.json"
COMPLAINTS = REPO_ROOT / "eval" / "golden" / "complaint_cases.json"


def context(client: LinerClient) -> StageContext:
    agents, teams = load_definitions(REPO_ROOT)
    ws = Workspace(source_from_fixture(json.loads(FIXTURE.read_text(encoding="utf-8"))), agents)
    return StageContext(ws, MessageBus(teams["default"], ws), AgentRunner(client, agents, ws))


def change_verdict(client: LinerClient, text: str) -> str:
    try:
        return propose_change(context(client), text)["target"]
    except UnrelatedChangeError:
        return "NONE"
    except (UnmappedChangeError, AgentOutputError, LinerAPIError) as exc:
        return f"error: {exc}"


def complaint_class(client: LinerClient, text: str) -> str:
    ctx = context(client)
    reqs = [{k: r.get(k) for k in ("id", "title", "statement", "acceptance")} for r in ctx.ws.items("requirements")]
    try:
        out: Any = ctx.runner.ask("qa", TASK_COMPLAINT, "complaint_check", COMPLAINT_CHECK,
                                  {"발주사 말": text, "확정 버전": "v1", "확정 요구사항": reqs})
        return str(out.get("classification"))
    except (AgentOutputError, LinerAPIError) as exc:
        return f"error: {exc}"


def main() -> int:
    if read_env("LINER_API_KEY", None) is None:
        print(KEY_MISSING_MESSAGE, file=sys.stderr)
        return 2
    client = LinerClient(None)
    golden = json.loads(HYGIENE.read_text(encoding="utf-8"))
    crit = golden["pass_criteria"]
    changes = {c["id"]: change_verdict(client, c["text"]) for c in golden["changes"]}
    talk = {c["id"]: complaint_class(client, c["text"]) for c in golden["complaints"]}
    real = {c["id"]: complaint_class(client, c["complaint"]) for c in json.loads(COMPLAINTS.read_text("utf-8"))["cases"]}
    none = sum(v == "NONE" for v in changes.values())
    unrelated = sum(v == UNRELATED_CLASS for v in talk.values())
    wrongly = [k for k, v in real.items() if v == UNRELATED_CLASS]
    ok = none >= crit["changes_unrelated_min"] and unrelated >= crit["complaints_unrelated_min"] and len(wrongly) <= 1
    print(f"잡담 변경 요청 → NONE {none}/{crit['changes_total']} · 잡담 불만 → 무관 {unrelated}/{crit['complaints_total']} "
          f"· 진짜 불만을 무관으로 버림 {len(wrongly)}/{len(real)} → {'합격' if ok else '불합격'}")
    for k, v in changes.items():
        if v != "NONE":
            print(f"  변경 {k}: {v}")
    for k, v in talk.items():
        if v != UNRELATED_CLASS:
            print(f"  잡담 불만 {k}: {v}")
    for k in wrongly:
        print(f"  진짜 불만 {k}: 무관으로 판정")
    for k, v in real.items():
        if v.startswith("error"):
            print(f"  진짜 불만 {k}: {v}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
