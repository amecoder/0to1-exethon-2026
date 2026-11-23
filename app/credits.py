from __future__ import annotations
"""Liner credit balance readings (free calls) written as system `credits` events.

Read at project start (S1) and after each work stage. G7 can cap money spent (EXETHON_MAX_COST_USD) and the
header shows the spent amount; both come from these events, not from agent reports. Fail-open: when the
credits API cannot be read the reason is logged and the work goes on.
"""

from collections.abc import Mapping
from typing import Any

from app.config import LinerKeyMissingError
from app.limits import spent_usd
from app.liner import LinerAPIError, LinerClient
from app.workspace import SYSTEM, Workspace


def balance_usd(body: Mapping[str, Any]) -> float | None:
    """`balance` is micro-USD (12500000 = $12.50); `balance_usd` is the same as a string."""
    if isinstance(body.get("balance"), int) and not isinstance(body.get("balance"), bool):
        return body["balance"] / 1_000_000
    try:
        return float(body["balance_usd"])
    except (KeyError, TypeError, ValueError):
        return None


def record_balance(ws: Workspace, client: LinerClient, point: str) -> dict[str, Any]:
    try:
        value = balance_usd(client.credits_balance())
        error = None if value is not None else "잔액 응답에 balance 가 없습니다"
    except (LinerAPIError, LinerKeyMissingError) as exc:
        value, error = None, str(exc)
    data = {"point": point, "balance_usd": value, "error": error}
    if error is None:
        data["spent_usd"] = spent_usd([*ws.log.events, {"type": "credits", "data": data}])
    return ws.emit("credits", SYSTEM, data)

