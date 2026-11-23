from __future__ import annotations
"""Shared pieces of the four document views: header (P9), change history (P5), blocks, two layers (P1)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.quality import annotate_terms

DRAFT = "작업본(미고정)"
NONE = "—"


@dataclass(frozen=True)
class DocContext:
    """Names that are not in the shared source itself (agent display names, external parties)."""
    agent_names: Mapping[str, str] = field(default_factory=dict)
    externals: tuple[tuple[str, str], ...] = (("client", "human"), ("consumer", "agent"))

    def name(self, agent_id: str) -> str:
        return self.agent_names.get(agent_id, agent_id)


def joined(values: Sequence[Any], sep: str = ", ") -> str:
    text = sep.join(str(v) for v in values if str(v).strip())
    return text or NONE


def table(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> dict[str, Any]:
    return {"type": "table", "columns": list(columns), "rows": [[str(c) for c in row] for row in rows]}


def paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "text": text}


def bullets(items: Sequence[str]) -> dict[str, Any]:
    return {"type": "list", "items": list(items)}


def section(sid: str, title: str, blocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"id": sid, "title": title, "blocks": list(blocks)}


def first(source: Mapping[str, Any], kind: str) -> dict[str, Any]:
    items = source.get(kind) or []
    return dict(items[0]) if items else {}


def approvals(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Approved confirmations that froze a version (CP2 → v1, CP3 → v2)."""
    return [{k: c.get(k) for k in ("id", "cp", "who", "at", "version")}
            for c in source.get("confirmations", []) if c.get("approved") and c.get("version")]


def header(source: Mapping[str, Any], owner: str, ctx: DocContext) -> dict[str, Any]:
    versions = source.get("versions", [])
    return {"owner_agent": owner, "owner_name": ctx.name(owner),
            "version": versions[-1]["version"] if versions else DRAFT, "approvals": approvals(source)}


def history_section(source: Mapping[str, Any], number: str, owner: str, ctx: DocContext) -> dict[str, Any]:
    confirmations = {c["id"]: c for c in source.get("confirmations", [])}
    rows = []
    for v in source.get("versions", []):
        cf = confirmations.get(v.get("confirmation_id"), {})
        rows.append([v["version"], str(v.get("created_at", ""))[:10], ctx.name(owner),
                     f"{cf.get('id', NONE)} ({cf.get('cp', '')} · {cf.get('who', '')})"])
    blocks: list[dict[str, Any]] = [table(["버전", "날짜", "작성", "승인(확인 ID)"], rows)]
    if not rows:
        blocks.append(paragraph("아직 고정된 버전이 없습니다. 확인하면 버전이 생깁니다."))
    return section("history", f"{number}. 변경 이력", blocks)


def make_doc(doc_id: str, title: str, owner: str, source: Mapping[str, Any], ctx: DocContext,
             summary: Sequence[str], sections: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    lines = [s.strip() for s in summary if s.strip()]
    return {"id": doc_id, "title": title, "header": header(source, owner, ctx), "summary": annotate_terms(lines),
            "sections": list(sections), "rule_warnings": [], "warnings": []}
