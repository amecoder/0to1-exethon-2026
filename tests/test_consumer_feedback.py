from __future__ import annotations
"""FR-20: the consumer agent comments on the screen specs (before CP3) and the prototype (before CP4).

Opinion only (PRD Q8 → "의견만, PM 이 정한다"): feedback is linked to SCR ids, shown at info level and
never blocks approval or writes requirements. The consumer talks to the coordinator only.
"""

from pathlib import Path

from app.checks import review
from tests.pipeline_helpers import CP3_WAIVERS, build, events, to_cp3, to_cp4


def test_consumer_reviews_screens_before_cp3(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp3(orch, ws)
    assert fake.chat_names[-1] == "consumer_feedback"
    items = ws.items("feedback")
    assert [i["screen_id"] for i in items] == ["SCR-01", "SCR-02"]
    assert {i["cp"] for i in items} == {"CP3"} and {i["owner_agent"] for i in items} == {"consumer"}
    assert any(e["data"]["ref"] == "SCR-99" for e in events(ws, "ref_dropped"))
    payload = fake.chat_payloads("consumer_feedback")[0]["messages"][-1]["content"]
    assert '"screens"' in payload and '"requirements"' not in payload


def test_feedback_is_info_on_the_card_and_does_not_block(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    r = review(ws.source, "CP3")
    assert [f["screen_id"] for f in r["consumer_feedback"]] == ["SCR-01", "SCR-02"]
    assert not any("feedback" in w["code"] for w in r["blocking"] + r["waivable"])
    orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)  # approvable exactly as before


def test_consumer_talks_only_with_the_coordinator(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    pairs = {(m["data"]["from"], m["data"]["to"]) for m in events(ws, "agent_message")
             if "consumer" in (m["data"]["from"], m["data"]["to"])}
    assert pairs == {("coordinator", "consumer"), ("consumer", "coordinator")}
    assert not [e for e in events(ws, "message_rerouted") if "consumer" in (e["data"]["from"], e["data"]["to"])]


def test_consumer_cannot_write_requirements(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp3(orch, ws)
    before = ws.items("requirements")
    assert ws.write("consumer", "requirements", {"id": "REQ-01", "title": "고객이 바꿈"}) is False
    assert ws.items("requirements") == before
    assert events(ws, "write_rejected")[-1]["actor"] == "consumer"


def test_consumer_reviews_prototype_before_cp4(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp4(orch, ws)
    assert fake.chat_names.count("consumer_feedback") == 2
    cp4 = [i for i in ws.items("feedback") if i["cp"] == "CP4"]
    assert cp4 and cp4[0]["target"] == "prototype"
    assert [f["cp"] for f in review(ws.source, "CP4")["consumer_feedback"]] == ["CP4"] * len(cp4)
    assert '"prototype"' in fake.chat_payloads("consumer_feedback")[1]["messages"][-1]["content"]


def test_consumer_failure_does_not_stop_the_stage(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, {"consumer_feedback": ["이건 JSON 이 아님"]})
    to_cp3(orch, ws)
    assert (ws.pipeline["stage"], ws.pipeline["status"]) == ("CP3", "awaiting_confirmation")
    assert ws.items("feedback") == ()
    checks = [e["data"] for e in events(ws, "check_result") if e["data"]["check"] == "consumer_feedback"]
    assert checks and checks[-1]["outcome"] == "failed"


def test_rework_replaces_only_that_checkpoints_feedback(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    orch.confirm("CP4", False, "발주사", "결제 안내 문구를 더 쉽게")
    orch.advance()
    by_cp = [i["cp"] for i in ws.items("feedback")]
    assert by_cp.count("CP3") == 2 and by_cp.count("CP4") == 1
    assert len({i["id"] for i in ws.items("feedback")}) == len(by_cp)
