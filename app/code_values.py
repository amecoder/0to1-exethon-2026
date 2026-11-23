from __future__ import annotations
"""Pull the times and quantities out of a Korean sentence so a coder can put them in a config at once:
「오전 8시~오후 9시」 → 08:00~21:00, 「48시간」 → 48h, 「30분」 → 30m, 「하루 80건」 → 80건.

Rule-based on purpose (no model): it never invents a value, and it does not decide boundaries — whether
"48시간" means 48 h or more, or whether 21:00 itself is allowed, stays in the sentence.
"""

import re

_TIME = r"(?:(?P<part>오전|오후|아침|밤|저녁|새벽|낮)\s*)?(?P<h>\d{1,2})시(?!간)(?:\s*(?P<m>\d{1,2})분)?"
_CLOCK = r"(?P<ch>\d{1,2}):(?P<cm>\d{2})"
_QTY = r"(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>시간|분|초|개월|일|주|년|회|번|건|명|개|자|%|원|MB|KB|GB)"
_TOKEN = re.compile(f"{_TIME}|{_CLOCK}|{_QTY}")
_SHORT = {"시간": "h", "분": "m", "초": "s"}
_PM = ("오후", "밤", "저녁")
_JOIN = ("~", "부터", "-", "–")


def _clock(part: str | None, hour: int, minute: int) -> str:
    if part in _PM and hour < 12:
        hour += 12
    elif part in ("오전", "새벽", "아침", "밤") and hour == 12:
        hour = 0
    return f"{hour % 24:02d}:{minute:02d}"


def code_values(text: str) -> str:
    """'08:00~21:00 · 48h' for the sentence, or '' when it holds no time or quantity."""
    found: list[tuple[str, bool, int, int]] = []  # (value, is_time, start, end)
    for m in _TOKEN.finditer(text or ""):
        if m.group("h") is not None:
            found.append((_clock(m.group("part"), int(m.group("h")), int(m.group("m") or 0)), True, *m.span()))
        elif m.group("ch") is not None:
            found.append((f"{int(m.group('ch')):02d}:{m.group('cm')}", True, *m.span()))
        else:
            unit = m.group("unit")
            found.append((f"{m.group('n')}{_SHORT.get(unit, unit)}", False, *m.span()))
    out: list[str] = []
    for i, (value, is_time, start, _) in enumerate(found):
        prev = found[i - 1] if i else None
        if prev and is_time and prev[1] and any(j in text[prev[3]:start] for j in _JOIN):
            out[-1] = f"{out[-1]}~{value}"
        elif value not in out:
            out.append(value)
    return " · ".join(out)
