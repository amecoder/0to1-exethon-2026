from __future__ import annotations
"""Hand-off documents built from the shared source by code (no model call, no new facts):

- AGENTS.md: a work order for a coding AI (Claude Code, Codex …) — goal, what not to do, values still open
  (as constants to keep in one place), tasks in dependency order with done-when, linked screens and tests
  (input / expected, and whether the expected value can be judged yet), data and links to other systems,
  where to look.
- 제안요약.md: one page for a decision maker — problem, scope, size (a rule over counts, with its basis),
  expected effect (BRD goals), risks, what still needs a decision.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.code_values import code_values
from app.placement import separated
from app.systems import FITS, REUSE

PLATFORM_KO = {"app": "휴대폰 앱", "web": "웹사이트(데스크톱·태블릿·모바일)"}
INPUT_KINDS = ("input", "select")


def _first(source: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    items = source.get(kind) or [{}]
    return items[0] if isinstance(items[0], Mapping) else {}


def task_order(requirements: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Dependencies first, otherwise list order. A cycle cannot stop the list: the rest follow in list order."""
    by_id = {r["id"]: r for r in requirements}
    done: list[str] = []
    visiting: set[str] = set()

    def visit(rid: str) -> None:
        if rid in done or rid in visiting or rid not in by_id:
            return
        visiting.add(rid)
        for dep in by_id[rid].get("depends_on", []):
            visit(dep)
        visiting.discard(rid)
        done.append(rid)

    for r in requirements:
        visit(r["id"])
    return [by_id[rid] for rid in done]


def size_class(requirements: int, screens: int, systems: int) -> tuple[str, str]:
    """작음 / 보통 / 큼 by a fixed rule over counts — never a made-up schedule or price."""
    basis = f"요구사항 {requirements}건 · 화면 {screens}개 · 연계 시스템 {systems}개"
    if requirements >= 20 or screens >= 8 or systems >= 3:
        return "큼", basis
    if requirements <= 6 and screens <= 3 and systems == 0:
        return "작음", basis
    return "보통", basis


def _gwt(req: Mapping[str, Any]) -> str:
    a = req.get("acceptance") or {}
    return f"Given {a.get('given', '')} / When {a.get('when', '')} / Then {a.get('then', '')}"


def _do_not(source: Mapping[str, Any]) -> list[str]:
    scope_out = [c.get("text", "") for c in _first(source, "scope").get("out", [])]
    non_goals = [f"{n.get('item', '')} — {n.get('reason', '')}".rstrip(" —") for n in _first(source, "brd").get("non_goals", [])]
    open_reqs = [f"{r['id']} {r.get('title', '')}: 아직 {r['status']} — 정해질 때까지 만들지 말고 물어볼 것"
                 for r in source.get("requirements", []) if r.get("status") in ("미결", "미확인")]
    rules = ["요구사항에 없는 기능을 더하지 않는다. 필요해 보이면 만들지 말고 질문으로 남긴다.",
             "프로토타입의 가짜 데이터·「예시」 값을 실제 값으로 쓰지 않는다."]
    return [line for line in (*scope_out, *non_goals, *open_reqs, *rules) if line.strip()]


