from __future__ import annotations
"""S5 documentation: PM ↔ designer (SCR), PM ↔ QA (TC), PM (BRD/PRD content), coordinator coverage check.

Ids are re-assigned by code (SCR-01, TC-01 ...), references to unknown items are dropped and logged,
and items without a requirement to stand on become 가정 (G5). Wireframes are drawn later by code.
"""

import re
from collections.abc import Mapping
from typing import Any

from app.change_revision import revise_requirements, revision_pending
from app.checks import coverage_warnings
from app.flow_chart import draw_flow_chart
from app.schemas import (
    DOCUMENT_CONTENT, ELEMENT_KINDS, PLATFORMS, PRIORITIES, SCREEN_SPEC, TC_KINDS, TEST_CASES,
)
from app.prototype_kit import platform_for
from app.stage_common import StageContext, masked_output, report_answer_consistency, str_list
from app.stage_consumer import collect_feedback
from app.swimlane import normalize_swimlane

TASK_ASSIGN = "단계 S5 문서화: 확정된 요구사항으로 화면설계서·테스트 케이스·BRD·PRD 를 만든다."
TASK_DESIGNER = (
    "확정된 요구사항(requirements)으로 화면설계서를 써라. 화면마다 id, 제목, 목적, 구성 요소(위에서 아래 순서: 요소명, "
    "종류 text/input/select/button/list/image, 설명, 동작과 결과, 입력 규칙(타입·필수·검증), 관련 요구사항 id), "
    "상태(빈 상태 empty·로딩 loading·오류 error 각각 한 줄), 관련 요구사항 id 를 적어라. 와이어프레임은 시스템이 구성 요소 "
    "순서대로 그린다. 화면 흐름 순서(flow, 화면 id 목록)와 처음 보는 사람용 요약(summary, 완전한 문장 5개 이하)을 적어라. "
    "화면이 필요 없는 요구사항(예: 알림)은 no_screen 에 요구사항 id 와 이유를 적어라. 요구사항에 없는 기능은 넣지 않는다. "
    "제품 형태(platform)를 정하라: 원문·요구사항이 PC 로 쓰는 웹사이트·관리자 화면·대시보드면 'web', 휴대폰으로 쓰는 앱이면 "
    "'app'. web 이면 넓은 화면에서 나란히 놓을 것(예: 왼쪽 목록·오른쪽 상세, 숫자 카드 4개 한 줄)을 구성 요소 설명에 적고 "
    "휴대폰 폭에서도 쓸 수 있게 한다. look 에는 첫인상을 정하는 시각 방향을 완전한 문장 2개로 적어라(분위기·색감, 첫 화면의 "
    "대표 시각 요소 — 예: '꽃잎이 천천히 떠다니는 3D 장면 위에 큰 제목', '숫자가 올라가는 지표 카드와 막대그래프'). "
    "구성 요소 설명에는 실제 서비스처럼 버튼 글자와 안내 문장을 구체적으로 적는다(예: '다음' 대신 '배송 요일 정하기'). "
    "swimlane 에는 발주사가 아는 역할(예: 고객·앱·사장, 5개 이하)을 lanes 로, 누가 무엇을 하는지 6~16단계를 steps 로 적어라"
    "(id, lane, 짧은 행동 label, 관련 화면 id 또는 빈 문자열, 바로 앞 단계 id 목록 after, kind normal/exception, "
    "예외면 갈림 이유 note 예: '결제 실패'). 요구사항에 실패·취소·지연 같은 예외가 있으면 예외 갈림을 하나 이상 넣는다."
)
TASK_QA_TC = (
    "요구사항(requirements)과 화면(screens)으로 테스트 케이스를 써라. 인수 조건 하나에 테스트 케이스 하나 이상, "
    "긍정 → 부정 → 경계 순서. 케이스마다 id, 제목, 목적, 관련 요구사항·화면 id, 우선순위(상/중/하), 사전조건, "
    "입력(발주사가 읽을 수 있는 쉬운 말), 절차(단계 목록), 기대 결과, 종류(긍정/부정/경계)를 적어라. "
    "요약(summary)은 '이럴 때 이렇게 되면 통과입니다' 형식의 완전한 문장 5개 이하. 추가 입력의 제품 형태가 app 이면 작은 폰"
    "(360px)·큰 폰(430px), web 이면 데스크톱(1440px)·모바일(390px) 폭에서 글자 잘림·겹침 없이 핵심 버튼이 보이는지 확인하는 "
    "경계 케이스를 화면마다 하나 넣고, 화면설계서의 빈 상태·로딩·오류 상태마다 그 상태가 보이는지 확인하는 케이스를 넣어라. "
    "무엇을 넣거나 빼기로 한 결정, 사람이 하는 업무 절차(업체 선정·계약·법무 확인), 출시 뒤에 재는 효과 측정은 "
    "테스트 케이스로 쓰지 말고 ops_checks 에 운영 확인 항목으로 적어라: 확인할 것(title), 관련 요구사항 id, 누가 언제 "
    "어떻게 확인하는지(how, 예: '출시 4주 뒤 CS 담당이 문의 태그 집계로 일평균을 본다')."
)
TASK_PM_DOCS = (
    "BRD·PRD 내용을 써라. BRD: summary(누가·무엇이 불편하고·무엇을 바라며·언제까지·성공하면 무엇이 달라지는지, 완전한 문장 "
    "5개 이하), background(원문 ID src_id 와 그 원문에 대한 해석 — 해결책은 쓰지 않는다), goals(목표와 측정 가능한 성공 "
    "기준 — 숫자가 없으면 상태 '미결'), non_goals(하지 않기로 한 것과 이유, 근거 원문 ID), constraints, risks(위험·영향·대응). "
    "PRD: summary(핵심 기능, 완전한 문장 5개 이하), decision_notes(결정 ID 별로 다른 선택지를 고르지 않은 이유)."
)
_DIGIT = re.compile(r"\d")


