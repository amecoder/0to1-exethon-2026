from __future__ import annotations
"""테스트 케이스 (format spec section 4): ISO/IEC/IEEE 29119-3 + NIA fields, REQ ↔ TC coverage."""

from collections.abc import Mapping
from typing import Any

from app.documents.common import DocContext, first, history_section, joined, make_doc, section, table

CASE_COLUMNS = ["TC ID", "목적", "관련 요구사항·화면", "우선순위", "사전조건", "입력", "절차", "기대 결과", "실제 결과·판정"]


def case_row(tc: Mapping[str, Any]) -> list[str]:
    steps = " ".join(f"{i}) {step}" for i, step in enumerate(tc.get("steps", []), start=1))
    return [tc["id"], tc.get("objective") or tc.get("title", ""),
            joined([*tc.get("requirement_refs", []), *tc.get("screen_refs", [])]), tc.get("priority", ""),
            tc.get("preconditions", ""), tc.get("inputs", ""), steps or "—", tc.get("expected", ""), ""]


def build_tests(source: Mapping[str, Any], ctx: DocContext) -> dict[str, Any]:
    tests = source.get("tests", [])
    ops = first(source, "test_plan").get("ops_checks", [])
    coverage = []
    for req in source.get("requirements", []):
        linked = [t["id"] for t in [*tests, *ops] if req["id"] in t.get("requirement_refs", [])]
        coverage.append([req["id"], req.get("statement", ""), ", ".join(linked) or "없음"])
    ops_part = [section("ops", "2. 운영 확인 항목 (화면이나 시험 대신 사람이 확인)", [table(
        ["ID", "확인할 것", "관련 요구사항", "누가·언제·어떻게"],
        [[o["id"], o["title"], joined(o.get("requirement_refs", [])), o["how"]] for o in ops])])] if ops else []
    n = 2 + len(ops_part)
    sections = [
        section("cases", "1. 테스트 케이스 표", [table(CASE_COLUMNS, [case_row(t) for t in tests])]),
        *ops_part,
        section("coverage", f"{n}. 커버리지 표 (요구사항 ↔ 테스트 케이스·운영 확인)",
                [table(["요구사항 ID", "요구사항 설명", "테스트 케이스·운영 확인"], coverage)]),
        history_section(source, str(n + 1), "qa", ctx),
    ]
    return make_doc("tests", "테스트 케이스 — 됐는지 어떻게 아나", "qa", source, ctx,
                    first(source, "test_plan").get("summary", []), sections)
