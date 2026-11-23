from __future__ import annotations
"""The compact brief of the approved change (CP5) that every agent gets while the team reworks it.

Read from the shared source only: meta.recheck names the change; the change item, the decisions it
superseded and the complaint it came from fill the brief. No recheck → no brief.
"""

from collections.abc import Mapping
from typing import Any

BRIEF_KEY = "승인된 변경(CP5)"
BRIEF_KINDS = ("changes", "decisions", "complaints")  # what change_brief() reads besides meta
INSTRUCTION = (
    "이번 작업은 발주사가 CP5 에서 승인한 변경을 반영하는 재작업이다. '바뀐 뒤' 내용을 문서·화면·테스트·프로토타입에 "
    "그대로 반영하고(예: 새로 고를 수 있게 된 선택지는 고를 수 있게 만든다), '바뀌기 전' 내용은 남기지 않는다."
)


def active_change(source: Mapping[str, Any]) -> Mapping[str, Any] | None:
    recheck = source.get("meta", {}).get("recheck") or {}
    change_id = recheck.get("change_id")
    return next((c for c in source.get("changes", []) if c.get("id") == change_id), None) if change_id else None


def superseded(source: Mapping[str, Any], change_id: str) -> list[dict[str, Any]]:
    return [{"id": d["id"], "이전 답": d.get("chosen", ""), "질문": d.get("topic", "")}
            for d in source.get("decisions", []) if d.get("superseded_by") == change_id]


def change_brief(source: Mapping[str, Any]) -> dict[str, Any] | None:
    item = active_change(source)
    if item is None:
        return None
    complaint = next((c for c in source.get("complaints", []) if c.get("id") == item.get("complaint_ref")), None)
    revision = item.get("revision") or {}
    brief = {
        "id": item["id"], "발주사 말": item.get("utterance", ""), "대상 요구사항": item.get("target"),
        "바뀌기 전": item.get("before", ""), "바뀐 뒤": item.get("after", ""), "요약": item.get("summary", ""),
        "대체된 결정": superseded(source, item["id"]),
        "고친 요구사항": [r["id"] for r in revision.get("requirements", [])],
        "지시": INSTRUCTION,
    }
    if complaint is not None:
        brief["이어진 불만"] = {"id": complaint["id"], "발주사 말": complaint.get("text", "")}
    return brief
