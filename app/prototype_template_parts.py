from __future__ import annotations
"""Building blocks of the template fallback: choices, shared-state keys, sample values, rule details.

Spec text is a rule, not customer copy, so it goes under 「자세히」 (details.help). Values the spec leaves
open are shown as plausible samples with the kit's 「예시」 badge. Keys tie a value chosen on one screen to the
places later screens show it (kit data-store / data-bind).
"""

import re
from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' \
       'stroke-linejoin="round" aria-hidden="true">{}</svg>'
ICONS = {
    "back": '<path d="m15 18-6-6 6-6"/>',
    "chev": '<path d="m9 18 6-6-6-6"/>',
    "home": '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    "card": '<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M2.5 10h19M7 15h3"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="16.5" rx="2.5"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    "alert": '<circle cx="12" cy="12" r="9.5"/><path d="M12 7.5v5.5M12 16.5h.01"/>',
    "info": '<circle cx="12" cy="12" r="9.5"/><path d="M12 11v5.5M12 7.5h.01"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
}
SAMPLE = '<span class="sample">예시</span>'
STATUS_KEY = "상태"
_DAYS = "월화수목금토일"
_OPTIONS = re.compile(r"([0-9A-Za-z가-힣]{1,8}(?:\s*[·/]\s*[0-9A-Za-z가-힣]{1,8})+)")
_QUOTED = re.compile(r"'([^']{1,60})'")
_PAIR = re.compile(r"([0-9A-Za-z가-힣]{1,8})\s*(?:또는|와|과)\s*([0-9A-Za-z가-힣]{1,8})\s*중")
_SUFFIX = re.compile(r"\s*(선택|입력|등록|고르기)$")
_PRICE_WORDS = ("가격", "금액", "요금", "사이즈", "상품", "플랜", "메뉴")


def icon(name: str) -> str:
    return _SVG.format(ICONS[name])


def text(value: Any) -> str:
    return escape(str(value or ""))


def help_details(*parts: Any) -> str:
    """Rule text one tap away; nothing when there is nothing to say."""
    body = " ".join(str(p).strip() for p in parts if p and str(p).strip() not in ("해당 없음", "없음"))
    if not body:
        return ""
    return f'<details class="help"><summary>자세히</summary><p>{text(body)}</p></details>'


def store_key(e: Mapping[str, Any]) -> str:
    """'사이즈 선택' → '사이즈': the name a chosen value is kept under and shown by on later screens."""
    return _SUFFIX.sub("", str(e.get("name", "")).strip()) or str(e.get("name", ""))


def bound_key(name: str, keys: Sequence[str]) -> str | None:
    """The stored key a later element talks about: '선택한 사이즈와 결제 방식' → '사이즈' (first match)."""
    for key in sorted(keys, key=len, reverse=True):
        if key and (key in name or (len(name) >= 2 and name in key)):
            return key
    return None


def _cut(option: str) -> str:
    return re.sub(r"\s*\(.*$", "", option).strip()


def _day_names(element: Mapping[str, Any], opts: list[str]) -> list[str]:
    if "요일" in str(element.get("name", "")) and all(len(o) == 1 and o in _DAYS for o in opts):
        return [f"{o}요일" for o in opts]
    return opts


def options_for(element: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]]) -> list[str]:
    """Choices for a select: its own rule/description first ('A'과 'B' 중 · A 또는 B 중 · A·B), else a linked
    requirement that names this element. Nothing found → two generic choices (shown with 「예시」)."""
    own = [str(element.get("input_rule") or ""), str(element.get("description") or "")]
    for source in own:
        quoted = [_cut(q) for q in _QUOTED.findall(source)]
        if len(quoted) >= 2 and "중" in source:
            return list(dict.fromkeys(q for q in quoted if q))[:4]
        pair = _PAIR.search(source)
        if pair:
            return _day_names(element, [pair.group(1), pair.group(2)])
        found = _OPTIONS.search(source)
        if found:
            return _day_names(element, [o.strip() for o in re.split(r"[·/]", found.group(1)) if o.strip()])
    refs, key = set(element.get("requirement_refs") or []), store_key(element)
    for r in requirements:
        line = f"{r.get('title', '')} {r.get('statement', '')}"
        at = line.find(key) if r.get("id") in refs and key else -1
        if at >= 0:
            found = _OPTIONS.search(line[at:at + len(key) + 30])
            if found:
                return _day_names(element, [o.strip() for o in re.split(r"[·/]", found.group(1)) if o.strip()])
    return ["선택 1", "선택 2"]


def is_generic(opts: Sequence[str]) -> bool:
    return list(opts) == ["선택 1", "선택 2"]


def wants_price(e: Mapping[str, Any]) -> bool:
    words = f"{e.get('name', '')} {e.get('description', '')} {e.get('action', '')}"
    return any(w in words for w in _PRICE_WORDS)


def price(i: int) -> str:
    return f"{24 + 10 * i},000원"


def sample_input(name: str) -> str:
    if "주소" in name or "배송지" in name:
        return "서울시 마포구 연남로 12"
    if "카드" in name:
        return "•••• 1234"
    if "이름" in name:
        return "김꽃님"
    return f"{name} 예시"


def seed_values(screens: Sequence[Mapping[str, Any]], requirements: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """What a returning customer would already have: first choice of every select, a sample for inputs."""
    seed: dict[str, str] = {STATUS_KEY: "이용 중"}
    for s in screens:
        for e in s.get("elements", []):
            key = store_key(e)
            if e.get("kind") == "select" and key not in seed:
                seed[key] = options_for(e, requirements)[0]
            elif e.get("kind") == "input" and key not in seed and "카드" not in key:
                seed[key] = sample_input(key)
    return seed


def is_admin(s: Mapping[str, Any]) -> bool:
    title = str(s.get("title", ""))
    return any(w in title for w in ("운영자", "관리자", "어드민"))
