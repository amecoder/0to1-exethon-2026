from __future__ import annotations
"""화면설계서 (format spec section 3): flow summary, screen list, one sheet per screen with wireframe."""

from collections.abc import Mapping
from typing import Any

from app.documents.common import DocContext, first, history_section, joined, make_doc, section, table
from app.wireframe import render_wireframe

ELEMENT_COLUMNS = ["번호", "요소명", "설명", "동작과 결과", "입력 규칙(타입·필수·검증)", "관련 REQ"]
STATE_LABELS = (("empty", "빈 상태"), ("loading", "로딩"), ("error", "오류"))


def screen_block(screen: Mapping[str, Any]) -> dict[str, Any]:
    elements = [[e["no"], e["name"], e["description"], e["action"] or "—", e["input_rule"] or "—",
                 joined(e.get("requirement_refs", []))] for e in screen.get("elements", [])]
    states = [[label, screen.get("states", {}).get(key, "") or "적힌 내용이 없습니다"] for key, label in STATE_LABELS]
    return {"type": "screen", "id": screen["id"], "title": screen.get("title", ""), "purpose": screen.get("purpose", ""),
            "svg": render_wireframe(screen), "wireframe_path": f"wireframes/{screen['id']}.svg",
            "elements": table(ELEMENT_COLUMNS, elements), "states": table(["상태", "화면 동작"], states)}


def flow_sentence(source: Mapping[str, Any]) -> str:
    titles = {s["id"]: s.get("title", "") for s in source.get("screens", [])}
    order = first(source, "screen_spec").get("flow") or list(titles)
    chain = " → ".join(f"{sid} {titles.get(sid, '')}".strip() for sid in order if sid in titles)
    return f"화면은 {chain} 순서로 이어집니다." if chain else ""


def build_screens(source: Mapping[str, Any], ctx: DocContext) -> dict[str, Any]:
    screens = source.get("screens", [])
    exempt = [[r["id"], r["title"], r["screen_exemption"]] for r in source.get("requirements", []) if r.get("screen_exemption")]
    sections = [
        section("screen_list", "1. 화면 목록", [table(
            ["화면 ID", "화면명", "관련 요구사항", "상태"],
            [[s["id"], s.get("title", ""), joined(s.get("requirement_refs", [])), s.get("status", "")] for s in screens])]),
        *[section(s["id"], f"2-{i}. {s['id']} {s.get('title', '')}", [screen_block(s)]) for i, s in enumerate(screens, start=1)],
        section("no_screen", "3. 화면 없는 요구사항과 사유", [table(["요구사항 ID", "이름", "사유"], exempt)]),
        history_section(source, "4", "designer", ctx),
    ]
    spec = first(source, "screen_spec")
    form = {"app": "휴대폰 앱으로 설계했습니다(폰 크기별로 확인).",
            "web": "웹사이트로 설계했습니다(데스크톱·태블릿·모바일 폭 모두)."}.get(spec.get("platform", ""), "")
    summary = [line for line in (*spec.get("summary", []), form, spec.get("look", ""), flow_sentence(source)) if line]
    return make_doc("screens", "화면설계서 — 어떻게 보이나", "designer", source, ctx, summary, sections)
