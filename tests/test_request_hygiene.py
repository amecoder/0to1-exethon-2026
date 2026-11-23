from __future__ import annotations
"""After confirmation the client may say things unrelated to the product, ask for what is already so, repeat an
applied request, or reverse an earlier change. None of these should raise a CP5 card for nothing."""

from pathlib import Path
from typing import Any

import pytest

from app.change_desk import ChangeDesk
from app.definitions import load_definitions
from app.errors import PipelineStateError
from tests.flower_script import change_mapping, complaint_check, extra_input
from tests.pipeline_helpers import CP3_WAIVERS, build, to_cp4


def completed(repo_root: Path, key_env: Path, overrides: dict[str, list[Any]] | None = None):
    orch, ws, fake = build(repo_root, key_env, overrides)
    to_cp4(orch, ws)
    orch.confirm("CP4", True, "발주사")
    orch.advance()
    _, teams = load_definitions(repo_root)
    return orch, ws, fake, ChangeDesk(ws, teams["default"], orch._ctx.runner)


def pm(payload: dict[str, Any]) -> dict[str, Any]:
    """The scripted PM, plus: small talk → NONE."""
    if "점심" in str(extra_input(payload).get("변경 요청", "")):
        return {"target": "NONE", "after_statement": "", "summary": "", "rationale": "제품과 관련 없는 말"}
    return change_mapping(payload)


def qa(payload: dict[str, Any]) -> dict[str, Any]:
    said = str(extra_input(payload).get("발주사 말", ""))
    if "점심" in said:
        return {"requirement_ids": [], "classification": "무관", "requested": "", "reason": "제품과 관련 없는 말"}
    return complaint_check(payload)


def finish_rework(orch: Any) -> None:
    orch.advance()
    orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)
    orch.advance()
    orch.confirm("CP4", True, "발주사")
    orch.advance()


def test_small_talk_change_is_recorded_without_a_cp5_card(repo_root: Path, key_env: Path) -> None:
    _, ws, _, desk = completed(repo_root, key_env, {"change_mapping": [pm]})
    change = desk.open_change("오늘 점심 뭐 먹을까요")
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["status"] == "unrelated" and "관련 없는" in item["error"]
    assert not [c for c in ws.items("confirmations") if c["cp"] == "CP5"]
    desk.open_change("결제는 배송 이틀 전에 해 주세요")  # the lane is open again right away


def test_change_to_what_is_already_there_is_no_change(repo_root: Path, key_env: Path) -> None:
    def same(payload: dict[str, Any]) -> dict[str, Any]:
        out = change_mapping(payload)
        req = next(r for r in ws.items("requirements") if r["id"] == out["target"])
        return {**out, "after_statement": f" {req['statement']} "}  # spacing differs, words are the same
    _, ws, _, desk = completed(repo_root, key_env, {"change_mapping": [same]})
    change = desk.open_change("배송 요일은 지금처럼 해 주세요")
    desk.map_change(change["id"])
    item = ws.get("changes", change["id"])
    assert item["status"] == "no_change" and item["target"] in item["error"] and "이미" in item["error"]


def test_repeating_an_applied_change_is_answered_without_the_pm(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake, desk = completed(repo_root, key_env)
    first = desk.open_change("결제는 배송 이틀 전에 해 주세요")
    desk.map_change(first["id"])
    desk.decide(first["id"], True, "발주사")
    finish_rework(orch)
    calls = len(fake.chat_names)
    with pytest.raises(PipelineStateError, match=first["id"]):
        desk.open_change("결제는  배송 이틀 전에 해 주세요.")  # same request, other spacing and a period
    assert len(fake.chat_names) == calls


def test_reverting_an_earlier_change_is_named_on_the_cp5_card(repo_root: Path, key_env: Path) -> None:
    seen: dict[str, str] = {}

    def back(payload: dict[str, Any]) -> dict[str, Any]:  # second mapping: the statement as it was in v2
        return {**change_mapping(payload), "after_statement": seen["original"]}
    orch, ws, _, desk = completed(repo_root, key_env, {"change_mapping": [change_mapping, back]})
    seen["original"] = ws.get("requirements", "REQ-02")["statement"]
    version_before = ws.items("versions")[-1]["version"]
    first = desk.open_change("결제는 배송 이틀 전에 해 주세요")
    desk.map_change(first["id"])
    desk.decide(first["id"], True, "발주사")
    finish_rework(orch)
    second = desk.open_change("결제는 원래대로 되돌려 주세요")
    desk.map_change(second["id"])
    item = ws.get("changes", second["id"])
    assert item["status"] == "awaiting_cp5"
    assert item["history"] == [first["id"]] and item["reverts_to"] == version_before


def test_small_talk_complaint_is_not_forced_into_a_verdict(repo_root: Path, key_env: Path) -> None:
    _, ws, fake, desk = completed(repo_root, key_env, {"complaint_check": [qa]})
    complaint = desk.open_complaint("오늘 점심 뭐 먹을까요")
    desk.check_complaint(complaint["id"])
    item = ws.get("complaints", complaint["id"])
    assert item["status"] == "unrelated" and "관련 없는" in item["error"]


def test_repeating_a_checked_complaint_points_to_the_earlier_verdict(repo_root: Path, key_env: Path) -> None:
    _, ws, fake, desk = completed(repo_root, key_env)
    first = desk.open_complaint("일요일에도 받고 싶은데 왜 안 되죠?")
    desk.check_complaint(first["id"])
    calls = len(fake.chat_names)
    with pytest.raises(PipelineStateError, match=first["id"]):
        desk.open_complaint("일요일에도 받고 싶은데 왜 안 되죠")
    assert len(fake.chat_names) == calls
