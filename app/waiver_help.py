from __future__ import annotations
"""11-22 (user): each 빈칸 (a waivable warning at CP3/CP4) comes with a plain explanation of what is missing and
why it matters, and a one-line reason already filled in that the client may edit before approving.

Code rules only — no Liner call, the same words every time. Names, not IDs, in the explanation (the client view
hides IDs). The filled reason is a proposal: approval still records whatever the client sends.
"""

from collections.abc import Mapping
from typing import Any

from app.korean import josa


DEFAULT_REASON = "이번 버전에서는 지금 내용대로 진행하고, 개발을 시작하기 전에 다시 확인해요."
STATUS_MEANING = {"미결": "아직 정한 답이 없다는 뜻이에요", "미확인": "원문이나 출처와 글자가 그대로 맞는지 아직 확인하지 못했다는 뜻이에요"}


def _title(source: Mapping[str, Any], kind: str, item_id: str) -> str:
    found = next((i for i in source.get(kind, []) if i.get("id") == item_id), {})
    return str(found.get("title") or item_id)


def _scope(source: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return next((d for d in reversed(source.get("decisions", [])) if d.get("kind") == "scope"), None)


def _no_screen(w: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[str, str]:
    title = _title(source, "requirements", w["target"])
    explain = (f"「{title}」 기능을 보여 주는 화면이 이번 화면설계서와 프로토타입에 없어요. 화면이 없으면 이 기능이 "
               "앱에서 어떻게 보이고 눌리는지 확인할 수 없어요. 화면을 일부러 뺐거나, 화면 없이 뒤에서 처리되는 기능이면 "
               "그 이유를 남겨 두면 돼요.")
    scope = _scope(source)
    dropped = scope.get("dropped_requirements") if scope else None
    if scope and (dropped is None or w["target"] in dropped):
        kept = len(scope.get("screens_kept") or [])
        return (explain + " 앞에서 만들 화면을 고를 때 이 기능의 화면이 빠졌어요.",
                f"화면 범위를 {kept}개로 줄이면서 이번 버전에서는 이 화면을 만들지 않았어요. 다음 버전에서 화면을 추가해요.")
    return explain, "화면 없이 뒤에서 처리되는 기능이라 이번 버전에서는 화면을 따로 두지 않아요."


def _no_test(w: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[str, str]:
    title = _title(source, "requirements", w["target"])
    return (f"{josa(f'「{title}」', '이/가')} 제대로 동작하는지 확인할 테스트 케이스가 없어요. 테스트가 없으면 개발이 끝난 뒤 이 기능이 "
            "맞게 만들어졌는지 판정할 기준이 없어요.",
            "이번 버전에서는 테스트 없이 두고, 개발을 시작하기 전에 테스트 케이스를 추가해요.")


def _open(w: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[str, str]:
    item = next((i for i in source.get("open_items", []) if i.get("id") == w["target"]), None)
    if item is None:  # a requirement still 미결 / 미확인
        req = next((r for r in source.get("requirements", []) if r.get("id") == w["target"]), {})
        status = str(req.get("status", "미결"))
        return (f"{josa(f"「{req.get('title') or w['target']}」", '은/는')} 아직 「{status}」 상태예요. {STATUS_MEANING.get(status, '')}. "
                "이대로 개발하면 개발자가 빈 곳을 짐작해서 채우게 돼요.",
                "지금 적힌 내용으로 진행하고, 개발을 시작하기 전에 다시 확인해요.")
    from app.stage_common import FIRST_ROUND_MAX_CARDS, UNCARDED  # here: stage_common imports app.checks

    names = [f"「{_title(source, 'requirements', r)}」" for r in item.get("requirement_refs", [])]
    where = f" 관련 기능은 {josa(', '.join(names), '이에요/예요')}." if names else ""
    why = {UNCARDED: " 팀이 원문이나 업계 관행으로 정해도 된다고 보고 질문 카드로 따로 묻지 않았어요.",
           "이번 회차 카드 수 상한 초과": f" 질문 카드는 한 번에 {FIRST_ROUND_MAX_CARDS}장까지만 물어서 이 점은 묻지 못했어요.",
           }.get(str(item.get("reason")), "")
    return (f"팀이 문서를 쓰다가 정하지 못한 점이에요. {item.get('title', '')}{where}{why} "
            "지금 정하지 않으면 개발자가 임의로 정하게 돼요.",
            "이번 버전에서는 정하지 않고 미결로 남겨 두고, 개발을 시작하기 전에 정해요.")


def _conflict(w: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[str, str]:
    finding = next((f for f in source.get("findings", []) if f.get("id") == w["target"]), {})
    return (f"요청 원문에서 서로 부딪히는 내용이 아직 풀리지 않았어요. {finding.get('note', '')} "
            "어느 쪽으로 만들지 정해지지 않은 채 개발에 들어가게 돼요.",
            "지금 문서에 적힌 쪽으로 진행하고, 다르면 「바꾸고 싶어요」로 고쳐요.")


def _stale(w: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[str, str]:
    title = _title(source, "requirements", w["target"])
    return (f"바꾸기로 한 내용이 반영됐는데, 「{title}」에는 바뀌기 전 문장이 아직 남아 있어요. "
            "개발자가 어느 쪽이 맞는지 헷갈릴 수 있어요.",
            "바뀐 내용이 우선이에요. 남은 예전 문장은 다음 버전에서 정리해요.")


def _missing_screen(w: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[str, str]:
    title = _title(source, "screens", w["target"])
    return (f"화면설계서에 있는 「{title}」 화면이 프로토타입에는 없어요. 눌러 보며 확인할 수 없는 화면이에요.",
            "이번 프로토타입에서는 이 화면을 빼고, 다음 버전에서 추가해요.")


RULES = {"coverage.no_scr": _no_screen, "coverage.no_tc": _no_test, "coverage.open": _open,
         "consistency.conflict": _conflict, "change.stale": _stale, "prototype.missing_scr": _missing_screen}


def help_for(w: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, str]:
    rule = RULES.get(str(w.get("code")))
    explain, suggested = rule(w, source) if rule else ("", DEFAULT_REASON)
    return {"explain": " ".join(explain.split()), "suggested": suggested}