def mutual_pairs(ordered: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Dependencies that point forward in the task order can only come from a cycle (A needs B, B needs A)."""
    pos = {r["id"]: i for i, r in enumerate(ordered)}
    pairs = []
    for r in ordered:
        for dep in r.get("depends_on", []):
            if dep in pos and pos[dep] > pos[r["id"]]:
                pair = tuple(sorted((r["id"], dep)))
                if pair not in pairs:
                    pairs.append(pair)
    return pairs


def test_owner(ordered: Sequence[Mapping[str, Any]], tests: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Each test belongs to the first task (1-based) that lists it; later tasks only refer to it."""
    owner: dict[str, int] = {}
    for n, req in enumerate(ordered, start=1):
        for t in tests:
            if req["id"] in t.get("requirement_refs", []):
                owner.setdefault(t["id"], n)
    return owner


def const_name(item_id: str) -> str:
    """The constant a coder keeps an open value under: the item's own ID, so it traces back to the source."""
    return item_id.replace("-", "_")


def _cell(value: Any) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def open_values(source: Mapping[str, Any]) -> list[tuple[str, str, str, str, str, str]]:
    """(constant, what, current value, code value, status, used by) for every value that is assumed or open."""
    reqs = source.get("requirements", [])
    assumed = {d["id"]: d for d in source.get("decisions", []) if d.get("status") == "가정" and not d.get("kind")}
    rows = [(const_name(d["id"]), d.get("topic", ""), d.get("chosen", ""), code_values(str(d.get("chosen", ""))),
             "가정(기본값으로 정함)",
             ", ".join(r["id"] for r in reqs if d["id"] in (r.get("decision_refs") or [])) or "—")
            for d in assumed.values()]
    for r in reqs:
        if r.get("status") == "가정" and not set(r.get("decision_refs") or []) & assumed.keys():
            rows.append((const_name(r["id"]), r.get("title", ""), r.get("statement", ""),
                         code_values(str(r.get("statement", ""))), "가정(근거 약함)", r["id"]))
        elif r.get("status") in ("미결", "미확인"):
            rows.append((const_name(r["id"]), r.get("title", ""), "미정", "", r["status"], r["id"]))
    rows += [(const_name(o.get("id", "")), o.get("title", ""), "미정", "", f"미결 — {o.get('reason', '')}".rstrip(" —"), "—")
             for o in source.get("open_items", [])]
    return rows


def _judgement(test: Mapping[str, Any], reqs: Mapping[str, Mapping[str, Any]], assumed: set[str]) -> str | None:
    """Whether the expected value can be asserted yet, from the test's status and the requirements it checks."""
    linked = [reqs[rid] for rid in test.get("requirement_refs", []) if rid in reqs]
    undecided = [r["id"] for r in linked if r.get("status") in ("미결", "미확인")]
    if undecided or test.get("status") == "미결":
        what = ", ".join(undecided) or "이 테스트의 기대값"
        return (f"판정 불가 — {what}이(가) 아직 정해지지 않았다. 구현할 때 결과를 기록만 하고 통과 조건으로 쓰지 않는다. "
                f"임시 동작: 값이 정해질 때까지 그 기능은 동작하지 않게 두고(설정 상수가 비어 있으면 건너뜀) 건너뛴 사실을 "
                f"로그로 남긴다. 테스트는 skip 으로 두고 이유에 {what}을(를) 적는다.")
    if test.get("status") != "가정" and not any(r.get("status") == "가정" for r in linked):
        return None
    consts = [const_name(d) for r in linked for d in (r.get("decision_refs") or []) if d in assumed]
    consts += [const_name(r["id"]) for r in linked
               if r.get("status") == "가정" and not set(r.get("decision_refs") or []) & assumed]
    what = ", ".join(dict.fromkeys(consts)) or "이 테스트의 기대값"
    return f"가정값 기준 — {what} 값이 바뀌면 기대값도 바뀐다(값은 「정해지지 않은 값」 표의 상수에서 읽는다)."


def _test_lines(test: Mapping[str, Any], reqs: Mapping[str, Mapping[str, Any]], assumed: set[str]) -> list[str]:
    lines = [f"  - {test['id']} {test.get('title', '')}"]
    if test.get("inputs"):
        lines.append(f"    - 입력: {test['inputs']}")
    lines.append(f"    - 기대: {test.get('expected', '')}")
    judgement = _judgement(test, reqs, assumed)
    if judgement:
        lines.append(f"    - {judgement}")
    return lines


def _task_block(n: int, req: Mapping[str, Any], screens: Mapping[str, Any], tests: Sequence[Mapping[str, Any]],
                systems: Mapping[str, Any], pos: Mapping[str, int], owner: Mapping[str, int],
                reqs: Mapping[str, Mapping[str, Any]], assumed: set[str]) -> list[str]:
    lines = [f"### TASK-{n:02d} · {req['id']} {req.get('title', '')}", "", f"- 할 일: {req.get('statement', '')}",
             f"- 인수 조건: {_gwt(req)}"]
    if req.get("exceptions"):
        lines.append(f"- 예외 처리: {' / '.join(req['exceptions'])}")
    before = [d for d in req.get("depends_on", []) if d in pos and pos[d] < pos[req["id"]]]
    together = [d for d in req.get("depends_on", []) if d in pos and pos[d] > pos[req["id"]]]
    if before:
        lines.append(f"- 먼저 끝나야 하는 것: {', '.join(before)}")
    if together:
        lines.append(f"- 함께 만들 것(서로 기대고 있음): {', '.join(together)}")
    linked = [screens[s] for s in req.get("screens", []) if s in screens]
    if linked:
        lines.append("- 화면: " + ", ".join(f"{s['id']} {s.get('title', '')}" for s in linked))
    elif req.get("screen_exemption"):
        lines.append(f"- 화면 없음: {req['screen_exemption']}")
    if req.get("change") in FITS and req.get("system_refs"):
        names = ", ".join(f"{sid} {systems.get(sid, {}).get('name', '')}".strip() for sid in req["system_refs"])
        titles = {f["id"]: f.get("title", "") for sid in req["system_refs"] for f in systems.get(sid, {}).get("features", [])}
        feats = ", ".join(f"{fid} {titles[fid]}".strip() for fid in req.get("feature_refs", []) if fid in titles)
        lines.append(f"- 기존 시스템: {req['change']} · {names}"
                     + (" — 새로 만들지 않는다. 이미 있는 것을 그대로 쓴다" if req["change"] == REUSE else "")
                     + (f" · 이미 있는 기능: {feats}" if feats else ""))
    mine = [t for t in tests if req["id"] in t.get("requirement_refs", [])]
    own = [t for t in mine if owner.get(t["id"]) == n]
    shared = [t for t in mine if owner.get(t["id"]) != n]
    if own:
        lines.append("- 통과해야 할 테스트:")
        lines += [line for t in own for line in _test_lines(t, reqs, assumed)]
    if shared:
        lines.append("- 앞 작업에서 이미 확인하는 테스트: "
                     + ", ".join(f"{t['id']}(TASK-{owner[t['id']]:02d}에서 확인)" for t in shared))
    if req.get("status") != "확정":
        lines.append(f"- 주의: 이 요구사항은 「{req.get('status')}」 상태다. 근거가 약하니 만들기 전에 확인한다.")
    return [*lines, ""]


def _data_draft(screens: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = []
    for s in screens:
        fields = [e for e in s.get("elements", []) if e.get("kind") in INPUT_KINDS]
        if fields:
            lines.append(f"- {s['id']} {s.get('title', '')}: "
                         + "; ".join(f"{e.get('name', '')}({e.get('input_rule') or e.get('kind')})" for e in fields))
    return lines


def _choices(screens: Sequence[Mapping[str, Any]]) -> list[str]:
    """Select elements with what the designer said they offer — the starting point for enum values."""
    return [f"- {s['id']} {e.get('name', '')}: {e['description']}" for s in screens for e in s.get("elements", [])
            if e.get("kind") == "select" and e.get("description")]


def _links(source: Mapping[str, Any]) -> list[str]:
    """Where the product meets something it does not build: listed systems (with the requirements that use
    them) and an existing product the client chose to keep (「모자란 부분만 만들기」)."""
    apart = separated(source.get("decisions", []))
    systems = {s["id"]: s for s in source.get("systems") or [] if s["id"] not in apart}
    reqs = source.get("requirements", [])
    lines: list[str] = []
    described: set[str] = set()
    for f in _first(source, "scope").get("systems", []):
        sid = f.get("system_ref", "")
        if sid in apart:  # the client chose to build this request apart from that service
            continue
        uses = [r for r in reqs if sid in (r.get("system_refs") or [])]
        same_kind = [r for r in uses if r.get("change") == f.get("fit")]  # 연계 rows list 연계 requirements
        users = ", ".join(r["id"] for r in same_kind or uses) or "—"
        about = systems.get(sid, {}).get("about", "") if sid not in described else ""
        described.add(sid)
        lines.append(f"- {sid} {f.get('name', '')} · {f.get('fit', '')}: {f.get('what', '')}"
                     + (f" (시스템 목록: {about})" if about else "") + f" — 쓰는 요구사항: {users}")
    alts = {a["id"]: a for a in source.get("alternatives", [])}
    for d in source.get("decisions", []):
        alt = alts.get(d.get("alternative_ref") or "")
        if d.get("kind") == "build_or_buy" and alt and "모자란" in str(d.get("chosen", "")):
            lines.append(f"- {alt['name']} (기존 제품 — 그대로 쓰고 연결만 만든다): 이 제품이 하는 것 {alt.get('covers', '')} "
                         f"/ 이 제품에 없는 것(이번에 만든다) {alt.get('lacks', '')}")
    return lines


def _data_section(source: Mapping[str, Any], screens: Sequence[Mapping[str, Any]]) -> list[str]:
    reqs = source.get("requirements", [])
    by_kind = {k: [f"- {r['id']} {r.get('title', '')}: {r.get('statement', '')}" for r in reqs
                   if str(r.get("category", "")).startswith(k)] for k in ("DAR", "INR")}
    parts = [("저장할 데이터 (DAR 요구사항 — 레코드와 필드의 출발점)", by_kind["DAR"]),
             ("연동 요구사항 (INR 요구사항 — 외부 입출력, 주기, 실패 처리)", by_kind["INR"]),
             ("입력 항목 (데이터 필드의 출발점)", _data_draft(screens)),
             ("선택 항목과 선택지 (상태값·enum 의 출발점)", _choices(screens)),
             ("외부 연동 (새로 만들지 않고 연결하는 곳)", _links(source))]
    out = []
    for title, lines in parts:
        if lines:
            out += [f"### {title}", "", *lines, ""]
    if not out:
        return []
    return ["## 데이터·연동 (화면설계서·시스템 목록·결정 기록에서 뽑음 — 구조를 정할 때 출발점으로만 쓴다)", "", *out]


def _open_table(source: Mapping[str, Any]) -> list[str]:
    rows = open_values(source)
    if not rows:
        return []
    return ["## 정해지지 않은 값 (설정 상수로 한 곳에 모은다)", "",
            "아래 값은 코드 곳곳에 직접 쓰지 말고 설정 상수 한 곳(예: config)에 모은다. 「미정」은 빈 값으로 두고, "
            "그 값을 쓰는 곳은 값이 없으면 멈추게 만든다. 상수 이름은 원본 ID 라 source.json 에서 근거를 찾을 수 있다. "
            "「코드값」은 문장에서 시각·수량만 규칙으로 뽑은 것이다. 경계(이상인지 초과인지, 정각을 넣는지)는 「지금 값」 문장으로 "
            "확인하고, 문장에 없으면 질문으로 남긴다.", "",
            "| 상수 이름 | 무엇 | 지금 값 | 코드값 | 상태 | 쓰는 요구사항 |", "|---|---|---|---|---|---|",
            *[f"| {' | '.join(_cell(v) for v in row)} |" for row in rows], ""]


def agents_md(source: Mapping[str, Any]) -> str:
    ps, spec = _first(source, "problem_statement"), _first(source, "screen_spec")
    screens = {s["id"]: s for s in source.get("screens", [])}
    apart = separated(source.get("decisions", []))
    systems = {s["id"]: s for s in source.get("systems", []) if s["id"] not in apart}
    tests = source.get("tests", [])
    ordered = task_order(source.get("requirements", []))
    out = ["# AGENTS.md — 이 제품을 만드는 AI 에이전트를 위한 작업 지시서", "",
           "> 0to1(영일)이 발주사와 확인을 거쳐 확정한 공유 원본(source.json)에서 자동으로 만든 문서다. "
           "문서 사이에 다른 말이 있으면 source.json 을 따른다.", "",
           "## 목표", "", f"- 누구를 위해: {ps.get('who', '')}", f"- 무엇이 불편한가: {ps.get('pain', '')}",
           f"- 성공 기준: {ps.get('done', '')}"]
    if spec.get("platform") in PLATFORM_KO:
        out.append(f"- 제품 형태: {PLATFORM_KO[spec['platform']]}")
    if spec.get("look"):
        out.append(f"- 시각 방향: {spec['look']}")
    out += ["", "## 하지 말 것", "", *[f"- {line}" for line in _do_not(source)], "", *_open_table(source)]
    if systems:
        out += ["## 이미 있는 시스템 (새로 만들지 말고 기능 추가·연계·재사용)", "",
                *[f"- {s['id']} {s['name']}: {s.get('about', '')}" for s in systems.values()], ""]
    out += ["## 작업 순서", "",
            "작업은 아래 순서대로 한다(먼저 끝나야 하는 요구사항이 앞에 온다). 작업마다 인수 조건을 만족하고 "
            "통과해야 할 테스트를 모두 통과해야 끝난 것으로 본다. 테스트는 처음 나오는 작업에 한 번만 적었다.", ""]
    pairs = mutual_pairs(ordered)
    if pairs:
        out += ["서로 기대는 요구사항(순서를 정할 수 없어 함께 만든다 — 어느 쪽이 먼저인지 발주사에게 확인하면 좋다): "
                + ", ".join(f"{a} ↔ {b}" for a, b in pairs), ""]
    pos = {r["id"]: i for i, r in enumerate(ordered)}
    owner = test_owner(ordered, tests)
    reqs = {r["id"]: r for r in ordered}
    assumed = {d["id"] for d in source.get("decisions", []) if d.get("status") == "가정" and not d.get("kind")}
    for n, req in enumerate(ordered, start=1):
        out += _task_block(n, req, screens, tests, systems, pos, owner, reqs, assumed)
    ops = _first(source, "test_plan").get("ops_checks", [])
    if ops:
        out += ["## 코드로 확인하지 않는 것 (운영 확인 항목 — 사람이 확인)", "",
                *[f"- {o['id']} {o['title']}: {o['how']}" for o in ops], ""]
    out += _data_section(source, list(screens.values()))
    out += ["## 참고 자료 (같은 묶음 안)", "",
            "- prototype.html: 화면 모양과 흐름의 기준. 가짜 데이터다.",
            "- PRD.md · 화면설계서.md · 테스트케이스.md: 사람이 읽는 같은 내용.",
            "- source.json: 요구사항·화면·테스트·결정·원문이 ID 로 연결된 전체 근거.", ""]
    return "\n".join(out)


def proposal_md(source: Mapping[str, Any]) -> str:
    ps, scope, brd = _first(source, "problem_statement"), _first(source, "scope"), _first(source, "brd")
    reqs, screens = source.get("requirements", []), source.get("screens", [])
    fits = scope.get("systems", [])
    label, basis = size_class(len(reqs), len(screens), len({f["system_ref"] for f in fits}))
    open_reqs = [f"- {r['id']} {r.get('title', '')} ({r['status']})" for r in reqs if r.get("status") in ("미결", "가정")]
    open_items = [f"- {o.get('id', '')} {o.get('title', '')}: {o.get('reason', '')}" for o in source.get("open_items", [])]
    out = ["# 제안 요약", "", "> 0to1(영일)이 확정한 공유 원본에서 자동으로 만든 한 장 요약이다. 자세한 내용은 BRD·PRD 를 본다.", "",
           "## 문제", "", f"- 누가: {ps.get('who', '')}", f"- 무엇이 불편한가: {ps.get('pain', '')}",
           f"- 성공 기준: {ps.get('done', '')}", *[f"- {s}" for s in brd.get("summary", [])[:3]], "",
           "## 범위", "", "이번에 하는 것", *[f"- {c.get('text', '')}" for c in scope.get("in", [])], "",
           "이번에 하지 않는 것", *[f"- {c.get('text', '')}" for c in scope.get("out", [])], ""]
    if fits:
        out += ["이미 있는 시스템 활용", *[f"- {f['name']} · {f['fit']}: {f.get('what', '')}" for f in fits], ""]
    out += ["## 규모", "", f"- 규모: **{label}** ({basis})",
            "- 기준: 요구사항 20건·화면 8개·연계 시스템 3개 중 하나라도 넘으면 큼, 요구사항 6건·화면 3개 이하이고 연계가 없으면 작음.",
            "- 기간과 비용은 이 규모와 작업 지시서(AGENTS.md)의 작업 수를 보고 개발팀이 정한다(이 문서는 숫자를 추정하지 않는다).", "",
           "## 기대 효과", ""]
    goals = brd.get("goals", [])
    out += [f"- {g.get('goal', '')} — 기준: {g.get('criterion', '')} ({g.get('status', '')})" for g in goals] or ["- (BRD 목표 없음)"]
    out += ["", "## 위험", ""]
    out += [f"- {r.get('risk', '')} → {r.get('response', '')}" for r in brd.get("risks", [])] or ["- (BRD 위험 없음)"]
    out += ["", "## 결정이 필요한 것", "", *(open_reqs + open_items or ["- 없음"]), ""]
    return "\n".join(out)
