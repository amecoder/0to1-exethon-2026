from __future__ import annotations
"""Per-element markup for the template fallback (see app/prototype_template.py for the screen layout)."""

from collections.abc import Mapping, Sequence
from typing import Any

from app.prototype_template_parts import (
    SAMPLE, STATUS_KEY, bound_key, help_details, icon, is_generic, options_for, price, sample_input, store_key,
    text, wants_price,
)

_TIME_WORDS = ("요일", "시간", "주기", "일자", "날짜", "회차")
_COUNT_WORDS = ("건수", "수량")
_WARN_WORDS = ("경고", "주의", "실패", "오류")
_INFO_WORDS = ("안내", "알림", "공지", "고지")
_DONE_WORDS = ("완료",)
_DATE_WORDS = ("예정일", "마감", "배송일", "결제일")
SAMPLE_DATE = "11월 22일(토)"


def _required(e: Mapping[str, Any]) -> bool:
    return "필수" in str(e.get("input_rule") or "")


def _label(e: Mapping[str, Any], label_id: str, tag: str = "p", for_id: str = "") -> str:
    star = '<span class="req" aria-hidden="true">*</span>' if _required(e) else ""
    target = f' for="{text(for_id)}"' if for_id else ""
    return f'<{tag} class="label" id="{text(label_id)}"{target}>{text(store_key(e))}{star}</{tag}>'


def _error(e: Mapping[str, Any]) -> str:
    return f'<p class="error-text">{text(store_key(e))}을(를) 확인해 주세요</p>'


def choice_field(sid: str, e: Mapping[str, Any], opts: list[str], kind: str) -> str:
    key, label_id = store_key(e), f"l-{sid}-{e.get('no', 0)}"
    req = " required" if _required(e) else ""
    sample = SAMPLE if is_generic(opts) else ""
    if kind == "seg":
        inner = "".join(f'<label><input type="radio" name="{text(key)}" data-label="{text(o)}"{req if i == 0 else ""}>'
                        f"<span>{text(o)}</span></label>" for i, o in enumerate(opts))
        control = f'<div class="seg" role="radiogroup" aria-labelledby="{text(label_id)}">{inner}</div>'
    else:
        priced = wants_price(e)
        inner = "".join(
            f'<label class="choice"><input type="radio" name="{text(key)}" data-label="{text(o)}"{req if i == 0 else ""}>'
            f'<span class="choice-title">{text(o)}{sample}</span>'
            + (f'<span class="choice-price">{price(i)}{SAMPLE}</span>' if priced else "") + "</label>"
            for i, o in enumerate(opts))
        control = f'<div class="choice-grid" role="radiogroup" aria-labelledby="{text(label_id)}">{inner}</div>'
    label = _label(e, label_id).replace("</p>", f"{sample}</p>", 1) if kind == "seg" else _label(e, label_id)
    return (f'<div class="field">{label}{control}{_error(e)}'
            f'{help_details(e.get("input_rule"), e.get("description"))}</div>')


def _input_field(sid: str, e: Mapping[str, Any], keys: Sequence[str], editing: bool) -> str:
    key = bound_key(store_key(e), keys) or store_key(e)
    fid = f"f-{sid}-{e.get('no', 0)}"
    card = "카드" in key
    attrs = ' inputmode="numeric" autocomplete="off" placeholder="0000 0000 0000 0000"' if card else \
        f' placeholder="예: {text(sample_input(key))}"'
    bind = f' data-bind="{text(key)}"' if editing else f' data-store="{text(key)}"'
    req = " required" if _required(e) else ""
    return (f'<div class="field">{_label(e, f"l-{fid}", "label", fid)}<input id="{text(fid)}" type="text"{bind}'
            f'{" " + bind.strip().replace("data-bind", "data-store") if editing else ""}{attrs}{req}>{_error(e)}'
            f'{help_details(e.get("input_rule"), e.get("description"))}</div>')


def _select(sid: str, e: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]]) -> str:
    opts = options_for(e, requirements)
    name = str(e.get("name", ""))
    kind = "seg" if any(w in name for w in _TIME_WORDS) or len(opts) > 4 or not wants_price(e) and len(opts) == 2 \
        and all(len(o) <= 8 for o in opts) else "choice"
    return choice_field(sid, e, opts, kind)


