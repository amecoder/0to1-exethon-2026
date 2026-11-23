from __future__ import annotations
"""FR-21 impact rule (deterministic). Same rule as eval/validate_golden.sh `close`:

    target REQ + every REQ that (transitively) depends_on it + the screens/tests linked from those REQs.

Lists come back sorted and de-duplicated, like jq's `unique`, so results compare 1:1 with the golden set.
"""

from collections.abc import Mapping, Sequence
from typing import Any

# Who owns which kind of item (PRD 2-5 `writes`). Only these roles need to re-check after a change.
OWNER_BY_KIND = (("requirements", "pm"), ("screens", "designer"), ("tests", "qa"))


def _ids(items: Any) -> list[str]:
    return [str(i) for i in items] if isinstance(items, list) else []


def dependents_closure(requirements: Sequence[Mapping[str, Any]], target: str) -> list[str]:
    known = {str(r["id"]) for r in requirements}
    if target not in known:
        raise KeyError(target)
    closed = {target}
    while True:
        grown = closed | {str(r["id"]) for r in requirements if set(_ids(r.get("depends_on"))) & closed}
        if grown == closed:
            return sorted(closed)
        closed = grown


def impacted(requirements: Sequence[Mapping[str, Any]], target: str) -> dict[str, list[str]]:
    reqs = dependents_closure(requirements, target)
    chosen = [r for r in requirements if str(r["id"]) in reqs]
    return {
        "requirements": reqs,
        "screens": sorted({s for r in chosen for s in _ids(r.get("screens"))}),
        "tests": sorted({t for r in chosen for t in _ids(r.get("tests"))}),
    }


def owners_of(impact: Mapping[str, Sequence[str]]) -> list[dict[str, Any]]:
    """Roles that own an impacted item, in pm → designer → qa order; roles with nothing impacted are left out."""
    return [{"agent": agent, "items": list(impact.get(kind, []))} for kind, agent in OWNER_BY_KIND
            if impact.get(kind)]
