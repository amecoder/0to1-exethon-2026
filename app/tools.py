from __future__ import annotations
"""에이전트 OS 3~4단계: every paid Liner call the product can make, one registry (the free balance read in
app/credits.py is left out: it is not a call G7 counts).

TOOLS are given per agent: an agent file (agents/*.json `tools`) may only name these (app/definitions.py), and the
agent runner calls one only for an agent whose file declares it (app/agent_runner.py `_tool`, G4 on refusal).
BUILT_IN calls are not declared — every agent thinks with the model, and S1 intake (audio, attachments) runs as
the system. G7 counts exactly the events these calls leave (CALL_EVENTS), and only app/agent_runner.py makes a
paid call (tests/test_tool_registry.py keeps it so). `/api/tools` lists both with the agents holding each tool.
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    title: str
    api: str
    model_env: str | None = None  # the setting that names its model, when it needs one
    event: str = ""  # the event type one call leaves (G7 counts these)


TOOLS: Mapping[str, Tool] = {
    "liner_search": Tool("웹 검색", "search", event="liner_search"),
    "liner_ai_search": Tool("AI 검색", "ai_search", event="liner_search"),
    "liner_visualization": Tool("시각화", "visualization", event="liner_visualization"),
    "liner_decisions": Tool("판정", "decisions", "LINER_DECISION_MODEL", "liner_decision"),
    "liner_rerank": Tool("재순위", "rerank", "LINER_RERANK_MODEL", "liner_rerank"),
    "liner_images": Tool("이미지", "images", "LINER_IMAGE_MODEL", "liner_image"),
}
BUILT_IN: Mapping[str, Tool] = {
    "liner_model": Tool("모델", "model", "LINER_MODEL", "liner_chat"),
    "liner_transcription": Tool("음성 받아 적기", "audio", "LINER_STT_MODEL", "liner_transcription"),
    "liner_attachment": Tool("첨부 읽기", "model", None, "liner_attachment"),
}
ALL_CALLS: Mapping[str, Tool] = {**TOOLS, **BUILT_IN}
CALL_EVENTS = frozenset(t.event for t in ALL_CALLS.values())


def call_of(event_type: str, api: str | None) -> str | None:
    """The registry id of the call an event records (event type + its `api` field), or None."""
    same_event = [(name, t) for name, t in ALL_CALLS.items() if t.event == event_type]
    exact = next((name for name, t in same_event if t.api == api), None)
    return exact or (same_event[0][0] if same_event else None)