def form_fields(s: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Signup fields as (step title, markup); a text block joins the field that follows it."""
    sid, groups, pending = str(s["id"]), [], ""
    for e in s.get("elements", []):
        kind = e.get("kind")
        if kind == "button":
            continue
        if kind == "select":
            groups.append((store_key(e), pending + _select(sid, e, requirements)))
            pending = ""
        elif kind == "input":
            groups.append((store_key(e), pending + _input_field(sid, e, [], False)))
            pending = ""
        else:
            pending += _info(e)
    if pending and groups:
        groups[-1] = (groups[-1][0], groups[-1][1] + pending)
    return groups


def summary_rows(keys: Sequence[str]) -> str:
    rows = "".join(f'<div class="summary-row"><dt>{text(k)}</dt><dd data-bind="{text(k)}"></dd></div>'
                   for k in dict.fromkeys(keys))
    return (f'<dl class="summary">{rows}<div class="summary-row summary-total"><dt>결제 예정 금액</dt>'
            f"<dd>{price(0)}{SAMPLE}</dd></div></dl>")


def _info(e: Mapping[str, Any]) -> str:
    name = str(e.get("name", ""))
    details = help_details(e.get("description"))
    if any(w in name for w in _WARN_WORDS):
        return f'<div class="banner banner-warn">{icon("alert")}<div><strong>{text(name)}</strong>{details}</div></div>'
    if any(w in name for w in _INFO_WORDS):
        return f'<div class="banner banner-info">{icon("info")}<div><strong>{text(name)}</strong>{details}</div></div>'
    return f'<div class="card flat"><p class="card-title">{text(name)}</p>{details}</div>'


def _bound_row(key: str, label: str) -> str:
    return f'<div class="summary-row"><dt>{text(label)}</dt><dd data-bind="{text(key)}"></dd></div>'


def _status_row() -> str:
    return (f'<div class="summary-row"><dt>{STATUS_KEY}</dt><dd><span class="badge badge-success" '
            f'data-bind="{STATUS_KEY}">이용 중</span></dd></div>')


def _kpis(e: Mapping[str, Any], keys: Mapping[str, Sequence[str]]) -> str:
    key = bound_key(str(e.get("name", "")), list(keys))
    labels = list(keys.get(key) or []) if key else []
    labels = labels if labels and not is_generic(labels) else [str(e.get("name", ""))]
    tiles = "".join(f'<div class="kpi"><span class="kpi-num">{12 - 4 * i}건</span><span class="kpi-label">'
                    f"{text(label)}</span></div>" for i, label in enumerate(labels[:4]))
    return f'<div class="field"><p class="label">{text(e.get("name"))}{SAMPLE}</p><div class="kpis">{tiles}</div></div>'


def _table(e: Mapping[str, Any], seed_rows: Sequence[tuple[str, str, str]]) -> str:
    body = "".join(f"<tr><td>{text(a)}</td><td>{text(b)}</td><td>{text(c)}</td></tr>" for a, b, c in seed_rows)
    return (f'<div class="field"><p class="label">{text(e.get("name"))}{SAMPLE}</p><div class="table-wrap">'
            f'<table class="table"><thead><tr><th>고객</th><th>배송지</th><th>구분</th></tr></thead>'
            f"<tbody>{body}</tbody></table></div>{help_details(e.get('description'))}</div>")


ADMIN_ROWS = (("김○○", "마포구 연남로 12", "S"), ("이○○", "성동구 서울숲길 8", "M"), ("박○○", "종로구 율곡로 3", "S"),
              ("최○○", "강서구 공항대로 21", "M · 결제 확인 대기"))
HISTORY_ROWS = (("11월 15일", f"{price(0)}", "결제 완료"), ("11월 8일", f"{price(0)}", "결제 완료"),
                ("11월 1일", f"{price(0)}", "결제 완료"))


def _history(e: Mapping[str, Any]) -> str:
    rows = "".join(f'<div class="row"><span class="row-main"><span class="row-title">{text(a)}</span>'
                   f'<span class="row-sub">{text(c)}</span></span><span class="row-end">{text(b)}{SAMPLE}</span></div>'
                   for a, b, c in HISTORY_ROWS)
    return f'<div class="field"><p class="label">{text(e.get("name"))}</p><div class="list" role="list">{rows}</div></div>'


def element_block(sid: str, e: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]],
                  keys: Mapping[str, Sequence[str]], admin: bool) -> tuple[str, str]:
    """→ ("row", summary row) for values to show in a group, else ("block", markup)."""
    kind, name = e.get("kind"), str(e.get("name", ""))
    if kind == "select":
        return "block", _select(sid, e, requirements)
    if kind == "input":
        return "block", _input_field(sid, e, keys, True)
    if kind == "list":
        return "block", _table(e, ADMIN_ROWS) if admin else _history(e)
    if kind == "image":
        return "block", f'<img data-img="{text(sid)}-{e.get("no", 0)}" alt="{text(name)}">'
    if "상태" in name and not admin:
        return "row", _status_row()
    if admin and any(w in name for w in _COUNT_WORDS):
        return "block", _kpis(e, keys)
    if not admin and any(w in name for w in _DATE_WORDS):
        value = f"{SAMPLE_DATE} 23:59까지" if "마감" in name else SAMPLE_DATE
        return "block", (f'<div class="card flat"><dl class="summary"><div class="summary-row"><dt>{text(name)}</dt>'
                         f"<dd>{value}{SAMPLE}</dd></div></dl>{help_details(e.get('description'))}</div>")
    key = bound_key(name, keys)
    if key and not admin:
        return "row", "".join(_bound_row(k, k) for k in keys if k in name) or _bound_row(key, key)
    return "block", _info(e)


def join_blocks(parts: Sequence[tuple[str, str]]) -> str:
    """Consecutive summary rows share one <dl class="summary">."""
    out, rows = [], []
    for kind, html in [*parts, ("block", "")]:
        if kind == "row":
            rows.append(html)
            continue
        if rows:
            out.append(f'<dl class="summary">{"".join(rows)}</dl>')
            rows = []
        out.append(html)
    return "".join(out)


def hero_title(sid: str, title: str) -> str:
    if any(w in title for w in _DONE_WORDS):
        return (f'<span class="empty-icon" aria-hidden="true">{icon("check")}</span>'
                f'<h2 class="title" id="t-{text(sid)}">{text(title)}</h2>')
    return f'<h2 class="title" id="t-{text(sid)}">{text(title)}</h2>'
