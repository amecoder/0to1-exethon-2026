from __future__ import annotations
"""Template fallback prototype built from the screen specs with the design kit's components.

Used when the developer agent's answer is unusable. Each spec screen becomes one app screen; spec IDs
stay in data attributes only (the client sees an app, not IDs). It should read like an app, not a wireframe:
- a screen with three or more fields becomes a step flow (kit data-flow) ending in a 확인 step
- chosen values are kept (data-store) and shown on later screens (data-bind); a seed fills them up front
- spec sentences go under 「자세히」; open values are samples with the 「예시」 badge
- pause / resume / cancel change a shared 상태 through sheets; admin screens get seed rows and numbers
Data shown is fake and marked so.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.prototype_template_blocks import choice_field, element_block, form_fields, hero_title, join_blocks, summary_rows
from app.prototype_template_parts import (
    STATUS_KEY, help_details, icon, is_admin, options_for, seed_values, store_key, text,
)

__all__ = ["TEMPLATE_NOTICE", "options_for", "template_html", "choice_field"]

TEMPLATE_NOTICE = "템플릿 대체본 — 개발자 에이전트의 응답이 올바르지 않아 화면설계서로 자동 생성했습니다"
MAX_TABS = 5
FIELDS_PER_STEP = 2
MAX_FIELD_STEPS = 3
TAB_ICONS = ("home", "card", "calendar", "user", "list")
_DANGER = ("해지", "탈퇴", "삭제")
_PAUSE = ("일시정지",)
_RESUME = ("재개",)
_SHORT_PURPOSE = 30
FIRST_HERO_FX = ' data-fx3d="orb"'  # the opening screen gets the kit's 3D stage (gradient without WebGL)


def _base(name: str) -> str:
    return name[:-2] if name.endswith("하기") else name


def _target(e: Mapping[str, Any], sid: str, titles: Mapping[str, str]) -> str | None:
    """Where a button goes: a screen title in its name, else in its action, else a screen ID in its action."""
    name, action = str(e.get("name", "")), str(e.get("action") or "")
    for words in (name, action):
        for t_id, title in titles.items():
            if t_id != sid and title and title in words:
                return t_id
    return next((t_id for t_id in titles if t_id != sid and t_id in action), None)


def _is_form(s: Mapping[str, Any]) -> bool:
    return sum(1 for e in s.get("elements", []) if e.get("kind") in ("input", "select")) >= 3


def _sheet(sheet_id: str, verb: str, rule: str, kind: str, set_to: str | None, go: str | None) -> str:
    title_id = f"{sheet_id}-t"
    effect = (f' data-set="{text(STATUS_KEY)}={text(set_to)}"' if set_to else "") + \
        (f' data-go="{text(go)}"' if go else "")
    return (f'<div class="sheet" id="{text(sheet_id)}" hidden role="dialog" aria-modal="true" '
            f'aria-labelledby="{text(title_id)}"><button type="button" class="sheet-backdrop" data-close '
            f'aria-label="닫기"></button><div class="sheet-panel"><h2 class="sheet-title" id="{text(title_id)}">'
            f'{text(verb)}할까요?</h2>{help_details(rule)}<div class="stack">'
            f'<button type="button" class="btn btn-{kind} btn-block" data-close{effect} data-toast="{text(verb)}했어요">'
            f'{text(verb)}</button><button type="button" class="btn btn-ghost btn-block" data-close>닫기</button>'
            f"</div></div></div>")


def _button(e: Mapping[str, Any], sid: str, titles: Mapping[str, str], cta: bool) -> tuple[str, str]:
    """One button → (markup, sheet). Pause / resume / cancel move the shared 상태; others go or toast."""
    name, action = str(e.get("name", "")), str(e.get("action") or "")
    go, sheet, show_if = _target(e, sid, titles), "", ""
    if any(w in name for w in _PAUSE):
        sheet_id = f"sheet-{sid}-{e.get('no', 0)}"
        sheet = _sheet(sheet_id, _base(name), action, "primary", "일시정지", None)
        trigger, show_if = f' data-sheet="{text(sheet_id)}"', ' data-show-if="상태=이용 중"'
    elif any(w in name for w in _RESUME):
        trigger = f' data-set="{text(STATUS_KEY)}=이용 중" data-toast="다시 받아요"'
        show_if = ' data-show-if="상태=일시정지"'
    elif any(w in name for w in _DANGER) and not go:
        sheet_id = f"sheet-{sid}-{e.get('no', 0)}"
        sheet = _sheet(sheet_id, _base(name), action, "danger", "해지", None)
        trigger = f' data-sheet="{text(sheet_id)}"'
    elif any(w in name for w in _DANGER) and "확인" in name:
        trigger = f' data-set="{text(STATUS_KEY)}=해지" data-go="{text(go)}" data-toast="해지했어요"'
    else:
        trigger = (f' data-go="{text(go)}"' if go else "") + f' data-toast="{text(_base(name))} 완료"'
    if cta:
        return (f'<button type="button" class="btn btn-primary btn-block"{trigger}{show_if}>{text(name)}</button>',
                sheet)
    danger = " row-danger" if any(w in name for w in _DANGER) else ""
    return (f'<button type="button" class="row{danger}"{trigger}{show_if}><span class="row-main"><span class="row-title">'
            f'{text(name)}</span></span><span class="chev">{icon("chev")}</span></button>', sheet)


def _buttons(s: Mapping[str, Any], titles: Mapping[str, str]) -> tuple[str, str, str]:
    """→ (action rows, CTA button or "", sheets). The last non-destructive button is the CTA."""
    sid = str(s["id"])
    buttons = [e for e in s.get("elements", []) if e.get("kind") == "button"]
    last = buttons[-1] if buttons and not any(w in str(buttons[-1].get("name", "")) for w in (*_DANGER, *_PAUSE)) \
        else None
    rows, sheets, cta = [], [], ""
    for e in buttons:
        markup, sheet = _button(e, sid, titles, e is last)
        sheets.append(sheet)
        if e is last:
            cta = markup
        else:
            rows.append(markup)
    return (f'<div class="list">{"".join(rows)}</div>' if rows else ""), cta, "".join(sheets)


def _flow(s: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]], keys: Mapping[str, Sequence[str]],
          rows: str, cta: str) -> str:
    """Fields in steps of FIELDS_PER_STEP (at most MAX_FIELD_STEPS), then a 확인 step with the CTA."""
    groups = form_fields(s, requirements)
    size = max(FIELDS_PER_STEP, -(-len(groups) // MAX_FIELD_STEPS))
    chunks = [groups[i:i + size] for i in range(0, len(groups), size)]
    steps = []
    for i, chunk in enumerate(chunks):
        title = chunk[0][0]
        back = '<button type="button" class="btn btn-ghost" data-prev>이전</button>' if i else ""
        steps.append(f'<div class="flow-step" data-title="{text(title)}">{"".join(h for _, h in chunk)}'
                     f'<div class="flow-nav">{back}<button type="button" class="btn btn-primary" data-next>다음</button>'
                     f"</div></div>")
    confirm = (f'<div class="flow-step" data-title="확인"><div class="section-head"><h3>이대로 신청할까요?</h3></div>'
               f'{summary_rows(keys)}{rows}<div class="flow-nav"><button type="button" class="btn btn-ghost" data-prev>'
               f"이전</button>{cta}</div></div>")
    return f'<div class="flow" data-flow>{"".join(steps)}{confirm}</div>'


def _screen(s: Mapping[str, Any], first: bool, titles: Mapping[str, str],
            requirements: Sequence[Mapping[str, Any]], keys: Mapping[str, Sequence[str]]) -> tuple[str, str]:
    sid, title, purpose = str(s["id"]), str(s.get("title", "")), str(s.get("purpose") or "")
    rows, cta, sheets = _buttons(s, titles)
    if _is_form(s):
        body, cta_bar = _flow(s, requirements, keys, rows, cta), ""
    else:
        parts = [element_block(sid, e, requirements, keys, is_admin(s))
                 for e in s.get("elements", []) if e.get("kind") != "button"]
        body = join_blocks(parts) + rows
        cta_bar = f'<div class="cta-bar">{cta}</div>' if cta else ""
    subtitle = f'<p class="subtitle">{text(purpose)}</p>' if len(purpose) <= _SHORT_PURPOSE else help_details(purpose)
    hero = hero_title(sid, title)
    html = (f'<section class="screen{" is-active" if first else ""}" data-scr="{text(sid)}" data-title="{text(title)}" '
            f'aria-labelledby="t-{text(sid)}"{"" if first else " hidden"}>'
            f'<div class="hero"{FIRST_HERO_FX if first else ""}>{hero}{subtitle}</div>'
            f'<div class="stack-lg stagger">{body}</div>{_states(s)}{cta_bar}</section>')
    return html, sheets


def _states(s: Mapping[str, Any]) -> str:
    st = s.get("states") or {}
    if not any(st.get(k) for k in ("empty", "loading", "error")):
        return ""
    parts = []
    if st.get("empty"):
        parts.append(f'<div class="empty"><span class="empty-icon">{icon("inbox")}</span>'
                     f'<p class="empty-title">비어 있을 때</p><p class="empty-text">{text(st["empty"])}</p></div>')
    if st.get("loading"):
        parts.append(f'<div class="stack" aria-label="불러오는 중"><span class="skeleton line"></span>'
                     f'<span class="skeleton block"></span><p class="help">{text(st["loading"])}</p></div>')
    if st.get("error"):
        parts.append(f'<div class="banner banner-danger">{icon("alert")}<div><strong>문제가 생겼을 때</strong>'
                     f'{text(st["error"])}</div></div>')
    return f'<details class="peek"><summary>다른 상태 미리보기</summary><div class="peek-body">{"".join(parts)}</div></details>'


def _tabbar(screens: Sequence[Mapping[str, Any]]) -> str:
    if len(screens) < 2:
        return ""
    shown = screens if len(screens) <= MAX_TABS else screens[:MAX_TABS - 1]
    tabs = [f'<button type="button" class="tab{" is-active" if i == 0 else ""}" data-go="{text(s["id"])}">'
            f'{icon(TAB_ICONS[i % len(TAB_ICONS)])}<span>{text(s.get("title"))}</span></button>'
            for i, s in enumerate(shown)]
    if len(screens) > MAX_TABS:
        tabs.append(f'<button type="button" class="tab" data-go="MENU">{icon("list")}<span>전체</span></button>')
    return f'<nav class="tabbar" aria-label="화면 이동">{"".join(tabs)}</nav>'


def _menu(screens: Sequence[Mapping[str, Any]]) -> str:
    if len(screens) <= MAX_TABS:
        return ""
    rows = "".join(f'<button type="button" class="row" data-go="{text(s["id"])}"><span class="row-main">'
                   f'<span class="row-title">{text(s.get("title"))}</span></span>'
                   f'<span class="chev">{icon("chev")}</span></button>' for s in screens)
    return (f'<section class="screen" data-scr="MENU" data-title="전체 화면" aria-labelledby="t-MENU" hidden>'
            f'<div class="hero"><h2 class="title" id="t-MENU">전체 화면</h2></div><div class="list">{rows}</div></section>')


def template_html(screens: Sequence[Mapping[str, Any]],
                  requirements: Sequence[Mapping[str, Any]] = ()) -> str:
    titles = {str(s["id"]): str(s.get("title", "")) for s in screens}
    seed = seed_values(screens, requirements)
    keys = {store_key(e): options_for(e, requirements) if e.get("kind") == "select" else []
            for s in screens if _is_form(s) for e in s.get("elements", [])
            if e.get("kind") in ("input", "select") and "카드" not in str(e.get("name", ""))}
    built = [_screen(s, i == 0, titles, requirements, keys) for i, s in enumerate(screens)]
    sections = "".join(html for html, _ in built) + _menu(screens)
    sheets = "".join(sheet for _, sheet in built)
    first_title = text(screens[0].get("title")) if screens else "프로토타입"
    seed_json = json.dumps(seed, ensure_ascii=False).replace("</", "<\\/")
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{first_title} — 프로토타입 (템플릿 대체본)</title></head><body><div class=\"app\">"
            f'<aside class="proto-note" aria-label="안내">{TEMPLATE_NOTICE} · 모든 데이터는 가짜입니다</aside>'
            f'<header class="appbar"><button type="button" class="appbar-back" data-back aria-label="뒤로" hidden>'
            f'{icon("back")}</button><h1 class="appbar-title">{first_title}</h1></header>'
            f'<main class="main">{sections}</main>{_tabbar(screens)}</div>{sheets}'
            f'<script type="application/json" id="proto-seed">{seed_json}</script></body></html>')
