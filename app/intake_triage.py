from __future__ import annotations
"""S1 intake triage: before the team gets anything, is the client's request one it can work on?

Four cases. ok → sent to the team as before. cannot → not something a software/digital-service team delivers
(physical work, hardware, legal/medical advice itself, no product to build). garbled → unreadable (keyboard
mash, jamo only, one word, repeated characters, small talk). insufficient → a real request missing one of the
three lines S2 writes into problem_statement: who (누가 쓰는지), pain (무엇이 불편한지), done (무엇이 되면 끝인지).

Order per round: G3 on everything that would go to Liner (blocked unless the client chose masking) → a code
pre-check that costs nothing → one Liner model call (coordinator, json_schema) → code rules on its answer
(the model cannot pass a request with an empty slot, and a request with every slot filled is ok) → on cannot or
insufficient, the G9 purpose check (one Decisions call), so a harmful request is refused as harmful.
Nothing is stored as a source: the round leaves one `intake_triage` event (case, missing slots) plus G3/G9 events.
"""

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.agent_runner import AgentOutputError
from app.config import LinerKeyMissingError
from app.guardrails import G3_PROMPT, mask_sensitive, sensitive_labels
from app.liner import LinerAPIError, LinerConfigError
from app.limits import LimitReachedError
from app.policy import guard_purpose
from app.schemas import INTAKE_CASES, INTAKE_SLOTS, INTAKE_TRIAGE

ACTOR = "coordinator"
EVENT = "intake_triage"
SCHEMA_NAME = "intake_triage"
MAX_CHARS = 6000  # same cut as the G9 purpose check
MIN_LETTERS = 5  # 제안: fewer letters than this cannot say what to build
MAX_DISTINCT_REPEATED = 2  # 제안: at most this many different letters → repeated characters
FIELD_MAX = 300
# ok goes straight on to /input, where G9 runs anyway; garbled text says nothing to judge.
PURPOSE_CHECKED = ("cannot", "insufficient")

SLOT_LABELS = {"who": "누가 쓰는지", "pain": "무엇이 불편한지", "done": "무엇이 되면 끝인지"}
DEFAULT_QUESTIONS = {
    "who": "이 서비스는 누가 쓰나요? (예: 꽃집 단골 고객과 사장님)",
    "pain": "지금 무엇이 불편하거나 잘 안 되나요?",
    "done": "무엇이 되면 이 일이 끝났다고 보시겠어요? (예: 고객이 앱으로 구독을 신청할 수 있으면)",
}
DEFAULT_REASONS = {
    "ok": "팀에 넘길 준비가 됐어요",
    "insufficient": "무엇을 만들지는 알겠어요. 팀에 넘기기 전에 아래 질문에 답해 주세요",
    "cannot": "이 팀은 앱·웹 같은 소프트웨어를 기획하고 만들어요. 이 요청은 그런 일이 아니라서 맡을 수 없어요. "
              "만들고 싶은 서비스로 다시 적어 주세요",
    "garbled": "무엇을 만들고 싶은지 읽기 어려워요. 누가 쓰고 무엇이 불편한지 문장으로 다시 적어 주세요",
}
EMPTY = "요청이 비어 있어요. 무엇을 만들고 싶은지 적어 주세요"
NO_LETTERS = "글자가 없어서 읽을 수 없어요. 무엇을 만들고 싶은지 문장으로 적어 주세요"
JAMO = "자음·모음만 있어서 읽을 수 없어요. 무엇을 만들고 싶은지 문장으로 다시 적어 주세요"
REPEATED = "같은 글자만 되풀이돼서 읽을 수 없어요. 무엇을 만들고 싶은지 문장으로 다시 적어 주세요"
TOO_SHORT = "너무 짧아서 무엇을 만들지 알 수 없어요. 누가 쓰고, 무엇이 불편하고, 무엇이 되면 끝인지 한두 문장으로 적어 주세요"
FAILED = "접수 확인을 하지 못했어요. 잠시 뒤 「팀에게 보내기」를 다시 눌러 주세요"
LIMITED = "이 프로젝트의 호출·비용 상한에 닿아 접수 확인을 하지 못했어요. 상한을 늘린 뒤 다시 눌러 주세요"

