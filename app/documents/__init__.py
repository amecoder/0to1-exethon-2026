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
from app.scope_view import MARK, fix_ids, known_ids, scope_view

__all__ = ["DOC_IDS", "DocContext", "build_documents", "to_markdown"]

DOC_IDS = ("brd", "prd", "screens", "tests")
_BUILDERS = {"brd": build_brd, "prd": build_prd, "screens": build_screens, "tests": build_tests}


def build_documents(source: Mapping[str, Any], ctx: DocContext | None = None) -> dict[str, dict[str, Any]]:
    """The four document views. They read the scoped view (what the client cut is listed once, not built);
    the CP3 checks still read the source itself, so approval rules do not change."""
    ctx = ctx or DocContext()
    view = scope_view(source)
    docs = {doc_id: _BUILDERS[doc_id](view, ctx) for doc_id in DOC_IDS}
    docs["brd"]["rule_warnings"] = brd_rule_warnings(docs["brd"], view, body_markdown(docs["brd"]))
    cut = {r["id"] for r in view["out_of_scope"]["requirements"]}
    dropped, known = cut | {s["id"] for s in view["out_of_scope"]["screens"]}, known_ids(source)
    warnings = [{**w, "message": fix_ids(str(w["message"]), dropped, known)}
                for w in cp_warnings(source, "CP3", docs) if w["target"] not in cut]
    for doc_id, doc in docs.items():
        doc["warnings"] = [{**w, "target": w["target"] + (MARK if w["target"] in dropped else "")}
                           for w in warnings if w["doc"] == doc_id]
    return docs