RESUME_REST = "S5-rest"  # pipeline.resume after the client narrowed the screens (G8)
RESUME_DOCS = "S5-docs"  # 11-22: the test cases are written; a retry after a failure goes on from the PM's documents


def run_s5(ctx: StageContext) -> bool:
    """Returns True when S5 waits for the client to narrow the screens (G8), else False."""
    if ctx.ws.pipeline.get("resume") not in (RESUME_REST, RESUME_DOCS):
        if revision_pending(ctx):
            revise_requirements(ctx)  # FR-21: an approved change rewrites requirements before the documents
        draw_screens(ctx)
        limit = ctx.runner.limits.max_screens
        count = len(ctx.ws.items("screens"))
        if count > limit:
            ask_scope(ctx, count, limit)
            return True
    finish_documents(ctx)
    return False


def draw_screens(ctx: StageContext) -> None:
    ctx.bus.send("coordinator", "pm", TASK_ASSIGN)
    ctx.bus.send("pm", "designer", "확정 요구사항으로 화면설계서를 부탁합니다")
    spec = masked_output(ctx, "designer", ctx.runner.ask(
        "designer", TASK_DESIGNER, "screen_spec", SCREEN_SPEC, ctx.feedback_extra()))
    screens, scr_map = normalize_screens(ctx, spec.get("screens"))
    ctx.ws.write_all("designer", "screens", screens)
    flow = [scr_map[f] for f in str_list(spec.get("flow")) if f in scr_map]
    exemptions = no_screen_reasons(ctx, spec.get("no_screen"))
    decided = spec.get("platform") in PLATFORMS
    platform = spec["platform"] if decided else platform_for(_request_text(ctx))
    ctx.ws.write("designer", "screen_spec", {"id": "SCRDOC-01", "summary": str_list(spec.get("summary")),
                                             "flow": flow or [s["id"] for s in screens], "no_screen": exemptions,
                                             "id_map": scr_map, "platform": platform, "platform_guessed": not decided,
                                             "look": str(spec.get("look", "")).strip(), **lanes_of(ctx, spec, scr_map)})
    ctx.bus.send("designer", "pm", f"화면 {len(screens)}개, 화면 없는 요구사항 {len(exemptions)}건")


def lanes_of(ctx: StageContext, spec: Mapping[str, Any], scr_map: Mapping[str, str]) -> dict[str, Any]:
    """{"swimlane": ...} when the designer gave a drawable one, else {} (the spec stays as before)."""
    lanes, dropped = normalize_swimlane(spec.get("swimlane"), scr_map)
    for drop in dropped:
        ctx.ws.emit("ref_dropped", "designer", {"item": "SCRDOC-01#swimlane", **drop})
    return {"swimlane": lanes} if lanes else {}


