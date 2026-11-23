from __future__ import annotations
"""CP2 card-by-card review: the client marks each requirement 확정 (ok) or leaves a 고칠 점 (fix) note.

Marks live in meta.req_reviews keyed by requirement id, each with a signature of the requirement's
content. After a rework (S4 again) a requirement whose content changed has a stale mark and must be
looked at again; an unchanged one keeps its 확정. Notes go back to the PM as one rework instruction.
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

VERDICTS = ("ok", "fix")
NOTE_MAX = 300


def signature(req: Mapping[str, Any]) -> str:
    """What the client actually read: title, sentence, done-when and exceptions."""
    body = {k: req.get(k) for k in ("title", "statement", "acceptance", "exceptions")}
    return hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def current_reviews(source: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Marks that still apply: the requirement exists and its content is what was reviewed."""
    stored = (source.get("meta") or {}).get("req_reviews") or {}
    reqs = {r["id"]: r for r in source.get("requirements", [])}
    return {rid: dict(mark) for rid, mark in stored.items()
            if rid in reqs and mark.get("sig") == signature(reqs[rid])}


def review_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    """Per requirement: ok / fix (+note) / open; counts for the deck header."""
    marks = current_reviews(source)
    items = [{"id": r["id"], "verdict": marks.get(r["id"], {}).get("verdict"), "note": marks.get(r["id"], {}).get("note")}
             for r in source.get("requirements", [])]
    count = {v: sum(1 for i in items if i["verdict"] == v) for v in VERDICTS}
    return {"items": items, "ok": count["ok"], "fix": count["fix"],
            "open": sum(1 for i in items if i["verdict"] is None), "total": len(items)}


def fix_lines(source: Mapping[str, Any]) -> list[str]:
    """One line per requirement with a 고칠 점 note: 「REQ-02 「title」: note」."""
    reqs = {r["id"]: r for r in source.get("requirements", [])}
    return [f"{rid} 「{reqs[rid].get('title', '')}」: {mark['note']}"
            for rid, mark in current_reviews(source).items() if mark.get("verdict") == "fix" and mark.get("note")]


def fixes_text(source: Mapping[str, Any]) -> str | None:
    """The rework instruction for the PM (the confirmation record keeps only the client's lines)."""
    lines = fix_lines(source)
    if not lines:
        return None
    return ("발주사가 요구사항 카드마다 남긴 고칠 점이다. 적힌 요구사항만 고치고, 나머지는 문구를 바꾸지 마라.\n"
            + "\n".join(f"- {line}" for line in lines))
