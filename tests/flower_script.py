from __future__ import annotations
"""Scripted agent outputs for the flower memo. Hand-written test data, not app prompts."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.intake import split_sentences

MEMO_PATH = Path(__file__).resolve().parent.parent / "examples" / "flower-subscription" / "request_memo.md"

SNIPPET = "정기 결제가 실패하면 대부분의 구독 서비스는 3일 안에 한 번 더 결제를 시도한다."
SEARCH_BODY = {"results": [{"title": "구독 결제 실패 처리", "url": "https://example.com/billing", "snippet": SNIPPET}]}


def memo_chunks() -> list[str]:
    """The pasted part of the memo (messages after the separator), split into two chunks."""
    body = MEMO_PATH.read_text(encoding="utf-8").split("\n---\n", 1)[1].strip()
    monday, tuesday = body.split("**[화", 1)
    return [monday.strip(), "**[화" + tuesday.strip()]


def src_id(chunks: list[str], fragment: str) -> str:
    return next(s["id"] for s in split_sentences(chunks) if fragment in s["text"])


def claim(text: str, refs: list[str], quote: str) -> dict[str, Any]:
    return {"text": text, "refs": refs, "quote": quote}


def problem_scope(chunks: list[str]) -> dict[str, Any]:
    weekly, seoul = src_id(chunks, "일주일에 한 번"), src_id(chunks, "서울만")
    return {
        "who": "꽃집 「꽃님」 사장과 정기구독 고객",
        "pain": "주 1회 꽃 구독을 받고 결제할 수단이 없다",
        "done": "고객이 구독을 신청하고 매주 꽃을 받는다",
        "claims": [claim("고객은 일주일에 한 번 꽃을 받는다", [weekly], "일주일에 한 번 꽃을 받는")],
        "scope_in": [claim("주 1회 정기구독", [weekly], "일주일에 한 번")],
        "scope_out": [claim("서울 밖 배송", [seoul], "서울만")],
        "interpretations": [claim("배송 지역은 서울로 한정", [seoul], "일단 서울만")],
        "research_requests": ["정기구독 결제 실패 처리 관행"],
    }


def research_evidence(_: list[str]) -> dict[str, Any]:
    return {"evidence": [{"result_id": "R1-1", "quote": "3일 안에 한 번 더 결제를 시도한다",
                          "fact": "구독 결제 실패 시 3일 안에 재시도하는 것이 흔하다"}], "not_found": []}


def requirement(rid: str, title: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    base = {
        "id": rid, "title": title, "statement": f"{title} 기능을 제공한다", "category": "SFR",
        "priority": "상", "acceptance": {"given": "구독 고객이", "when": f"{title}을 하면", "then": "처리된다"},
        "exceptions": [], "status": "확정", "source_refs": refs, "evidence_refs": [],
        "decision_refs": [], "depends_on": [],
    }
    return {**base, **extra}


def candidates(chunks: list[str]) -> dict[str, Any]:
    day, saturday = src_id(chunks, "요일은 고객이"), src_id(chunks, "토요일")
    pay = src_id(chunks, "매주 자동결제")
    return {"requirements": [
        requirement("REQ-01", "배송 요일 선택", [day, saturday], status="미결"),
        requirement("REQ-02", "자동결제", [pay], depends_on=["REQ-01"], status="미결"),
    ]}


def qa_findings(chunks: list[str]) -> dict[str, Any]:
    day, saturday = src_id(chunks, "요일은 고객이"), src_id(chunks, "토요일")
    pay = src_id(chunks, "매주 자동결제")
    return {"findings": [
        {"type": "conflict", "requirement_ids": ["REQ-01"], "source_refs": [day, saturday],
         "note": "고객 요일 선택과 토요일 일괄 배송이 부딪힌다"},
        {"type": "missing_exception", "requirement_ids": ["REQ-02"], "source_refs": [pay],
         "note": "결제 실패 시 처리가 없다"},
    ]}


def card(question: str, options: list[str], refs: list[str], **extra: Any) -> dict[str, Any]:
    base = {"question": question, "why": "원문 두 문장이 서로 다릅니다", "options": options,
            "default_option": options[0], "source_refs": refs, "evidence_refs": [],
            "finding_refs": ["FND-01"], "requirement_refs": ["REQ-01"]}
    return {**base, **extra}


def question_cards(chunks: list[str]) -> dict[str, Any]:
    day, saturday = src_id(chunks, "요일은 고객이"), src_id(chunks, "토요일")
    pay = src_id(chunks, "매주 자동결제")
    return {"cards": [
        card("고객이 요일을 고르나요, 토요일에 한꺼번에 보내나요?", ["고객이 고름", "토요일 일괄", "수·토 중 고름"],
             [day, saturday]),
        card("결제가 실패하면 어떻게 할까요?", ["3일 안에 다시 결제", "바로 구독 정지"], [pay],
             why="결제 실패 처리가 없습니다", evidence_refs=["EV-01"], finding_refs=["FND-02"],
             requirement_refs=["REQ-02"]),
    ]}


def final_requirements_for(chunks: list[str], day: str, pay: str) -> dict[str, Any]:
    """S4 output that reflects the given answers (day: DEC-01, pay: DEC-02)."""
    saturday, pay_src = src_id(chunks, "토요일"), src_id(chunks, "매주 자동결제")
    return {"requirements": [
        requirement("REQ-01", f"배송 요일 {day}", [saturday], decision_refs=["DEC-01"],
                    statement=f"배송 요일은 {day} 방식으로 정한다"),
        requirement("REQ-02", "자동결제와 실패 처리", [pay_src], evidence_refs=["EV-01"],
                    decision_refs=["DEC-02"], depends_on=["REQ-01"],
                    statement=f"매주 카드 자동결제가 실패하면 {pay}",
                    exceptions=["카드가 만료되면 결제 실패로 처리한다"]),
    ]}


def decisions_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the decisions the PM was given (the shared-source JSON in the user message)."""
    content = payload["messages"][-1]["content"]
    body = content.split("[공유 원본 — 읽기 권한 항목]\n", 1)[1].split("\n\n[추가 입력]", 1)[0]
    return json.loads(body).get("decisions", [])


