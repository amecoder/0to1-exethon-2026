from __future__ import annotations
"""Low-fidelity wireframe (format spec P4, section 3): grey boxes in element order, numbered callouts.

Deterministic code, not LLM drawing. Callout numbers match the `no` column of the element table.
"""

from collections.abc import Mapping
from typing import Any
from xml.sax.saxutils import escape

WIDTH = 360
PAD = 16
GAP = 10
HEADER = 44
CALLOUT_R = 11
BOX_RIGHT = WIDTH - PAD - CALLOUT_R * 2 - 8
HEIGHTS = {"text": 28, "input": 40, "select": 40, "button": 40, "list": 96, "image": 96}
LABEL_PREFIX = {"input": "[입력] ", "select": "[선택 ▾] ", "button": "", "list": "[목록] ", "image": "[이미지] ", "text": ""}


def _box(kind: str, y: int, label: str) -> str:
    height = HEIGHTS.get(kind, 40)
    width = BOX_RIGHT - PAD
    if kind == "button":
        shape = (f'<rect x="{PAD + width // 4}" y="{y}" width="{width // 2}" height="{height}" rx="20" '
                 f'fill="#bdbdbd" stroke="#8a8a8a"/>')
        text_x, anchor = PAD + width // 2, "middle"
    elif kind == "text":
        shape = f'<rect x="{PAD}" y="{y + 8}" width="{width * 2 // 3}" height="12" fill="#d6d6d6"/>'
        text_x, anchor = PAD, "start"
    else:
        shape = f'<rect x="{PAD}" y="{y}" width="{width}" height="{height}" rx="4" fill="#ececec" stroke="#9e9e9e"/>'
        text_x, anchor = PAD + 10, "start"
    text_y = y + (height // 2) + 5 if kind != "text" else y + 6
    caption = escape(LABEL_PREFIX.get(kind, "") + label)
    return f'{shape}<text x="{text_x}" y="{text_y}" font-size="12" fill="#555" text-anchor="{anchor}">{caption}</text>'


def _callout(no: int, y: int, height: int) -> str:
    cx, cy = WIDTH - PAD - CALLOUT_R, y + height // 2
    return (f'<g class="callout"><line x1="{BOX_RIGHT}" y1="{cy}" x2="{cx - CALLOUT_R}" y2="{cy}" stroke="#d9480f"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{CALLOUT_R}" fill="#d9480f"/>'
            f'<text class="callout-no" x="{cx}" y="{cy + 4}" font-size="11" fill="#fff" text-anchor="middle">{no}</text></g>')


def render_wireframe(screen: Mapping[str, Any]) -> str:
    parts = []
    y = HEADER + PAD
    for element in screen.get("elements", []):
        kind = str(element.get("kind", "text"))
        height = HEIGHTS.get(kind, 40)
        parts.append(_box(kind, y, str(element.get("name", ""))))
        parts.append(_callout(int(element.get("no", len(parts) // 2 + 1)), y, height))
        y += height + GAP
    total = max(y + PAD, HEADER + PAD * 3)
    title = escape(f"{screen.get('id', '')} {screen.get('title', '')}".strip(), {'"': "&quot;"})
    head = (f'<rect x="0" y="0" width="{WIDTH}" height="{total}" rx="10" fill="#fff" stroke="#9e9e9e"/>'
            f'<rect x="0" y="0" width="{WIDTH}" height="{HEADER}" rx="10" fill="#e0e0e0"/>'
            f'<text x="{PAD}" y="{HEADER // 2 + 5}" font-size="14" font-weight="bold" fill="#333">{title}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {total}" width="{WIDTH}" height="{total}" '
            f'role="img" aria-label="{title} 와이어프레임">{head}{"".join(parts)}</svg>')
