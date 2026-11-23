from __future__ import annotations

import pytest

from app.prototype import (
    PREVIEW_CSP, SANDBOX, missing_screens, preview_page, qa_checklist, sanitize, template_prototype,
)

SCREENS = [
    {"id": "SCR-01", "title": "구독 신청", "purpose": "구독을 시작한다", "requirement_refs": ["REQ-01", "REQ-02"],
     "elements": [{"no": 1, "name": "배송 요일", "kind": "select", "description": "", "action": "", "input_rule": "필수"},
                  {"no": 2, "name": "신청하기", "kind": "button", "description": "", "action": "결제", "input_rule": ""}],
     "states": {"empty": "비활성", "loading": "결제 중", "error": "실패 안내"}},
    {"id": "SCR-02", "title": "결제 안내", "purpose": "재결제", "requirement_refs": ["REQ-02"],
     "elements": [{"no": 1, "name": "안내 <문구>", "kind": "text", "description": "", "action": "", "input_rule": ""}],
     "states": {"empty": "", "loading": "", "error": ""}},
]


def page(body: str, head: str = "") -> str:
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"


@pytest.mark.parametrize(("html", "code", "gone"), [
    (page('<script src="https://cdn.example.com/x.js"></script><p>SCR-01</p>'), "external_script", "cdn.example.com"),
    (page("<p>SCR-01</p>", '<link rel="stylesheet" href="https://fonts.example.com/a.css">'), "external_link",
     "fonts.example.com"),
    (page("<p>SCR-01</p>", "<style>@import url('https://x.example.com/a.css'); p{color:red}</style>"), "css_import",
     "x.example.com"),
    (page('<form action="https://evil.example.com/collect"><button>보내기</button></form>'), "external_form",
     "evil.example.com"),
    (page('<img src="https://img.example.com/a.png" alt="꽃">'), "external_media", "img.example.com"),
    (page("<div style=\"background:url('https://bg.example.com/a.png')\">x</div>"), "css_external_url",
     "bg.example.com"),
])
def test_markup_violations_are_stripped(html: str, code: str, gone: str) -> None:
    result = sanitize(html)
    assert result.valid is True
    assert code in [v["code"] for v in result.violations]
    assert gone not in result.html


@pytest.mark.parametrize("script", [
    "fetch('https://api.example.com/orders')",
    "fetch(`//api.example.com/x`)",
    "new WebSocket('wss://ws.example.com')",
    "new EventSource('https://ev.example.com')",
    "const x = new XMLHttpRequest(); x.open('GET', 'https://api.example.com/x')",
    "navigator.sendBeacon('https://b.example.com', 'd')",
])
def test_network_calls_to_absolute_urls_are_rejected(script: str) -> None:
    result = sanitize(page(f"<script>{script}</script>"))
    assert result.valid is False
    assert "external_network" in [v["code"] for v in result.violations]


def test_relative_fetch_and_inline_script_are_fine() -> None:
    result = sanitize(page("<script>const data = [1,2]; fetch('data.json');</script><p>SCR-01</p>"))
    assert result.valid is True and result.violations == []


@pytest.mark.parametrize("html", ["", "그냥 문장입니다", "<div>조각만 있음</div>", "<html><body>" + "a" * 400_001 + "</body></html>"])
def test_non_documents_are_invalid(html: str) -> None:
    assert sanitize(html).valid is False


def test_missing_screens_by_scr_id() -> None:
    assert missing_screens(page("<h2>SCR-01 구독 신청</h2>"), SCREENS) == ["SCR-02"]
    assert missing_screens(page("SCR-01 SCR-02"), SCREENS) == []


def test_template_contains_every_screen_and_passes_own_validation() -> None:
    html = template_prototype(SCREENS)
    result = sanitize(html)
    assert result.valid is True and result.violations == []
    assert missing_screens(html, SCREENS) == []
    assert "템플릿 대체본" in html
    assert "안내 &lt;문구&gt;" in html and "안내 <문구>" not in html


def test_qa_checklist_maps_tests_to_screens_and_presence() -> None:
    tests = [
        {"id": "TC-01", "title": "신청", "requirement_refs": ["REQ-01"], "screen_refs": ["SCR-01"]},
        {"id": "TC-02", "title": "재결제", "requirement_refs": ["REQ-02"], "screen_refs": []},
        {"id": "TC-03", "title": "알림", "requirement_refs": ["REQ-09"], "screen_refs": []},
    ]
    reqs = [{"id": "REQ-09", "screen_exemption": "알림은 화면이 아니라 문자로 받는다"}]
    rows = qa_checklist(tests, SCREENS, page("SCR-01 만 있음"), reqs)
    assert [r["tc_id"] for r in rows] == ["TC-01", "TC-02", "TC-03"]
    assert rows[0]["screens"] == [{"id": "SCR-01", "present": True}] and rows[0]["result"] == "확인 가능"
    # no screen_refs → screens linked through requirements; SCR-02 is missing from the prototype
    assert rows[1]["screens"] == [{"id": "SCR-01", "present": True}, {"id": "SCR-02", "present": False}]
    assert rows[1]["result"] == "프로토타입에 화면 빠짐"
    # nothing to click: checked without a screen, with the screen spec's reason for having none
    assert rows[2]["screens"] == [] and rows[2]["result"] == "화면 없이 확인"
    assert rows[2]["reason"] == "알림은 화면이 아니라 문자로 받는다" and "reason" not in rows[0]


def test_preview_page_isolates_with_sandbox_and_csp() -> None:
    wrapper = preview_page(page("<p>SCR-01</p><script>1</script>"))
    assert SANDBOX == "allow-scripts"
    assert 'sandbox="allow-scripts"' in wrapper and "allow-same-origin" not in wrapper
    assert "srcdoc=" in wrapper and "&lt;p&gt;SCR-01" in wrapper
    assert "Content-Security-Policy" in wrapper  # meta injected into the prototype itself
    assert "default-src 'none'" in PREVIEW_CSP and "connect-src 'none'" in PREVIEW_CSP
