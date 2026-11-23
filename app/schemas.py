from __future__ import annotations
"""JSON schemas for agent outputs (Liner chat response_format=json_schema, strict)."""

from typing import Any

from app.systems import CHANGES, FITS

CATEGORIES = ("SFR", "PER", "SER", "DAR", "INR", "COR")
PRIORITIES = ("상", "중", "하")
REQ_STATUSES = ("확정", "가정", "미결")
FINDING_TYPES = ("conflict", "missing_exception", "missing_acceptance", "missing_rule")

STR: dict[str, Any] = {"type": "string"}
STR_LIST: dict[str, Any] = {"type": "array", "items": STR}


def obj(**props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def array(item: dict[str, Any], **limits: int) -> dict[str, Any]:
    return {"type": "array", "items": item, **limits}


def enum(values: tuple[str, ...]) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


CLAIM = obj(text=STR, refs=STR_LIST, quote=STR)

PROBLEM_SCOPE = obj(
    who=STR, pain=STR, done=STR,
    claims=array(CLAIM), scope_in=array(CLAIM), scope_out=array(CLAIM), interpretations=array(CLAIM),
    research_requests=STR_LIST,
    system_fit=array(obj(system_ref=STR, fit=enum(FITS), what=STR, refs=STR_LIST, quote=STR)),
    service_name=STR,
)

CLIENT_REPLY = obj(answer=STR, refs=STR_LIST)

# After CP2: the PM rewrites the problem statement's "done" line so it reflects the client's answers.
PROBLEM_DONE = obj(done=STR)

RESEARCH_EVIDENCE = obj(
    evidence=array(obj(result_id=STR, quote=STR, fact=STR)),
    alternatives=array(obj(name=STR, covers=STR, lacks=STR, result_id=STR, quote=STR)),
    not_found=STR_LIST,
)

REQUIREMENT = obj(
    id=STR, title=STR, statement=STR, category=enum(CATEGORIES), priority=enum(PRIORITIES),
    acceptance=obj(given=STR, when=STR, then=STR), exceptions=STR_LIST, status=enum(REQ_STATUSES),
    source_refs=STR_LIST, evidence_refs=STR_LIST, decision_refs=STR_LIST, depends_on=STR_LIST,
    system_refs=STR_LIST, change=enum(CHANGES), feature_refs=STR_LIST,
)
REQUIREMENTS = obj(requirements=array(REQUIREMENT))

QA_FINDINGS = obj(findings=array(obj(
    type=enum(FINDING_TYPES), requirement_ids=STR_LIST, source_refs=STR_LIST, note=STR,
)))

QUESTION_CARDS = obj(cards=array(obj(
    question=STR, why=STR, options=array(STR, minItems=2, maxItems=4), default_option=STR,
    source_refs=STR_LIST, evidence_refs=STR_LIST, finding_refs=STR_LIST, requirement_refs=STR_LIST,
)))
# 11-22: the team's default answer for each point the cards do not ask (app/team_defaults.py)
TEAM_DEFAULTS = obj(defaults=array(obj(id=STR, default=STR, why=STR)))

# --- S5 documentation ---------------------------------------------------------------------------
ELEMENT_KINDS = ("text", "input", "select", "button", "list", "image")
TC_KINDS = ("긍정", "부정", "경계")
GOAL_STATUSES = ("확정", "미결")

PLATFORMS = ("app", "web")

SWIMLANE_KINDS = ("normal", "exception")
# Role swimlane: one lane per role the client knows, steps follow `after`, exception steps carry a short note.
SWIMLANE = obj(
    lanes=array(STR, maxItems=5),
    steps=array(obj(id=STR, lane=STR, label=STR, screen_ref=STR, after=STR_LIST, kind=enum(SWIMLANE_KINDS),
                    note=STR), maxItems=16),
)

SCREEN_SPEC = obj(
    summary=STR_LIST, flow=STR_LIST, platform=enum(PLATFORMS), look=STR,
    screens=array(obj(
        id=STR, title=STR, purpose=STR,
        elements=array(obj(name=STR, kind=enum(ELEMENT_KINDS), description=STR, action=STR, input_rule=STR,
                           requirement_refs=STR_LIST)),
        states=obj(empty=STR, loading=STR, error=STR), requirement_refs=STR_LIST,
    )),
    no_screen=array(obj(requirement_id=STR, reason=STR)),
    swimlane=SWIMLANE,
)

TEST_CASES = obj(summary=STR_LIST, tests=array(obj(
    id=STR, title=STR, objective=STR, requirement_refs=STR_LIST, screen_refs=STR_LIST, priority=enum(PRIORITIES),
    preconditions=STR, inputs=STR, steps=STR_LIST, expected=STR, kind=enum(TC_KINDS),
)), ops_checks=array(obj(title=STR, requirement_refs=STR_LIST, how=STR)))

DOCUMENT_CONTENT = obj(
    brd=obj(
        summary=STR_LIST, background=array(obj(src_id=STR, interpretation=STR)),
        goals=array(obj(goal=STR, criterion=STR, status=enum(GOAL_STATUSES))),
        non_goals=array(obj(item=STR, reason=STR, refs=STR_LIST)), constraints=STR_LIST,
        risks=array(obj(risk=STR, impact=STR, response=STR)),
    ),
    prd=obj(summary=STR_LIST, decision_notes=array(obj(decision_id=STR, reason=STR))),
)

# --- S6 development -----------------------------------------------------------------------------
PROTOTYPE = obj(html=STR, summary=STR_LIST, images=array(obj(slot=STR, prompt=STR)), platform=enum(PLATFORMS))

# --- P1 -----------------------------------------------------------------------------------------
FEEDBACK_KINDS = ("헷갈림", "불편", "포기 위험")
CONSUMER_FEEDBACK = obj(items=array(obj(screen_id=STR, kind=enum(FEEDBACK_KINDS), comment=STR)))

# FR-21: the PM maps a change utterance to one requirement and rewrites its statement.
# `rationale` (why this requirement) is required by the schema but read as optional: older outputs lack it.
CHANGE_MAPPING = obj(target=STR, after_statement=STR, summary=STR, rationale=STR)
# After CP5: the PM returns only the requirements it rewrote (ids kept) and the new key phrase.
REQUIREMENTS_REVISION = obj(
    after_key=STR,
    requirements=array(obj(id=STR, title=STR, statement=STR, acceptance=obj(given=STR, when=STR, then=STR),
                           exceptions=STR_LIST)),
)

# FR-22: QA compares a complaint with the confirmed requirements.
COMPLAINT_CLASSES = ("합의 위반", "새 변경 요청", "무관")  # 무관: small talk, not about the product
COMPLAINT_CHECK = obj(requirement_ids=STR_LIST, classification=enum(COMPLAINT_CLASSES), requested=STR, reason=STR)

# --- S1 intake triage -----------------------------------------------------------------------------
# Before the team gets anything: is the request adequate, out of scope, unreadable, or missing who/pain/done?
INTAKE_CASES = ("ok", "cannot", "garbled", "insufficient")
INTAKE_SLOTS = ("who", "pain", "done")  # same three lines as problem_statement (S2)
INTAKE_TRIAGE = obj(case=enum(INTAKE_CASES), reason=STR, who=STR, pain=STR, done=STR,
                    questions=array(obj(slot=enum(INTAKE_SLOTS), question=STR), maxItems=3))
