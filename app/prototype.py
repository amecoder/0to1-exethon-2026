from __future__ import annotations
"""FR-12/13, G6: deterministic checks around the developer agent's single-HTML prototype.

- sanitize(): markup that loads outside resources is stripped (and reported); script code that talks to
  absolute URLs cannot be stripped safely, so the document is rejected (the stage retries, then falls back)
- template_prototype(): a fallback built from the screen specs (app/prototype_template.py) with the design kit
- qa_checklist(): TC ↔ screen mapping and whether those SCR ids exist in the prototype (no execution)
- preview_page(): sandboxed iframe (scripts only, opaque origin) + CSP that blocks every network request
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from html import escape
from typing import Any

from app.prototype_kit import DEFAULT_ACCENT, ensure_kit, with_three
from app.prototype_template import TEMPLATE_NOTICE, template_html

MAX_HTML_CHARS = 400_000
SANDBOX = "allow-scripts"
PREVIEW_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
               "font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'")

_ABS = r"(?:[a-z][a-z0-9+.-]*:)?//"
STRIP_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("external_script", re.compile(r"<script\b[^>]*\bsrc\s*=[^>]*>.*?</script\s*>|<script\b[^>]*\bsrc\s*=[^>]*/?>",
                                   re.I | re.S), ""),
    ("external_link", re.compile(r"<link\b[^>]*>", re.I), ""),
    ("css_import", re.compile(r"@import\b[^;<]*;?", re.I), ""),
    ("external_form", re.compile(rf"(<form\b[^>]*?)\s+action\s*=\s*(['\"]?){_ABS}[^'\"\s>]*\2", re.I), r"\1"),
    ("external_media", re.compile(
        rf"(<(?:img|iframe|video|audio|source|embed|object|track|input)\b[^>]*?)\s+(?:src|data|poster|srcset)\s*=\s*"
        rf"(['\"]?)(?:https?:)?//[^'\"\s>]*\2", re.I), r"\1"),
    ("css_external_url", re.compile(rf"url\(\s*(['\"]?)(?:https?:)?//[^)]*\)", re.I), "url()"),
)
_NETWORK = re.compile(
    rf"(?:fetch|sendBeacon)\s*\(\s*['\"`]{_ABS}"
    rf"|new\s+(?:WebSocket|EventSource|Worker|SharedWorker)\s*\(\s*['\"`]{_ABS}"
    rf"|\.open\s*\(\s*['\"`][A-Za-z]+['\"`]\s*,\s*['\"`]{_ABS}"
    rf"|\bimport\s*\(\s*['\"`]{_ABS}", re.I)
_DOCUMENT = re.compile(r"<html\b.*</html\s*>", re.I | re.S)


@dataclass(frozen=True)
class Sanitized:
    html: str
    valid: bool
    violations: list[dict[str, str]] = field(default_factory=list)
    reason: str = ""


def sanitize(html: str) -> Sanitized:
    if len(html) > MAX_HTML_CHARS:
        return Sanitized(html, False, reason=f"HTML 이 너무 깁니다({len(html)}자, 상한 {MAX_HTML_CHARS}자)")
    if not _DOCUMENT.search(html):
        return Sanitized(html, False, reason="<html> … </html> 로 된 HTML 문서 하나가 아닙니다")
    cleaned, violations = html, []
    for code, pattern, replacement in STRIP_RULES:
        for match in pattern.finditer(cleaned):
            violations.append({"code": code, "detail": match.group(0)[:160], "action": "stripped"})
        cleaned = pattern.sub(replacement, cleaned)
    network = [m.group(0)[:160] for m in _NETWORK.finditer(cleaned)]
    if network:
        found = [{"code": "external_network", "detail": d, "action": "rejected"} for d in network]
        return Sanitized(cleaned, False, violations + found, reason="스크립트가 외부 주소로 요청을 보냅니다")
    return Sanitized(cleaned, True, violations)


def missing_screens(html: str, screens: Sequence[Mapping[str, Any]]) -> list[str]:
    return [s["id"] for s in screens if s["id"] not in html]


def _linked_screens(test: Mapping[str, Any], screens: Sequence[Mapping[str, Any]]) -> list[str]:
    if test.get("screen_refs"):
        return list(test["screen_refs"])
    reqs = set(test.get("requirement_refs", []))
    return [s["id"] for s in screens if reqs & set(s.get("requirement_refs", []))]


def qa_checklist(tests: Sequence[Mapping[str, Any]], screens: Sequence[Mapping[str, Any]],
                 html: str, requirements: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """A test with no screen at all (automation, notices…) is 「화면 없이 확인」 — not a defect — and carries
    the screen spec's reason why its requirement has no screen."""
    exempt = {r["id"]: str(r.get("screen_exemption") or "").strip() for r in requirements}
    rows = []
    for t in tests:
        linked = [{"id": sid, "present": sid in html} for sid in _linked_screens(t, screens)]
        row: dict[str, Any] = {"tc_id": t["id"], "title": t.get("title", ""), "screens": linked}
        if not linked:
            reason = next((exempt[r] for r in t.get("requirement_refs", []) if exempt.get(r)), "")
            row.update(result="화면 없이 확인", reason=reason)
        else:
            row["result"] = "확인 가능" if all(s["present"] for s in linked) else "프로토타입에 화면 빠짐"
        rows.append(row)
    return rows


