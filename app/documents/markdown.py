from __future__ import annotations
"""Render a document view (JSON) as Markdown. Reused by the later zip download (FR-14)."""

from collections.abc import Mapping, Sequence
from typing import Any


def _cell(value: Any) -> str:
    return " ".join(str(value).replace("|", "\\|").split())


def md_table(block: Mapping[str, Any]) -> list[str]:
    columns: Sequence[str] = block["columns"]
    lines = [f"| {' | '.join(_cell(c) for c in columns)} |", f"|{'|'.join('---' for _ in columns)}|"]
    lines += [f"| {' | '.join(_cell(c) for c in row)} |" for row in block["rows"]]
    return lines + ([] if block["rows"] else ["", "_항목 없음_"])


def md_block(block: Mapping[str, Any]) -> list[str]:
    kind = block["type"]
    if kind == "table":
        return md_table(block)
    if kind == "paragraph":
        return [block["text"]]
    if kind == "list":
        return [f"- {item}" for item in block["items"]]
    if kind == "screen":
        lines = [f"![{block['id']} 와이어프레임]({block['wireframe_path']})", ""]
        if block.get("purpose"):
            lines += [f"목적: {block['purpose']}", ""]
        return lines + md_table(block["elements"]) + [""] + md_table(block["states"])
    raise ValueError(f"unknown block type: {kind}")


def header_lines(header: Mapping[str, Any]) -> list[str]:
    approvals = [f"{a['id']} ({a['cp']} · {a['who']} · {str(a.get('at', ''))[:10]} · {a['version']})"
                 for a in header.get("approvals", [])]
    return [f"> 작성 책임 에이전트: {header['owner_name']} · 버전: {header['version']}  ",
            f"> 승인 기록: {', '.join(approvals) if approvals else '아직 없음'}"]


def body_lines(doc: Mapping[str, Any], skip: Sequence[str] = ()) -> list[str]:
    summary = doc.get("summary") or ["(아직 요약이 없습니다)"]
    lines = ["## 한눈에 보기", *[part for line in summary for part in ("", line)]]
    for sec in doc["sections"]:
        if sec["id"] in skip:
            continue
        lines += ["", f"## {sec['title']}"]
        for block in sec["blocks"]:
            lines += ["", *md_block(block)]
    return lines


def body_markdown(doc: Mapping[str, Any]) -> str:
    """Document body without header and change history (used for the BRD length rule)."""
    return "\n".join(body_lines(doc, skip=("history",)))


def to_markdown(doc: Mapping[str, Any]) -> str:
    lines = [f"# {doc['title']}", "", *header_lines(doc["header"]), "", *body_lines(doc)]
    warnings = doc.get("warnings") or []
    if warnings:
        lines += ["", f"## 검사 경고 ({len(warnings)})", ""]
        lines += [f"- [{w['target']}] {w['message']}" for w in warnings]
    return "\n".join(lines) + "\n"
