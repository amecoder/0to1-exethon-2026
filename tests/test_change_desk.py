from __future__ import annotations
"""FR-21 change request → impact → CP5, and FR-22 「아 이거 아닌데?」 check against the confirmed version."""

from pathlib import Path
from typing import Any

import pytest

from app.change_desk import ChangeDesk, lane
from app.definitions import load_definitions
from app.orchestrator import ConfirmationRequiredError, PipelineStateError
from tests.pipeline_helpers import CP3_WAIVERS, build, events, to_cp2, to_cp3, to_cp4

PAUSE = "일시정지는 배송 하루 전까지 되게 해 주세요"


def desk_for(orch: Any, ws: Any, repo_root: Path) -> ChangeDesk:
    _, teams = load_definitions(repo_root)
    return ChangeDesk(ws, teams["default"], orch._ctx.runner)


def completed(repo_root: Path, key_env: Path, overrides: dict[str, list[Any]] | None = None):
    orch, ws, fake = build(repo_root, key_env, overrides)
    to_cp4(orch, ws)
    orch.confirm("CP4", True, "발주사")
    orch.advance()
    assert ws.pipeline["status"] == "completed"
    return orch, ws, fake, desk_for(orch, ws, repo_root)


# --- lane ----------------------------------------------------------------------------------------
def test_lane_opens_only_after_cp2_and_when_idle(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    assert lane(ws.source)["open"] is False  # waiting at CP2: nothing confirmed yet
    orch.confirm("CP2", True, "발주사")
    orch.advance()
    assert lane(ws.source)["open"] is True  # CP3 is waiting, v1 is fixed
    desk = desk_for(orch, ws, repo_root)
    desk.open_change("결제는 배송 이틀 전에 해 주세요")
    state = lane(ws.source)
    assert state["open"] is False and state["busy"] is True
    with pytest.raises(PipelineStateError):
        desk.open_change("하나 더")


def test_lane_rejects_empty_multiline_or_sensitive_text(repo_root: Path, key_env: Path) -> None:
    *_, desk = completed(repo_root, key_env)
    for bad in ("", "  ", "두 줄\n요청", "제 카드 1234-5678-9012-3456 로 바꿔 주세요"):
        with pytest.raises(PipelineStateError):
            desk.open_change(bad)


# --- FR-21 ---------------------------------------------------------------------------------------
def test_change_maps_target_and_computes_impact_without_touching_the_source(repo_root: Path, key_env: Path) -> None:
    _, ws, fake, desk = completed(repo_root, key_env)
    before = ws.items("requirements")
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["status"] == "awaiting_cp5" and item["target"] == "REQ-01"
    assert item["impact"] == {"requirements": ["REQ-01", "REQ-02"], "screens": ["SCR-01", "SCR-02"],
                              "tests": ["TC-01", "TC-02"]}
    assert item["before"] == before[0]["statement"] and item["after"] != item["before"]
    assert [r["agent"] for r in item["recheck"]] == ["pm", "designer", "qa"]
    assert item["based_on"] == "v2"
    assert ws.items("requirements") == before  # CP5 not approved yet → unchanged
    assert fake.chat_names[-1] == "change_mapping"
    assert PAUSE in fake.chat_payloads("change_mapping")[0]["messages"][-1]["content"]
    pairs = [(m["data"]["from"], m["data"]["to"]) for m in events(ws, "agent_message")][-3:]
    assert ("client", "coordinator") in pairs or ("coordinator", "pm") in pairs


def test_only_owners_of_impacted_items_must_recheck(repo_root: Path, key_env: Path) -> None:
    *_, ws, _, desk = completed(repo_root, key_env)
    change = desk.open_change("결제가 실패하면 바로 문자로 알려 주세요")
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["target"] == "REQ-02" and item["impact"]["tests"] == []
    assert [r["agent"] for r in item["recheck"]] == ["pm", "designer"]  # no TC impacted → QA not listed


def test_cp5_approve_creates_new_version_and_rewrites_target(repo_root: Path, key_env: Path) -> None:
    _, ws, _, desk = completed(repo_root, key_env)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    desk.decide(change["id"], True, "발주사")
    item = ws.get("changes", change["id"])
    req = ws.get("requirements", "REQ-01")
    assert item["status"] == "approved" and item["version"] == "v3"
    assert req["statement"] == item["after"] and change["id"] in req["change_refs"]
    cf = ws.items("confirmations")[-1]
    assert (cf["cp"], cf["approved"], cf["version"], cf["change_id"]) == ("CP5", True, "v3", change["id"])
    snap = ws.items("versions")[-1]
    assert snap["version"] == "v3" and snap["snapshot"]["requirements"][0]["statement"] == item["after"]
    # the answer it replaced no longer counts as "고른 답과 다름"
    assert ws.get("decisions", "DEC-01")["superseded_by"] == change["id"]
    recheck_msgs = [m["data"]["to"] for m in events(ws, "agent_message") if change["id"] in m["data"]["content"]]
    assert {"pm", "designer", "qa"} <= set(recheck_msgs)
    # the delivered work is stale: back to S5, download locked, lane closed until the team is idle again
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S5", "running")
    assert ws.source["meta"]["recheck"]["change_id"] == change["id"]
    assert lane(ws.source)["open"] is False


def test_cp5_reject_keeps_the_source_unchanged(repo_root: Path, key_env: Path) -> None:
    _, ws, _, desk = completed(repo_root, key_env)
    before = (ws.items("requirements"), ws.items("versions"))
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    with pytest.raises(PipelineStateError):
        desk.decide(change["id"], False, "발주사", "")
    desk.decide(change["id"], False, "발주사", "지금은 그대로 둘게요")
    assert ws.get("changes", change["id"])["status"] == "rejected"
    assert (ws.items("requirements"), ws.items("versions")) == before
    assert ws.items("confirmations")[-1]["cp"] == "CP5" and ws.items("confirmations")[-1]["approved"] is False


def test_apply_without_cp5_record_is_blocked_by_g2(repo_root: Path, key_env: Path) -> None:
    _, ws, _, desk = completed(repo_root, key_env)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    with pytest.raises(ConfirmationRequiredError):
        desk._apply(ws.get("changes", change["id"]))
    assert [g["data"]["id"] for g in events(ws, "guardrail")][-1] == "G2"


def test_unmapped_target_is_reported_not_failed(repo_root: Path, key_env: Path) -> None:
    bad = {"change_mapping": [{"target": "REQ-77", "after_statement": "x", "summary": "x"}]}
    _, ws, _, desk = completed(repo_root, key_env, bad)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["status"] == "unmapped" and "요구사항" in item["error"]
    assert lane(ws.source)["open"] is True


def test_change_allowed_after_cp2_blocks_cp3_until_decided(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    desk = desk_for(orch, ws, repo_root)
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    with pytest.raises(PipelineStateError):
        orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)
    desk.decide(change["id"], True, "발주사")
    assert ws.get("changes", change["id"])["based_on"] == "v1"
    orch.advance()  # S5 is redone on the changed requirement, then CP3 waits again
    orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)  # superseded answer no longer blocks
    assert ws.items("versions")[-1]["version"] == "v3"


