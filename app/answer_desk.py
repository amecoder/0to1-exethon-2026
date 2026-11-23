from __future__ import annotations
"""What the client wrote at a confirmation (CP1~CP4) when not approving: a question, a fix, or both.

Liner Decisions sorts the message first, so a plain question does not rerun the whole stage:
    question → (Liner search if outside facts are needed) → PM answers → back to the same confirmation
    change   → the stage is reworked with the reason (the behaviour before this desk existed)
    both     → answer first, then rework
Code keeps the final say and errs toward rework: an unusable or low-confidence decision counts as `both`,
so a fix request is never dropped as if it were only a question. Without a decision model it is `change`.
"""

from collections.abc import Mapping
from typing import Any

from app.config import LinerKeyMissingError
from app.decisions import min_confidence, needs_human, read_noul
from app.liner import LinerAPIError, LinerConfigError
from app.schemas import CLIENT_REPLY
from app.stage_common import StageContext, masked_output, str_list
from app.stage_problem import run_research
from app.agent_runner import ToolNotAllowedError

INTENTS = ("question", "change", "both")
INTENT_LABELS = {"question": "질문", "change": "수정 요청", "both": "질문과 수정 요청"}
INTENT_QUESTION = {
    "type": "choice",
    "instructions": "발주사가 확인 단계에서 승인하지 않고 남긴 말은 팀에게 묻는 질문인가, 결과물을 고쳐 달라는 요청인가, 둘 다인가?",
    "criteria": {
        "question": "정보·설명·사실 확인만 원한다. 결과물(문제 정의·범위·요구사항·문서·프로토타입)에 무엇을 넣거나 빼거나 "
                    "바꿔 달라는 말이 없다. '~알려 주면 좋지 않을까?'처럼 알려 달라는 부탁도 질문이다",
        "change": "결과물에 무엇을 넣거나 빼거나 바꿔 달라고 한다. 묻는 형태라도('~넣어 주면 안 될까?') 결과물을 바꾸라는 뜻이면 수정 요청이다",
        "both": "묻는 것과 결과물을 고쳐 달라는 것이 한 말에 함께 있다",
    },
}
SEARCH_QUESTION = {
    "type": "noul",
    "instructions": "이 말에 답하려면 팀이 가진 자료 밖의 정보(이미 있는 제품·서비스, 업계 관행, 법·규정, 기술 사실)를 검색해야 하는가?",
    "criteria": {"true": "바깥 정보를 찾아야 답할 수 있다", "false": "발주사 원문과 팀이 만든 결과물만으로 답할 수 있다"},
}
SEARCH_MIN = 0.5  # 제안
TASK_ANSWER = (
    "발주사가 확인 단계({cp})에서 승인하지 않고 질문을 남겼다(추가 입력의 질문). 공유 원본과 출처(evidence)·이미 있는 "
    "제품(alternatives)을 근거로 발주사에게 쉬운 말로 답하라. 첫 문장에서 질문에 바로 답하고(예: '네, 있어요.'), "
    "3~5문장으로 짧게 쓴다. 근거가 없으면 모른다고 말하고 지어내지 않는다. 결과물은 고치지 않는다 — 고칠 필요가 "
    "보이면 마지막 문장에서 고칠지 묻는다. 근거로 쓴 ID(SRC-·EV-·ALT-·REQ- 등)를 refs 에 적어라."
)


def classify(ctx: StageContext, cp: str, text: str) -> dict[str, Any]:
    """{intent, confidence, search, fallback}. Fail-safe: anything unusable → `both` (answer and rework)."""
    try:
        body = ctx.runner.decide("coordinator", "client_intent", {"확인 단계": cp, "발주사의 말": text},
                                 {"intent": INTENT_QUESTION, "search": SEARCH_QUESTION})
    except ToolNotAllowedError as exc:  # the coordinator's file does not declare the decision tool
        return {"intent": "change", "confidence": None, "search": None,
                "fallback": f"판정 도구가 없어 예전처럼 다시 만들어요 ({exc})"}
    except LinerConfigError:
        # No decision model configured: behave exactly as before this desk existed (rework with the reason).
        return {"intent": "change", "confidence": None, "search": None,
                "fallback": "판정 모델(LINER_DECISION_MODEL)이 없어 예전처럼 다시 만들어요"}
    except (LinerAPIError, LinerKeyMissingError) as exc:
        return {"intent": "both", "confidence": None, "search": None, "fallback": f"의도 판정을 못 했어요: {exc}"}
    answers = body.get("answers") if isinstance(body.get("answers"), Mapping) else {}
    raw = answers.get("intent") if isinstance(answers.get("intent"), Mapping) else {}
    confidence = raw.get("confidence") if isinstance(raw.get("confidence"), (int, float)) else None
    decision = {"intent": raw.get("choice"), "confidence": confidence, "search": read_noul(answers.get("search")),
                "fallback": None}
    if decision["intent"] not in INTENTS:
        return {**decision, "intent": "both", "fallback": "판정 응답에 의도 선택이 없어요"}
    if needs_human({"confidence": confidence, "error": None}, min_confidence(ctx.runner.client.env_file)):
        return {**decision, "intent": "both", "fallback": f"확신도가 낮아요({confidence})"}
    return decision


def answer(ctx: StageContext, cp: str, text: str, decision: Mapping[str, Any]) -> dict[str, Any]:
    """Search when the decision says outside facts are needed (or is unsure), then the PM answers. Stores ANS-."""
    search = decision.get("search")
    searched = search is None or search >= SEARCH_MIN
    if searched:
        ctx.bus.send("coordinator", "researcher", f"발주사 질문 근거 찾기: {text}")
        found = run_research(ctx, [text])
        ctx.bus.send("researcher", "coordinator", f"출처 {found}건 저장")
    ctx.bus.send("coordinator", "pm", f"발주사 질문에 답해 주세요: {text}")
    out = masked_output(ctx, "pm", ctx.runner.ask("pm", TASK_ANSWER.format(cp=cp), "client_reply", CLIENT_REPLY,
                                                  {"질문": text}))
    reply = {"id": ctx.ws.next_id("replies", "ANS"), "cp": cp, "question": text,
             "answer": str(out.get("answer", "")).strip(), "refs": str_list(out.get("refs")),
             "intent": decision["intent"], "confidence": decision.get("confidence"), "searched": searched,
             "answered_by": "pm"}
    ctx.ws.write("coordinator", "replies", reply)
    ctx.bus.send("coordinator", "client", reply["answer"])
    return reply
