from __future__ import annotations
"""What the hand-off documents are rendered from: the shared source with the client's scope cut applied.

When the client narrows the screens (G8), the scope decision records the screens kept and the requirements
that lost every screen (`dropped_requirements`). The source itself keeps everything (it is the record); this
view is what a builder may read, so that no document tells a reader to build what was cut:

- dropped requirements leave `requirements` and are listed once under `out_of_scope`
- a test that only checks dropped requirements, or that needs a dropped screen, moves to `out_of_scope.tests`
- an element that leads to a dropped screen is flagged `out_of_scope` and says so in its action
- a lane step on a dropped screen is flagged `out_of_scope`
- every other mention of a dropped ID in the text gets the mark 「(범위 밖)」
- an ID written with extra zeros (TC-014 for TC-14) is rewritten to the ID the source has

A scope decision whose kept screens are no longer the current screens (screens redrawn after a change) is stale
and ignored. Rendering a view again gives the same view.
"""

import re
from collections.abc import Mapping, Set
from typing import Any

from app.korean import josa

MARK = "(범위 밖)"
ID_PREFIXES = {"REQ": "requirements", "SCR": "screens", "TC": "tests", "DEC": "decisions", "SRC": "sources",
               "EV": "evidence", "FND": "findings", "Q": "questions", "ALT": "alternatives", "SYS": "systems"}
TEXT_KINDS = ("requirements", "screens", "tests", "test_plan", "brd", "prd", "screen_spec", "problem_statement",
              "scope", "decisions", "findings", "open_items")
KEEP_KEYS = ("id", "screens_kept", "dropped_requirements", "id_map", "owner_agent", "status", "kind")
TEST_TEXT = ("title", "objective", "preconditions", "inputs", "steps", "expected")
_ID_GROUP = re.compile(r"(?<![A-Za-z0-9/])([A-Z]{1,5})-(\d{1,4})((?:·\d{2,4}(?![\d-]))*)")


