from __future__ import annotations
"""D5 (Fable 5.2 decision, 11-20): the round cap stays 8 cards and the prompt stays; over the cap, code decides
what stays — cards on a conflict first, then exceptions, acceptance, rules — and keeps the given order."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.definitions import load_definitions
from app.stage_common import FIRST_ROUND_MAX_CARDS
from app.stage_requirements import record_cards
from app.store import empty_source
from app.workspace import Workspace


def ctx_with(repo_root: Path, kinds: list[str]) -> Any:
    agents, _ = load_definitions(repo_root)
    ws = Workspace(empty_source(), agents)
    for n, kind in enumerate(kinds, start=1):
        ws.write("qa", "findings", {"id": f"FND-{n:02d}", "type": kind, "note": f"지적 {n}",
                                    "requirement_ids": [], "source_refs": []})
    return SimpleNamespace(ws=ws)


def card(n: int) -> dict[str, Any]:
    return {"question": f"질문 {n}", "why": "", "options": ["가", "나"], "default_option": "가",
            "source_refs": [], "evidence_refs": [], "finding_refs": [f"FND-{n:02d}"], "requirement_refs": []}


def test_a_usual_round_of_findings_is_asked_in_full(repo_root: Path) -> None:
    """11-22 user decision: blanks are filled by asking, not left for CP3 — the cap only stops a runaway round."""
    ctx = ctx_with(repo_root, ["missing_rule"] * 28)  # the most findings a real run has had (17~28)
    assert FIRST_ROUND_MAX_CARDS == 30
    assert record_cards(ctx, [card(n) for n in range(1, 29)]) == 28
    assert not ctx.ws.items("open_items")


def test_conflict_cards_stay_when_the_round_is_over_the_cap(repo_root: Path) -> None:
    cap = FIRST_ROUND_MAX_CARDS
    ctx = ctx_with(repo_root, ["missing_rule"] * cap + ["conflict"] * 2)
    assert record_cards(ctx, [card(n) for n in range(1, cap + 3)]) == cap
    asked = [q["question"] for q in ctx.ws.items("questions")]
    assert asked == [f"질문 {n}" for n in (*range(1, cap - 1), cap + 1, cap + 2)]  # the order they were given
    over = [o["title"] for o in ctx.ws.items("open_items") if o["reason"] == "이번 회차 카드 수 상한 초과"]
    assert over == [f"질문 {cap - 1}", f"질문 {cap}"]


def test_under_the_cap_nothing_changes(repo_root: Path) -> None:
    ctx = ctx_with(repo_root, ["missing_rule", "conflict", "missing_exception", "missing_rule", "conflict"])
    assert record_cards(ctx, [card(n) for n in range(1, 6)]) == 5
    assert [q["question"] for q in ctx.ws.items("questions")] == [f"질문 {n}" for n in range(1, 6)]
    assert [q["id"] for q in ctx.ws.items("questions")] == [f"Q-{n:02d}" for n in range(1, 6)]
    assert ctx.ws.items("open_items") == ()


def test_a_code_made_card_still_takes_a_place(repo_root: Path) -> None:
    cap = FIRST_ROUND_MAX_CARDS
    ctx = ctx_with(repo_root, ["missing_rule"] * (cap + 1))
    assert record_cards(ctx, [card(n) for n in range(1, cap + 2)], taken=1) == cap - 1
