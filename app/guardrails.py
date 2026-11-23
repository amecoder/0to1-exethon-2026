from __future__ import annotations
"""Deterministic guardrail checks: G3 sensitive-pattern scan/mask, G1 verbatim quote check."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Order matters: a resident number must be caught before the looser card/phone patterns see it.
_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("resident_id", "주민등록번호", re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")),
    ("card", "카드번호", re.compile(r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)")),
    ("phone", "전화번호", re.compile(r"(?<!\d)(?:01[016789]|0[2-6]\d?)[- ]?\d{3,4}[- ]?\d{4}(?!\d)")),
    ("api_key", "API 키", re.compile(
        r"(?<![A-Za-z0-9])(?:(?:sk|pk|api|key|token|secret)[-_](?:key[-_])?[A-Za-z0-9_\-]{16,}"
        r"|AKIA[0-9A-Z]{16}"
        r"|(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,})(?![A-Za-z0-9])",
        re.IGNORECASE,
    )),
)
LABELS = {kind: label for kind, label, _ in _PATTERNS}

G3_PROMPT = (
    "입력에 개인정보·비밀값으로 보이는 문자열({kinds})이 있어 저장하지 않았습니다. "
    "해당 부분을 가린 값으로 바꿔서 진행할까요?"
)


@dataclass(frozen=True)
class SensitiveHit:
    kind: str
    label: str
    start: int
    end: int


def scan_sensitive(text: str) -> tuple[SensitiveHit, ...]:
    """G3: return non-overlapping hits. The raw matched value is deliberately not kept."""
    hits: list[SensitiveHit] = []
    for kind, label, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if not any(h.start < match.end() and match.start() < h.end for h in hits):
                hits.append(SensitiveHit(kind, label, match.start(), match.end()))
    return tuple(sorted(hits, key=lambda h: h.start))


def mask_sensitive(text: str) -> str:
    masked = text
    for hit in reversed(scan_sensitive(text)):
        masked = f"{masked[:hit.start]}[{hit.label} 가림]{masked[hit.end:]}"
    return masked


def strings_in(value: Any) -> list[str]:
    """Every string inside nested dicts/lists (keys included), for checking a whole JSON body."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [s for k, v in value.items() for s in (*strings_in(k), *strings_in(v))]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in strings_in(v)]
    return []


# Embedded images (prototype photos) and attached PDFs: their base64 looks like a key to the pattern above
# and is never text.
DATA_URI = re.compile(r"data:(?:image/[A-Za-z0-9.+-]+|application/pdf);base64,[A-Za-z0-9+/=]+")
DATA_URI_PLACEHOLDER = "data:image/jpeg;base64,[이미지 생략]"


def strip_data_uris(text: str) -> str:
    return DATA_URI.sub(DATA_URI_PLACEHOLDER, text)


SECRET_MASK = "[API 키 가림]"
PERSONAL_KINDS = ("resident_id", "card", "phone")  # patterns that never collide with markup ids or hashes
PERSONAL_LABELS = tuple(LABELS[k] for k in PERSONAL_KINDS)


def mask_personal(value: Any) -> Any:
    """Like redact(patterns=True) but only for personal numbers (resident id, card, phone) — for HTML."""
    if isinstance(value, str):
        masked = value
        for hit in reversed([h for h in scan_sensitive(value) if h.kind in PERSONAL_KINDS]):
            masked = f"{masked[:hit.start]}[{hit.label} 가림]{masked[hit.end:]}"
        return masked
    if isinstance(value, Mapping):
        return {k: mask_personal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_personal(v) for v in value]
    return value


def strip_secrets(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, SECRET_MASK)
    return text


def redact(value: Any, secrets: Sequence[str] = (), patterns: bool = True) -> Any:
    """Recursively hide the configured secrets and (if `patterns`) G3 sensitive patterns in every string."""
    if isinstance(value, str):
        cleaned = strip_secrets(value, secrets)
        return mask_sensitive(cleaned) if patterns else cleaned
    if isinstance(value, Mapping):
        return {k: redact(v, secrets, patterns) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets, patterns) for v in value]
    return value


def sensitive_labels(texts: Sequence[str]) -> list[str]:
    labels = {hit.label for text in texts for hit in scan_sensitive(text)}
    return [label for label in LABELS.values() if label in labels]


def _normalize(text: str) -> str:
    return " ".join(text.split())


def verify_quote(quote: str, refs: Sequence[str], texts: Mapping[str, str]) -> bool:
    """G1: the quote must appear verbatim (whitespace runs collapsed) in at least one cited, stored text."""
    needle = _normalize(quote)
    if not needle or not refs:
        return False
    return any(ref in texts and needle in _normalize(texts[ref]) for ref in refs)