def scope_decision(source: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The latest scope decision, if its kept screens are still the screens of the source."""
    found = next((d for d in reversed(source.get("decisions", [])) if d.get("kind") == "scope"), None)
    current = {s["id"] for s in source.get("screens", [])}
    return found if found and set(found.get("screens_kept") or []) == current else None


def dropped_screens(source: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, str]:
    """{screen ID: title} of the screens that were drawn but not kept (titles in the order the client saw them)."""
    spec = (source.get("screen_spec") or [{}])[0]
    kept = set(decision.get("screens_kept") or [])
    ids = [sid for sid in dict.fromkeys((spec.get("id_map") or {}).values()) if sid not in kept]
    titles = list(decision.get("rejected") or [])
    return {sid: (titles[i] if len(titles) == len(ids) else "") for i, sid in enumerate(ids)}


def known_ids(source: Mapping[str, Any]) -> set[str]:
    return {str(i["id"]) for kind in ID_PREFIXES.values() for i in source.get(kind, [])
            if isinstance(i, Mapping) and i.get("id")}


def fix_ids(text: str, dropped: Set[str], known: Set[str]) -> str:
    """Mark dropped IDs and rewrite zero-padded IDs. 「REQ-12·14」 is read as REQ-12 and REQ-14."""
    everything = known | dropped

    def canonical(prefix: str, number: str) -> str:
        short = f"{prefix}-{int(number):02d}"
        return short if f"{prefix}-{number}" not in everything and short in everything else f"{prefix}-{number}"

    def replace(m: re.Match[str]) -> str:
        prefix, first = m.group(1), m.group(2)
        if prefix not in ID_PREFIXES:
            return m.group(0)
        numbers = [first, *[n.zfill(len(first)) for n in m.group(3).split("·") if n]]
        ids = [canonical(prefix, n) for n in numbers]
        cut = [i in dropped for i in ids]
        marked = m.string[m.end():].startswith(MARK)
        if not any(cut) or marked:
            return "·".join([ids[0], *[i.split("-")[1] for i in ids[1:]]])
        if all(cut):
            return "·".join([ids[0], *[i.split("-")[1] for i in ids[1:]]]) + MARK
        return "·".join(i + (MARK if c else "") for i, c in zip(ids, cut))

    return _ID_GROUP.sub(replace, text)


def _fixed(node: Any, dropped: Set[str], known: Set[str]) -> Any:
    if isinstance(node, Mapping):
        return {k: (v if k in KEEP_KEYS else _fixed(v, dropped, known)) for k, v in node.items()}
    if isinstance(node, list):
        return [_fixed(v, dropped, known) for v in node]
    return fix_ids(node, dropped, known) if isinstance(node, str) else node


def _mentions(node: Any, ids: Set[str]) -> list[str]:
    """Dropped IDs named anywhere in a value (marked or not), in reading order."""
    if isinstance(node, Mapping):
        return [i for v in node.values() for i in _mentions(v, ids)]
    if isinstance(node, list):
        return [i for v in node for i in _mentions(v, ids)]
    if not isinstance(node, str):
        return []
    found = []
    for m in _ID_GROUP.finditer(node):
        numbers = [m.group(2), *[n.zfill(len(m.group(2))) for n in m.group(3).split("·") if n]]
        found += [f"{m.group(1)}-{n}" for n in numbers if f"{m.group(1)}-{n}" in ids]
    return found


def _name(screens: Mapping[str, str], sid: str) -> str:
    return f"{sid}{MARK} {screens.get(sid, '')}".strip()


def _split_tests(tests: list[dict[str, Any]], reqs: Set[str], screens: Mapping[str, str]
                 ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept, parked = [], []
    for t in tests:
        refs = [r.removesuffix(MARK) for r in t.get("requirement_refs", [])]
        needs = list(dict.fromkeys(_mentions({k: t.get(k) for k in (*TEST_TEXT, "screen_refs")}, set(screens))))
        if refs and all(r in reqs for r in refs):
            parked.append({**t, "reason": f"확인하는 요구사항 {', '.join(r + MARK for r in refs)}만 보는 테스트다"})
        elif needs:
            names = ", ".join(_name(screens, s) for s in needs)
            parked.append({**t, "reason": f"{josa(f'필요한 화면 {names}', '이/가')} 이번 범위에 없다. 그 화면이 생긴 뒤에 실행한다"})
        else:
            kept.append(t)
    return kept, parked


def _cut_elements(screens: list[dict[str, Any]], dropped: Mapping[str, str]) -> list[dict[str, Any]]:
    """Flag the elements that lead to a dropped screen; returns what was flagged."""
    cut = []
    for screen in screens:
        for e in screen.get("elements", []):
            targets = list(dict.fromkeys(_mentions(e.get("action", ""), set(dropped))))
            if not targets:
                continue
            names = ", ".join(_name(dropped, s) for s in targets)
            e.update(out_of_scope=True,
                     action=f"이번 버전에서는 이 요소를 넣지 않는다. {josa(f'눌러서 가는 화면 {names}', '이/가')} 이번 범위에 없다")
            cut.append({"screen": screen["id"], "no": e.get("no"), "name": e.get("name", ""), "target": names})
    return cut


def scope_view(source: Mapping[str, Any]) -> dict[str, Any]:
    """The source as the hand-off documents may read it (see the module text). Never changes `source`."""
    if "out_of_scope" in source:  # already a view
        return dict(source)
    decision = scope_decision(source)
    reqs = set(decision.get("dropped_requirements") or []) if decision else set()
    screens = dropped_screens(source, decision) if decision else {}
    dropped, known = reqs | set(screens), known_ids(source)
    view = {k: (_fixed(v, dropped, known) if k in TEXT_KINDS else v) for k, v in source.items()}
    out: dict[str, Any] = {"decision": decision["id"] if decision else None,
                           "requirements": [r for r in view.get("requirements", []) if r["id"] in reqs],
                           "screens": [{"id": sid, "title": title} for sid, title in screens.items()],
                           "tests": [], "elements": []}
    if dropped:
        view["requirements"] = [r for r in view.get("requirements", []) if r["id"] not in reqs]
        view["tests"], out["tests"] = _split_tests(view.get("tests", []), reqs, screens)
        gone = {t["id"] for t in out["tests"]}
        view["requirements"] = [{**r, "tests": [t for t in r.get("tests", []) if t not in gone]}
                                for r in view["requirements"]]
        out["elements"] = _cut_elements(view.get("screens", []), screens)
        for spec in view.get("screen_spec", []):
            for step in (spec.get("swimlane") or {}).get("steps", []):
                if str(step.get("screen_ref") or "").removesuffix(MARK) in screens:
                    step["out_of_scope"] = True
    return {**view, "out_of_scope": out}


def has_cut(view: Mapping[str, Any]) -> bool:
    out = view.get("out_of_scope") or {}
    return any(out.get(k) for k in ("requirements", "screens", "tests", "elements"))
