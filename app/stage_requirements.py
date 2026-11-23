from __future__ import annotations
"""S3 (PM candidates → QA findings → coordinator question cards) and S4 (PM finalizes requirements)."""

from collections.abc import Mapping, Sequence
from typing import Any

from app.company import (QUESTION_CARDS_COMPANY, TASK_CARDS_COMPANY, TASK_PM_COMPANY, settled_candidates,
                         write_settled)
from app.schemas import (
    CATEGORIES, FINDING_TYPES, PRIORITIES, QA_FINDINGS, QUESTION_CARDS, REQ_STATUSES, REQUIREMENTS,
)
from app.agent_runner import AgentOutputError
from app.checks import consistency_violations
from app.config import LinerKeyMissingError
from app.liner import LinerAPIError, LinerConfigError
from app.stage_common import (
    FIRST_ROUND_MAX_CARDS, UNCARDED, UNKNOWN_OPTION, StageContext, report_answer_consistency, str_list,
)
from app.placement import ask_placement, separated
from app import team_defaults
from app.systems import ADD, REUSE, TASK_PM_SYSTEMS, requirement_features, requirement_systems

TASK_PM_CANDIDATES = (
    "단계 S3 구체화: 원문(sources)·문제 진술·범위·출처(evidence)를 근거로 요구사항 후보를 만들어라. "
    "요구사항마다 id(REQ-01 형식), 제목, 한 문장 진술, 분류(SFR 기능/PER 성능/SER 보안/DAR 데이터/INR 인터페이스/"
    "COR 제약), 중요도(상/중/하), 인수 조건(given/when/then), 예외, 상태, 근거 원문 ID(source_refs), "
    "출처 ID(evidence_refs), 반영한 결정 ID(decision_refs), 기대는 요구사항 id(depends_on)를 적어라."
    + TASK_PM_SYSTEMS
)
MAX_RULE_FINDINGS = 4  # 제안: rule gaps come after the other three kinds and never crowd them out of the cards
TASK_QA = (
    "PM 의 요구사항 후보(requirements)를 원문과 대조해 먼저 (1) 서로 부딪히는 곳 conflict (2) 실패·취소·지연 같은 "
    "예외가 빠진 곳 missing_exception (3) 완료 기준이 없어 확인할 수 없는 곳 missing_acceptance 를 빠짐없이 지적하라. "
    "그다음 (4) 만드는 사람이 마음대로 정해야 하는 동작 규칙이 빠진 곳 missing_rule 을 영향이 큰 것부터 "
    f"최대 {MAX_RULE_FINDINGS}건 지적하라. missing_rule 은 이런 것이다: 상태·결과가 어떤 값들 중 하나인지(값 목록), "
    "횟수·한도를 무엇 단위로 어디부터 세는지, 한 단계의 결과가 다음 단계로 무엇을 넘기는지, 시각을 무엇 기준으로 재고 "
    "경계(정각·이상·초과)를 넣는지, 필요한 값이 없을 때 어떻게 하는지. 원문이나 요구사항에 이미 정해져 있으면 지적하지 "
    "않는다. 지적마다 관련 요구사항 id 와 근거 원문 ID 를 붙이고 무엇이 문제인지 note 에 한 문장으로 적어라."
)
FAILURES = (AgentOutputError, LinerAPIError, LinerConfigError, LinerKeyMissingError)
TASK_PM_FIX = (
    "S4 확정본의 요구사항 일부가 발주사가 고른 답과 맞지 않는다(추가 입력). 요구사항 목록 전체를 다시 내되, 지적된 요구사항만 "
    "고쳐라: 그 결정이 정말 반영된 요구사항이면 고른 답의 문구를 한 글자도 바꾸지 않고 제목·진술·인수 조건 중 한 곳에 넣고, "
    "관련만 있는 요구사항이면 decision_refs 에서 그 결정 ID 를 빼라. 지적되지 않은 요구사항은 그대로 둔다."
)
TASK_CARDS = (
    "QA 지적(추가 입력의 findings)을 발주사가 고를 수 있는 질문 카드로 바꿔라. 카드마다 쉬운 말 질문, 왜 묻는지 "
    "한 줄(why), 선택지 2~4개(options — '잘 모르겠어요'와 직접 입력은 시스템이 붙이므로 넣지 않는다), 발주사가 "
    "모를 때 쓸 기본값(default_option — options 중 하나, 출처가 있으면 출처를 따른다), 관련 원문·출처·지적·"
    "요구사항 ID를 적어라. 카드는 발주사만 정할 수 있는 것만 만든다 — 원문·출처로 답이 정해지거나 업계 관행으로 "
    "정해도 되는 지적은 카드로 만들지 않는다. 같은 요구사항의 같은 결정에 걸린 지적들은 한 장으로 묶고 finding_refs 에 "
    "모두 적는다. 장수는 지적 내용이 정한다 — 발주사만 정할 수 있는 지적은 하나도 빼지 않고 카드로 만든다(빠지면 나중에 "
    f"빈칸이 된다). 지적이 적고 대부분 정해져 있으면 한두 장이어도 된다. 상한은 {FIRST_ROUND_MAX_CARDS}장, 중요한 것부터. 지적은 conflict·missing_exception·missing_acceptance 가 "
    "먼저 오고 missing_rule 이 뒤에 온다 — 앞의 세 종류를 카드로 다 만든 뒤 남는 자리에만 missing_rule 카드를 만든다. "
    "이미 답한 질문(questions)은 다시 묻지 않는다."
)
TASK_PM_FINAL = (
    "단계 S4 원본 확정: 발주사 답(decisions)과 질문 카드(questions)를 반영해 요구사항 목록을 확정하라. 필드는 S3 와 같다. "
    "상태는 원문이나 발주사가 고른 답에 근거하면 '확정', 기본값·추정으로 채웠으면 '가정', 아직 답이 없으면 '미결'. "
    "결정 ID 는 그 결정에서 발주사가 고른 답의 문구를 제목·진술·인수 조건 중 한 곳에 한 글자도 바꾸지 않고 넣은 요구사항의 "
    "decision_refs 에만 적어라 — 관련만 있고 그 문구가 없는 요구사항에는 적지 않는다. 고르지 않은 선택지의 문구는 쓰지 않는다."
    + TASK_PM_SYSTEMS
)