TASK = (
    "발주사가 처음 보낸 요청을 팀에 넘기기 전에 접수 상태를 판정한다. [추가 입력]의 request 는 발주사가 쓴 원문, "
    "answers 는 앞서 물은 질문에 발주사가 단 답이다. 둘을 합쳐 판단한다.\n"
    "case 는 넷 중 하나다.\n"
    "- ok: 소프트웨어·디지털 서비스(앱·웹·업무 도구·자동화)로 만들 요청이고, 누가 쓰는지·무엇이 불편한지·"
    "무엇이 되면 끝인지가 모두 글에 있다.\n"
    "- insufficient: 소프트웨어로 만들 수 있는 요청이지만 세 가지 중 빠진 것이 있다.\n"
    "- cannot: 소프트웨어 팀이 만들어 줄 수 없는 요청이다. 몸으로 하는 일(이사·청소·배달 대행), 하드웨어·제품 제조, "
    "법률·의료·세무 상담 그 자체, 만들 제품이 없는 부탁(돈을 빌려 달라, 숙제를 대신 해 달라 등).\n"
    "- garbled: 무엇을 만들어 달라는 글인지 읽을 수 없다. 자판을 아무렇게나 친 글, 뜻 없는 단어 나열, "
    "요청과 상관없는 잡담.\n"
    "who·pain·done 에는 원문과 답에 실제로 있는 내용만 한 문장으로 옮긴다. 글에 없으면 빈 문자열로 둔다. "
    "짐작해서 채우지 않는다.\n"
    "- who: 이 서비스를 실제로 쓰는 사람 (예: 꽃집 단골 고객과 사장)\n"
    "- pain: 지금 무엇이 불편하거나 안 되는지\n"
    "- done: 무엇이 되면 이 일이 끝났다고 볼지 (예: 고객이 앱으로 구독을 신청하고 사장이 주문 목록을 본다)\n"
    "questions 에는 빈 칸마다 하나씩, 발주사가 바로 답할 수 있는 쉬운 질문을 해요체로 쓴다. "
    "칸이 다 찼거나 case 가 cannot·garbled 이면 빈 목록이다.\n"
    "reason 은 발주사에게 보여 줄 한두 문장(해요체)이다. cannot·garbled 이면 왜 그런지와 어떻게 다시 쓰면 되는지 적는다."
)


@dataclass(frozen=True)
class Question:
    slot: str
    question: str


@dataclass(frozen=True)
class Answer:
    slot: str
    question: str
    answer: str


@dataclass(frozen=True)
class Verdict:
    case: str
    reason: str
    who: str = ""
    pain: str = ""
    done: str = ""
    questions: tuple[Question, ...] = ()
    by: str = "model"  # code: the pre-check decided without a call

    def slots(self) -> dict[str, str]:
        return {"who": self.who, "pain": self.pain, "done": self.done}

    def missing(self) -> tuple[str, ...]:
        return tuple(slot for slot, value in self.slots().items() if not value)

    def to_dict(self) -> dict[str, Any]:
        return {"case": self.case, "reason": self.reason, "slots": self.slots(),
                "questions": [{"slot": q.slot, "question": q.question} for q in self.questions]}


@dataclass(frozen=True)
class TriageResult:
    verdict: Verdict | None = None
    blocked: bool = False  # G3: sensitive text not masked · G9: a harmful product (refused, cannot be masked)
    message: str = ""
    kinds: tuple[str, ...] = ()
    guard: str = "G3"
    error: str | None = None  # the Liner call failed; the client can press again


def _is_jamo(ch: str) -> bool:
    return "ㄱ" <= ch <= "ㆎ" or "ᄀ" <= ch <= "ᇿ"


def _is_syllable(ch: str) -> bool:
    return "가" <= ch <= "힣"


def precheck(text: str) -> Verdict | None:
    """Garbled by code, without a Liner call; None when the text needs the model's judgement."""
    stripped = unicodedata.normalize("NFC", text).strip()
    letters = [ch for ch in stripped if ch.isalnum()]
    jamo = sum(1 for ch in letters if _is_jamo(ch))
    syllables = sum(1 for ch in letters if _is_syllable(ch))
    if not stripped:
        reason = EMPTY
    elif not letters:
        reason = NO_LETTERS
    elif jamo and jamo >= syllables:
        reason = JAMO
    elif len(set(letters)) <= MAX_DISTINCT_REPEATED:
        reason = REPEATED
    elif len(letters) < MIN_LETTERS:
        reason = TOO_SHORT
    else:
        return None
    return Verdict("garbled", reason, by="code")


