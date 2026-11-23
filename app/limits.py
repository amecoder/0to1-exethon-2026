from __future__ import annotations
"""FR-23 G7 (Liner calls per project, elapsed time per work stage) and G8 (screens per project).

All three defaults are 제안 (provisional): no real Liner latency has been measured yet (PRD R5).
Override them in .env or the process env:
    EXETHON_MAX_LINER_CALLS    (default 60  — the fake flower run uses about 15 calls)
    EXETHON_MAX_STAGE_SECONDS  (default 600 — 10 minutes per work stage)
    EXETHON_MAX_SCREENS        (default 5   — the G8 example in the team-relations doc)
    EXETHON_MAX_COST_USD       (default off — money spent per project, from Liner credit balance reads)

Judged from the event log only (system records, not agent reports): every Liner call event (CALL_EVENTS)
counts as one call, `credits` events (system balance reads, app/credits.py) give the money spent, `stage_started` gives the stage clock, and a G7 `resumed` guardrail event (the client pressed
「계속」) allows `max_calls` more calls from that point and restarts the stage clock.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import read_env
from app.tools import CALL_EVENTS  # the registry decides what G7 counts (re-exported)

DEFAULT_MAX_LINER_CALLS = 60  # 제안
DEFAULT_MAX_STAGE_SECONDS = 600  # 제안
DEFAULT_MAX_SCREENS = 5  # 제안
BUDGET_MODE_SHARE = 0.6  # 제안: from 60% of the cost budget every router call asks for the cheap model
# Typical cost (USD) of each work stage, measured on one real run on 2026-11-16 (balance differences).
# A CP5 change rework (S5+S6 again) measured $3.58 on the same day. Used to stop a stage before it starts.
STAGE_TYPICAL_COST_USD = {"S2": 0.34, "S3": 0.60, "S4": 0.40, "S5": 2.48, "S6": 0.88}


class LimitReachedError(RuntimeError):
    """G7: the next Liner call would exceed a limit. Carries what was measured."""

    def __init__(self, limit: str, used: float, maximum: float, stage: str, predicted: float | None = None) -> None:
        super().__init__(f"G7 {limit} limit reached ({used}/{maximum}) at {stage}")
        self.limit = limit
        self.used = used
        self.maximum = maximum
        self.stage = stage
        self.predicted = predicted  # set when a stage was stopped before it started (its typical cost)


def _int_setting(name: str, default: int, env_file: Path | None) -> int:
    raw = read_env(name, env_file)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} 는 0 이상의 정수여야 합니다 (지금 값: {raw!r})") from None
    if value < 0:
        raise ValueError(f"{name} 는 0 이상의 정수여야 합니다 (지금 값: {raw!r})")
    return value


def _cost_setting(env_file: Path | None) -> float | None:
    raw = read_env("EXETHON_MAX_COST_USD", env_file)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"EXETHON_MAX_COST_USD 는 0 보다 큰 숫자(달러)여야 합니다 (지금 값: {raw!r})") from None
    if value <= 0:
        raise ValueError(f"EXETHON_MAX_COST_USD 는 0 보다 큰 숫자(달러)여야 합니다 (지금 값: {raw!r})")
    return value


@dataclass(frozen=True)
class Limits:
    max_calls: int = DEFAULT_MAX_LINER_CALLS
    max_stage_seconds: int = DEFAULT_MAX_STAGE_SECONDS
    max_screens: int = DEFAULT_MAX_SCREENS
    max_cost_usd: float | None = None  # off unless EXETHON_MAX_COST_USD is set

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Limits:
        return cls(
            max_calls=_int_setting("EXETHON_MAX_LINER_CALLS", DEFAULT_MAX_LINER_CALLS, env_file),
            max_stage_seconds=_int_setting("EXETHON_MAX_STAGE_SECONDS", DEFAULT_MAX_STAGE_SECONDS, env_file),
            max_screens=max(1, _int_setting("EXETHON_MAX_SCREENS", DEFAULT_MAX_SCREENS, env_file)),
            max_cost_usd=_cost_setting(env_file),
        )


def _g7(event: Mapping[str, Any], outcome: str) -> bool:
    data = event.get("data", {})
    return event.get("type") == "guardrail" and data.get("id") == "G7" and data.get("outcome") == outcome


def calls_used(events: Iterable[Mapping[str, Any]]) -> int:
    return sum(1 for e in events if e.get("type") in CALL_EVENTS)


def calls_allowed(events: Iterable[Mapping[str, Any]], limits: Limits) -> int:
    """`max_calls` in total; after the latest 「계속」 on the call cap, `max_calls` more from that point."""
    used = 0
    allowed = limits.max_calls
    for e in events:
        if e.get("type") in CALL_EVENTS:
            used += 1
        elif _g7(e, "resumed") and e["data"].get("limit") == "calls":
            allowed = used + limits.max_calls
    return allowed


def spent_usd(events: Iterable[Mapping[str, Any]]) -> float:
    """First recorded balance minus the latest one (0 when fewer than two readings)."""
    readings = [float(e["data"]["balance_usd"]) for e in events
                if e.get("type") == "credits" and isinstance(e.get("data", {}).get("balance_usd"), (int, float))]
    return round(max(0.0, readings[0] - readings[-1]), 6) if len(readings) >= 2 else 0.0


def cost_allowed(events: tuple[Mapping[str, Any], ...], limits: Limits) -> float | None:
    """`max_cost_usd` in total; after the latest 「계속」 on the cost cap, that much more from that point."""
    if limits.max_cost_usd is None:
        return None
    allowed = limits.max_cost_usd
    for i, e in enumerate(events):
        if _g7(e, "resumed") and e["data"].get("limit") == "cost":
            allowed = spent_usd(events[: i + 1]) + limits.max_cost_usd
    return allowed


def budget_mode_switched(events: Iterable[Mapping[str, Any]]) -> bool:
    """The one G7 `flagged` event that turned budget mode on is in the log."""
    return any(_g7(e, "flagged") and e["data"].get("limit") == "budget_mode" for e in events)


def budget_mode_due(events: tuple[Mapping[str, Any], ...], limits: Limits) -> bool:
    """Measured spend reached BUDGET_MODE_SHARE of the cost budget (never without a budget)."""
    budget = cost_allowed(events, limits)
    return budget is not None and spent_usd(events) >= BUDGET_MODE_SHARE * budget


def predict_stage(events: tuple[Mapping[str, Any], ...], stage: str, limits: Limits) -> None:
    """Raise LimitReachedError (cost, with `predicted`) when spent + the stage's typical cost would pass the
    budget. Skipped without a budget, for stages without a measured cost, and after a 「계속」 that came after
    the latest stage start (the client chose to run it anyway; the regular cost check still applies)."""
    budget = cost_allowed(events, limits)
    typical = STAGE_TYPICAL_COST_USD.get(stage)
    if budget is None or typical is None:
        return
    for e in reversed(events):
        if e.get("type") == "stage_started":
            break
        if _g7(e, "resumed"):
            return
    spent = spent_usd(events)
    if spent + typical > budget:
        raise LimitReachedError("cost", spent, round(budget, 6), stage, predicted=typical)


def stage_started_at(events: Iterable[Mapping[str, Any]], stage: str) -> datetime | None:
    """Latest of: this stage's start, a retry, a G7 「계속」, or what the client wrote at this confirmation
    (each restarts the stage clock — time spent reading a confirmation is the client's, not the team's)."""
    latest = None
    for e in events:
        restart = (e.get("type") == "stage_started" and e.get("data", {}).get("stage") == stage) or \
                  (e.get("type") == "client_message" and e.get("data", {}).get("cp") == stage) or \
                  e.get("type") == "run_retried" or _g7(e, "resumed")
        if restart:
            latest = datetime.fromisoformat(str(e["ts"]))
    return latest


def check(events: tuple[Mapping[str, Any], ...], stage: str, limits: Limits, timed: bool,
          now: datetime | None = None) -> None:
    """Raise LimitReachedError when the next call would go over a limit. `timed`: a work stage is running."""
    used = calls_used(events)
    allowed = calls_allowed(events, limits)
    if used >= allowed:
        raise LimitReachedError("calls", used, allowed, stage)
    budget = cost_allowed(events, limits)
    spent = spent_usd(events)
    if budget is not None and spent >= budget:
        raise LimitReachedError("cost", spent, round(budget, 6), stage)
    if not timed:
        return
    started = stage_started_at(events, stage)
    if started is None:
        return
    elapsed = ((now or datetime.now(timezone.utc)) - started).total_seconds()
    if elapsed > limits.max_stage_seconds:
        raise LimitReachedError("time", round(elapsed), limits.max_stage_seconds, stage)


def unresolved_block(events: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any] | None:
    """The latest G7 block that no 「계속」 has answered yet."""
    for e in reversed(events):
        if _g7(e, "resumed"):
            return None
        if _g7(e, "blocked"):
            return e["data"]
    return None


def stop_message(err: LimitReachedError, stage_title: str, batch: int, lane: bool = False) -> str:
    """The Korean stop card text. `lane`: a change request / complaint (sent again) rather than a stage."""
    after = "같은 말을 다시 보내 주세요" if lane else f"{stage_title} 단계를 처음부터 다시 해요"
    if err.limit == "cost" and err.predicted is not None:
        return (f"{stage_title} 단계는 보통 ${err.predicted:.2f} 정도 들어요. 지금까지 ${err.used:.4f}를 써서 "
                f"시작하면 예산(${err.maximum:.2f})을 넘을 것 같아 시작하기 전에 멈췄어요. "
                "「계속」을 누르면 이 단계를 그대로 시작하고, 예산도 같은 금액만큼 늘어나요.")
    if err.limit == "cost":
        return (f"이 프로젝트에 쓴 비용이 상한(${err.maximum:.2f})에 닿아 멈췄어요 (지금 ${err.used:.4f}). "
                f"「계속」을 누르면 같은 금액만큼 더 쓸 수 있고, {after}.")
    if err.limit == "calls":
        return (f"Liner 호출이 이 프로젝트의 상한({err.maximum}회)에 닿아 멈췄어요. "
                f"「계속」을 누르면 {batch}회를 더 쓸 수 있고, {after}.")
    minutes = max(1, round(err.maximum / 60))
    return f"{stage_title} 단계가 상한 시간({minutes}분)을 넘겨 멈췄어요. 「계속」을 누르면 {after}."