# Shared-source kinds each call's task refers to (AgentRunner.ask `reads`): the rest of the agent's read list
# (screens, tests, prototype, confirmations, feedback …) is not sent — less context per call, same task.
# `requirements` in the candidates call keeps the previous list visible when CP2 sends S3 back.
READS_PM_CANDIDATES = ("systems", "sources", "evidence", "problem_statement", "scope", "decisions", "requirements")
READS_QA = ("sources", "requirements")
READS_CARDS = ("company", "sources", "evidence", "requirements", "decisions", "questions")
READS_PM_FINAL = ("systems", "sources", "evidence", "requirements", "questions", "decisions")
READS_PM_FIX = ("systems", "requirements", "questions", "decisions")

def run_s3(ctx: StageContext) -> bool:
    """Returns True when new question cards wait for the client."""
    ctx.bus.send("coordinator", "pm", TASK_PM_CANDIDATES)
    out = ctx.runner.ask("pm", TASK_PM_CANDIDATES, "requirement_candidates", REQUIREMENTS, ctx.feedback_extra(),
                         reads=READS_PM_CANDIDATES)
    ctx.ws.write_all("pm", "requirements", normalize_requirements(ctx, out.get("requirements")))
    placed = ask_placement(ctx)  # a built service the memo never named: ask before fixing requirements
    ctx.bus.send("pm", "qa", f"요구사항 후보 {len(ctx.ws.items('requirements'))}건 검토 요청")
    qa = ctx.runner.ask("qa", TASK_QA, "qa_findings", QA_FINDINGS, ctx.gap_extra(), reads=READS_QA)
    findings = record_findings(ctx, qa.get("findings"))
    ctx.bus.send("qa", "pm", f"지적 {len(findings)}건")
    ctx.bus.send("qa", "coordinator", f"지적 {len(findings)}건 — 질문 카드로 바꿔 주세요")
    if not findings:
        return placed > 0
    has_company = bool(ctx.ws.items("company"))
    task, schema = (TASK_CARDS + TASK_CARDS_COMPANY, QUESTION_CARDS_COMPANY) if has_company else (TASK_CARDS, QUESTION_CARDS)
    out = ctx.runner.ask("coordinator", task, "question_cards", schema, {"findings": findings}, reads=READS_CARDS)
    candidates = settled_candidates(ctx, findings, out.get("settled")) if has_company else {}
    before = {q["id"] for q in ctx.ws.items("questions")}
    added = record_cards(ctx, out.get("cards"), taken=placed, settled=frozenset(candidates))
    carded = {ref for q in ctx.ws.items("questions") if q["id"] not in before for ref in q.get("finding_refs", [])}
    settled = write_settled(ctx, findings, {k: v for k, v in candidates.items() if k not in carded})  # a card wins
    if settled:
        ctx.bus.send("coordinator", "pm", f"회사 자료로 이미 정해진 지적 {len(settled)}건은 묻지 않고 결정으로 남겼어요")
    keep_uncarded(ctx, [f for f in findings if f["id"] not in settled], out.get("cards"))
    defaults = team_defaults.propose(ctx)  # 11-22: said at the question stage, not left for CP3
    if added:
        ctx.bus.send("coordinator", "client", f"질문 카드 {added}장을 한 장씩 보여 드립니다")
    return added + placed + defaults > 0


