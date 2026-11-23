from __future__ import annotations
"""What approving a confirmation stage does, declared per stage in the flow file (`on_approve`, D6 c 11-20).

Each hook may add values to the confirmation record (`fields`, e.g. the version it creates) and act after the record
is written (`after`). Hooks run in the order the flow file lists them. Confirmation features (`features`) name what
a person can do at that stage beyond approve/reject.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.workspace import SNAPSHOT_KINDS, Workspace


def _none(ws: Workspace) -> dict[str, Any]:
    return {}


def _nothing(ws: Workspace, record: Mapping[str, Any]) -> None:
    return None


@dataclass(frozen=True)
class ApproveHook:
    fields: Callable[[Workspace], dict[str, Any]] = field(default=_none)
    after: Callable[[Workspace, Mapping[str, Any]], None] = field(default=_nothing)


def _next_version(ws: Workspace) -> dict[str, Any]:
    return {"version": f"v{len(ws.items('versions')) + 1}"}


def _snapshot(ws: Workspace, record: Mapping[str, Any]) -> None:
    ws.add_version(record["version"], record["id"], SNAPSHOT_KINDS)


def _bound(ws: Workspace) -> dict[str, Any]:
    """The approval accepts the deliverables of one fixed version; a later version (CP5) needs a new approval."""
    return {"based_on": ws.items("versions")[-1]["version"]} if ws.items("versions") else {}


APPROVE_HOOKS: Mapping[str, ApproveHook] = {
    "snapshot": ApproveHook(fields=_next_version, after=_snapshot),  # a new version (v1 requirements, v2 documents)
    "bind_version": ApproveHook(fields=_bound),
    "clear_recheck": ApproveHook(after=lambda ws, record: ws.clear_recheck()),
    "refresh_problem": ApproveHook(after=lambda ws, record: ws.set_pipeline(refresh_problem=True)),
}
FEATURES = ("build_or_buy", "requirement_review")  # CP1 기존 제품 선택 · CP2 요구사항 카드 검토
