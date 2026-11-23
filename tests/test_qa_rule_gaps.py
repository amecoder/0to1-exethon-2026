from __future__ import annotations
"""QA also flags missing behaviour rules (value lists, how counts are counted, what one step hands the next,
time boundaries, missing values) — these became the coding AI's most repeated assumptions in mock runs."""

from pathlib import Path

from app.stage_requirements import TASK_QA
from tests.flower_script import qa_findings, src_id
from tests.pipeline_helpers import CHUNKS, build, events


def test_qa_task_names_the_rule_gaps() -> None:
    assert "missing_rule" in TASK_QA
    for words in ("값 목록", "세는지", "다음 단계", "경계", "값이 없을 때"):
        assert words in TASK_QA


def test_a_missing_rule_finding_is_kept_and_reaches_the_coordinator(repo_root: Path, key_env: Path) -> None:
    def findings(payload: dict) -> dict:
        base = qa_findings(CHUNKS)
        pay = src_id(CHUNKS, "매주 자동결제")
        rule = {"type": "missing_rule", "requirement_ids": ["REQ-02"], "source_refs": [pay],
                "note": "결제 재시도 횟수를 0과 1 중 어디부터 세는지 정해지지 않았다"}
        return {"findings": [*base["findings"], rule]}
    orch, ws, fake = build(repo_root, key_env, {"qa_findings": [findings]})
    orch.ingest(CHUNKS)
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    kept = [f for f in ws.items("findings") if f["type"] == "missing_rule"]
    assert kept and "어디부터 세는지" in kept[0]["note"]
    cards_input = fake.chat_payloads("question_cards")[0]["messages"][-1]["content"]
    assert "어디부터 세는지" in cards_input


def test_rule_gaps_come_last_and_are_capped(repo_root: Path, key_env: Path) -> None:
    from app.stage_requirements import MAX_RULE_FINDINGS

    def findings(payload: dict) -> dict:
        pay = src_id(CHUNKS, "매주 자동결제")
        rules = [{"type": "missing_rule", "requirement_ids": ["REQ-02"], "source_refs": [pay], "note": f"규칙 {n}"}
                 for n in range(MAX_RULE_FINDINGS + 2)]
        return {"findings": [rules[0], *qa_findings(CHUNKS)["findings"], *rules[1:]]}
    orch, ws, _ = build(repo_root, key_env, {"qa_findings": [findings]})
    orch.ingest(CHUNKS)
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    kinds = [f["type"] for f in ws.items("findings")]
    assert kinds[:2] == ["conflict", "missing_exception"]  # classic kinds first, whatever order QA used
    assert kinds.count("missing_rule") == MAX_RULE_FINDINGS
