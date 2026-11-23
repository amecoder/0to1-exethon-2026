from __future__ import annotations
"""결정 현황: what is settled, what was filled with a default (가정), what is still open (미결).

Two completion levels: 「기획 완료」 = CP4 approved; 「결정 완료」 = CP4 approved and no 가정·미결 left.
"""

from collections.abc import Mapping
from typing import Any

BUCKETS = {"확정": "confirmed", "가정": "assumed", "미결": "open", "미확인": "open"}
PLANNING_DONE = "기획 완료"
DECISION_DONE = "결정 완료"


def _entries(source: Mapping[str, Any]) -> list[tuple[str, dict[str, str]]]:
    rows = [(BUCKETS.get(r.get("status", "")), {"id": r["id"], "title": r.get("title", "")})
            for r in source.get("requirements", [])]
    rows += [(BUCKETS.get(d.get("status", "")), {"id": d["id"], "title": d.get("topic", "")})
             for d in source.get("decisions", [])]
    rows += [("open", {"id": o["id"], "title": o.get("title", "")}) for o in source.get("open_items", [])]
    return [(bucket, item) for bucket, item in rows if bucket]


def cp4_approved(source: Mapping[str, Any]) -> bool:
    records = [c for c in source.get("confirmations", []) if c.get("cp") == "CP4"]
    return bool(records) and records[-1].get("approved") is True


def decision_status(source: Mapping[str, Any]) -> dict[str, Any]:
    items: dict[str, list[dict[str, str]]] = {"confirmed": [], "assumed": [], "open": []}
    for bucket, item in _entries(source):
        items[bucket].append(item)
    planning = cp4_approved(source)
    decided = not items["assumed"] and not items["open"]
    level = (DECISION_DONE if decided else PLANNING_DONE) if planning else None
    return {"counts": {k: len(v) for k, v in items.items()}, "items": items,
            "planning_done": planning, "decision_done": planning and decided, "level": level}
