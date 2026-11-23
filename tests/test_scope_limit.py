from __future__ import annotations
"""FR-23 G8: when the designer draws more screens than the limit, the coordinator asks the client which
screens to keep. The kept screens are trimmed by code (no second drawing call) and S5 carries on."""

from pathlib import Path
from typing import Any

import pytest

from app.checks import review
from app.orchestrator import PipelineStateError
from app.views import client_todo
from tests.flower_script import element, screen_spec
from tests.pipeline_helpers import CHUNKS, build, events, to_cp2


def six_screens(_: Any = None) -> dict[str, Any]:
    spec = screen_spec(CHUNKS)
    extra = [{"id": f"S-{n}", "title": f"추가 화면 {n}", "purpose": "더 보여 준다",
              "elements": [element("안내", "text", ["REQ-01"])],
              "states": {"empty": "없음", "loading": "불러오는 중", "error": "오류 안내"},
              "requirement_refs": ["REQ-01"]} for n in range(3, 7)]
    return {**spec, "screens": [*spec["screens"], *extra], "flow": ["S-A", "S-B", "S-3", "S-4", "S-5", "S-6"]}


def to_scope(repo_root: Path, key_env: Path):
    orch, ws, fake = build(repo_root, key_env, {"screen_spec": [six_screens()]})
    to_cp2(orch, ws)
    orch.confirm("CP2", True, "발주사")
    orch.advance()
    return orch, ws, fake


def test_too_many_screens_pauses_s5_and_asks_the_client(repo_root: Path, key_env: Path) -> None:
    _, ws, fake = to_scope(repo_root, key_env)
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S5", "awaiting_scope")
    assert fake.chat_names[-1] == "screen_spec" and "test_cases" not in fake.chat_names
    g8 = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G8"]
    assert g8[-1]["outcome"] == "flagged" and (g8[-1]["count"], g8[-1]["max"]) == (6, 5)
    todo = client_todo(ws.source)
    assert todo["kind"] == "scope" and todo["max"] == 5 and len(todo["screens"]) == 6
    assert {"id", "title", "purpose"} <= set(todo["screens"][0])
    asked = [m["data"] for m in events(ws, "agent_message") if m["data"]["to"] == "client"]
    assert "5개" in asked[-1]["content"]


def test_narrowing_keeps_chosen_screens_and_finishes_s5(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = to_scope(repo_root, key_env)
    orch.narrow_scope(["SCR-01", "SCR-02"], "발주사")
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    assert [s["id"] for s in ws.items("screens")] == ["SCR-01", "SCR-02"]
    assert ws.items("screen_spec")[0]["flow"] == ["SCR-01", "SCR-02"]
    assert fake.chat_names.count("screen_spec") == 1 and fake.chat_names.count("test_cases") == 1
    scope = [d for d in ws.items("decisions") if d.get("kind") == "scope"]
    assert len(scope) == 1 and scope[0]["answered_by"] == "client" and scope[0]["screens_kept"] == ["SCR-01", "SCR-02"]
    r = review(ws.source, "CP3")
    assert scope[0]["id"] not in [a["decision_id"] for a in r["answers"]]
    assert not [n for n in r["notices"] if n["target"] == scope[0]["id"]]
    assert [e["data"]["outcome"] for e in events(ws, "guardrail") if e["data"]["id"] == "G8"] == ["flagged", "resolved"]


@pytest.mark.parametrize("keep", [[], ["SCR-01", "SCR-02", "SCR-03", "SCR-04", "SCR-05", "SCR-06"], ["SCR-77"]])
def test_narrowing_must_fit_the_limit(repo_root: Path, key_env: Path, keep: list[str]) -> None:
    orch, _, _ = to_scope(repo_root, key_env)
    with pytest.raises(PipelineStateError):
        orch.narrow_scope(keep, "발주사")


def test_limit_comes_from_env(repo_root: Path, key_env: Path) -> None:
    key_env.write_text(key_env.read_text(encoding="utf-8") + "EXETHON_MAX_SCREENS=1\n", encoding="utf-8")
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    orch.confirm("CP2", True, "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "awaiting_scope" and client_todo(ws.source)["max"] == 1


def test_narrow_only_while_waiting_for_scope(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    with pytest.raises(PipelineStateError):
        orch.narrow_scope(["SCR-01"], "발주사")


# --- 11-22 (user): 「모두 만들기」 keeps every screen past the limit -------------------------------------------
def test_keeping_every_screen_goes_past_the_limit(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = to_scope(repo_root, key_env)
    every = [s["id"] for s in ws.items("screens")]
    orch.narrow_scope(every, "발주사", keep_all=True)
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    assert [s["id"] for s in ws.items("screens")] == every
    scope = next(d for d in ws.items("decisions") if d.get("kind") == "scope")
    assert scope["chosen"].startswith("모두 만들기") and scope["dropped_requirements"] == []
    g8 = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G8"]
    assert g8[-1]["outcome"] == "resolved" and g8[-1]["count"] == 6


def test_keep_all_must_name_every_screen(repo_root: Path, key_env: Path) -> None:
    orch, _, _ = to_scope(repo_root, key_env)
    with pytest.raises(PipelineStateError):
        orch.narrow_scope(["SCR-01"], "발주사", keep_all=True)
