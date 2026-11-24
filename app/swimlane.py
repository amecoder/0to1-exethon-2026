from __future__ import annotations
"""Role swimlane flow chart (역할별 레인 흐름도) drawn by code from the designer's S5 output.

One horizontal lane per role, time flows left → right (column = longest path along `after`), exception
steps are reached by dashed red arrows and carry a short note. No model call and no outside resource:
the SVG uses inline attributes only, so it can be shown as an image or saved as one HTML file.
"""

from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

MAX_LANES = 5
MAX_STEPS = 16
LANE_CHARS = 12
LABEL_CHARS = 30
NOTE_CHARS = 40
KINDS = ("normal", "exception")

FONT = "'Pretendard','Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif"
PAD, HEADER, LANE_W = 16, 40, 96
BOX_W, BOX_H, GAP = 140, 60, 56
NOTE_H, CAP_H = 34, 18  # note: two lines of 12px text above an exception box
SLOT = NOTE_H + BOX_H + CAP_H + 8
INK, MUTED, LINE, RED = "#0f172a", "#64748b", "#475569", "#dc2626"
LANE_FILLS = ("#f8fafc", "#eef2f7")


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _steps(raw: Mapping[str, Any], lanes: list[str], scr_map: Mapping[str, str],
           dropped: list[dict[str, str]]) -> list[dict[str, Any]]:
    known_screens = set(scr_map.values())
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in raw.get("steps") or []:
        if not isinstance(s, Mapping):
            continue
        sid, lane, label = _text(s.get("id"), 40), _text(s.get("lane"), LANE_CHARS), _text(s.get("label"), LABEL_CHARS)
        if not sid or not label or sid in seen:
            dropped.append({"ref": sid, "reason": "id·이름이 없거나 겹치는 단계"})
            continue
        if lane not in lanes:
            dropped.append({"ref": lane, "reason": f"레인 목록에 없는 역할(단계 {sid})"})
            continue
        if len(steps) == MAX_STEPS:
            dropped.append({"ref": sid, "reason": f"단계 {MAX_STEPS}개를 넘음"})
            continue
        ref = str(s.get("screen_ref") or "").strip()
        screen = scr_map.get(ref) or (ref if ref in known_screens else "")
        if ref and not screen:
            dropped.append({"ref": ref, "reason": f"화면설계서에 없는 화면(단계 {sid})"})
        kind = s.get("kind") if s.get("kind") in KINDS else "normal"
        after = [str(a) for a in s.get("after") or [] if isinstance(a, str)]
        seen.add(sid)
        steps.append({"id": sid, "lane": lane, "label": label, "screen_ref": screen, "after": after, "kind": kind,
                      "note": _text(s.get("note"), NOTE_CHARS) if kind == "exception" else ""})
    return steps


def _reaches(preds: Mapping[str, list[str]], start: str, goal: str) -> bool:
    """True when `goal` is already an ancestor of `start` (following `after` backwards)."""
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(preds.get(node, []))
    return False


def normalize_swimlane(raw: Any, scr_map: Mapping[str, str]) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Designer output → {lanes, steps} with known lanes/steps/screens only, capped, without cycles.

    Returns (None, dropped) when nothing drawable is left. `dropped` lists what was removed and why."""
    dropped: list[dict[str, str]] = []
    if not isinstance(raw, Mapping):
        return None, dropped
    lanes: list[str] = []
    for name in raw.get("lanes") or []:
        lane = _text(name, LANE_CHARS)
        if lane and lane not in lanes:
            lanes.append(lane)
    lanes = lanes[:MAX_LANES]
    steps = _steps(raw, lanes, scr_map, dropped)
    ids = {s["id"] for s in steps}
    preds: dict[str, list[str]] = {}
    for step in steps:
        kept: list[str] = []
        for pred in step["after"]:
            if pred not in ids or pred == step["id"]:
                dropped.append({"ref": pred, "reason": f"없는 단계를 뒤따름(단계 {step['id']})"})
            elif pred in kept:
                continue
            elif _reaches(preds, pred, step["id"]):
                dropped.append({"ref": pred, "reason": f"순환 연결이라 뺌(단계 {step['id']})"})
            else:
                kept.append(pred)
                preds[step["id"]] = kept
        step["after"] = kept
    if not steps:
        return None, dropped
    return {"lanes": lanes, "steps": steps}, dropped


# --- drawing --------------------------------------------------------------------------------------
def _columns(steps: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Column = longest path from a start step. Edges back into the current path are ignored (cycle-safe)."""
    by_id = {s["id"]: s for s in steps}
    cols: dict[str, int] = {}

    def col(sid: str, path: frozenset[str]) -> int:
        if sid not in cols:
            preds = [p for p in by_id[sid].get("after", []) if p in by_id and p not in path]
            cols[sid] = max((col(p, path | {sid}) + 1 for p in preds), default=0)
        return cols[sid]

    for s in steps:
        col(s["id"], frozenset())
    return cols