def run_s4(ctx: StageContext) -> None:
    task = TASK_PM_FINAL + (TASK_PM_COMPANY if ctx.ws.items("company") else "")  # D2: the client's answer wins
    ctx.bus.send("coordinator", "pm", task)
    out = ctx.runner.ask("pm", task, "requirements_final", REQUIREMENTS, ctx.feedback_extra(),
                         reads=READS_PM_FINAL)
    ctx.ws.write_all("pm", "requirements", normalize_requirements(ctx, out.get("requirements")))
    fix_answer_consistency(ctx)
    counts = {s: sum(r["status"] == s for r in ctx.ws.items("requirements")) for s in ("확정", "가정", "미결", "미확인")}
    ctx.bus.send("pm", "coordinator", "요구사항 정리 완료: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    report_answer_consistency(ctx)


def fix_answer_consistency(ctx: StageContext) -> None:
    """One self-repair pass when requirements disagree with the client's answers (before CP2 blocks them).
    Code keeps the final say: the repair is kept only when it leaves fewer violations. Fail-open on errors."""
    before = consistency_violations(ctx.ws.source)
    if not before:
        return
    ctx.bus.send("coordinator", "pm", f"고른 답과 다른 요구사항 {len(before)}건 — 한 번 고쳐 주세요")
    try:
        out = ctx.runner.ask("pm", TASK_PM_FIX, "requirements_fix", REQUIREMENTS,
                             {"고른 답과 다른 요구사항": [v["message"] for v in before]}, reads=READS_PM_FIX)
    except FAILURES as exc:
        ctx.ws.emit("check_result", "coordinator", {"check": "answer_fix", "outcome": "skipped", "items": [],
                                                    "details": [f"스스로 고치지 못했어요: {exc}"]})
        return
    previous = list(ctx.ws.items("requirements"))
    ctx.ws.write_all("pm", "requirements", normalize_requirements(ctx, out.get("requirements")))
    after = consistency_violations(ctx.ws.source)
    kept = len(after) < len(before)
    if not kept:
        ctx.ws.write_all("pm", "requirements", previous)
    ctx.ws.emit("check_result", "coordinator", {
        "check": "answer_fix", "outcome": "passed" if kept and not after else "flagged", "items": [],
        "details": [f"고른 답과 다른 요구사항 {len(before)}건 → {len(after)}건" + ("" if kept else " (줄지 않아 고치기 전으로 둠)")]})


def record_findings(ctx: StageContext, raw: Any) -> list[dict[str, Any]]:
    """Valid findings, the three classic kinds first and at most MAX_RULE_FINDINGS rule gaps after them."""
    items = [i for i in (raw if isinstance(raw, list) else []) if isinstance(i, Mapping) and i.get("type") in FINDING_TYPES]
    rules = [i for i in items if i["type"] == "missing_rule"][:MAX_RULE_FINDINGS]
    findings = []
    for item in [*(i for i in items if i["type"] != "missing_rule"), *rules]:
        finding = {"id": ctx.ws.next_id("findings", "FND"), "type": item["type"], "note": str(item.get("note", "")),
                   "requirement_ids": str_list(item.get("requirement_ids")),
                   "source_refs": str_list(item.get("source_refs"))}
        ctx.ws.write("qa", "findings", finding)
        findings.append(finding)
    return findings


def card_options(raw: Mapping[str, Any]) -> list[str]:
    options = []
    for option in str_list(raw.get("options")):
        if option.strip() and option.strip() != UNKNOWN_OPTION and option.strip() not in options:
            options.append(option.strip())
    return options


# D5 (11-20): over the round cap, the cards that stay are the ones on a conflict first, then a missing exception,
# a missing acceptance, a missing rule (the cap is FIRST_ROUND_MAX_CARDS).
CARD_RANK = {"conflict": 0, "missing_exception": 1, "missing_acceptance": 2, "missing_rule": 3}


def record_cards(ctx: StageContext, raw: Any, taken: int = 0, settled: frozenset[str] = frozenset()) -> int:
    """FR-06: keep valid cards (2–4 options) up to the round cap (`taken` places already used by code-made cards),
    chosen by the kind of finding they are on and written in the order given; the rest become open items. An open
    item does not name findings the company material settled (`settled`), and is skipped when none are left."""
    items = [i for i in (raw if isinstance(raw, list) else []) if isinstance(i, Mapping)]
    types = {f["id"]: f.get("type") for f in ctx.ws.items("findings")}
    valid = [n for n, i in enumerate(items) if str(i.get("question", "")).strip() and 2 <= len(card_options(i)) <= 4]
    rank = {n: min((CARD_RANK.get(str(types.get(ref)), 4) for ref in str_list(items[n].get("finding_refs"))), default=4)
            for n in valid}
    kept = set(sorted(valid, key=lambda n: (rank[n], n))[:max(FIRST_ROUND_MAX_CARDS - taken, 0)])
    added = 0
    for n, item in enumerate(items):
        question = str(item.get("question", "")).strip()
        if n not in kept:
            # as before: a card past the point where the cap was full in the given order is 「over the cap」
            full = n in rank or sum(1 for v in valid if v < n) + taken >= FIRST_ROUND_MAX_CARDS
            reason = "이번 회차 카드 수 상한 초과" if full else "선택지 2~4개 조건 불충족"
            refs = str_list(item.get("finding_refs"))
            left = [r for r in refs if r not in settled]
            if refs and not left:
                continue  # every finding it was on is settled by the company material
            ctx.ws.write("coordinator", "open_items", {
                "id": ctx.ws.next_id("open_items", "OPEN"), "title": question or "(빈 질문)", "reason": reason,
                "source_refs": str_list(item.get("source_refs")), "finding_refs": left})
            continue
        options = card_options(item)
        default = str(item.get("default_option", ""))
        ctx.ws.write("coordinator", "questions", {
            "id": ctx.ws.next_id("questions", "Q"), "question": question, "why": str(item.get("why", "")),
            "options": options, "unknown_option": UNKNOWN_OPTION, "allow_free_text": True,
            "default_option": default if default in options else options[0],
            "source_refs": str_list(item.get("source_refs")), "evidence_refs": str_list(item.get("evidence_refs")),
            "finding_refs": str_list(item.get("finding_refs")),
            "requirement_refs": str_list(item.get("requirement_refs")), "status": "pending", "answer": None,
        })
        added += 1
    return added




def keep_uncarded(ctx: StageContext, findings: Sequence[Mapping[str, Any]], raw_cards: Any) -> None:
    """A QA finding no card names (kept or turned into an open item) would otherwise vanish before AGENTS.md:
    keep it as an open item so the coding AI still sees the decision it needs."""
    named = {ref for item in (raw_cards if isinstance(raw_cards, list) else []) if isinstance(item, Mapping)
             for ref in str_list(item.get("finding_refs"))}
    for f in findings:
        if f["id"] in named:
            continue
        ctx.ws.write("coordinator", "open_items", {
            "id": ctx.ws.next_id("open_items", "OPEN"), "title": f["note"] or f["id"], "reason": UNCARDED,
            "source_refs": list(f["source_refs"]), "finding_refs": [f["id"]],
            "requirement_refs": list(f["requirement_ids"])})


def normalize_requirements(ctx: StageContext, raw: Any) -> list[dict[str, Any]]:
    """Assign REQ-xx ids in order, map depends_on to the new ids, then apply G1/G5 status rules."""
    items = [r for r in (raw if isinstance(raw, list) else []) if isinstance(r, Mapping)]
    id_map: dict[str, str] = {}
    for i, r in enumerate(items, start=1):
        id_map.setdefault(str(r.get("id")), f"REQ-{i:02d}")
    apart = separated(ctx.ws.items("decisions"))  # services the client chose to keep out of this request
    systems = [s for s in ctx.ws.items("systems") if s["id"] not in apart]
    reqs = [requirement_item(r, f"REQ-{i:02d}", id_map, systems) for i, r in enumerate(items, start=1)]
    return [{**r, "status": apply_status_rules(ctx, r)} for r in reqs]


def requirement_item(raw: Mapping[str, Any], rid: str, id_map: Mapping[str, str],
                     systems: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    acceptance = raw.get("acceptance") if isinstance(raw.get("acceptance"), Mapping) else {}
    system_refs, change = requirement_systems(raw, [s["id"] for s in systems])
    features = requirement_features(raw, systems, system_refs)  # 재사용 needs a real feature, else it is 기능 추가
    return {
        "id": rid, "title": str(raw.get("title", "")), "statement": str(raw.get("statement", "")),
        "category": raw.get("category") if raw.get("category") in CATEGORIES else "SFR",
        "priority": raw.get("priority") if raw.get("priority") in PRIORITIES else "중",
        "acceptance": {k: str(acceptance.get(k, "")) for k in ("given", "when", "then")},
        "exceptions": str_list(raw.get("exceptions")),
        "status": raw.get("status") if raw.get("status") in REQ_STATUSES else "미결",
        "source_refs": str_list(raw.get("source_refs")), "evidence_refs": str_list(raw.get("evidence_refs")),
        "decision_refs": str_list(raw.get("decision_refs")),
        "depends_on": [id_map[d] for d in str_list(raw.get("depends_on")) if d in id_map and id_map[d] != rid],
        "system_refs": system_refs, "change": change if change != REUSE or features else ADD,
        "feature_refs": features,
        "screens": [], "tests": [], "owner_agent": "pm",
    }


def apply_status_rules(ctx: StageContext, req: Mapping[str, Any]) -> str:
    """G1: unverified/unknown evidence → 미확인. G5: no valid basis or an assumed decision → 가정."""
    evidence = {e["id"]: e for e in ctx.ws.items("evidence")}
    sources = {s["id"] for s in ctx.ws.items("sources")}
    decisions = {d["id"]: d for d in ctx.ws.items("decisions")}
    if any(evidence.get(ref, {}).get("status") != "확인" for ref in req["evidence_refs"]):
        ctx.ws.guardrail("G1", "flagged", "확인되지 않은 출처를 인용한 요구사항", actor="pm", item=req["id"])
        return "미확인"
    has_basis = any(r in sources for r in req["source_refs"]) or bool(req["evidence_refs"])
    if not has_basis:
        ctx.ws.guardrail("G5", "flagged", "근거 없이 채운 요구사항 → 가정", actor="pm", item=req["id"])
        return "가정"
    if req["status"] == "확정" and any(decisions.get(d, {}).get("status") == "가정" for d in req["decision_refs"]):
        return "가정"
    return req["status"]
