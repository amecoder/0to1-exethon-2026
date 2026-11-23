from __future__ import annotations
"""Shared pieces for stage handlers: context object and G1 text lookup."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.agent_runner import AgentRunner
from app.bus import MessageBus
from app.change_brief import BRIEF_KEY, BRIEF_KINDS, change_brief
from app.checks import consistency_violations
from app.errors import PipelineStateError
from app.guardrails import G3_PROMPT, mask_sensitive, sensitive_labels
from app.workspace import Workspace

# 제안 values (PRD FR-06 "첫 회 8장 이하"), kept as constants so they can be tuned in one place.
# 11-22 user decision: blanks are filled by asking (a real run has 17~28 findings); the cap only stops a runaway
# round of hundreds. Was 8 (FR-06), which left 13 of 25 findings as CP3 blanks.
FIRST_ROUND_MAX_CARDS = 30
MAX_RESEARCH_QUERIES = 3
UNKNOWN_OPTION = "잘 모르겠어요"
UNCARDED = "질문 카드에 들어가지 못한 지적"  # an open item's reason: a QA finding no question card named
GAP_KEY = "발주사 결정(기존 제품 활용)"


def gap_instruction(name: str, covers: str, lacks: str) -> str:
    """CP1 「모자란 부분만 만들기」: what the PM, QA and later agents must not rebuild."""
    return (f"발주사가 {name}을(를) 쓰기로 했다. 그 제품이 해 주는 것({covers})은 만들지 말고, "
            f"모자란 것({lacks})과 그 제품과 연결하는 부분만 요구사항으로 만든다")


@dataclass(frozen=True)
class StageContext:
    ws: Workspace
    bus: MessageBus
    runner: AgentRunner

    def feedback_extra(self) -> dict[str, Any]:
        """The client's one-line rejection reason, if this stage is being reworked,
        and, while an approved change (CP5) is being reworked, its brief (FR-21)."""
        reason = self.ws.pipeline.get("feedback")
        # Blocked by G3 when it was written; masked again here for reasons stored before that check existed.
        extra: dict[str, Any] = {"반려 사유(발주사)": mask_sensitive(reason)} if reason else {}
        brief = change_brief({"meta": self.ws.meta, **{k: self.ws.items(k) for k in BRIEF_KINDS}})
        extra = {**extra, BRIEF_KEY: brief} if brief else extra
        return {**extra, **self.gap_extra()}

    def gap_extra(self) -> dict[str, Any]:
        """The CP1 build-gap decision stays on record, so every later stage keeps the instruction."""
        note = next((d.get("instruction") for d in reversed(self.ws.items("decisions"))
                     if d.get("kind") == "build_or_buy" and d.get("instruction")), None)
        return {GAP_KEY: note} if note else {}


def g3_check(ws: Workspace, texts: Sequence[str | None], what: str) -> None:
    """G3 on the client's free text (reasons, waivers, answers…): block before anything is stored or sent."""
    labels = sensitive_labels([t for t in texts if t])
    if labels:
        ws.guardrail("G3", "blocked", f"{what}의 민감 정보 — 저장하지 않음", actor="client", kinds=labels)
        raise PipelineStateError(G3_PROMPT.format(kinds=", ".join(labels)))


def citation_texts(ws: Workspace) -> dict[str, str]:
    """Texts a citation can point to: SRC sentences and EV raw snippets (plus their quotes)."""
    texts = {s["id"]: s["text"] for s in ws.items("sources")}
    texts.update({e["id"]: f"{e.get('raw_snippet', '')}\n{e.get('quote', '')}" for e in ws.items("evidence")
                  if e.get("status") == "확인"})
    return texts


def str_list(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def masked_output(ctx: StageContext, actor: str, value: Any) -> Any:
    """G3 on generated output: mask sensitive patterns in every string before it is stored."""
    labels = sensitive_labels(_strings(value))
    if not labels:
        return value
    ctx.ws.guardrail("G3", "masked", "생성물의 민감 정보를 가린 값으로 저장", actor=actor, kinds=labels)
    return _mask(value)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return mask_sensitive(value)
    if isinstance(value, dict):
        return {k: _mask(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return value


def report_answer_consistency(ctx: StageContext) -> list[dict[str, Any]]:
    """Coordinator: compare requirements with the client's answers (DEC-) and record the result."""
    violations = consistency_violations(ctx.ws.source)
    ctx.ws.emit("check_result", "coordinator", {
        "check": "answer_consistency", "outcome": "flagged" if violations else "passed",
        "items": [v["id"] for v in violations], "details": [v["message"] for v in violations]})
    if violations:
        ctx.bus.send("coordinator", "pm", "고른 답과 다른 요구사항: " + " / ".join(v["message"] for v in violations))
    return violations
