from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from app.demo import load_recording, replay
from app.prototype import missing_screens, sanitize, template_prototype
from app.prototype_kit import accent_for
from app.prototype_template_parts import options_for


# A frozen real run (the 2026-11-16 demo), so these tests do not move when the demo is re-recorded.
REAL_RUN = Path(__file__).parent / "fixtures" / "real_run_2026-11-16.json"


@pytest.fixture(scope="module")
def real() -> dict:
    """Screens and requirements of the committed real Liner run (REQ-20 price left 미결)."""
    return replay(load_recording(REAL_RUN)["events"])


@pytest.fixture(scope="module")
def html(real: dict) -> str:
    return template_prototype(real["screens"], real["requirements"], accent_for("꽃집"))


def screen(html: str, sid: str) -> str:
    return re.search(rf'<section class="screen[^"]*" data-scr="{sid}".*?</section>', html, re.S).group(0)


def outside_help(fragment: str) -> str:
    return re.sub(r'<details class="help">.*?</details>', "", fragment, flags=re.S)


def test_options_come_from_the_elements_own_words(real: dict) -> None:
    by_name = {e["name"]: e for s in real["screens"] for e in s["elements"]}
    reqs = real["requirements"]
    assert options_for(by_name["사이즈 선택"], reqs) == ["S", "M"]
    assert options_for(by_name["배송 요일 선택"], reqs) == ["수요일", "토요일"]
    assert options_for(by_name["결제 방식 선택"], reqs)[:2] == ["매주 결제", "한 달치 선결제"]
    assert options_for(by_name["고지 동의"], reqs) == ["동의함", "동의하지 않음"]


def test_signup_is_a_step_flow_with_required_fields(html: str) -> None:
    signup = screen(html, "SCR-01")
    steps = re.findall(r'class="flow-step"', signup)
    assert 'data-flow' in signup and 3 <= len(steps) <= 4
    assert signup.count("data-next") == len(steps) - 1 and "data-prev" in signup
    assert "required" in signup and 'name="사이즈"' in signup  # a radio's name is its kit key


def test_choices_carry_to_later_screens_and_seed_management(html: str) -> None:
    done, manage = screen(html, "SCR-02"), screen(html, "SCR-03")
    for fragment in (done, manage):
        assert 'data-bind="사이즈"' in fragment and 'data-bind="배송 요일"' in fragment
    seed = json.loads(re.search(r'<script type="application/json" id="proto-seed">(.*?)</script>', html).group(1))
    assert seed["사이즈"] == "S" and seed["배송 요일"] == "수요일" and seed["상태"]


def test_undecided_values_are_samples_not_blanks(html: str) -> None:
    assert 'class="sample"' in html
    for blank in ("미정", "— 원", "N회", ">—<"):
        assert blank not in outside_help(html), blank


def test_rule_sentences_live_under_details(html: str, real: dict) -> None:
    rule = "토요일 회차는 그 주 화요일, 수요일 회차는 직전 토요일"
    assert rule in html and rule not in outside_help(html)
    purpose = real["screens"][0]["purpose"]
    assert purpose not in outside_help(screen(html, "SCR-01"))


def test_pause_and_cancel_are_sheets_that_change_the_status(html: str) -> None:
    manage = screen(html, "SCR-03")
    assert 'data-show-if="상태=이용 중"' in manage and 'data-show-if="상태=일시정지"' in manage
    assert 'data-set="상태=일시정지"' in html and 'data-set="상태=이용 중"' in html
    assert 'data-bind="상태"' in manage


def test_admin_screen_has_seed_rows_and_numbers(html: str) -> None:
    admin = screen(html, "SCR-05")
    assert 'class="table"' in admin and admin.count("<tr>") >= 4 and 'class="kpi"' in admin


def test_template_stays_g6_clean_and_complete(html: str, real: dict) -> None:
    assert sanitize(html).valid and missing_screens(html, real["screens"]) == []