def template_prototype(screens: Sequence[Mapping[str, Any]], requirements: Sequence[Mapping[str, Any]] = (),
                       accent: str = DEFAULT_ACCENT, platform: str = "app") -> str:
    """Fallback built from the screen specs, already wearing the design kit."""
    return ensure_kit(template_html(screens, requirements), accent, platform)


def with_csp(html: str) -> str:
    meta = f'<meta http-equiv="Content-Security-Policy" content="{PREVIEW_CSP}">'
    head = re.search(r"<head\b[^>]*>", html, re.I)
    if head:
        return html[:head.end()] + meta + html[head.end():]
    tag = re.search(r"<html\b[^>]*>", html, re.I)
    at = tag.end() if tag else 0
    return html[:at] + f"<head>{meta}</head>" + html[at:]


def preview_page(html: str, kit: bool = True) -> str:
    """Wrapper served by the API. srcdoc frames inherit this page's CSP header as well as the meta tag.
    Older stored prototypes get the design kit here too (no-op when it is already inlined). The flow chart
    passes kit=False: the kit lays a page out as a phone screen, which cut the chart to a phone's width."""
    srcdoc = escape(with_csp(with_three(ensure_kit(html)) if kit else html), quote=True)
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>격리 미리보기</title>'
            "<style>html,body{margin:0;height:100%}iframe{border:0;width:100%;height:100%}</style></head>"
            f'<body><iframe title="프로토타입 미리보기" sandbox="{SANDBOX}" referrerpolicy="no-referrer" '
            f'srcdoc="{srcdoc}"></iframe></body></html>')


def prototype_warnings(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """CP4: a missing SCR needs a one-line reason (waivable); template use and stripped code are notices."""
    from app.checks import warning  # local: checks imports this module

    proto = (source.get("prototype") or [{}])[-1]
    out = [warning("prototype.missing_scr", "waivable", sid, "prototype", f"프로토타입에 {sid} 화면이 없습니다")
           for sid in proto.get("missing_screens", [])]
    if proto.get("origin") == "template":
        out.append(warning("prototype.template", "info", proto.get("id", "PROTO-01"), "prototype", TEMPLATE_NOTICE))
    if proto.get("image_notice"):
        out.append(warning("prototype.images", "info", proto.get("id", "PROTO-01"), "prototype", proto["image_notice"]))
    stripped = [v for v in proto.get("violations", []) if v.get("action") == "stripped"]
    if stripped:
        codes = sorted({v["code"] for v in stripped})
        out.append(warning("prototype.g6_stripped", "info", proto.get("id", "PROTO-01"), "prototype",
                           f"외부 자원을 부르는 코드 {len(stripped)}곳을 지웠습니다(G6): {', '.join(codes)}"))
    return out
