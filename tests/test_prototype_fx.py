from __future__ import annotations
"""Prototype platform (app / web) and visual effects: the kit marks the platform, three.js is added only
where a 3D part is used and only when the prototype is shown (never stored, never sent to an agent)."""

from pathlib import Path
from typing import Any

from app.prototype import preview_page
from app.prototype_kit import SCRIPT_ID, THREE_ID, ensure_kit, platform_for, with_three
from app.export import bundle_files
from tests.flower_script import PROTOTYPE_HTML, prototype_output, screen_spec
from tests.pipeline_helpers import CHUNKS, CP3_WAIVERS, build, to_cp3

FX3D = '<!doctype html><html><head></head><body><div class="app"><div data-fx3d="orb"></div></div></body></html>'
PLAIN = '<!doctype html><html><head></head><body><div class="app"><p>안녕</p></div></body></html>'


def test_platform_from_words() -> None:
    assert platform_for("꽃집 정기구독 앱을 만들고 싶어요") == "app"
    assert platform_for("사내 관리자 페이지와 대시보드를 웹으로") == "web"
    assert platform_for("홈페이지에서 예약을 받고 싶어요") == "web"
    assert platform_for("아무 말") == "app"


def test_kit_marks_platform_once() -> None:
    web = ensure_kit(PLAIN, platform="web")
    assert '<html data-platform="web">' in web
    assert ensure_kit(web, platform="app") == web  # already marked: the first choice stays
    assert '<html data-platform="app">' in ensure_kit(PLAIN)


def test_three_only_where_3d_is_used() -> None:
    assert THREE_ID not in with_three(ensure_kit(PLAIN))
    out = with_three(ensure_kit(FX3D))
    assert out.count(f'id="{THREE_ID}"') == 1 and "THREE" in out
    assert out.index(f'id="{THREE_ID}"') < out.index(f'id="{SCRIPT_ID}"')  # loaded before the kit uses it
    assert with_three(out) == out
    assert "are deprecated with r150+" not in out  # the build's console warning is dropped
    assert f'id="{THREE_ID}"' in preview_page(FX3D).replace("&quot;", '"')


def test_three_is_never_stored_or_sent(repo_root: Path, key_env: Path) -> None:
    html = PROTOTYPE_HTML.replace("<body>", '<body><div class="hero" data-fx3d="orb"></div>', 1)
    orch, ws, fake = build(repo_root, key_env, {"prototype": [prototype_output(html)]})
    to_cp3(orch, ws)
    orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)
    orch.advance()
    proto = ws.items("prototype")[-1]
    assert proto["platform"] == "app" and 'data-platform="app"' in proto["html"]
    assert THREE_ID not in proto["html"] and "data-fx3d" in proto["html"]
    for name in fake.chat_names:
        for payload in fake.chat_payloads(name):
            assert THREE_ID not in payload["messages"][-1]["content"]
    assert f'id="{THREE_ID}"' in bundle_files(ws.source)["prototype.html"]


def run_platform(repo_root: Path, key_env: Path, designer: str | None, developer: str | None) -> str:
    overrides: dict[str, list[Any]] = {"prototype": [{**prototype_output(), **({"platform": developer} if developer else {})}]}
    if designer:
        overrides["screen_spec"] = [lambda payload: {**screen_spec(CHUNKS), "platform": designer, "look": "밝고 산뜻한 꽃집"}]
    orch, ws, fake = build(repo_root, key_env, overrides)
    to_cp3(orch, ws)
    orch.confirm("CP3", True, "발주사", waivers=CP3_WAIVERS)
    orch.advance()
    if designer:
        qa = fake.chat_payloads("test_cases")[0]["messages"][-1]["content"]
        dev = fake.chat_payloads("prototype")[0]["messages"][-1]["content"]
        assert f'"제품 형태": "{designer}"' in qa and "밝고 산뜻한 꽃집" in dev
    return str(ws.items("prototype")[-1]["platform"])


def test_platform_order_designer_developer_guess(repo_root: Path, key_env: Path) -> None:
    assert run_platform(repo_root, key_env, "web", "app") == "web"
    assert run_platform(repo_root, key_env, None, "web") == "web"
    assert run_platform(repo_root, key_env, None, None) == "app"
