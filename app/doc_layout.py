from __future__ import annotations
"""What the Word and PDF documents share (11-22): which blocks a document has, its cover lines, and when a page
turns sideways."""

from collections.abc import Mapping
from typing import Any

from app.documents.markdown import header_lines

WIDE_COLUMNS = 6  # 제안: a table with more columns than this does not fit an upright A4 page
EMPTY_ROWS = "항목 없음"


def cover_lines(doc: Mapping[str, Any]) -> list[str]:
    """The author / version / approval lines of the Markdown header, without the quote marks."""
    return [line.removeprefix("> ").rstrip() for line in header_lines(doc["header"])]


def tables_of(doc: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for sec in doc["sections"]:
        for block in sec["blocks"]:
            if block["type"] == "table":
                out.append(block)
            elif block["type"] == "screen":
                out += [block["elements"], block["states"]]
    return out


def is_wide(doc: Mapping[str, Any]) -> bool:
    return any(len(t["columns"]) > WIDE_COLUMNS for t in tables_of(doc))


def warning_lines(doc: Mapping[str, Any]) -> list[str]:
    return [f"[{w['target']}] {w['message']}" for w in doc.get("warnings") or []]