# --- FR-22 ---------------------------------------------------------------------------------------
def test_complaint_new_change_shows_evidence_and_converts(repo_root: Path, key_env: Path) -> None:
    _, ws, fake, desk = completed(repo_root, key_env)
    complaint = desk.open_complaint("일요일에도 받고 싶은데 왜 안 되죠?")
    desk.check_complaint(complaint["id"])
    item = ws.get("complaints", complaint["id"])
    assert item["status"] == "classified" and item["classification"] == "새 변경 요청"
    ev = item["evidence"][0]
    assert ev["requirement"]["id"] == "REQ-01" and ev["requirement"]["statement"]
    assert (ev["confirmation"]["cp"], ev["confirmation"]["who"], ev["confirmation"]["version"]) == ("CP3", "발주사", "v2")
    assert ev["confirmation"]["at"]
    assert item["guard"]["applied"] is False
    assert fake.chat_names[-1] == "complaint_check"
    change = desk.open_change(item["text"], complaint_ref=item["id"])
    assert ws.get("changes", change["id"])["complaint_ref"] == item["id"]


def test_guard_turns_request_equal_to_confirmed_text_into_violation(repo_root: Path, key_env: Path) -> None:
    _, ws, _, desk = completed(repo_root, key_env)
    complaint = desk.open_complaint("배송 요일을 수·토 중 고름으로 하기로 했는데 화면에 없어요")
    desk.check_complaint(complaint["id"])
    item = ws.get("complaints", complaint["id"])
    assert item["model_classification"] == "새 변경 요청"  # the scripted model got it wrong
    assert item["classification"] == "합의 위반" and item["guard"]["applied"] is True
    checks = [e["data"] for e in events(ws, "check_result") if e["data"]["check"] == "complaint_guard"]
    assert checks and checks[-1]["outcome"] == "flagged"


def test_complaint_compares_against_the_confirmed_snapshot(repo_root: Path, key_env: Path) -> None:
    _, ws, fake, desk = completed(repo_root, key_env)
    complaint = desk.open_complaint("일요일에도 받고 싶은데 왜 안 되죠?")
    desk.check_complaint(complaint["id"])
    content = fake.chat_payloads("complaint_check")[0]["messages"][-1]["content"]
    assert "확정 요구사항" in content and "v2" in content


def test_complaint_needs_a_confirmed_version(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    with pytest.raises(PipelineStateError):
        desk_for(orch, ws, repo_root).open_complaint("이거 아닌데요")


def test_interrupted_lane_item_becomes_failed(repo_root: Path, key_env: Path) -> None:
    _, ws, _, desk = completed(repo_root, key_env)
    change = desk.open_change(PAUSE)
    desk.mark_interrupted()
    assert ws.get("changes", change["id"])["status"] == "failed"
    assert lane(ws.source)["open"] is True


def test_change_request_respects_g7_and_continue(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake, desk = completed(repo_root, key_env)
    used = len(fake.requests)
    key_env.write_text(key_env.read_text(encoding="utf-8") + f"EXETHON_MAX_LINER_CALLS={used}\n", encoding="utf-8")
    change = desk.open_change(PAUSE)
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["status"] == "failed" and item["limit"] is True and "다시 보내" in item["error"]
    assert len(fake.requests) == used  # refused before sending
    orch.continue_after_limit()
    assert ws.pipeline["status"] == "completed"
    again = desk.open_change(PAUSE)
    desk.map_change(again["id"])
    assert ws.get("changes", again["id"])["status"] == "awaiting_cp5"
