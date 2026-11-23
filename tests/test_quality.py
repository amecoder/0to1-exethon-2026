from __future__ import annotations
"""Format spec section 5: deterministic quality rules, one positive and one negative case each."""

from typing import Any

from app import quality as q
from app.checks import unresolved_conflicts


def req(**extra: Any) -> dict[str, Any]:
    base = {"id": "REQ-01", "category": "SFR", "statement": "고객은 배송 요일을 고른다",
            "acceptance": {"given": "구독 고객이", "when": "요일을 고르면", "then": "저장된다"},
            "exceptions": ["요일이 마감되면 다른 요일을 안내한다"], "status": "확정"}
    return {**base, **extra}


# --- expert rules (ISO 29148) ---------------------------------------------------------------------
def test_singular() -> None:
    assert q.singular_violation("결제하고 알림을 보낸다") is True
    assert q.singular_violation("고객은 요일을 고르고 그리고 결제를 한다") is True
    assert q.singular_violation("고객은 S 및 M 사이즈 중 하나를 고른다") is False


def test_ambiguous_words() -> None:
    assert q.ambiguous_words("배송은 무조건 빨리 한다") == ["빨리", "무조건"]
    assert q.ambiguous_words("꽃, 화분 등을 판다") == ["등"]
    assert q.ambiguous_words("회원 등록 후 2일 안에 배송한다") == []


def test_verifiable() -> None:
    assert q.missing_acceptance(req(acceptance={"given": "고객이", "when": "", "then": "저장된다"})) is True
    assert q.missing_acceptance(req()) is False


def test_complete_exceptions() -> None:
    assert q.missing_exceptions(req(exceptions=[])) is True
    assert q.missing_exceptions(req()) is False
    assert q.missing_exceptions(req(category="PER", exceptions=[])) is False


def test_consistent_unresolved_conflicts() -> None:
    finding = {"id": "FND-01", "type": "conflict", "note": "요일이 부딪힌다", "requirement_ids": ["REQ-01"]}
    open_src = {"findings": [finding], "questions": []}
    assert [w["target"] for w in unresolved_conflicts(open_src)] == ["FND-01"]
    answered = {"id": "Q-01", "status": "answered", "finding_refs": ["FND-01"]}
    assert unresolved_conflicts({"findings": [finding], "questions": [answered]}) == []


# --- first-time reader rules ----------------------------------------------------------------------
def test_summary_present_complete_and_short() -> None:
    assert q.summary_problems(["고객은 매주 꽃을 받습니다.", "결제는 자동입니다."]) == []
    assert q.summary_problems([]) == ["missing"]
    assert q.summary_problems(["고객 매주 꽃"]) == ["fragment"]
    assert q.summary_problems([f"문장 {i}입니다." for i in range(6)]) == ["too_long"]


def test_brd_length() -> None:
    assert q.brd_too_long("가" * (q.BRD_MAX_CHARS + 1)) is True
    assert q.brd_too_long("가" * q.BRD_MAX_CHARS) is False


def test_glossary_explanations() -> None:
    lines = ["PRD 에는 인수 조건이 있습니다."]
    assert q.missing_explanations(lines) == ["PRD", "인수 조건"]
    annotated = q.annotate_terms(lines)
    assert q.missing_explanations(annotated) == []
    assert annotated[0].startswith("PRD(") and annotated == q.annotate_terms(annotated)


def test_glossary_explanations_contain_no_other_terms() -> None:
    terms = [g["term"] for g in q.GLOSSARY]
    for entry in q.GLOSSARY:
        assert not [t for t in terms if t in entry["explain"]], entry


def test_client_jargon() -> None:
    assert q.client_jargon("REQ-01 의 인수 조건을 골라 주세요") == ["인수 조건", "REQ-"]
    assert q.client_jargon("고객이 요일을 고르나요?") == []


def test_quote_and_interpretation_are_separate() -> None:
    texts = {"SRC-01": "배송은 토요일에 나가요."}
    assert q.quote_interpretation_problem(["SRC-01", "배송은 토요일에 나가요.", "배송 요일은 토요일이다"], texts) is False
    assert q.quote_interpretation_problem(["SRC-01", "배송은 토요일", "배송 요일은 토요일이다"], texts) is True
    assert q.quote_interpretation_problem(["SRC-01", "배송은 토요일에 나가요.", "배송은 토요일에 나가요."], texts) is True


def test_problem_section_has_no_solution() -> None:
    assert q.solution_words("결제 화면에 버튼을 만든다") == ["화면", "버튼"]
    assert q.solution_words("사장이 결제를 매주 손으로 챙긴다") == []


def test_quality_warnings_attach_to_items_and_documents() -> None:
    source = {"requirements": [req(statement="배송은 빨리 한다", exceptions=[])], "questions": [
        {"id": "Q-01", "question": "REQ-01 을 바꿀까요?", "why": "", "options": ["예", "아니요"], "status": "pending"}]}
    docs = {k: {"summary": [], "sections": []} for k in ("brd", "prd", "screens", "tests")}
    warnings = q.quality_warnings(source, docs)
    codes = {(w["code"], w["target"], w["doc"]) for w in warnings}
    assert ("quality.ambiguous", "REQ-01", "prd") in codes
    assert ("quality.no_exceptions", "REQ-01", "prd") in codes
    assert ("quality.client_jargon", "Q-01", "client") in codes
    assert ("quality.summary", "brd", "brd") in codes
    assert all(w["severity"] == "info" for w in warnings)