def _units(ch: str) -> float:
    return 1.0 if ord(ch) >= 0x1100 else 0.58


def _width(text: str) -> float:
    return sum(_units(ch) for ch in text)


def _wrap(text: str, width: float, lines: int) -> list[str]:
    """Greedy word wrap (Korean breaks at spaces); a word wider than a line is cut by characters."""
    out: list[str] = []
    cur = ""
    for word in text.split(" "):
        joined = f"{cur} {word}" if cur else word
        if _width(joined) <= width:
            cur = joined
            continue
        if cur:
            out.append(cur)
        cur = ""
        for ch in word:
            if _width(cur + ch) > width and cur:
                out.append(cur)
                cur = ""
            cur += ch
    out.append(cur)
    if len(out) > lines:
        out = [*out[:lines - 1], out[lines - 1][:-1] + "…"]
    return out


def _label(x: float, y: float, text: str, width: float, lines: int, size: int, color: str, weight: int = 500) -> str:
    rows = _wrap(text, width, lines)
    top = y - (len(rows) - 1) * (size + 3) / 2
    spans = "".join(f'<tspan x="{x:.0f}" y="{top + i * (size + 3):.0f}">{escape(r)}</tspan>' for i, r in enumerate(rows))
    return (f'<text text-anchor="middle" dominant-baseline="middle" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{spans}</text>')


def _layout(swimlane: Mapping[str, Any]) -> tuple[dict[str, tuple[float, float]], list[tuple[float, float]], int]:
    """Box top-left per step, (top, height) per lane, and the column count."""
    steps, lanes = swimlane["steps"], list(swimlane["lanes"])
    cols = _columns(steps)
    stacks: dict[tuple[str, int], int] = {}
    slot: dict[str, int] = {}
    for s in steps:
        key = (s["lane"], cols[s["id"]])
        slot[s["id"]] = stacks.get(key, 0)
        stacks[key] = slot[s["id"]] + 1
    bands, top = [], float(HEADER)
    for lane in lanes:
        depth = max([n for (name, _), n in stacks.items() if name == lane], default=1)
        bands.append((top, depth * SLOT + 8))
        top += depth * SLOT + 8
    boxes = {}
    for s in steps:
        band_top = bands[lanes.index(s["lane"])][0]
        x = PAD + LANE_W + GAP / 2 + cols[s["id"]] * (BOX_W + GAP)
        boxes[s["id"]] = (x, band_top + 4 + slot[s["id"]] * SLOT + NOTE_H)
    return boxes, bands, max(cols.values(), default=0) + 1


def _legend() -> str:
    y = HEADER / 2
    return (f'<text x="{PAD}" y="{y}" dominant-baseline="middle" font-family="{FONT}" font-size="15" '
            f'font-weight="700" fill="{INK}">역할별 흐름</text>'
            f'<path d="M{PAD + 110} {y} h28" stroke="{LINE}" stroke-width="2" marker-end="url(#arr)"/>'
            f'<text x="{PAD + 144}" y="{y}" dominant-baseline="middle" font-family="{FONT}" font-size="12" '
            f'fill="{MUTED}">기본 흐름</text>'
            f'<path d="M{PAD + 210} {y} h28" stroke="{RED}" stroke-width="2" stroke-dasharray="6 4" '
            f'marker-end="url(#arr-x)"/>'
            f'<text x="{PAD + 244}" y="{y}" dominant-baseline="middle" font-family="{FONT}" font-size="12" '
            f'fill="{RED}">예외(실패·취소 등)</text>')


