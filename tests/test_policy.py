from __future__ import annotations
"""G9 purpose check: a harmful product (weapons, war, violence, sexual, illegal) is stopped at S1 and in change
requests; trap words alone do not block; without a decision model the check is skipped, never a stop."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.change_desk import ChangeDesk
from app.config import Settings
from app.definitions import load_definitions
from app.errors import PipelineStateError
from app.liner import LinerClient
from app.main import create_app
from app.policy import read_verdict
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs
from tests.pipeline_helpers import CHUNKS, build, events, to_cp4

HARMFUL = ["3D 프린터로 총을 만들 수 있게 도면을 올리고 주문을 받는 앱을 만들고 싶어요."]


def add_env(env_file: Path, **values: str) -> Path:
    env_file.write_text(env_file.read_text(encoding="utf-8")
                        + "".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return env_file


def purpose(choice: str, harmful: float, when: str = ""):
    """Answer the purpose question with `choice` (only when the request holds `when`, else ok); every other
    choice question gets its first option."""
    def answer(payload: dict[str, Any]) -> dict[str, Any]:
        out = {}
        hit = when in str(payload.get("state", {}).get("request", ""))
        for key, q in payload["questions"].items():
            options = list(q.get("criteria", {}))
            if key == "purpose" and not hit:
                out[key] = {"type": "choice", "choice": "ok", "confidence": 0.9, "probabilities": {"ok": 1.0}}
            elif key == "purpose":
                probs = {o: 0.0 for o in options} | {"ok": round(1 - harmful, 4)}
                if choice != "ok":
                    probs[choice] = harmful
                out[key] = {"type": "choice", "choice": choice, "confidence": 0.9, "probabilities": probs}
            elif q["type"] == "choice":
                out[key] = {"type": "choice", "choice": options[0], "confidence": 0.9,
                            "probabilities": {o: (0.9 if i == 0 else 0.1) for i, o in enumerate(options)}}
            else:
                out[key] = {"type": "noul", "noul": 0.9}
        return out
    return answer


def test_read_verdict_sums_harmful_options() -> None:
    assert not read_verdict({"choice": "ok", "probabilities": {"ok": 0.7, "weapons": 0.2, "war": 0.1}}).blocked
    split = read_verdict({"choice": "ok", "probabilities": {"ok": 0.4, "war": 0.35, "violence": 0.25}})
    assert split.blocked and split.category == "war" and split.harmful == 0.6  # harm split across options
    with pytest.raises(ValueError):
        read_verdict({"choice": "violation"})


def test_harmful_request_is_stopped_before_anything_is_stored(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="m")
    orch, ws, _ = build(repo_root, key_env, decision=purpose("weapons", 1.0))
    result = orch.ingest(HARMFUL)
    assert result.blocked and result.guard == "G9" and "무기·폭발물" in result.message
    assert not ws.items("sources") and ws.pipeline["stage"] == "S1"
    (g9,) = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G9"]
    assert g9["outcome"] == "blocked" and g9["category"] == "weapons"


def test_legitimate_request_passes_and_the_check_is_recorded(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="m")
    orch, ws, _ = build(repo_root, key_env, decision=purpose("ok", 0.05))
    assert not orch.ingest(CHUNKS).blocked
    assert ws.items("sources") and ws.pipeline["stage"] == "S2"
    (g9,) = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G9"]
    assert g9["outcome"] == "passed"


def test_without_decision_model_the_check_is_skipped_not_a_stop(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    assert not orch.ingest(HARMFUL).blocked  # fail-open: README keeps the decision model optional
    (g9,) = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G9"]
    assert g9["outcome"] == "skipped" and "LINER_DECISION_MODEL" in g9["detail"]
    assert events(ws, "liner_decision") == []


def test_harmful_change_request_is_refused(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="m")
    orch, ws, _ = build(repo_root, key_env, decision=purpose("sexual", 0.95, when="성인 영상"))
    to_cp4(orch, ws)
    teams = load_definitions(repo_root)[1]
    desk = ChangeDesk(ws, teams["default"], orch._ctx.runner)  # noqa: SLF001 — same wiring as app/routes
    with pytest.raises(PipelineStateError, match="성인물·성매매"):
        desk.open_change("성인 영상을 올리고 유료로 파는 메뉴를 추가해 주세요")
    assert not ws.items("changes")


def test_api_tells_the_screen_which_guard_stopped_it(tmp_path: Path, key_env: Path) -> None:
    add_env(key_env, LINER_DECISION_MODEL="m")
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY, decision=purpose("illegal", 0.9))
    app = create_app(Settings(db_path=tmp_path / "p.sqlite3", env_file=key_env),
                     liner=LinerClient(env_file=key_env, transport=fake.transport()))
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "p", "mode": "real"}).json()["id"]
    body = client.post(f"/api/projects/{pid}/input", json={"chunks": HARMFUL}).json()
    assert body["blocked"] and body["guard"] == "G9" and body["kinds"] == []
