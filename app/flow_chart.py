from __future__ import annotations
"""S5 user-flow chart from Liner Visualization (`/tools/visualization`, SSE `data-atlas` → HTML).

The HTML Liner returns loads its stylesheet and font from a CDN. The G6 preview blocks every network
request (CSP), so before storing we strip external stylesheets, scripts, fonts and any http(s) resource
reference (reusing the G6 strip rules) and record what was removed. Failure never blocks S5: it leaves a
참고 notice at CP3 instead.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.config import LinerKeyMissingError
from app.liner import LinerAPIError, LinerConfigError
from app.prototype import STRIP_RULES

FLOW_ID = "FLOW-01"
FAILED_NOTE = "사용자 흐름도를 만들지 못했어요 — 문서 4종에는 영향이 없어요(참고)"
_HTTP_ATTR = re.compile(r"""(<[a-z][^>]*?)\s+(?:href|src|srcset|poster|data|action)\s*=\s*(['"]?)https?://[^'"\s>]*\2""", re.I)
_HTTP_LEFT = re.compile(r"https?://[^\s'\"<>)]+", re.I)


def strip_external(html: str) -> tuple[str, list[dict[str, str]]]:
    """Remove outside resources. Script text that still names an http(s) URL loses the URL (CSP blocks it anyway)."""
    cleaned, removed = html, []
    rules = (*STRIP_RULES, ("external_attr", _HTTP_ATTR, r"\1"), ("external_url", _HTTP_LEFT, ""))
    for code, pattern, replacement in rules:
        for match in pattern.finditer(cleaned):
            removed.append({"code": code, "detail": match.group(0)[:160], "action": "stripped"})
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned, removed


MAX_QUERY = 1500
SHAPE = ("모양: 역할마다 가로 구역을 나누고 단계 상자는 그 역할 구역에 둔다. 정상 흐름은 실선 화살표, 예외 흐름은 점선 "
         "화살표와 다른 색으로 그리고 화살표에 예외 이유를 짧게 적는다. 상자 글은 짧은 한국어로 쓴다.")


def _lane_lines(swimlane: Mapping[str, Any]) -> list[str]:
    """One line per step: who does what, after which step, and why an exception branch starts."""
    steps = [s for s in swimlane.get("steps") or [] if isinstance(s, Mapping)]
    label = {s.get("id"): s.get("label", "") for s in steps}
    lines = []
    for s in steps:
        after = ", ".join(label.get(a, a) for a in s.get("after") or [])
        line = f"- [{s.get('lane', '')}] {s.get('label', '')}" + (f" (앞 단계: {after})" if after else "")
        if s.get("kind") == "exception":
            line += f" — 예외: {s.get('note') or '예외 흐름'}"
        lines.append(line)
    return lines


def flow_query(screens: Sequence[Mapping[str, Any]], flow: Sequence[str], who: str = "",
               swimlane: Mapping[str, Any] | None = None) -> str:
    """The request to Liner Visualization: who uses it, the screen order, each role's steps with the exception
    branches (from the designer's swimlane), and the shape wanted, in words — capped at MAX_QUERY characters."""
    by_id = {s["id"]: s for s in screens}
    ordered = [by_id[f] for f in flow if f in by_id] or list(screens)
    steps = " → ".join(f"{s.get('title', s['id'])}({s.get('purpose', '')})" for s in ordered)
    head = "사용자가 서비스를 쓰는 흐름도를 한국어로 그려 줘."
    parts = [head, f"쓰는 사람: {who}" if who else "", f"화면 순서: {steps}"]
    lanes = [str(x) for x in (swimlane or {}).get("lanes") or []]
    lines = _lane_lines(swimlane or {})
    if lanes and lines:
        parts += [f"역할: {', '.join(lanes)}", "역할별 단계(정상과 예외):", *lines]
    parts.append(SHAPE)
    query = "\n".join(p for p in parts if p)
    while len(query) > MAX_QUERY and lines:  # drop the last steps first; the shape request always stays
        lines = lines[:-1]
        query = "\n".join(p for p in [*parts[:3], f"역할: {', '.join(lanes)}", "역할별 단계(정상과 예외):", *lines, SHAPE] if p)
    return query[:MAX_QUERY]


def draw_flow_chart(ctx: Any) -> None:
    """Designer → Liner Visualization → stripped HTML in `flow_chart`. Errors only leave a note."""
    screens = ctx.ws.items("screens")
    if not screens:
        return
    spec = (ctx.ws.items("screen_spec") or ({},))[0]
    problem = (ctx.ws.items("problem_statement") or ({},))[0]
    query = flow_query(screens, spec.get("flow") or [], str(problem.get("who", "")), spec.get("swimlane"))
    try:
        body = ctx.runner.visualize("designer", query)
    except (LinerAPIError, LinerConfigError, LinerKeyMissingError) as exc:
        ctx.ws.emit("check_result", "coordinator", {"check": "visualization", "outcome": "failed", "items": [],
                                                    "details": [f"{FAILED_NOTE}: {exc}"]})
        return
    html, removed = strip_external(body["html"])
    ctx.ws.write("designer", "flow_chart", {
        "id": FLOW_ID, "html": html, "description": body.get("description", ""), "query": query,
        "based_on": [s["id"] for s in screens], "violations": removed})
    ctx.ws.emit("check_result", "coordinator", {
        "check": "visualization", "outcome": "passed", "items": [FLOW_ID],
        "details": [f"외부 자원 {len(removed)}곳을 지움(G6)"] if removed else []})


def flow_warnings(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """CP3 notice when the last flow-chart attempt failed (info only)."""
    from app.checks import warning  # local: checks imports app.prototype which this module also uses

    checks = [e["data"] for e in source.get("events", []) if e.get("type") == "check_result"
              and e.get("data", {}).get("check") == "visualization"]
    if checks and checks[-1].get("outcome") == "failed":
        return [warning("flow.failed", "info", FLOW_ID, "screens", FAILED_NOTE)]
    return []
