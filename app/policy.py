from __future__ import annotations
"""G9 purpose check: before the team starts, is the product the client asks for harmful by purpose?

Judged on what the product is for, not on words: a kitchen-knife shop, a war-history museum guide or an
English class for adults pass; a 3D-printed gun store, a strike-target picker or a paid adult-video site
do not. One Liner Decisions `choice` call over the client's text (about $0.0002).

Fail-open on purpose: without LINER_DECISION_MODEL or when the call fails, the request goes on and a
`skipped` G9 event says the check did not run (the decision model is optional in README). A block is
final for that text — there is no 「send anyway」, unlike G3's masking.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.config import LinerKeyMissingError
from app.liner import LinerAPIError, LinerConfigError

MAX_CHARS = 6000  # what the client wrote first is what defines the product; long transcripts are cut
BLOCK_SHARE = 0.5  # 제안: blocked when the harmful options together are at least this likely

# key → (label shown to the client, criterion given to the model)
CATEGORIES: dict[str, tuple[str, str]] = {
    "weapons": ("무기·폭발물", "총·폭탄·폭발물·불법 도검 같은 무기를 만들거나, 만드는 법을 알려 주거나, 불법으로 팔고 구하게 하는 서비스"),
    "war": ("전쟁·공격 지원", "실제 전쟁이나 군사 공격을 수행·지휘하거나 공격 목표를 고르는 등 사람을 해치는 작전을 돕는 서비스"),
    "violence": ("테러·폭력", "테러·폭력 조직의 모집과 모의, 특정인을 해치거나 괴롭히는 일을 돕는 서비스"),
    "sexual": ("성인물·성매매", "성인 영상·음란물을 만들거나 파는 서비스, 성매매·조건 만남을 연결하는 서비스"),
    "illegal": ("불법 행위", "마약 거래, 불법 도박, 불법 촬영물 공유, 사기, 남의 계정·정보를 몰래 빼내는 해킹 등 법을 어기는 것이 목적인 서비스"),
}
OK = "ok"
QUESTION = {
    "type": "choice",
    "instructions": "발주사가 만들어 달라는 제품(서비스)의 목적은 무엇인가? 단어가 아니라 제품이 하는 일로 판단한다. "
                    "칼국수집·주방칼 쇼핑몰·전쟁사 교육·성인 대상 강의·보안 교육처럼 합법적인 목적이면 ok 다.",
    "criteria": {OK: "합법적이고 사람을 해치지 않는 일반 제품·서비스", **{k: v[1] for k, v in CATEGORIES.items()}},
}
BLOCK_MESSAGE = (
    "만들어 드릴 수 없는 요청이에요. 이 서비스는 「{label}」에 해당해서 0to1 팀이 기획하지 않아요. "
    "다른 요구로 다시 적어 주세요. (판단이 틀렸다고 생각되면 무엇을 만드는지 더 구체적으로 적어 주세요)"
)


@dataclass(frozen=True)
class PolicyVerdict:
    blocked: bool
    category: str | None = None  # key of CATEGORIES when blocked
    label: str | None = None
    harmful: float | None = None  # summed probability of the harmful options
    error: str | None = None  # the check did not run (fail-open)

    def message(self) -> str:
        return BLOCK_MESSAGE.format(label=self.label or "만들 수 없는 서비스")


def request_text(chunks: Sequence[str]) -> str:
    return "\n".join(c.strip() for c in chunks if c.strip())[:MAX_CHARS]


def read_verdict(answer: Any) -> PolicyVerdict:
    """Blocked when the harmful options together reach BLOCK_SHARE; the category is the likeliest harmful one."""
    if not isinstance(answer, Mapping) or answer.get("choice") not in (OK, *CATEGORIES):
        raise ValueError("용도 판정 응답에 정해진 선택이 없습니다")
    raw = answer.get("probabilities")
    probs = {k: float(v) for k, v in raw.items() if isinstance(v, (int, float))} if isinstance(raw, Mapping) else {}
    harmful = {k: probs.get(k, 0.0) for k in CATEGORIES}
    total = sum(harmful.values()) if probs else (0.0 if answer["choice"] == OK else 1.0)
    if total < BLOCK_SHARE:
        return PolicyVerdict(False, harmful=round(total, 4))
    top = answer["choice"] if answer["choice"] in CATEGORIES else max(harmful, key=lambda k: harmful[k])
    return PolicyVerdict(True, top, CATEGORIES[top][0], round(total, 4))


def check_purpose(runner: Any, agent_id: str, chunks: Sequence[str]) -> PolicyVerdict:
    """One Decisions call. Config or API trouble returns an unchecked verdict instead of raising."""
    text = request_text(chunks)
    if not text:
        return PolicyVerdict(False)
    try:
        body = runner.decide(agent_id, "purpose", {"request": text}, {"purpose": QUESTION})
        answers = body.get("answers") if isinstance(body.get("answers"), Mapping) else {}
        return read_verdict(answers.get("purpose"))
    except (LinerAPIError, LinerConfigError, LinerKeyMissingError, ValueError) as exc:
        return PolicyVerdict(False, error=str(exc))


def guard_purpose(ws: Any, runner: Any, chunks: Sequence[str], where: str) -> PolicyVerdict:
    """check_purpose plus its G9 record: blocked (with category and summed probability), passed, or skipped."""
    verdict = check_purpose(runner, "coordinator", chunks)
    if verdict.error is not None:
        ws.guardrail("G9", "skipped", f"{where}: 용도 검사를 하지 못함 — {verdict.error}")
    elif verdict.blocked:
        ws.guardrail("G9", "blocked", f"{where}: 「{verdict.label}」 목적의 요청 — 저장하지 않음",
                     category=verdict.category, harmful=verdict.harmful)
    else:
        ws.guardrail("G9", "passed", f"{where}: 용도 검사 통과", harmful=verdict.harmful)
    return verdict
