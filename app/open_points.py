from __future__ import annotations
"""What is still open in a project, counted the same way for every hand-off document.

「미결」 used to mean only items whose status is 미결 — so a bundle could say 「미결 0건」 while a screen said
「가격 미정이라 빈칸」. Here an open point is any of:

- a requirement, screen or test whose status is 미결 or 미확인, and every open item
- a BRD goal without a number to measure it by (status 미결)
- a requirement or screen element whose own text still says 미정 · 빈칸 · 확인 필요 · 결정 필요 · 정해지지 않 (a blank)

Tests, risks and checks that repeat a blank are not counted again: the blank is counted where it is written.
Outside services the requirements lean on (payment provider, push, address search …) are found with the word
list in app/data/integrations.json; a clause that negates the word does not count.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.quality import _load

BLANK_WORDS = ("미정", "빈칸", "확인 필요", "확인이 필요", "결정 필요", "정해지지 않")
OPEN_STATUSES = ("미결", "미확인")
MARKED = ("가정", "미결", "미확인")
KINDS = (("requirements", "요구사항"), ("screens", "화면"), ("tests", "테스트 케이스"))
REQ_TEXT = ("title", "statement", "acceptance", "exceptions")
ELEMENT_TEXT = ("name", "description", "action", "input_rule")
_INTEGRATIONS = _load("integrations.json")
_SENTENCE = re.compile(r"(?<=[.?!])\s+")
_CLAUSE = re.compile(r"[.,;]\s|\n")


def _strings(node: Any) -> Iterable[str]:
    if isinstance(node, Mapping):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)
    elif isinstance(node, str):
        yield node


def blank_sentences(node: Any) -> list[str]:
    """The sentences of a value that carry a blank word, in reading order."""
    return [s.strip() for text in _strings(node) for s in _SENTENCE.split(text) if any(w in s for w in BLANK_WORDS)]


def blanks(view: Mapping[str, Any]) -> list[dict[str, str]]:
    """{id, title, doc, text}: where a blank is written — in-scope requirements (prd) and screen elements (screens)."""
    out = []
    for r in view.get("requirements", []):
        found = blank_sentences({k: r.get(k) for k in REQ_TEXT}) if r.get("status") not in OPEN_STATUSES else []
        if found:
            out.append({"id": r["id"], "title": r.get("title", ""), "doc": "prd", "text": " / ".join(found)})
    for s in view.get("screens", []):
        for e in s.get("elements", []):
            found = blank_sentences({k: e.get(k) for k in ELEMENT_TEXT})
            if found:
                out.append({"id": f"{s['id']}#{e.get('no')}", "title": f"{s.get('title', '')} 화면의 {e.get('name', '')}",
                            "doc": "screens", "text": " / ".join(found)})
    return out


def open_goals(view: Mapping[str, Any]) -> list[str]:
    return [str(g.get("goal", "")) for b in view.get("brd", []) for g in b.get("goals", []) if g.get("status") == "미결"]


def marked_by_kind(view: Mapping[str, Any]) -> dict[str, dict[str, list[str]]]:
    """{requirements|screens|tests: {가정|미결|미확인: ["ID 제목"]}} — each item is named under its own kind only."""
    out: dict[str, dict[str, list[str]]] = {}
    for kind, _ in KINDS:
        out[kind] = {status: [] for status in MARKED}
        for item in view.get(kind, []):
            if item.get("status") in MARKED:
                out[kind][item["status"]].append(f"{item['id']} {item.get('title', '')}".strip())
    return out


def open_counts(view: Mapping[str, Any]) -> dict[str, int]:
    """How many points are open, by reason. `total` is the 미결 number README.txt and the summary state."""
    by_kind = marked_by_kind(view)
    status = sum(len(by_kind[kind][s]) for kind, _ in KINDS for s in OPEN_STATUSES)
    counts = {"status": status, "open_items": len(view.get("open_items", [])), "goals": len(open_goals(view)),
              "blanks": len(blanks(view))}
    return {**counts, "total": sum(counts.values())}


def assumed_counts(view: Mapping[str, Any]) -> dict[str, int]:
    by_kind = marked_by_kind(view)
    return {kind: len(by_kind[kind]["가정"]) for kind, _ in KINDS}


def integrations(view: Mapping[str, Any]) -> list[dict[str, Any]]:
    """[{name, what, refs}]: outside services named by in-scope requirements and screens (not negated)."""
    negations = _INTEGRATIONS["negations"]
    items = [(r["id"], {k: r.get(k) for k in REQ_TEXT}) for r in view.get("requirements", [])]
    items += [(s["id"], [e for e in s.get("elements", []) if not e.get("out_of_scope")]) for s in view.get("screens", [])]
    clauses = [(item_id, c) for item_id, node in items for text in _strings(node) for c in _CLAUSE.split(text)]
    out = []
    for service in _INTEGRATIONS["services"]:
        refs = list(dict.fromkeys(item_id for item_id, c in clauses
                                  if any(w in c for w in service["words"]) and not any(n in c for n in negations)))
        if refs:
            out.append({"name": service["name"], "what": service["what"], "refs": refs})
    return out