def final_requirements(chunks: list[str]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """A PM that writes the chosen answers into the requirements (the consistent case)."""
    def build(payload: dict[str, Any]) -> dict[str, Any]:
        chosen = {d["id"]: d["chosen"] for d in decisions_from_payload(payload)}
        return final_requirements_for(chunks, chosen.get("DEC-01", "토요일 일괄"),
                                      chosen.get("DEC-02", "3일 안에 다시 결제"))
    return build


def element(name: str, kind: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    base = {"name": name, "kind": kind, "description": f"{name}을 보여 준다", "action": "",
            "input_rule": "", "requirement_refs": refs}
    return {**base, **extra}


def screen_spec(_: list[str]) -> dict[str, Any]:
    return {
        "summary": ["고객은 구독 신청 화면에서 배송 요일과 결제 카드를 정합니다.",
                    "결제가 실패하면 결제 안내 화면에서 다시 결제합니다."],
        "flow": ["S-A", "S-B"],
        "screens": [
            {"id": "S-A", "title": "구독 신청", "purpose": "구독을 시작한다",
             "elements": [element("사이즈 선택", "select", ["REQ-01"], input_rule="S·M 중 하나, 필수"),
                          element("배송 요일", "select", ["REQ-01"], input_rule="필수"),
                          element("카드 입력", "input", ["REQ-02"], input_rule="숫자 16자리, 필수"),
                          element("신청하기", "button", ["REQ-01", "REQ-02"], action="누르면 결제 후 완료 안내")],
             "states": {"empty": "선택 전에는 신청하기가 비활성", "loading": "결제 중 표시",
                        "error": "결제 실패 시 결제 안내로 이동"},
             "requirement_refs": ["REQ-01", "REQ-02"]},
            {"id": "S-B", "title": "결제 안내", "purpose": "실패한 결제를 다시 한다",
             "elements": [element("실패 안내 문구", "text", ["REQ-02"]),
                          element("다시 결제", "button", ["REQ-02"], action="누르면 재결제")],
             "states": {"empty": "실패 내역이 없으면 안내 없음", "loading": "재결제 중 표시",
                        "error": "재결제도 실패하면 고객센터 안내"},
             "requirement_refs": ["REQ-02", "REQ-99"]},
        ],
        "no_screen": [],
        "swimlane": flower_swimlane(),
    }


def lane_step(sid: str, lane: str, label: str, after: list[str], screen: str = "", kind: str = "normal",
              note: str = "") -> dict[str, Any]:
    return {"id": sid, "lane": lane, "label": label, "screen_ref": screen, "after": after, "kind": kind, "note": note}


def flower_swimlane() -> dict[str, Any]:
    """Who does what in the flower subscription, with the card-payment failure branch."""
    return {"lanes": ["고객", "앱", "사장"], "steps": [
        lane_step("c1", "고객", "사이즈와 배송 요일 고르기", [], "S-A"),
        lane_step("c2", "고객", "카드 입력하고 신청하기", ["c1"], "S-A"),
        lane_step("a1", "앱", "카드로 첫 결제하기", ["c2"]),
        lane_step("a2", "앱", "구독 시작 안내 보내기", ["a1"]),
        lane_step("o1", "사장", "주문 목록에서 배송 준비", ["a2"]),
        lane_step("x1", "앱", "결제 실패 안내 띄우기", ["a1"], "S-B", "exception", "결제 실패"),
        lane_step("x2", "고객", "다시 결제 누르기", ["x1"], "S-B"),
        lane_step("x3", "사장", "실패 주문 확인하고 연락", ["x2"], "", "exception", "재결제도 실패"),
    ]}


def tc_item(tid: str, title: str, refs: list[str], kind: str, **extra: Any) -> dict[str, Any]:
    base = {"id": tid, "title": title, "objective": f"{title}을 확인한다", "requirement_refs": refs,
            "screen_refs": ["S-A"], "priority": "상", "preconditions": "구독하지 않은 고객",
            "inputs": "사이즈 S, 첫 번째로 보이는 배송 요일", "steps": ["구독 신청 화면을 연다", "신청하기를 누른다"],
            "expected": "구독이 시작된다", "kind": kind}
    return {**base, **extra}


def qa_test_cases(_: list[str]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def build(payload: dict[str, Any]) -> dict[str, Any]:
        content = payload["messages"][-1]["content"]
        screen = "SCR-01" if "SCR-01" in content else "S-A"
        return {
            "summary": ["배송 요일을 고르고 신청하면 구독이 시작되면 통과입니다.",
                        "요일을 고르지 않으면 신청할 수 없으면 통과입니다."],
            "tests": [tc_item("T1", "요일 고르고 신청", ["REQ-01"], "긍정", screen_refs=[screen]),
                      tc_item("T2", "요일 없이 신청", ["REQ-01"], "부정", screen_refs=[screen],
                                expected="신청하기가 눌리지 않는다")],
        }
    return build


def document_content(chunks: list[str]) -> dict[str, Any]:
    weekly, saturday = src_id(chunks, "일주일에 한 번"), src_id(chunks, "토요일")
    seoul = src_id(chunks, "서울만")
    return {
        "brd": {
            "summary": ["꽃집 꽃님의 사장은 정기구독 고객을 손으로 관리하고 있습니다.",
                        "고객은 매주 한 번 꽃을 받기를 바랍니다.",
                        "사장은 결제와 배송 요일 관리가 번거롭다고 말했습니다.",
                        "이번 일은 구독 신청과 자동결제를 먼저 갖추는 것입니다.",
                        "성공하면 사장이 매주 결제를 따로 챙기지 않아도 됩니다."],
            "background": [{"src_id": weekly, "interpretation": "고객은 주 1회 받는 정기구독을 원한다"},
                           {"src_id": saturday, "interpretation": "가게는 배송을 한 요일에 모으고 싶어 한다"}],
            "goals": [{"goal": "매주 꽃 받기", "criterion": "신청 후 7일 안에 첫 배송", "status": "확정"},
                      {"goal": "결제 챙김 줄이기", "criterion": "사장이 결제를 덜 챙긴다", "status": "확정"}],
            "non_goals": [{"item": "서울 밖 배송", "reason": "가게가 직접 배송할 수 있는 곳만 먼저 한다",
                           "refs": [seoul]}],
            "constraints": ["배송 지역은 서울이다"],
            "risks": [{"risk": "결제 실패가 쌓인다", "impact": "꽃을 사 두고 돈을 못 받는다",
                       "response": "재결제 안내 화면을 둔다"}],
        },
        "prd": {
            "summary": ["고객은 배송 요일을 정해 구독을 신청합니다.",
                        "결제는 매주 카드로 자동으로 됩니다.",
                        "결제가 실패하면 정해진 방식으로 다시 결제합니다."],
            "decision_notes": [{"decision_id": "DEC-01", "reason": "발주사가 직접 골랐다"}],
        },
    }


def flower_outputs(chunks: list[str]) -> dict[str, list[Any]]:
    return {
        "problem_scope": [problem_scope(chunks)],
        "problem_done": [{"done": "고객이 수·토 중 배송 요일을 골라 구독을 신청하고, 결제가 실패해도 3일 안에 다시 결제되어 매주 꽃을 받는다"}],
        "research_evidence": [research_evidence(chunks)],
        "requirement_candidates": [candidates(chunks)],
        "qa_findings": [qa_findings(chunks)],
        "question_cards": [question_cards(chunks)],
        "requirements_final": [final_requirements(chunks)],
        "screen_spec": [screen_spec(chunks)],
        "test_cases": [qa_test_cases(chunks)],
        "document_content": [document_content(chunks)],
        "prototype": [prototype_output()],
        "consumer_feedback": [consumer_feedback],
        "change_mapping": [change_mapping],
        "requirements_revision": [requirements_revision],
        "complaint_check": [complaint_check],
    }


def extra_input(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload["messages"][-1]["content"]
    return json.loads(content.split("[추가 입력]\n", 1)[1]) if "[추가 입력]\n" in content else {}


def change_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    """A PM that maps payment wording to REQ-02 and anything else to REQ-01 (scripted, not a model)."""
    utterance = str(extra_input(payload).get("변경 요청", ""))
    target = "REQ-02" if "결제" in utterance else "REQ-01"
    return {"target": target, "after_statement": f"{utterance} — 발주사 변경 요청을 반영한다",
            "summary": f"{target} 진술을 변경 요청대로 고친다",
            "rationale": "결제 이야기라 자동결제 요구사항" if target == "REQ-02" else "배송 일정 이야기라 배송 요일 요구사항"}


def requirements_revision(payload: dict[str, Any]) -> dict[str, Any]:
    """A PM that swaps every superseded answer for the new key phrase and rewrites the target's acceptance."""
    extra = extra_input(payload)
    brief = extra.get("변경") or {}
    utterance = str(brief.get("발주사 말", ""))
    key = utterance.removesuffix(" 해 주세요").removesuffix(" 되게").removesuffix(" 수 있게")
    old = [str(d["이전 답"]) for d in brief.get("대체된 결정", []) if d.get("이전 답")]

    def swap(text: str) -> str:
        for phrase in old:
            text = text.replace(phrase, key)
        return text

    out = []
    for req in extra.get("고칠 수 있는 요구사항", []):
        acceptance = {k: swap(v) for k, v in req["acceptance"].items()}
        if req["관계"] == "바뀌는 곳":
            acceptance = {**acceptance, "then": f"{key}에 맞게 처리된다"}
        revised = {"id": req["id"], "title": req["title"], "statement": swap(req["statement"]),
                   "acceptance": acceptance, "exceptions": [swap(e) for e in req["exceptions"]]}
        if revised != {k: req[k] for k in revised}:
            out.append(revised)
    return {"after_key": key, "requirements": out}


def complaint_check(payload: dict[str, Any]) -> dict[str, Any]:
    """QA's comparison. For anything but 일요일 it (wrongly) says 새 변경 요청, so the code guard can be seen."""
    said = str(extra_input(payload).get("발주사 말", ""))
    if "일요일" in said:
        return {"requirement_ids": ["REQ-01"], "classification": "새 변경 요청", "requested": "일요일에도 배송",
                "reason": "확정된 배송 요일에는 일요일이 없습니다"}
    return {"requirement_ids": ["REQ-01"], "classification": "새 변경 요청", "requested": "수·토 중 고름",
            "reason": "배송 요일을 바꾸려는 것으로 보입니다"}


def consumer_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    """The consumer agent: screen comments before CP3, prototype comments before CP4 (SCR-99 is dropped)."""
    if '"prototype"' in payload["messages"][-1]["content"]:
        return {"items": [{"screen_id": "SCR-02", "kind": "헷갈림",
                           "comment": "결제가 실패했다는데 언제 다시 빠져나가는지 몰라서 불안해요"}]}
    return {"items": [
        {"screen_id": "SCR-01", "kind": "불편", "comment": "카드 번호를 매번 다 쳐야 하나요? 처음엔 좀 귀찮아요"},
        {"screen_id": "SCR-02", "kind": "포기 위험", "comment": "결제 실패 안내만 보면 꽃이 오는지 안 오는지 모르겠어요"},
        {"screen_id": "SCR-99", "kind": "불편", "comment": "없는 화면"},
    ]}


# A developer answer that uses the design-kit classes (the kit itself is injected by the app).
PROTOTYPE_HTML = (Path(__file__).resolve().parent / "flower_prototype.html").read_text(encoding="utf-8")


def prototype_output(html: str = PROTOTYPE_HTML) -> dict[str, Any]:
    return {"html": html, "summary": ["구독 신청 화면과 결제 안내가 있는 내 구독 화면을 만들었습니다."]}
