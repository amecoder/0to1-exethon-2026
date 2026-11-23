from __future__ import annotations
"""「같은 앱에 넣을까요?」: when the team builds a request into a service the company already built with 0to1 but
the memo never said so, the client is asked (a code-made question card) before the requirements are fixed."""

from pathlib import Path
from typing import Any

from app.placement import SEPARATE
from tests.flower_script import candidates, final_requirements, problem_scope, src_id
from tests.test_orchestrator import CHUNKS, build

SERVICE = {"name": "꽃님 정기구독", "features": [{"id": "REQ-01", "title": "정기구독 신청"}]}
FIT = {"system_ref": "SYS-01", "fit": "기능 추가", "what": "정기구독 앱에 기능을 더한다",
       "refs": [src_id(CHUNKS, "일주일에 한 번")], "quote": "일주일에 한 번"}


def tagged(out: dict[str, Any]) -> dict[str, Any]:
    first = {**out["requirements"][0], "system_refs": ["SYS-01"], "change": "기능 추가"}
    return {**out, "requirements": [first, *out["requirements"][1:]]}


def to_s3(repo_root: Path, key_env: Path, placement: list[dict[str, Any]], services: list[dict[str, Any]] | None = None):
    scope = {**problem_scope(CHUNKS), "system_fit": [FIT], "placement": placement}
    orch, ws, fake = build(repo_root, key_env, {"problem_scope": [scope], "requirement_candidates": [tagged(candidates(CHUNKS))],
                                                "requirements_final": [lambda payload: tagged(final_requirements(CHUNKS)(payload))]})
    orch.ingest(CHUNKS, services=[SERVICE] if services is None else services)
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    return orch, ws, fake


def placement_cards(ws: Any) -> list[dict[str, Any]]:
    return [q for q in ws.items("questions") if q.get("kind") == "placement"]


def test_a_service_the_memo_never_named_is_asked_about(repo_root: Path, key_env: Path) -> None:
    _, ws, fake = to_s3(repo_root, key_env, placement=[])
    (card,) = placement_cards(ws)
    assert card["system_ref"] == "SYS-01" and "꽃님 정기구독" in card["question"]
    assert card["options"] == ["「꽃님 정기구독」 안에 넣는다", SEPARATE]
    assert card["requirement_refs"] == ["REQ-01"]
    schema = fake.chat_payloads("problem_scope")[0]["response_format"]["json_schema"]["schema"]
    assert "placement" in schema["properties"]


def test_a_service_the_memo_named_is_not_asked_about(repo_root: Path, key_env: Path) -> None:
    named = [{"system_ref": "SYS-01", "refs": [src_id(CHUNKS, "일주일에 한 번")], "quote": "일주일에 한 번"}]
    _, ws, _ = to_s3(repo_root, key_env, placement=named)
    assert placement_cards(ws) == []
    assert ws.items("scope")[0]["placement"][0]["status"] == "확인"


def test_a_naming_quote_not_in_the_memo_does_not_count(repo_root: Path, key_env: Path) -> None:
    made_up = [{"system_ref": "SYS-01", "refs": [src_id(CHUNKS, "일주일에 한 번")], "quote": "정기구독 앱에 넣어 주세요"}]
    _, ws, _ = to_s3(repo_root, key_env, placement=made_up)
    assert len(placement_cards(ws)) == 1


def test_choosing_to_build_separately_unlinks_the_service(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = to_s3(repo_root, key_env, placement=[])
    for q in ws.items("questions"):
        orch.answer(q["id"], "choice", SEPARATE if q.get("kind") == "placement" else q["options"][0])
    orch.submit_answers()
    orch.advance()
    first = ws.items("requirements")[0]
    assert first["system_refs"] == [] and first["change"] == "신규"
    (dec,) = [d for d in ws.items("decisions") if d.get("kind") == "placement"]
    assert dec["chosen"] == SEPARATE and dec["system_ref"] == "SYS-01"
    assert ws.pipeline["stage"] == "CP2"  # the answer is not a sentence the requirements must repeat


def test_without_a_built_service_nothing_changes(repo_root: Path, key_env: Path) -> None:
    _, ws, fake = to_s3(repo_root, key_env, placement=[], services=[])
    assert placement_cards(ws) == []
    schema = fake.chat_payloads("problem_scope")[0]["response_format"]["json_schema"]["schema"]
    assert "placement" not in schema["properties"]


def test_a_placement_card_refuses_free_text(repo_root: Path, key_env: Path) -> None:
    import pytest
    from app.errors import PipelineStateError
    orch, ws, _ = to_s3(repo_root, key_env, placement=[])
    (card,) = placement_cards(ws)
    with pytest.raises(PipelineStateError, match="고른 답"):
        orch.answer(card["id"], "free_text", "아무 데나 넣어 주세요")
    assert ws.get("questions", card["id"])["status"] == "pending"
