from __future__ import annotations
"""화면설계서 (format spec section 3): flow summary, screen list, one sheet per screen with wireframe."""

from collections.abc import Mapping
from typing import Any

from app.documents.common import DocContext, cut_of, first, history_section, joined, make_doc, paragraph, section, table
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
    return f"화면은 {chain} 순서로 이어진다." if chain else ""


def cut_section(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Screens that were drawn but not kept, and the elements that led to them."""
    cut = cut_of(source)
    if not cut["screens"] and not cut["elements"]:
        return []
    rows = [[s["id"], s.get("title", ""), "화면 전체"] for s in cut["screens"]]
    rows += [[f"{e['screen']} #{e['no']}", e["name"], f"눌러서 가는 화면이 빠짐: {e['target']}"] for e in cut["elements"]]
    return [section("out_of_scope", "3-1. 이번 범위에서 뺀 화면과 요소", [
        paragraph("화면 범위를 줄이면서 뺀 화면과, 그 화면으로 가던 요소다. 이번 버전에서는 만들지 않으므로 와이어프레임에도 그리지 않았다."),
        table(["어디", "이름", "뺀 것"], rows)])]


def build_screens(source: Mapping[str, Any], ctx: DocContext) -> dict[str, Any]:
    screens = source.get("screens", [])
    exempt = [[r["id"], r["title"], r["screen_exemption"]] for r in source.get("requirements", []) if r.get("screen_exemption")]
    sections = [
        section("screen_list", "1. 화면 목록", [paragraph("이번에 만드는 화면이다. 화면마다 아래에 그림과 구성 요소 표가 있다."), table(
            ["화면 ID", "화면명", "관련 요구사항", "상태"],
            [[s["id"], s.get("title", ""), joined(s.get("requirement_refs", [])), s.get("status", "")] for s in screens])]),
        *[section(s["id"], f"2-{i}. {s['id']} {s.get('title', '')}", [screen_block(s)]) for i, s in enumerate(screens, start=1)],
        section("no_screen", "3. 화면 없는 요구사항과 사유", [
            paragraph("화면 없이 뒤에서 처리하는 요구사항과 그 이유를 적었다."), table(["요구사항 ID", "이름", "사유"], exempt)]),
        *cut_section(source),
        history_section(source, "4", "designer", ctx, polite=False),
    ]
    spec = first(source, "screen_spec")
    form = {"app": "휴대폰 앱으로 설계했다(폰 크기별로 확인).",
            "web": "웹사이트로 설계했다(데스크톱·태블릿·모바일 폭 모두)."}.get(spec.get("platform", ""), "")
    cut = cut_of(source)["screens"]
    before = (f"아래 요약 가운데 디자이너가 쓴 문장은 화면 범위를 줄이기 전의 것이다. 그래서 뺀 화면 {len(cut)}개와 그 기능은 "
              "「3-1. 이번 범위에서 뺀 화면과 요소」를 따른다.") if cut else ""
    summary = [line for line in (before, *spec.get("summary", []), form, spec.get("look", ""), flow_sentence(source)) if line]
    return make_doc("screens", "화면설계서 — 어떻게 보이나", "designer", source, ctx, summary, sections)
