from __future__ import annotations
"""Read-only view of what the client must do next (left pane)."""

from collections.abc import Mapping
from typing import Any

from app import team_defaults
from app.checks import review
from app.decision_status import decision_status
from app.documents import build_documents
from app.orchestrator import STAGES
from app.req_review import review_summary

REVIEWED_CPS = ("CP2", "CP3", "CP4")


def client_todo(source: Mapping[str, Any]) -> dict[str, Any]:
    """What the client does next. While a CP5 change is being reworked, `recheck` says why download is locked."""
    todo = _todo(source)
    recheck = source.get("meta", {}).get("recheck")
    return {**todo, "recheck": recheck} if recheck else todo


def _todo(source: Mapping[str, Any]) -> dict[str, Any]:
    pipeline = source.get("meta", {}).get("pipeline", {"stage": "S1", "status": "awaiting_input"})
    status = pipeline.get("status")
    if status == "awaiting_input":
        return {"kind": "input"}
    if status == "awaiting_confirmation":
        cp = pipeline["stage"]
        todo = {"kind": "confirmation", "cp": cp, "title": STAGES[cp].title}
        if cp == "CP2":
            todo["req_reviews"] = review_summary(source)
        if cp in REVIEWED_CPS:
            docs = build_documents(source) if cp == "CP3" else None
            todo["review"] = review(source, cp, docs)
        if cp == "CP4":
            todo["decision_status"] = decision_status(source)
        return todo
    if status == "awaiting_answers":
        return question_todo(source)
    if status == "completed":
        return {"kind": "download", "decision_status": decision_status(source)}
    if status == "closed":
        return closed_todo(source)
    if status == "awaiting_scope":
        return scope_todo(source)
    if status == "stopped":
        return limit_todo(source, pipeline)
    return {"kind": "none", "status": status}


def closed_todo(source: Mapping[str, Any]) -> dict[str, Any]:
    """CP1 build-or-buy ended the project: which product the client took, and the comparison it came from."""
    chosen = next((d for d in reversed(source.get("decisions", [])) if d.get("kind") == "build_or_buy"), {})
    alts = source.get("alternatives", [])
    return {"kind": "closed", "chosen": chosen.get("chosen"),
            "alternative": next((a for a in alts if a["id"] == chosen.get("alternative_ref")), None)}


def question_todo(source: Mapping[str, Any]) -> dict[str, Any]:
    """The next open card; once every card has an answer, the review list (S4 waits for 「이대로 진행」)."""
    cards = list(source.get("questions", []))
    pending = [q for q in cards if q.get("status") == "pending"]
    if not pending:  # 11-22: and the team's defaults for what the cards did not ask (app/team_defaults.py)
        return {"kind": "answers_review", "questions": cards, "defaults": team_defaults.pending(source)}
    card = pending[0]
    sources = [s for s in source.get("sources", []) if s["id"] in card["source_refs"]]
    evidence = [e for e in source.get("evidence", []) if e["id"] in card["evidence_refs"]]
    return {"kind": "question", "question": card, "remaining": len(pending), "total": len(cards),
            "answered": [q for q in cards if q.get("status") == "answered"],
            "sources": sources, "evidence": evidence}


def scope_todo(source: Mapping[str, Any]) -> dict[str, Any]:
    """G8: which screens to keep. The limit is the one the last G8 flag recorded."""
    flags = [e["data"] for e in source.get("events", []) if e.get("type") == "guardrail"
             and e.get("data", {}).get("id") == "G8" and e["data"].get("outcome") == "flagged"]
    screens = [{k: s.get(k) for k in ("id", "title", "purpose", "requirement_refs")} for s in source.get("screens", [])]
    limit = flags[-1].get("max") if flags else len(screens)
    return {"kind": "scope", "screens": screens, "max": limit}


def limit_todo(source: Mapping[str, Any], pipeline: Mapping[str, Any]) -> dict[str, Any]:
    """G7: the stop card. What was measured comes from the guardrail event, not from an agent."""
    blocks = [e["data"] for e in source.get("events", []) if e.get("type") == "guardrail"
              and e.get("data", {}).get("id") == "G7" and e["data"].get("outcome") == "blocked"]
    last = blocks[-1] if blocks else {}
    return {"kind": "limit", "limit": last.get("limit"), "used": last.get("used"), "max": last.get("max"),
            "stage": pipeline.get("stage"), "message": pipeline.get("error")}
