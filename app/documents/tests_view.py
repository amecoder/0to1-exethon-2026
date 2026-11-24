from __future__ import annotations
"""테스트 케이스 (format spec section 4): ISO/IEC/IEEE 29119-3 + NIA fields, REQ ↔ TC coverage."""

from collections.abc import Mapping
from typing import Any

from app.documents.common import DocContext, cut_of, first, history_section, joined, make_doc, paragraph, section, table

CASE_COLUMNS = ["TC ID", "목적", "관련 요구사항·화면", "우선순위", "사전조건", "입력", "절차", "기대 결과", "실제 결과·판정"]


def case_row(tc: Mapping[str, Any]) -> list[str]:
    steps = " ".join(f"{i}) {step}" for i, step in enumerate(tc.get("steps", []), start=1))
    return [tc["id"], tc.get("objective") or tc.get("title", ""),
            joined([*tc.get("requirement_refs", []), *tc.get("screen_refs", [])]), tc.get("priority", ""),
            tc.get("preconditions", ""), tc.get("inputs", ""), steps or "—", tc.get("expected", ""), ""]


def build_tests(source: Mapping[str, Any], ctx: DocContext) -> dict[str, Any]:
    tests = source.get("tests", [])
    ops = first(source, "test_plan").get("ops_checks", [])
    parked = cut_of(source)["tests"]
    coverage = []
    for req in source.get("requirements", []):
        linked = [t["id"] for t in [*tests, *ops] if req["id"] in t.get("requirement_refs", [])]
        waiting = [t["id"] for t in parked if req["id"] in t.get("requirement_refs", [])]
        coverage.append([req["id"], req.get("statement", ""), (", ".join(linked) or "없음")
                         + (f" (보류: {', '.join(waiting)})" if waiting else "")])
    ops_part = [section("ops", "2. 운영 확인 항목 (화면이나 시험 대신 사람이 확인)", [
        paragraph("화면이나 자동 시험으로 확인할 수 없어 사람이 확인하는 항목이다."),
        table(["ID", "확인할 것", "관련 요구사항", "누가·언제·어떻게"],
              [[o["id"], o["title"], joined(o.get("requirement_refs", [])), o["how"]] for o in ops])])] if ops else []
    parked_part = [section("out_of_scope", "1-1. 이번 범위 밖 테스트 (보류)", [
        paragraph("이번 범위 밖이라 지금은 실행하지 않는 테스트다. 지우지 않고 이유와 함께 남긴다."),
        table(["TC ID", "목적", "보류한 이유"], [[t["id"], t.get("objective") or t.get("title", ""), t.get("reason", "")]
                                         for t in parked])])] if parked else []
    n = 2 + len(ops_part)
    sections = [
        section("cases", "1. 테스트 케이스 표", [
            paragraph("테스트 케이스마다 한 줄이다. 사전조건을 갖추고 절차대로 했을 때 기대 결과가 나오면 통과다."),
            table(CASE_COLUMNS, [case_row(t) for t in tests])]),
        *parked_part,
        *ops_part,
        section("coverage", f"{n}. 커버리지 표 (요구사항 ↔ 테스트 케이스·운영 확인)", [
            paragraph("요구사항마다 그것을 확인하는 테스트 케이스와 운영 확인 항목을 적었다. 「없음」은 확인할 방법이 아직 없다는 뜻이다."),
            table(["요구사항 ID", "요구사항 설명", "테스트 케이스·운영 확인"], coverage)]),
        history_section(source, str(n + 1), "qa", ctx, polite=False),
    ]
    return make_doc("tests", "테스트 케이스 — 됐는지 어떻게 아나", "qa", source, ctx,
                    first(source, "test_plan").get("summary", []), sections)
