from __future__ import annotations
"""S3/S4 calls send only the shared-source kinds their task refers to (less context, same outputs)."""

import json
from pathlib import Path

import pytest

from app.agent_runner import AgentRunner
from app.liner import CHAT_URL
from tests.pipeline_helpers import build, to_cp2

S3_S4 = ("requirement_candidates", "qa_findings", "question_cards", "requirements_final", "requirements_fix")


def s3_s4_sizes(repo_root: Path, key_env: Path) -> tuple[dict[str, int], list[dict], dict[str, str]]:
    orch, ws, fake = build(repo_root, key_env)
    to_cp2(orch, ws)
    sizes: dict[str, int] = {}
    users: dict[str, str] = {}
    for p in fake.payloads(CHAT_URL):
        name = p["response_format"]["json_schema"]["name"]
        if name in S3_S4:
            user = next(m["content"] for m in p["messages"] if m["role"] == "user")
            sizes[name] = sizes.get(name, 0) + len(user)
            users[name] = user
    return sizes, list(ws.items("requirements")), users


def test_s3_s4_context_shrinks_and_outputs_stay_the_same(repo_root: Path, key_env: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    narrow, narrow_reqs, users = s3_s4_sizes(repo_root, key_env)

    original = AgentRunner.ask

    def full_reads(self, *args, reads=None, **kwargs):  # noqa: ANN001 — the agent's whole `reads` list
        return original(self, *args, **kwargs)

    monkeypatch.setattr(AgentRunner, "ask", full_reads)
    full, full_reqs, _ = s3_s4_sizes(repo_root, key_env)

    print(f"\nS3+S4 user-message chars: full={sum(full.values())} narrow={sum(narrow.values())} "
          f"per call full={full} narrow={narrow}")
    assert set(narrow) == set(full)
    assert sum(narrow.values()) < sum(full.values())
    assert all(narrow[k] <= full[k] for k in full)
    assert narrow_reqs == full_reqs
    shared = json.loads(users["question_cards"].split("[공유 원본 — 읽기 권한 항목]\n", 1)[1].split("\n\n[추가 입력]")[0])
    assert {"sources", "requirements"} <= set(shared) and not {"confirmations", "screens", "tests"} & set(shared)


def test_reads_override_cannot_widen_the_agent_permission(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp2(orch, ws)
    assert ws.write("researcher", "alternatives", {"id": "ALT-01", "name": "기성 구독 솔루션"})
    assert ws.items("decisions")
    orch._ctx.runner.ask("qa", "확인", "qa_findings", {"type": "object"}, reads=("sources", "alternatives"))
    user = fake.payloads(CHAT_URL)[-1]["messages"][1]["content"]
    shared = json.loads(user.split("[공유 원본 — 읽기 권한 항목]\n", 1)[1])
    assert set(shared) == {"sources"}  # qa may not read alternatives; decisions were not asked for
