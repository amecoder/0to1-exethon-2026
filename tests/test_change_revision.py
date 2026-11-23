from __future__ import annotations
"""Real-run bug (11-17): CP5 patched one statement and restarted at S5, so the target's acceptance and every
requirement leaning on it kept the old choice, and the designer/developer never heard about the change.

Now CP5 approval → PM revision of the affected requirements → consistency check → S5 → CP3 → S6 → CP4."""

import json
from pathlib import Path
from typing import Any

from app.change_desk import ChangeDesk
from app.checks import review
from app.definitions import load_definitions
from tests.flower_script import final_requirements_for
from tests.pipeline_helpers import CHUNKS, CP3_WAIVERS, build, events, to_cp4

OLD = "토요일 일괄"
DAY_CHANGE = "배송 요일을 수요일과 토요일 중에서 고객이 고를 수 있게 해 주세요"


def saturday_requirements(payload: dict[str, Any]) -> dict[str, Any]:
    """S4 like the real run: the chosen answer is in the target's acceptance and in a dependent's statement."""
    out = final_requirements_for(CHUNKS, OLD, "3일 안에 다시 결제")
    first, second = out["requirements"]
    first = {**first, "acceptance": {"given": "구독 고객이", "when": "신청하면", "then": f"모든 회차가 {OLD} 배송으로 배정된다"}}
    second = {**second, "statement": f"{OLD} 배송이므로 매주 카드 자동결제가 실패하면 3일 안에 다시 결제"}
    return {"requirements": [first, second]}


def completed_on_saturday(repo_root: Path, key_env: Path, overrides: dict[str, list[Any]] | None = None):
    orch, ws, fake = build(repo_root, key_env, {"requirements_final": [saturday_requirements], **(overrides or {})})
    to_cp4(orch, ws, day=OLD)
    orch.confirm("CP4", True, "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "completed"
    _, teams = load_definitions(repo_root)
    return orch, ws, fake, ChangeDesk(ws, teams["default"], orch._ctx.runner)


def approve_day_change(orch: Any, ws: Any, desk: ChangeDesk) -> str:
    change = desk.open_change(DAY_CHANGE)
    desk.map_change(change["id"])
    desk.decide(change["id"], True, "발주사")
    orch.advance()
    return change["id"]


def req_text(req: dict[str, Any]) -> str:
    return " ".join([req["statement"], *req["acceptance"].values()])


def extra_of(payload: dict[str, Any]) -> str:
    return payload["messages"][-1]["content"].split("[추가 입력]\n", 1)[-1]


def test_cp5_revises_target_acceptance_and_dependents(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake, desk = completed_on_saturday(repo_root, key_env)
    cps_before = [c["cp"] for c in ws.items("confirmations")]
    change_id = approve_day_change(orch, ws, desk)

    target, dependent = ws.get("requirements", "REQ-01"), ws.get("requirements", "REQ-02")
    assert OLD not in req_text(target), target["acceptance"]
    assert OLD not in req_text(dependent), dependent["statement"]
    assert change_id in dependent["change_refs"]
    # the PM got a compact brief and the affected requirements, then the revision is recorded with its diff
    brief = json.loads(extra_of(fake.chat_payloads("requirements_revision")[0]))
    assert brief["변경"]["id"] == change_id and brief["변경"]["발주사 말"] == DAY_CHANGE
    assert {r["id"] for r in brief["고칠 수 있는 요구사항"]} == {"REQ-01", "REQ-02"}
    item = ws.get("changes", change_id)
    revised = {r["id"]: r for r in item["revision"]["requirements"]}
    assert set(revised) == {"REQ-01", "REQ-02"}
    assert OLD in revised["REQ-02"]["before"]["statement"] and OLD not in revised["REQ-02"]["after"]["statement"]
    assert item["direct"] == ["REQ-01", "REQ-02"]
    assert [e["data"]["change_id"] for e in events(ws, "change_revised")] == [change_id]
    assert ws.get("decisions", "DEC-01")["superseded_by"] == change_id  # history kept, marked superseded
    # no CP2 again: the team waits at CP3, without a stale-text warning
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    assert [c["cp"] for c in ws.items("confirmations")] == [*cps_before, "CP5"]
    assert not [w for w in review(ws.source, "CP3")["waivable"] if w["code"] == "change.stale"]


def test_designer_and_developer_get_the_change_brief(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake, desk = completed_on_saturday(repo_root, key_env)
    change_id = approve_day_change(orch, ws, desk)
    for name in ("screen_spec", "test_cases"):
        assert change_id in extra_of(fake.chat_payloads(name)[-1]) and DAY_CHANGE in extra_of(fake.chat_payloads(name)[-1])
    assert change_id not in extra_of(fake.chat_payloads("screen_spec")[0])  # first run had no change
    orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)
    orch.advance()
    developer = extra_of(fake.chat_payloads("prototype")[-1])
    assert change_id in developer and DAY_CHANGE in developer


def test_stale_dependent_is_a_waivable_cp3_warning(repo_root: Path, key_env: Path) -> None:
    lazy_pm = {"requirements_revision": [{"after_key": "수요일 또는 토요일", "requirements": [
        {"id": "REQ-01", "title": "배송 요일", "statement": "무시됨",
         "acceptance": {"given": "구독 고객이", "when": "신청하면", "then": "수요일 또는 토요일 중 고른 요일로 배정된다"},
         "exceptions": []}]}]}
    orch, ws, _, desk = completed_on_saturday(repo_root, key_env, lazy_pm)
    change_id = approve_day_change(orch, ws, desk)
    assert ws.get("requirements", "REQ-01")["statement"] == ws.get("changes", change_id)["after"]  # approved text kept
    stale = [w for w in review(ws.source, "CP3")["waivable"] if w["code"] == "change.stale"]
    assert [w["target"] for w in stale] == ["REQ-02"] and change_id in stale[0]["message"]
    checks = [e["data"] for e in events(ws, "check_result") if e["data"]["check"] == "change_consistency"]
    assert checks[-1]["outcome"] == "flagged" and checks[-1]["items"] == ["REQ-02"]
    waivers = {**CP3_WAIVERS, stale[0]["id"]: "결제 문장은 다음 버전에서 고침"}
    orch.confirm("CP3", True, "발주사", waivers=waivers)
    assert ws.pipeline["stage"] == "S6"
