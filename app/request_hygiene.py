from __future__ import annotations
"""What the client says after confirmation is not always a real change: small talk, a request for what is
already so, the same request again, or a reversal of an earlier change. These are judged by code from the
record (the PM / QA only say "unrelated"), so no CP5 card or model call is spent on them.

- repeat_of: the same words (spacing, punctuation and case ignored) as an earlier settled item
- no_change: the PM's new statement is the current statement
- change_history: earlier approved changes to the same requirement, and the fixed version whose statement the
  new one brings back (a reversal)
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.checks import normalize_key

UNRELATED_TARGET = "NONE"  # the PM's answer when the words are about no confirmed requirement
UNRELATED_CLASS = "무관"  # QA's classification for the same in a complaint
UNRELATED_CHANGE = ("확정된 요구사항과 관련 없는 말씀이라 바꿀 것이 없어요. 기록만 남겼어요. "
                    "바꾸고 싶은 화면이나 기능이 있으면 그걸 적어 주세요")
UNRELATED_COMPLAINT = ("확정된 요구사항과 관련 없는 말씀이라 대조할 것이 없어요. 기록만 남겼어요. "
                       "결과물에서 다르다고 느낀 곳이 있으면 그 화면이나 기능을 적어 주세요")
NO_CHANGE = "{target}에 이미 그렇게 적혀 있어요. 바꿀 것이 없어서 확인(CP5)을 띄우지 않았어요"
REPEATED_CHANGE = "{id}에서 같은 요청을 이미 반영했어요({version}). 다시 바꾸려면 무엇이 달라져야 하는지 적어 주세요"
REPEATED_COMPLAINT = "{id}에서 같은 말씀을 이미 확정 기록과 맞춰 봤어요(판정: {label}). 그 카드를 확인해 주세요"


def same_words(a: str, b: str) -> bool:
    key = normalize_key(a)
    return bool(key) and key == normalize_key(b)


def repeat_of(items: Sequence[Mapping[str, Any]], text: str, field: str, settled: Sequence[str]
              ) -> Mapping[str, Any] | None:
    """The latest earlier item with the same words whose status is one of `settled`."""
    return next((i for i in reversed(items) if i.get("status") in settled and same_words(str(i.get(field, "")), text)),
                None)


def change_history(versions: Sequence[Mapping[str, Any]], requirement: Mapping[str, Any], after: str
                   ) -> dict[str, Any]:
    """{history: earlier approved change ids, reverts_to: the latest fixed version whose statement `after` restores}."""
    history = list(requirement.get("change_refs") or [])
    current = str(requirement.get("statement", ""))
    reverts_to = None
    if history and not same_words(after, current):
        for v in reversed(versions):
            old = next((r for r in v.get("snapshot", {}).get("requirements", []) if r.get("id") == requirement["id"]),
                       None)
            if old is not None and same_words(str(old.get("statement", "")), after):
                reverts_to = v["version"]
                break
    return {"history": history, "reverts_to": reverts_to}
