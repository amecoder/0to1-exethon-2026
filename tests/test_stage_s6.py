from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.checks import review
from app.orchestrator import STAGE_TABLE, ConfirmationRequiredError, PipelineStateError
from app.prototype import TEMPLATE_NOTICE
from tests.fake_liner import STREAM_ERROR
from tests.flower_script import PROTOTYPE_HTML, prototype_output
from tests.pipeline_helpers import build, events, to_cp3, to_cp4


def test_stage_table_includes_development_and_cp4() -> None:
    assert [s.id for s in STAGE_TABLE][-2:] == ["S6", "CP4"]


def test_s6_is_blocked_without_cp3_record(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp3(orch, ws)
    with pytest.raises(ConfirmationRequiredError, match="CP3"):
        orch.run_stage("S6")
    assert events(ws, "guardrail")[-1]["data"]["id"] == "G2"
    assert "prototype" not in fake.chat_names


def test_s6_builds_prototype_strips_g6_and_stops_at_cp4(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp4(orch, ws)
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP4", "awaiting_confirmation")
    proto = ws.items("prototype")[-1]
    assert proto["origin"] == "agent" and proto["attempts"] == 1 and proto["based_on"] == "v2"
    assert proto["missing_screens"] == [] and "fonts.example.com" not in proto["html"]
    assert [v["code"] for v in proto["violations"]] == ["external_link"]
    g6 = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G6"]
    assert g6 and g6[0]["outcome"] == "stripped" and g6[0]["code"] == "external_link"
    # the developer got the confirmed source (screens, tests) and the version label
    payload = fake.chat_payloads("prototype")[0]["messages"][-1]["content"]
    assert "SCR-01" in payload and "TC-01" in payload and "v2" in payload
    routes = {(e["data"]["from"], e["data"]["to"]) for e in events(ws, "agent_message") if e["stage"] == "S6"}
    assert {("coordinator", "developer"), ("designer", "developer"), ("qa", "developer"),
            ("developer", "qa")} <= routes
    checklist = ws.items("qa_checklist")[-1]["rows"]
    assert [r["tc_id"] for r in checklist] == ["TC-01", "TC-02"]
    assert all(r["result"] == "확인 가능" for r in checklist)


def test_missing_scr_becomes_cp4_warning(repo_root: Path, key_env: Path) -> None:
    html = PROTOTYPE_HTML.replace("SCR-02", "결제화면")
    orch, ws, _ = build(repo_root, key_env, {"prototype": [prototype_output(html)]})
    to_cp4(orch, ws)
    assert ws.items("prototype")[-1]["missing_screens"] == ["SCR-02"]
    result = review(ws.source, "CP4")
    assert [w["id"] for w in result["waivable"]] == ["prototype.missing_scr:SCR-02"]
    assert result["can_approve"] is False
    with pytest.raises(PipelineStateError, match="SCR-02"):
        orch.confirm("CP4", True, "발주사")
    orch.confirm("CP4", True, "발주사", waivers={"prototype.missing_scr:SCR-02": "결제 안내는 다음에"})
    assert ws.pipeline["status"] == "completed"


def test_invalid_output_retries_once_then_uses_template(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env, {"prototype": ["이건 JSON 이 아님", {"html": "<div>조각</div>",
                                                                                "summary": []}]})
    to_cp4(orch, ws)
    assert fake.chat_names.count("prototype") == 2
    proto = ws.items("prototype")[-1]
    assert proto["origin"] == "template" and proto["attempts"] == 2
    assert TEMPLATE_NOTICE in proto["html"] and proto["missing_screens"] == []
    built = events(ws, "prototype_built")[-1]["data"]
    assert built["origin"] == "template" and len(built["failures"]) == 2
    notices = [w["code"] for w in review(ws.source, "CP4")["notices"]]
    assert "prototype.template" in notices
    # the retry told the developer what was wrong
    retry_payload = fake.chat_payloads("prototype")[1]["messages"][-1]["content"]
    assert "JSON" in retry_payload


def test_network_call_is_rejected_then_second_answer_used(repo_root: Path, key_env: Path) -> None:
    bad = PROTOTYPE_HTML.replace("</script>", "fetch('https://api.example.com/orders');</script>")
    orch, ws, fake = build(repo_root, key_env, {"prototype": [prototype_output(bad), prototype_output()]})
    to_cp4(orch, ws)
    proto = ws.items("prototype")[-1]
    assert proto["origin"] == "agent" and proto["attempts"] == 2
    rejected = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G6" and e["data"]["outcome"] == "rejected"]
    assert rejected and rejected[0]["code"] == "external_network"


def test_cp4_reject_reworks_s6_with_feedback(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp4(orch, ws)
    orch.confirm("CP4", False, "발주사", reason="결제 화면 문구를 더 쉽게")
    orch.advance()
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP4", "awaiting_confirmation")
    assert fake.chat_names.count("prototype") == 2
    assert "결제 화면 문구를 더 쉽게" in fake.chat_payloads("prototype")[1]["messages"][-1]["content"]
    assert len(ws.items("prototype")) == 1  # replaced, not appended
    orch.confirm("CP4", True, "발주사")
    assert ws.pipeline["status"] == "completed" and ws.items("confirmations")[-1]["version"] is None


def test_developer_gets_today_and_the_rules_from_the_demo_check(repo_root: Path, key_env: Path) -> None:
    """11-22 recording: a 「미리보기 · 오늘 6월 11일」 date switch sat on top, and the hero was a dot pattern."""
    orch, ws, fake = build(repo_root, key_env)
    to_cp4(orch, ws)
    sent = "\n".join(str(m["content"]) for m in fake.chat_payloads("prototype")[0]["messages"])
    assert re.search(r"\d{4}년 \d{1,2}월 \d{1,2}일", sent)  # dates in sample data start from today
    assert "시연용 조작" in sent  # no date/state switches on the screen
    assert "hero-photo" in sent  # a fitting business opens with its photo
    assert "카드마다 사진" in sent  # 11-22: told to be short, the model dropped the size cards' photos
    assert "HTML 은 짧게" in sent  # the first attempt is already asked for a short answer (the cut came at ~300 s)
    assert 'data-fx=\\"particles\\"' not in sent and 'data-fx="particles"' not in sent


def test_broken_stream_is_a_failed_attempt_not_a_failed_stage(repo_root: Path, key_env: Path) -> None:
    """11-22 re-recording: Liner cut the developer's stream at ~300 s and S6 failed outright."""
    orch, ws, fake = build(repo_root, key_env, {"prototype": [STREAM_ERROR, prototype_output()]})
    to_cp4(orch, ws)
    proto = ws.items("prototype")[-1]
    assert proto["origin"] == "agent" and proto["attempts"] == 2
    retry = fake.chat_payloads("prototype")[1]["messages"][-1]["content"]
    assert "짧게" in retry  # the second attempt is asked for a shorter answer


def test_every_attempt_broken_still_ends_with_the_template(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, {"prototype": [STREAM_ERROR]})
    to_cp4(orch, ws)
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP4", "awaiting_confirmation")
    proto = ws.items("prototype")[-1]
    assert proto["origin"] == "template" and proto["attempts"] == 2


def test_developer_thinks_less_to_finish_inside_liners_limit(repo_root: Path, key_env: Path) -> None:
    key_env.write_text(key_env.read_text(encoding="utf-8").replace("LINER_MODEL=test-model", "LINER_MODEL=liner-claude-router"),
                       encoding="utf-8")
    orch, ws, fake = build(repo_root, key_env)
    to_cp4(orch, ws)
    assert fake.chat_payloads("prototype")[0].get("reasoning_effort") == "low"
    assert all("reasoning_effort" not in p for p in fake.chat_payloads("screen_spec"))  # others unchanged
    [call] = [e["data"] for e in events(ws, "liner_chat") if e["data"]["schema"] == "prototype"]
    assert call["reasoning_effort"] == "low"


def test_non_router_model_gets_no_reasoning_effort(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)  # LINER_MODEL=test-model: like liner-mark, not checked with it
    to_cp4(orch, ws)
    assert "reasoning_effort" not in fake.chat_payloads("prototype")[0]


def test_the_developer_is_not_retried_by_the_runner(repo_root: Path, key_env: Path) -> None:
    """S6 runs its own attempts (shorter answer, then the template); a runner retry would double ~300 s cuts."""
    orch, ws, fake = build(repo_root, key_env, {"prototype": [STREAM_ERROR, prototype_output()]})
    to_cp4(orch, ws)
    assert fake.chat_names.count("prototype") == 2 and ws.items("prototype")[-1]["attempts"] == 2
    assert not [e for e in events(ws, "liner_retry") if e["data"]["agent"] == "developer"]