def _arrow(pred: str, step: Mapping[str, Any], boxes: Mapping[str, tuple[float, float]]) -> str:
    (px, py), (sx, sy) = boxes[pred], boxes[step["id"]]
    x1, y1, x2, y2 = px + BOX_W, py + BOX_H / 2, sx - 2, sy + BOX_H / 2
    bend = max((x2 - x1) / 2, 20)
    exception = step["kind"] == "exception"
    style = (f'stroke="{RED}" stroke-dasharray="6 4" marker-end="url(#arr-x)"' if exception
             else f'stroke="{LINE}" marker-end="url(#arr)"')
    return (f'<path data-from="{escape(pred)}" data-to="{escape(step["id"])}" fill="none" stroke-width="2" {style} '
            f'd="M{x1:.0f} {y1:.0f} C{x1 + bend:.0f} {y1:.0f} {x2 - bend:.0f} {y2:.0f} {x2:.0f} {y2:.0f}"/>')


def _box(step: Mapping[str, Any], x: float, y: float, titles: Mapping[str, str]) -> str:
    exception = step["kind"] == "exception"
    border = f'stroke="{RED}" stroke-dasharray="5 3" fill="#fef2f2"' if exception else f'stroke="{LINE}" fill="#ffffff"'
    parts = [f'<g data-step="{escape(step["id"])}" data-x="{x:.0f}">',
             f'<rect x="{x:.0f}" y="{y:.0f}" width="{BOX_W}" height="{BOX_H}" rx="10" stroke-width="1.5" {border}/>',
             _label(x + BOX_W / 2, y + BOX_H / 2, step["label"], 9.6, 3, 13, INK)]
    if exception and step.get("note"):
        # Up to two lines; a longer note ends with … and keeps its full text as the hover title.
        parts.insert(1, f'<title>{escape(step["note"])}</title>')  # first child: the box's hover text
        parts.append(_label(x + BOX_W / 2, y - NOTE_H / 2, step["note"], 11.4, 2, 12, RED, 700))
    title = titles.get(step.get("screen_ref", ""))
    caption = "화면: 이번 범위 밖" if step.get("out_of_scope") else f"화면: {title}" if title else ""
    if caption:
        parts.append(_label(x + BOX_W / 2, y + BOX_H + CAP_H / 2 + 1, caption, 12.5, 1, 11, MUTED, 400))
    return "".join([*parts, "</g>"])


def swimlane_svg(swimlane: Mapping[str, Any], screens: Sequence[Mapping[str, Any]]) -> str:
    """Normalized swimlane → standalone SVG (all text escaped, inline attributes only)."""
    boxes, bands, ncols = _layout(swimlane)
    width = PAD * 2 + LANE_W + ncols * (BOX_W + GAP)
    height = int(bands[-1][0] + bands[-1][1] + PAD) if bands else HEADER + PAD
    titles = {str(s.get("id")): str(s.get("title", "")) for s in screens}
    marker = ('<marker id="{id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" '
              'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>')
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}" role="img" aria-label="역할별 흐름도">',
             f'<defs>{marker.format(id="arr", c=LINE)}{marker.format(id="arr-x", c=RED)}</defs>',
             f'<rect width="{width}" height="{height}" fill="#ffffff"/>', _legend()]
    for i, (lane, (top, h)) in enumerate(zip(swimlane["lanes"], bands)):
        parts.append(f'<rect x="{PAD}" y="{top:.0f}" width="{width - PAD * 2}" height="{h:.0f}" '
                     f'fill="{LANE_FILLS[i % 2]}" stroke="#cbd5e1"/>')
        parts.append(f'<rect x="{PAD}" y="{top:.0f}" width="{LANE_W}" height="{h:.0f}" fill="#e2e8f0" stroke="#cbd5e1"/>')
        parts.append(_label(PAD + LANE_W / 2, top + h / 2, lane, 6.2, 2, 14, INK, 700))
    for step in swimlane["steps"]:
        parts.extend(_arrow(p, step, boxes) for p in step["after"] if p in boxes)
    for step in swimlane["steps"]:
        parts.append(_box(step, *boxes[step["id"]], titles))
    return "".join([*parts, "</svg>"])


def swimlane_page(svg: str, title: str = "역할별 흐름도") -> str:
    """One HTML file around the SVG for the download bundle (no script, no outside resource)."""
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title></head>'
            '<body style="margin:0;padding:16px;background:#ffffff;overflow-x:auto">'
            f'{svg}</body></html>')