def ask_scope(ctx: StageContext, count: int, limit: int) -> None:
    """G8: more screens than the PoC limit → the coordinator asks the client which ones to keep."""
    ctx.ws.guardrail("G8", "flagged", f"화면 {count}개 — PoC 상한 {limit}개를 넘음", actor="coordinator",
                     count=count, max=limit)
    ctx.bus.send("designer", "coordinator", f"화면이 {count}개 나왔습니다")
    ctx.bus.send("coordinator", "client",
                 f"화면이 {count}개라 이번 시제품 범위(화면 {limit}개)를 넘어요. 먼저 만들 화면을 {limit}개 이하로 골라 주세요")


def finish_documents(ctx: StageContext) -> None:
    screens = ctx.ws.items("screens")
    spec = (ctx.ws.items("screen_spec") or ({},))[0]
    scr_map = {k: v for k, v in (spec.get("id_map") or {}).items() if any(s["id"] == v for s in screens)}
    exemptions = dict(spec.get("no_screen") or {})
    if ctx.ws.pipeline.get("resume") != RESUME_DOCS:
        write_test_cases(ctx, scr_map)
        ctx.ws.set_pipeline(resume=RESUME_DOCS)  # 11-22: a retry from here does not ask (and pay) QA again

    content = masked_output(ctx, "pm", ctx.runner.ask(
        "pm", TASK_PM_DOCS, "document_content", DOCUMENT_CONTENT, ctx.feedback_extra()))
    write_brd_prd(ctx, content)
    link_requirements(ctx, exemptions)
    ctx.bus.send("pm", "coordinator", "문서 4종 초안 완료")
    draw_flow_chart(ctx)
    report_coverage(ctx)
    report_answer_consistency(ctx)
    collect_feedback(ctx, "CP3")
    ctx.bus.send("coordinator", "client", "문서 4종을 확인하고 프로토타입 작성을 승인해 주세요")
    ctx.ws.set_pipeline(resume=None)


def write_test_cases(ctx: StageContext, scr_map: Mapping[str, str]) -> None:
    ctx.bus.send("pm", "qa", "요구사항과 화면으로 테스트 케이스를 부탁합니다")
    plan = masked_output(ctx, "qa", ctx.runner.ask("qa", TASK_QA_TC, "test_cases", TEST_CASES,
                                                    {**product_form(ctx), **ctx.feedback_extra()}))
    tests = normalize_tests(ctx, plan.get("tests"), scr_map)
    ctx.ws.write_all("qa", "tests", tests)
    renamed = test_id_map(plan.get("tests"))
    ops = [{**o, "title": retarget(o["title"], renamed), "how": retarget(o["how"], renamed)}
           for o in normalize_ops(ctx, plan.get("ops_checks"))]
    ctx.ws.write("qa", "test_plan", {"id": "TCDOC-01", "summary": str_list(plan.get("summary")), "ops_checks": ops})
    ctx.bus.send("qa", "pm", f"테스트 케이스 {len(tests)}건")


def _request_text(ctx: StageContext) -> str:
    """The client's own words plus the problem statement: what platform_for() reads."""
    words = [s.get("text", "") for s in ctx.ws.items("sources")]
    words += [str(p.get(k, "")) for p in ctx.ws.items("problem_statement") for k in ("who", "pain", "done")]
    return " ".join(words)


def product_form(ctx: StageContext) -> dict[str, str]:
    """What the designer decided in the screen spec, handed to QA and the developer as extra input."""
    spec = (ctx.ws.items("screen_spec") or ({},))[0]
    form = {"제품 형태": spec["platform"]} if spec.get("platform") in PLATFORMS else {}
    return {**form, **({"시각 방향": spec["look"]} if spec.get("look") else {})}


def keep_screens(ctx: StageContext, keep: list[str]) -> None:
    """G8 answer: designer keeps only the chosen screens (order kept) and the flow follows."""
    kept = [s for s in ctx.ws.items("screens") if s["id"] in keep]
    ctx.ws.write_all("designer", "screens", kept)
    spec = (ctx.ws.items("screen_spec") or ({"id": "SCRDOC-01"},))[0]
    ctx.ws.write("designer", "screen_spec", {**spec, "flow": [f for f in spec.get("flow", []) if f in keep]})


