from __future__ import annotations
"""S5 documentation (designer SCR, QA TC, PM BRD/PRD), coverage check (FR-10) and CP3 (FR-11)."""

import copy
from pathlib import Path
from typing import Any

import pytest

from app.checks import review
from app.orchestrator import STAGE_TABLE, ConfirmationRequiredError, PipelineStateError
from tests.flower_script import flower_outputs, screen_spec
from tests.pipeline_helpers import CHUNKS, build, events, to_cp2, to_cp3


def test_stage_table_ends_with_s5_and_cp3() -> None:
    assert [s.id for s in STAGE_TABLE] == ["S1", "S2", "CP1", "S3", "S4", "CP2", "S5", "CP3", "S6", "CP4"]


def test_cp2_approval_freezes_v1_then_runs_s5_in_order(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp3(orch, ws)
    assert ws.items("versions")[0]["version"] == "v1"
    assert fake.chat_names[-4:] == ["screen_spec", "test_cases", "document_content", "consumer_feedback"]
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    s5 = [(m["data"]["from"], m["data"]["to"]) for m in events(ws, "agent_message") if m["stage"] == "S5"]
    assert s5[:5] == [("coordinator", "pm"), ("pm", "designer"), ("designer", "pm"), ("pm", "qa"), ("qa", "pm")]
    assert ("pm", "coordinator") in s5 and ("coordinator", "client") in s5
    assert not [e for e in events(ws, "message_rerouted") if e["stage"] == "S5"]
    assert {e["actor"] for e in events(ws, "liner_chat") if e["stage"] == "S5"} == {"designer", "qa", "pm", "consumer"}


def test_s5_needs_cp2_record(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp2(orch, ws)
    with pytest.raises(ConfirmationRequiredError):
        orch.run_stage("S5")


def test_screens_and_tests_are_normalized_and_linked(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    screens = ws.items("screens")
    assert [s["id"] for s in screens] == ["SCR-01", "SCR-02"]
    assert [e["no"] for e in screens[0]["elements"]] == [1, 2, 3, 4]
    assert screens[1]["requirement_refs"] == ["REQ-02"]  # REQ-99 does not exist
    assert any(e["data"]["ref"] == "REQ-99" for e in events(ws, "ref_dropped"))
    assert set(screens[0]["states"]) == {"empty", "loading", "error"}
    tests = ws.items("tests")
    assert [t["id"] for t in tests] == ["TC-01", "TC-02"]
    assert tests[0]["screen_refs"] == ["SCR-01"] and tests[0]["requirement_refs"] == ["REQ-01"]
    assert {"objective", "priority", "preconditions", "inputs", "steps", "expected"} <= set(tests[0])
    reqs = {r["id"]: r for r in ws.items("requirements")}
    assert reqs["REQ-01"]["screens"] == ["SCR-01"] and reqs["REQ-01"]["tests"] == ["TC-01", "TC-02"]
    assert reqs["REQ-02"]["screens"] == ["SCR-01", "SCR-02"] and reqs["REQ-02"]["tests"] == []
    assert ws.items("brd")[0]["id"] == "BRD-01" and ws.items("prd")[0]["id"] == "PRD-01"


def test_goal_without_number_becomes_open(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    assert [g["status"] for g in ws.items("brd")[0]["goals"]] == ["확정", "미결"]


def test_write_gate_for_s5_bundles(repo_root: Path, key_env: Path) -> None:
    _, ws, _ = build(repo_root, key_env)
    assert ws.write("designer", "tests", {"id": "TC-01"}) is False
    assert ws.write("qa", "screens", {"id": "SCR-01"}) is False
    assert ws.write("designer", "brd", {"id": "BRD-01"}) is False
    assert ws.write("qa", "prd", {"id": "PRD-01"}) is False
    assert ws.write("designer", "screens", {"id": "SCR-01"}) is True
    assert ws.write("qa", "tests", {"id": "TC-01"}) is True
    assert ws.write("pm", "brd", {"id": "BRD-01"}) is True and ws.write("pm", "prd", {"id": "PRD-01"}) is True
    assert len(events(ws, "write_rejected")) == 4


def test_coverage_warning_disables_cp3_until_reason(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    result = review(ws.source, "CP3")
    assert [w["id"] for w in result["waivable"]] == ["coverage.no_tc:REQ-02"]
    assert result["blocking"] == [] and result["can_approve"] is False
    with pytest.raises(PipelineStateError, match="REQ-02"):
        orch.confirm("CP3", True, "발주사")
    with pytest.raises(PipelineStateError):
        orch.confirm("CP3", True, "발주사", waivers={"coverage.no_tc:REQ-02": "  "})
    orch.confirm("CP3", True, "발주사", waivers={"coverage.no_tc:REQ-02": "결제 실패는 다음 단계에서 시험"})
    record = ws.items("confirmations")[-1]
    assert record["cp"] == "CP3" and record["version"] == "v2"
    assert record["waivers"] == {"coverage.no_tc:REQ-02": "결제 실패는 다음 단계에서 시험"}
    assert [v["version"] for v in ws.items("versions")] == ["v1", "v2"]
    assert ws.items("versions")[1]["snapshot"]["screens"] == list(ws.items("screens"))
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S6", "running")  # S6 runs on the next advance()


def test_requirement_without_screen_needs_reason(repo_root: Path, key_env: Path) -> None:
    spec = copy.deepcopy(screen_spec(CHUNKS))
    spec["screens"] = spec["screens"][:1]
    spec["screens"][0]["elements"] = spec["screens"][0]["elements"][:2]
    spec["screens"][0]["requirement_refs"] = ["REQ-01"]
    for el in spec["screens"][0]["elements"]:
        el["requirement_refs"] = ["REQ-01"]
    orch, ws, _ = build(repo_root, key_env, {"screen_spec": [spec]})
    to_cp3(orch, ws)
    assert "coverage.no_scr:REQ-02" in [w["id"] for w in review(ws.source, "CP3")["waivable"]]

    with_reason = {**spec, "no_screen": [{"requirement_id": "REQ-02", "reason": "결제 재시도는 화면 없이 처리"}]}
    orch, ws, _ = build(repo_root, key_env, {"screen_spec": [with_reason]})
    to_cp3(orch, ws)
    assert "coverage.no_scr:REQ-02" not in [w["id"] for w in review(ws.source, "CP3")["waivable"]]
    assert ws.get("requirements", "REQ-02")["screen_exemption"] == "결제 재시도는 화면 없이 처리"


def test_open_requirement_is_a_coverage_warning(repo_root: Path, key_env: Path) -> None:
    def open_pm(payload: dict[str, Any]) -> dict[str, Any]:
        out = flower_outputs(CHUNKS)["requirements_final"][0](payload)
        out["requirements"][1]["status"] = "미결"
        return out
    orch, ws, _ = build(repo_root, key_env, {"requirements_final": [open_pm]})
    to_cp3(orch, ws)
    assert "coverage.open:REQ-02" in [w["id"] for w in review(ws.source, "CP3")["waivable"]]


def test_s5_outputs_pass_g3_and_g5(repo_root: Path, key_env: Path) -> None:
    spec = copy.deepcopy(screen_spec(CHUNKS))
    spec["screens"][0]["elements"][0]["description"] = "문의 010-1234-5678 로 안내"
    spec["screens"][1]["requirement_refs"] = ["REQ-99"]
    orch, ws, _ = build(repo_root, key_env, {"screen_spec": [spec]})
    to_cp3(orch, ws)
    assert "010-1234-5678" not in str(ws.items("screens"))
    guards = [(g["data"]["id"], g["data"].get("item")) for g in events(ws, "guardrail") if g["stage"] == "S5"]
    assert ("G3", None) in [(gid, None) for gid, _ in guards]
    assert ("G5", "SCR-02") in guards
    assert ws.get("screens", "SCR-02")["status"] == "가정"


def test_cp3_rejection_reruns_s5_with_reason(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp3(orch, ws)
    orch.confirm("CP3", False, "발주사", "결제 안내 화면 문구가 어려워요")
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "running")  # sorted in the background
    orch.advance()
    assert fake.chat_names.count("screen_spec") == 2
    assert "결제 안내 화면 문구가 어려워요" in fake.chat_payloads("screen_spec")[1]["messages"][-1]["content"]
    assert ws.pipeline["stage"] == "CP3"


# --- 11-22 v3 recording: S5 stopped on a cut Liner stream, and 「다시 시도」 redid the finished test cases ---------
def test_a_cut_stream_is_retried_once_without_failing_the_stage(repo_root: Path, key_env: Path) -> None:
    from tests.fake_liner import STREAM_ERROR
    docs = flower_outputs(CHUNKS)["document_content"]
    orch, ws, fake = build(repo_root, key_env, {"document_content": [STREAM_ERROR, *docs]})
    to_cp3(orch, ws)
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    assert fake.chat_names.count("document_content") == 2
    (cut,) = [e["data"] for e in events(ws, "liner_retry")]
    assert cut["agent"] == "pm" and cut["schema"] == "document_content"


def test_retry_after_a_failed_s5_skips_the_finished_test_cases(repo_root: Path, key_env: Path) -> None:
    from tests.fake_liner import STREAM_ERROR
    docs = flower_outputs(CHUNKS)["document_content"]
    orch, ws, fake = build(repo_root, key_env, {"document_content": [STREAM_ERROR, STREAM_ERROR, *docs]})
    to_cp3(orch, ws)
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("S5", "failed")
    assert fake.chat_names.count("test_cases") == 1
    orch.retry()
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    assert fake.chat_names.count("test_cases") == 1  # done before the cut: not asked (and paid) again
    assert ws.items("tests") and ws.pipeline.get("resume") is None
