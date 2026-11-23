from __future__ import annotations
"""「우리 시스템 목록」: the systems the client already runs, one per line (SYS-01 …).

S2 compares the request with them (system_fit: 기능 추가 = add to that system, 연계 = connect to it, 재사용 = it
already does this, use it as it is), and each requirement says which systems it touches and how it is built
(change: 신규 / 기능 추가 / 연계 / 재사용). A system built with 0to1 also lists its features (`features`,
ids like SYS-03/REQ-02); a requirement names the ones it builds on in `feature_refs`. Without a list nothing
changes: no hint goes to the agents and every requirement is 신규.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

MAX_SYSTEMS = 30
MAX_SERVICES = 10  # 제안값 (D4 11-20) — built services listed apart from the client's list, newest kept
NAME_MAX = 60
LINE_MAX = 300
TEXT_MAX = 6000
REUSE = "재사용"
ADD = "기능 추가"
FITS = (ADD, "연계", REUSE)
CHANGES = ("신규", *FITS)
NEW = "신규"

_BULLET = re.compile(r"^(?:[-*•]|\d+[.)])\s*")
_SPLIT = re.compile(r"\s*(?::|：|\s[—–-]\s)\s*")

TASK_FDE_SYSTEMS = (
    " 공유 원본의 systems 는 발주사 회사가 이미 운영하는 시스템 목록이다. 원문이 바라는 일 중 그 시스템에 기능을 "
    "더하면 되는 것은 fit '기능 추가', 그 시스템과 데이터를 주고받으면 되는 것은 fit '연계', 그 시스템에 이미 있어 "
    "새로 만들지 않고 그대로 쓰면 되는 것은 fit '재사용'으로 system_fit 에 적어라. "
    "항목마다 system_ref(SYS-01 형식), 무엇을 하면 되는지(what), 근거 원문 ID(refs)와 원문에서 그대로 옮긴 인용문(quote)을 붙인다. "
    "목록의 어느 시스템으로도 안 되는 부분은 새로 만드는 것이므로 적지 않는다."
)
TASK_FDE_NO_SYSTEMS = " system_fit 은 빈 배열로 둔다."
TASK_PM_SYSTEMS = (
    " 공유 원본에 systems(발주사 회사가 이미 운영하는 시스템)가 있으면 요구사항마다 고치거나 연계할 시스템 ID 를 "
    "system_refs 에, 만드는 방식을 change 에 적어라('신규' 새로 만듦 / '기능 추가' 그 시스템에 기능을 더함 / "
    "'연계' 그 시스템과 연결 / '재사용' 그 시스템에 이미 있어 새로 만들지 않고 그대로 씀). '재사용'은 이번 요청 때문에 "
    "그 기능을 하나도 고치지 않아도 될 때만 쓴다 — 쓰는 사람·대상·조건·금액·화면 중 하나라도 바뀌면 '기능 추가'다. "
    "시스템에 features(이미 만든 기능, ID 는 SYS-03/REQ-02 형식)가 있으면 그 요구사항이 그대로 쓰거나 기대는 기능 ID 를 "
    "feature_refs 에 적는다. '재사용'은 feature_refs 에 그 기능 ID 가 있어야 한다. "
    "systems 가 없으면 system_refs·feature_refs 는 빈 배열, change 는 '신규'."
)


def listed_lines(text: str) -> int:
    """How many systems the client listed (non-empty, non-heading lines) — to tell what the cap left out."""
    return sum(1 for line in text[:TEXT_MAX].splitlines()
               if line.strip() and not line.strip().startswith("#") and _BULLET.sub("", line.strip()).strip())


def parse_systems(text: str, start: int = 1) -> list[dict[str, Any]]:
    """One system per non-empty line: 「이름: 하는 일」 or 「이름 — 하는 일」. '#' lines are headings and skipped.
    Numbered SYS-<start> onward (the client's list starts at 1; built services follow it, D4)."""
    systems: list[dict[str, Any]] = []
    for line in text[:TEXT_MAX].splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        body = _BULLET.sub("", raw)[:LINE_MAX].strip()
        if not body:
            continue
        name, about = (_SPLIT.split(body, maxsplit=1) + [""])[:2]
        systems.append({"id": f"SYS-{len(systems) + start:02d}", "name": name.strip()[:NAME_MAX],
                        "about": about.strip(), "raw": body})
        if len(systems) == MAX_SYSTEMS:
            break
    return systems


def system_texts(systems: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {s["id"]: s.get("raw", "") for s in systems}


def requirement_systems(raw: Mapping[str, Any], known: Sequence[str]) -> tuple[list[str], str]:
    """Only listed systems; a 기능 추가·연계 without one of them is really 신규."""
    refs = raw.get("system_refs")
    kept = [str(r) for r in refs if str(r) in known] if isinstance(refs, list) else []
    change = str(raw.get("change")) if raw.get("change") in CHANGES else NEW
    return (kept, change) if kept and change != NEW else (kept, NEW)


def requirement_features(raw: Mapping[str, Any], systems: Sequence[Mapping[str, Any]],
                         system_refs: Sequence[str]) -> list[str]:
    """Only feature ids of the systems this requirement names (each once, in the given order)."""
    refs = raw.get("feature_refs")
    named = {f["id"] for s in systems if s["id"] in system_refs for f in s.get("features", [])}
    return list(dict.fromkeys(str(r) for r in refs if str(r) in named)) if isinstance(refs, list) else []
