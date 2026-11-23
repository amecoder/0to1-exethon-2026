from __future__ import annotations
"""Liner Decisions API questions used by FR-22 and the G1 secondary check, and how their answers are read.

Decisions return probabilities, not text (`noul` yes-probability, `choice` + `probabilities` + `confidence`).
Code keeps the final say: the FR-22 complaint guard overrides the choice, and G1 stays a verbatim check —
a low support probability only adds a 참고 (info) note.

Thresholds are 제안 (provisional) until measured (scripts/ 의 FR-22 판정 측정, README 참조):
    EXETHON_DECISION_MIN_CONFIDENCE  (default 0.6) — below it a complaint is marked 「사람 판단 필요」
    SUPPORT_MIN                      (0.5)          — below it a G1-checked sentence gets a 참고 note
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.config import read_env

DEFAULT_MIN_CONFIDENCE = 0.6  # 제안
SUPPORT_MIN = 0.5  # 제안
LABELS = {"violation": "합의 위반", "new_change": "새 변경 요청"}
COMPLAINT_QUESTION = {
    "type": "choice",
    "instructions": "발주사의 불만은 확정된 합의를 결과물이 어긴 것인가, 확정된 것과 다른 새 요구인가?",
    "criteria": {
        "violation": "발주사가 원하는 것이 확정된 요구사항 문장과 같은데 결과물이 그렇게 되지 않았다",
        "new_change": "발주사가 원하는 것이 확정된 요구사항 문장과 다르다(합의에 없던 새 요구다)",
    },
}
SUPPORT_CRITERIA = {"true": "근거 문장이 주장의 내용을 직접 말한다", "false": "근거 문장이 주장을 뒷받침하지 않거나 다른 말을 한다"}


def min_confidence(env_file: Path | None = None) -> float:
    raw = read_env("EXETHON_DECISION_MIN_CONFIDENCE", env_file)
    if raw is None:
        return DEFAULT_MIN_CONFIDENCE
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"EXETHON_DECISION_MIN_CONFIDENCE 는 0~1 사이 숫자여야 합니다 (지금 값: {raw!r})") from None
    if not 0 <= value <= 1:
        raise ValueError(f"EXETHON_DECISION_MIN_CONFIDENCE 는 0~1 사이 숫자여야 합니다 (지금 값: {raw!r})")
    return value


# --- FR-22 ----------------------------------------------------------------------------------------
def complaint_state(requirements: Sequence[Mapping[str, Any]], confirmation: Mapping[str, Any] | None,
                    complaint: str) -> dict[str, Any]:
    confirmed = [{k: r.get(k) for k in ("id", "title", "statement", "acceptance") if r.get(k) is not None}
                 for r in requirements]
    cp = {k: confirmation.get(k) for k in ("cp", "who", "at", "version")} if confirmation else None
    return {"confirmed_requirements": confirmed, "confirmation": cp, "complaint": complaint}


def read_choice(answer: Any) -> dict[str, Any]:
    """{choice, label, probabilities, confidence}. Raises ValueError on a shape we cannot trust."""
    if not isinstance(answer, Mapping) or answer.get("choice") not in LABELS:
        raise ValueError("판정 응답에 violation/new_change 선택이 없습니다")
    probs = answer.get("probabilities") if isinstance(answer.get("probabilities"), Mapping) else {}
    confidence = answer.get("confidence")
    return {"choice": answer["choice"], "label": LABELS[answer["choice"]],
            "probabilities": {k: float(v) for k, v in probs.items() if isinstance(v, (int, float))},
            "confidence": float(confidence) if isinstance(confidence, (int, float)) else None}


def needs_human(decision: Mapping[str, Any], threshold: float) -> bool:
    """No usable probability, or a spread-out one, goes to a person."""
    confidence = decision.get("confidence")
    return decision.get("error") is not None or confidence is None or confidence < threshold


# --- G1 secondary check ---------------------------------------------------------------------------
def support_questions(pairs: Sequence[tuple[str, str, str]]) -> dict[str, Any]:
    """One `noul` per (key, claim, evidence). Questions are answered independently (docs), so one call does all."""
    return {key: {"type": "noul", "instructions": {"질문": "이 근거 문장이 이 주장을 뒷받침하는가?",
                                                  "주장": claim, "근거": evidence},
                  "criteria": SUPPORT_CRITERIA}
            for key, claim, evidence in pairs}


def read_noul(answer: Any) -> float | None:
    if isinstance(answer, Mapping) and isinstance(answer.get("noul"), (int, float)):
        return float(answer["noul"])
    return None
