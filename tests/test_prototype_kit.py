from __future__ import annotations

import re
from pathlib import Path

from app.prototype import missing_screens, preview_page, sanitize, template_prototype
from app.prototype_kit import DEFAULT_ACCENT, SCRIPT_ID, STYLE_ID, accent_for, ensure_kit, has_kit
from app.prototype_template import options_for
from tests.pipeline_helpers import build, to_cp4
from tests.test_prototype import SCREENS

DOC = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>x</title></head><body><p>SCR-01</p></body></html>'
MANAGE = {"id": "SCR-03", "title": "구독 관리", "purpose": "구독을 멈추거나 해지한다", "requirement_refs": ["REQ-01"],
          "elements": [{"no": 1, "name": "일시정지", "kind": "button", "action": "다음 배송부터 멈춤"},
                       {"no": 2, "name": "해지하기", "kind": "button", "action": "자동결제를 해지한다"}],
          "states": {}}
FLOWER = [
    {"id": "SCR-01", "title": "구독 신청", "purpose": "구독을 시작한다", "requirement_refs": ["REQ-01", "REQ-02"],
     "elements": [
         {"no": 1, "name": "사이즈 선택", "kind": "select", "input_rule": "S·M 중 하나, 필수", "requirement_refs": ["REQ-01"]},
         {"no": 2, "name": "배송 요일", "kind": "select", "input_rule": "필수", "requirement_refs": ["REQ-01"]},
         {"no": 3, "name": "카드 입력", "kind": "input", "input_rule": "숫자 16자리, 필수", "requirement_refs": ["REQ-02"]},
         {"no": 4, "name": "신청하기", "kind": "button", "action": "누르면 결제 후 완료 안내"}],
     "states": {"empty": "선택 전에는 비활성", "loading": "결제 중", "error": "결제 실패 시 결제 안내로 이동"}},
    {"id": "SCR-02", "title": "결제 안내", "purpose": "실패한 결제를 다시 한다", "requirement_refs": ["REQ-02"],
     "elements": [{"no": 1, "name": "실패 안내 문구", "kind": "text"},
                  {"no": 2, "name": "다시 결제", "kind": "button", "action": "누르면 재결제"}], "states": {}},
    MANAGE,
]
REQS = [{"id": "REQ-01", "title": "배송 요일 수·토 중 고름", "statement": "배송 요일은 수·토 중 고름 방식으로 정한다"}]


def visible_text(html: str) -> str:
    body = re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", body)


def test_ensure_kit_inlines_style_and_script_once() -> None:
    once = ensure_kit(DOC)
    assert has_kit(once) and ensure_kit(once) == once
    assert once.count(f'id="{STYLE_ID}"') == 1 and once.count(f'id="{SCRIPT_ID}"') == 1
    assert once.index(f'id="{SCRIPT_ID}"') < once.index("</body>")


def test_kit_keeps_charset_in_first_1024_bytes() -> None:
    assert b"charset" in ensure_kit(DOC).encode("utf-8")[:1024]
    bare = ensure_kit("<html><body>x</body></html>")
    assert '<meta charset="utf-8">' in bare[:200] and has_kit(bare)


def test_kit_survives_g6_sanitization_untouched() -> None:
    html = ensure_kit(DOC, "#c2255c")
    result = sanitize(html)
    assert result.valid and result.violations == [] and result.html == html


def test_kit_has_no_outside_requests() -> None:
    html = ensure_kit(DOC)
    assert not re.search(r"url\(\s*['\"]?(?:https?:)?//", html)
    assert "@import" not in html and "<link" not in html and "src=" not in html


def test_accent_follows_domain_and_rejects_bad_values() -> None:
    assert accent_for("꽃집 「꽃님」 사장과 정기구독 고객") == "#c2255c"
    assert accent_for("알 수 없는 업종") == DEFAULT_ACCENT
    assert "--accent:#c2255c" in ensure_kit(DOC, "#c2255c")
    assert f"--accent:{DEFAULT_ACCENT}" in ensure_kit(DOC, "red;}body{display:none")


def test_options_come_from_rule_or_linked_requirement() -> None:
    assert options_for(FLOWER[0]["elements"][0], REQS) == ["S", "M"]
    assert options_for(FLOWER[0]["elements"][1], REQS) == ["수요일", "토요일"]
    assert options_for({"name": "x", "kind": "select"}, []) == ["선택 1", "선택 2"]


def test_florist_template_uses_kit_components() -> None:
    html = template_prototype(FLOWER, REQS, accent_for("꽃집"))
    assert sanitize(html).valid and has_kit(html) and missing_screens(html, FLOWER) == []
    assert html.count('class="choice"') == 2  # S / M as selectable cards
    assert '<div class="seg"' in html and "수요일" in html  # delivery day as a segmented control
    assert 'class="summary"' in html and "data-flow" in html  # step flow ending in a summary of the choices
    assert 'data-toast="신청 완료"' in html and "cta-bar" in html  # sticky CTA → confirmation toast
    assert 'data-sheet="sheet-SCR-03-2"' in html and "해지할까요?" in html  # cancel asks first
    assert html.count('class="tab') >= 3 and 'data-go="SCR-03"' in html  # every screen reachable


def test_template_hides_spec_ids_from_visible_text() -> None:
    html = template_prototype(FLOWER, REQS)
    text = visible_text(html)
    assert "SCR-0" not in text and 'data-scr="SCR-01"' in html


def test_many_screens_get_a_menu_screen() -> None:
    many = [{**MANAGE, "id": f"SCR-{i:02d}", "title": f"화면 {i}"} for i in range(1, 8)]
    html = template_prototype(many)
    assert 'data-go="MENU"' in html and all(f'data-go="SCR-{i:02d}"' in html for i in range(1, 8))


def test_preview_adds_kit_to_older_prototypes() -> None:
    page = preview_page(DOC)
    assert STYLE_ID in page and SCRIPT_ID in page
    assert sanitize(template_prototype(SCREENS)).valid


def test_stage_inlines_kit_into_agent_and_template_prototypes(repo_root: Path, key_env: Path) -> None:
    for outputs, origin in ((None, "agent"), ({"prototype": ["JSON 아님", "또 아님"]}, "template")):
        orch, ws, fake = build(repo_root, key_env, outputs)
        to_cp4(orch, ws)
        proto = ws.items("prototype")[-1]
        assert proto["origin"] == origin and has_kit(proto["html"]) and proto["missing_screens"] == []
        assert "--accent:#c2255c" in proto["html"]  # florist → rose, from the problem statement
        messages = fake.chat_payloads("prototype")[0]["messages"]
        assert any("data-scr" in m["content"] for m in messages)  # the developer was told the kit pattern


def test_kit_never_builds_a_selector_from_a_model_written_name() -> None:
    """Review C2: input.name comes from model HTML; quotes or brackets in it must not break the selector."""
    script = (Path(__file__).resolve().parent.parent / "app" / "data" / "prototype_kit.js").read_text(encoding="utf-8")
    assert "' + input.name" not in script and "' + key" not in script
    assert 'getAttribute("data-store") === key' in script and 'state[el.getAttribute("data-bind")]' in script


def test_kit_styles_a_hero_photo() -> None:
    from app.prototype_kit import KIT_CSS
    assert ".hero-photo" in KIT_CSS