def _text(value: Any) -> str:
    return str(value).strip()[:FIELD_MAX] if isinstance(value, str) else ""


def merge_verdict(model_out: Mapping[str, Any]) -> Verdict:
    """Code rules over the model's answer: ok/insufficient is decided by the three slots, never by the model.
    Questions are kept only for empty slots (one each, a default when the model gave none)."""
    case = model_out.get("case")
    if case not in INTAKE_CASES:
        raise ValueError("접수 판정 응답에 정해진 case 가 없습니다")
    slots = {slot: _text(model_out.get(slot)) for slot in INTAKE_SLOTS}
    reason = _text(model_out.get("reason"))
    if case in ("cannot", "garbled"):
        return Verdict(case, reason or DEFAULT_REASONS[case], **slots)
    missing = [slot for slot in INTAKE_SLOTS if not slots[slot]]
    if not missing:
        return Verdict("ok", reason if case == "ok" and reason else DEFAULT_REASONS["ok"], **slots)
    raw = model_out.get("questions")
    asked = {q.get("slot"): _text(q.get("question")) for q in raw if isinstance(q, Mapping)} \
        if isinstance(raw, list) else {}
    questions = tuple(Question(slot, asked.get(slot) or DEFAULT_QUESTIONS[slot]) for slot in missing)
    reason = reason if case == "insufficient" and reason else DEFAULT_REASONS["insufficient"]
    return Verdict("insufficient", reason, **slots, questions=questions)


def ask_model(runner: Any, request: str, answers: Sequence[Answer]) -> Verdict:
    """One coordinator call with no shared-source context. Raises on Liner, limit or shape trouble."""
    extra = {"request": request[:MAX_CHARS],
             "answers": [{"slot": a.slot, "question": a.question, "answer": a.answer} for a in answers]}
    output = runner.ask(ACTOR, TASK, SCHEMA_NAME, INTAKE_TRIAGE, extra=extra, reads=[])
    return merge_verdict(output)


def run_triage(ws: Any, runner: Any, chunks: Sequence[str], answers: Sequence[Answer],
               mask: bool = False) -> TriageResult:
    """One triage round. G3 runs before anything goes to Liner; the round is recorded as one event."""
    texts = [c for c in chunks if c.strip()]
    answers = [a for a in answers if a.answer.strip()]
    labels = sensitive_labels([*texts, *(a.answer for a in answers)])
    if labels and not mask:
        ws.guardrail("G3", "blocked", "접수 확인: 민감 정보 패턴 발견 — Liner 에 보내지 않음", kinds=labels)
        return TriageResult(blocked=True, message=G3_PROMPT.format(kinds=", ".join(labels)), kinds=tuple(labels))
    if labels:
        ws.guardrail("G3", "masked", "접수 확인: 민감 정보를 가린 값으로 확인", kinds=labels)
        texts = [mask_sensitive(t) for t in texts]
        answers = [Answer(a.slot, a.question, mask_sensitive(a.answer)) for a in answers]
    request = "\n".join(t.strip() for t in texts)
    verdict = precheck(request)
    if verdict is None:
        try:
            verdict = ask_model(runner, request, answers)
        except LimitReachedError:
            return TriageResult(error=LIMITED)
        except (LinerAPIError, LinerConfigError, LinerKeyMissingError, AgentOutputError, ValueError):
            ws.emit(EVENT, ACTOR, {"case": None, "missing": [], "by": "model", "answers": len(answers),
                                   "error": "판정 실패"})
            return TriageResult(error=FAILED)
    ws.emit(EVENT, ACTOR, {"case": verdict.case, "missing": list(verdict.missing()) if verdict.case == "insufficient"
                           else [], "by": verdict.by, "answers": len(answers)})
    if verdict.case in PURPOSE_CHECKED:
        harmful = _purpose(ws, runner, [request, *(a.answer for a in answers)])
        if harmful is not None:
            return TriageResult(blocked=True, message=harmful, guard="G9")
    return TriageResult(verdict)


def _purpose(ws: Any, runner: Any, texts: Sequence[str]) -> str | None:
    """G9 before a refusal or more questions, so a harmful request hears why (11-22: it heard only 「맡을 수 없어요」).
    The refusal message when blocked; None when the check passed, was skipped, or hit a limit (fail-open)."""
    try:
        verdict = guard_purpose(ws, runner, texts, "접수 확인")
    except LimitReachedError:
        return None
    return verdict.message() if verdict.blocked else None