def known_refs(ctx: StageContext, refs: Any, known: Mapping[str, Any], actor: str, item: str) -> list[str]:
    kept = []
    for ref in str_list(refs):
        if ref in known and ref not in kept:
            kept.append(ref)
        elif ref not in known:
            ctx.ws.emit("ref_dropped", actor, {"item": item, "ref": ref, "reason": "공유 원본에 없는 ID"})
    return kept


def derived_status(ctx: StageContext, refs: list[str], statuses: Mapping[str, str], actor: str, item: str) -> str:
    """G5: no requirement to stand on → 가정. Otherwise inherit the weakest linked requirement status."""
    if not refs:
        ctx.ws.guardrail("G5", "flagged", "근거 요구사항 없이 만든 항목 → 가정", actor=actor, item=item)
        return "가정"
    linked = {statuses[r] for r in refs}
    return next((s for s in ("미확인", "미결", "가정") if s in linked), "확정")


def _mappings(raw: Any) -> list[Mapping[str, Any]]:
    return [r for r in (raw if isinstance(raw, list) else []) if isinstance(r, Mapping)]


def normalize_screens(ctx: StageContext, raw: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    statuses = {r["id"]: r["status"] for r in ctx.ws.items("requirements")}
    items = _mappings(raw)
    scr_map = {str(s.get("id")): f"SCR-{i:02d}" for i, s in enumerate(items, start=1)}
    screens = []
    for i, s in enumerate(items, start=1):
        sid = f"SCR-{i:02d}"
        refs = known_refs(ctx, s.get("requirement_refs"), statuses, "designer", sid)
        states = s.get("states") if isinstance(s.get("states"), Mapping) else {}
        elements = [{
            "no": n, "name": str(e.get("name", "")), "kind": e.get("kind") if e.get("kind") in ELEMENT_KINDS else "text",
            "description": str(e.get("description", "")), "action": str(e.get("action", "")),
            "input_rule": str(e.get("input_rule", "")),
            "requirement_refs": known_refs(ctx, e.get("requirement_refs"), statuses, "designer", f"{sid}#{n}"),
        } for n, e in enumerate(_mappings(s.get("elements")), start=1)]
        screens.append({
            "id": sid, "title": str(s.get("title", "")), "purpose": str(s.get("purpose", "")), "elements": elements,
            "states": {k: str(states.get(k, "")) for k in ("empty", "loading", "error")},
            "requirement_refs": refs, "status": derived_status(ctx, refs, statuses, "designer", sid),
            "owner_agent": "designer",
        })
    return screens, scr_map


def test_id_map(raw: Any) -> dict[str, str]:
    """{the ID QA wrote: the ID the code gave} for the tests that were renumbered (TC-010 → TC-10)."""
    pairs = {str(t.get("id") or "").strip(): f"TC-{i:02d}" for i, t in enumerate(_mappings(raw), start=1)}
    return {old: new for old, new in pairs.items() if old and old != new}


def retarget(text: str, renamed: Mapping[str, str]) -> str:
    """Rewrite the old test IDs a sentence still names (「TC-010 상태」), all at once so a new ID is not renamed again."""
    if not renamed:
        return text
    names = "|".join(re.escape(old) for old in sorted(renamed, key=len, reverse=True))
    return re.sub(rf"(?<![A-Za-z0-9-])({names})(?![0-9])", lambda m: renamed[m.group(1)], text)


def normalize_tests(ctx: StageContext, raw: Any, scr_map: Mapping[str, str]) -> list[dict[str, Any]]:
    statuses = {r["id"]: r["status"] for r in ctx.ws.items("requirements")}
    screen_ids = {s["id"]: s for s in ctx.ws.items("screens")}
    renamed = test_id_map(raw)
    tests = []
    for i, t in enumerate(_mappings(raw), start=1):
        tid = f"TC-{i:02d}"
        refs = known_refs(ctx, t.get("requirement_refs"), statuses, "qa", tid)
        mapped = [scr_map.get(r, r) for r in str_list(t.get("screen_refs"))]
        tests.append({
            "id": tid, "title": retarget(str(t.get("title", "")), renamed),
            "objective": retarget(str(t.get("objective", "")), renamed),
            "requirement_refs": refs, "screen_refs": known_refs(ctx, mapped, screen_ids, "qa", tid),
            "priority": t.get("priority") if t.get("priority") in PRIORITIES else "중",
            "preconditions": retarget(str(t.get("preconditions", "")), renamed),
            "inputs": retarget(str(t.get("inputs", "")), renamed),
            "steps": [retarget(s, renamed) for s in str_list(t.get("steps"))],
            "expected": retarget(str(t.get("expected", "")), renamed),
            "kind": t.get("kind") if t.get("kind") in TC_KINDS else "긍정",
            "status": derived_status(ctx, refs, statuses, "qa", tid), "owner_agent": "qa",
        })
    return tests


def normalize_ops(ctx: StageContext, raw: Any) -> list[dict[str, Any]]:
    """운영 확인 항목 (OPS-): checked by a person, not on a screen. Unknown requirement ids are dropped."""
    statuses = {r["id"]: r["status"] for r in ctx.ws.items("requirements")}
    ops = []
    for item in _mappings(raw):
        title, how = str(item.get("title", "")).strip(), str(item.get("how", "")).strip()
        if not title or not how:
            continue
        oid = f"OPS-{len(ops) + 1:02d}"
        ops.append({"id": oid, "title": title, "how": how,
                    "requirement_refs": known_refs(ctx, item.get("requirement_refs"), statuses, "qa", oid)})
    return ops


def no_screen_reasons(ctx: StageContext, raw: Any) -> dict[str, str]:
    known = {r["id"] for r in ctx.ws.items("requirements")}
    return {str(e.get("requirement_id")): str(e.get("reason", "")).strip() for e in _mappings(raw)
            if str(e.get("requirement_id")) in known and str(e.get("reason", "")).strip()}


def write_brd_prd(ctx: StageContext, content: Mapping[str, Any]) -> None:
    brd = content.get("brd") if isinstance(content.get("brd"), Mapping) else {}
    prd = content.get("prd") if isinstance(content.get("prd"), Mapping) else {}
    sources = {s["id"] for s in ctx.ws.items("sources")}
    decisions = {d["id"] for d in ctx.ws.items("decisions")}
    background = []
    for row in _mappings(brd.get("background")):
        if str(row.get("src_id")) in sources:
            background.append({"src_id": str(row["src_id"]), "interpretation": str(row.get("interpretation", ""))})
        else:
            ctx.ws.guardrail("G1", "flagged", "BRD 배경이 없는 원문 ID 를 인용했습니다", actor="pm", ref=str(row.get("src_id")))
    goals = [{"goal": str(g.get("goal", "")), "criterion": str(g.get("criterion", "")),
              "status": "확정" if g.get("status") == "확정" and _DIGIT.search(str(g.get("criterion", ""))) else "미결"}
             for g in _mappings(brd.get("goals"))]
    ctx.ws.write("pm", "brd", {
        "id": "BRD-01", "summary": str_list(brd.get("summary")), "background": background, "goals": goals,
        "non_goals": [{"item": str(n.get("item", "")), "reason": str(n.get("reason", "")),
                       "refs": [r for r in str_list(n.get("refs")) if r in sources]} for n in _mappings(brd.get("non_goals"))],
        "constraints": str_list(brd.get("constraints")),
        "risks": [{k: str(r.get(k, "")) for k in ("risk", "impact", "response")} for r in _mappings(brd.get("risks"))],
    })
    ctx.ws.write("pm", "prd", {
        "id": "PRD-01", "summary": str_list(prd.get("summary")),
        "decision_notes": [{"decision_id": str(n["decision_id"]), "reason": str(n.get("reason", ""))}
                           for n in _mappings(prd.get("decision_notes")) if str(n.get("decision_id")) in decisions],
    })


def link_requirements(ctx: StageContext, exemptions: Mapping[str, str]) -> None:
    """PM records the SCR/TC links (and designer's no-screen reasons) on its own requirements."""
    screens, tests = ctx.ws.items("screens"), ctx.ws.items("tests")
    for req in ctx.ws.items("requirements"):
        rid = req["id"]
        linked = {**req, "screens": [s["id"] for s in screens if rid in s["requirement_refs"]],
                  "tests": [t["id"] for t in tests if rid in t["requirement_refs"]],
                  "screen_exemption": exemptions.get(rid)}
        if linked != req:
            ctx.ws.write("pm", "requirements", linked)


def report_coverage(ctx: StageContext) -> None:
    warnings = coverage_warnings(ctx.ws.source)
    ctx.ws.emit("check_result", "coordinator", {
        "check": "coverage", "outcome": "flagged" if warnings else "passed",
        "items": [w["id"] for w in warnings], "details": [w["message"] for w in warnings]})
