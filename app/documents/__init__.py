from __future__ import annotations
"""FR-09: BRD · PRD · 화면설계서 · 테스트 케이스, all built from the ONE shared source (same ID, same text)."""

from collections.abc import Mapping
from typing import Any

from app.checks import cp_warnings
from app.documents.brd import brd_rule_warnings, build_brd
from app.documents.common import DocContext
from app.documents.markdown import body_markdown, to_markdown
from app.documents.prd import build_prd
from app.documents.screens import build_screens
from app.documents.tests_view import build_tests

__all__ = ["DOC_IDS", "DocContext", "build_documents", "to_markdown"]

DOC_IDS = ("brd", "prd", "screens", "tests")
_BUILDERS = {"brd": build_brd, "prd": build_prd, "screens": build_screens, "tests": build_tests}


def build_documents(source: Mapping[str, Any], ctx: DocContext | None = None) -> dict[str, dict[str, Any]]:
    ctx = ctx or DocContext()
    docs = {doc_id: _BUILDERS[doc_id](source, ctx) for doc_id in DOC_IDS}
    docs["brd"]["rule_warnings"] = brd_rule_warnings(docs["brd"], source, body_markdown(docs["brd"]))
    warnings = cp_warnings(source, "CP3", docs)
    for doc_id, doc in docs.items():
        doc["warnings"] = [w for w in warnings if w["doc"] == doc_id]
    return docs
