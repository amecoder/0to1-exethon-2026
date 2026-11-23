from __future__ import annotations
"""The single path for agent-to-agent handoffs. Enforces FR-03 relations via can_message."""

from typing import Any

from app.definitions import DefinitionError, TeamDef, can_message
from app.workspace import Workspace


class MessageBus:
    def __init__(self, team: TeamDef, workspace: Workspace) -> None:
        self._team = team
        self._ws = workspace

    def send(self, from_id: str, to_id: str, content: str) -> tuple[dict[str, Any], ...]:
        """Deliver directly along a relation; otherwise relay through the coordinator and record it."""
        if can_message(self._team, from_id, to_id):
            return (self._message(from_id, to_id, content, None),)
        hub = self._team.coordinator
        if hub in (from_id, to_id) or not (can_message(self._team, from_id, hub)
                                          and can_message(self._team, hub, to_id)):
            raise DefinitionError(f"'{from_id}' → '{to_id}' 메시지를 조율자 경유로도 보낼 수 없습니다")
        self._raw("message_rerouted", from_id, {"from": from_id, "to": to_id, "via": hub,
                                                "reason": "관계선 없음 → 조율자 경유"})
        return (self._message(from_id, hub, content, to_id), self._message(hub, to_id, content, from_id))

    def _message(self, from_id: str, to_id: str, content: str, relay: str | None) -> dict[str, Any]:
        data: dict[str, Any] = {"from": from_id, "to": to_id, "content": content}
        if relay is not None:
            data["relay"] = relay
        return self._raw("agent_message", from_id, data)

    def _raw(self, type_: str, actor: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._ws.log._append_raw(type_, actor, data, self._ws.pipeline["stage"])
