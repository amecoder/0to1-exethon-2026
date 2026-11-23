from __future__ import annotations
"""S6 development: coordinator → developer (designer ↔ developer, qa ↔ developer), then QA's checklist.

The developer agent returns one HTML document. Code then decides what is kept (G6): outside-resource
markup is stripped, network calls to absolute URLs reject the answer. One retry, then a template built
from the screen specs, so the run never dead-ends. QA's checklist is deterministic (no execution, FR-28 later).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.korean import josa
from app.agent_runner import AgentOutputError
from app.liner import LinerAPIError
from app.prototype import Sanitized, missing_screens, qa_checklist, sanitize, template_prototype
from app.prototype_images import add_images, requested_images
from app.prototype_kit import CHEATSHEET, FX_CHEATSHEET, accent_for, ensure_kit, platform_for
from app.stage_documents import product_form
from app.schemas import PROTOTYPE
from app.stage_common import StageContext, masked_output, str_list
from app.stage_consumer import collect_feedback

MAX_ATTEMPTS = 2
# 11-22: Liner ended a ~300 s developer stream with an error; the next attempt is asked for less.
CUT_OFF = ("Liner 호출이 중간에 끊겼다(응답이 너무 길어 시간 안에 끝나지 않았을 수 있다). 화면과 구성 요소는 그대로 두고 "
           "HTML 을 더 짧게 써라 — 같은 마크업 반복·주석·키트에 이미 있는 CSS 를 빼고, 추가 CSS·JS 는 꼭 필요한 것만.")
KST = timezone(timedelta(hours=9))
WEEKDAYS = "월화수목금토일"
TASK_DEVELOPER = (
    "확정된 원본(화면 screens, 요구사항 requirements, 테스트 케이스 tests)으로 프로토타입을 HTML 문서 하나로 만들어라. "
    "추가 입력의 제품 형태가 app 이면 휴대폰 앱처럼(탭바·한 열), web 이면 PC 웹사이트처럼(위쪽 메뉴·여러 열 — 키트가 "
    "<html data-platform> 로 배치를 바꾸고 좁은 폭에서는 한 열로 접는다) 만들고, 같은 값을 platform 에 적어라. "
    "추가 입력의 시각 방향을 따르되 효과는 화면마다 한두 개만, 글 읽기를 방해하지 않게 쓴다. <!doctype html> 부터 </html> 까지 완전한 문서 하나, 추가 CSS 는 <style>, JS 는 <script> 안에. "
    "외부 파일·글꼴·이미지·CDN 을 부르지 말고, 네트워크 요청(fetch 등)을 하지 말고, 데이터는 지어낸 가짜 데이터만 쓴다. "
    "화면설계서의 화면을 하나도 빠짐없이 만들고, 화면 ID 는 data-scr 속성에만 넣고 화면 글자로는 보이지 않게 한다. "
    "화면 사이는 탭바·버튼으로 오가고(페이지 새로고침 없음), 구성 요소는 화면설계서 순서대로, 빈 상태·오류 상태도 볼 수 있게 한다. "
    "화면설계서에 없는 기능은 넣지 않는다. summary 에는 만든 것을 완전한 문장 3개 이하로 적어라. "
    "실제 앱처럼 보이게 하는 규칙: ① 미결·가정이라 값이 비면 '미정'·'— 원'·'N회' 대신 그럴듯한 예시 값 뒤에 "
    "<span class=\"sample\">예시</span>(확정 요구사항과 어긋나는 값은 금지). ② 화면 글은 고객에게 하는 짧고 친근한 말, "
    "규칙·조건은 <details class=\"help\"><summary>자세히</summary>…</details> 안에 — 예) 전: '토요일 회차는 그 주 화요일, "
    "수요일 회차는 직전 토요일에 1회분이 결제돼요' → 후: '배송 전에 한 번씩 결제돼요' + 자세히. ③ 입력이 많은 신청 화면은 "
    "단계 흐름(data-flow) 3~4단계, 고른 값은 data-store 로 남겨 완료·관리 화면에서 data-bind 로 보여 준다. ④ 관리·운영 화면은 "
    "이미 쓰는 중인 가짜 데이터(proto-seed·표)로 채운다. ⑤ 상품·분위기 사진이 어울리는 곳 최대 3곳에 <img data-img=\"슬롯\" alt>를 "
    "두고(상품·옵션을 고르는 카드가 있으면 첫 화면 대표 사진 다음으로 카드마다 사진을 우선 — 짧게 쓸 때도 사진은 빼지 않는다) images 에 {slot, prompt}(사진 묘사 한 문장, 사람 얼굴·글자·로고 없이)를 적는다. 없으면 images 는 []. "
    "⑥ 첫 화면 .hero: 상품·음식·꽃·공간·여행처럼 사진이 어울리는 업종이면 .hero 맨 위에 대표 사진 "
    "<img data-img=\"hero\" class=\"hero-photo\" alt>(⑤의 3곳에 포함), 사진이 어울리지 않을 때만 data-fx3d 3D 장면. "
    "점·선을 이은 무늬 배경은 쓰지 않는다. 숫자에는 data-count, 추이·비율에는 data-chart, 신청 완료 버튼에는 data-confetti. "
    "⑦ 시연용 조작(오늘 날짜·시각 바꾸기, 상태 전환 스위치, '미리보기' 막대)을 화면에 두지 않는다. 다른 상태는 빈 상태·오류 "
    "상태 화면이나 data-show-if 로 보여 주고, 날짜 예시는 추가 입력의 오늘 날짜를 기준으로 쓴다. "
    "⑧ HTML 은 짧게 — 같은 마크업을 되풀이하지 말고(목록 예시는 3~4줄), 주석을 쓰지 말고, 키트에 있는 CSS 는 다시 쓰지 않고, "
    "추가 CSS·JS 는 꼭 필요한 것만(11-22: 길게 쓰면 Liner 응답이 300초 근처에서 끊긴다). " + CHEATSHEET + FX_CHEATSHEET
)


def run_s6(ctx: StageContext) -> None:
    screens, tests = ctx.ws.items("screens"), ctx.ws.items("tests")
    version = _confirmed_version(ctx)
    ctx.bus.send("coordinator", "developer", f"단계 S6 개발: 확정 원본 {josa(version, '으로/로')} 단일 HTML 프로토타입을 만든다")
    ctx.bus.send("designer", "developer", f"화면설계서 {version}: 화면 {len(screens)}개 — 디자인 키트 클래스로, SCR ID 는 data-scr 에")
    ctx.bus.send("qa", "developer", f"테스트 케이스 {len(tests)}건 기준으로 화면을 대조하겠습니다")

    html, summary, attempts, failures, kept, pictures, said = _develop(ctx, version)
    origin = "agent" if kept is not None else "template"
    accent = accent_for(_domain_text(ctx))
    platform = _platform(ctx, said)
    html = ensure_kit(html, accent, platform) if kept is not None else template_prototype(
        screens, ctx.ws.items("requirements"), accent, platform)
    html, image_notice = add_images(ctx, html, pictures)
    missing = missing_screens(html, screens)
    ctx.ws.write("developer", "prototype", {
        "id": "PROTO-01", "html": html, "origin": origin, "attempts": attempts, "based_on": version,
        "summary": summary, "violations": kept.violations if kept else [], "missing_screens": missing,
        "owner_agent": "developer", "images": [p["slot"] for p in pictures], "image_notice": image_notice,
        "platform": platform,
    })
    ctx.ws.emit("prototype_built", "developer", {"origin": origin, "attempts": attempts, "failures": failures,
                                                 "missing_screens": missing, "chars": len(html)})
    ctx.bus.send("developer", "qa", f"프로토타입 완료({'템플릿 대체본' if origin == 'template' else '개발자 작성'}), "
                                    f"빠진 화면 {len(missing)}개")
    rows = qa_checklist(tests, screens, html, ctx.ws.items("requirements"))
    ctx.ws.write("qa", "qa_checklist", {"id": "QAC-01", "rows": rows, "executed": False})
    ready = sum(1 for r in rows if r["result"] == "확인 가능")
    ctx.bus.send("qa", "coordinator", f"체크리스트 {len(rows)}건 중 화면 대조 가능 {ready}건 (실행은 다음 단계)")
    collect_feedback(ctx, "CP4")
    ctx.bus.send("coordinator", "client", "프로토타입을 미리보기로 확인하고 인수 여부를 정해 주세요")


def _platform(ctx: StageContext, said: str | None) -> str:
    """The designer's choice first, then the developer's, then the screen spec's word guess."""
    spec = (ctx.ws.items("screen_spec") or ({},))[0]
    if spec.get("platform") in ("app", "web") and not spec.get("platform_guessed"):
        return str(spec["platform"])
    return said or str(spec.get("platform") or platform_for(_domain_text(ctx)))


def _domain_text(ctx: StageContext) -> str:
    """What the product is about (for the kit's accent colour): the problem statement's who/pain/done."""
    return " ".join(str(p.get(k, "")) for p in ctx.ws.items("problem_statement") for k in ("who", "pain", "done"))


def _confirmed_version(ctx: StageContext) -> str:
    versions = ctx.ws.items("versions")
    return versions[-1]["version"] if versions else "작업본"


def _develop(ctx: StageContext, version: str
             ) -> tuple[str, list[str], int, list[str], Sanitized | None, list[dict[str, str]], str | None]:
    """Ask up to MAX_ATTEMPTS times. Returns (html, summary, attempts, failure reasons, accepted result,
    picture requests whose slot is in the accepted HTML)."""
    failures: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        extra: dict[str, Any] = {"확정 버전": version, "오늘": _today(), **product_form(ctx), **ctx.feedback_extra()}
        if failures:
            extra["이전 응답의 문제"] = failures[-1]
        try:
            output = masked_output(ctx, "developer", ctx.runner.ask(
                "developer", TASK_DEVELOPER, "prototype", PROTOTYPE, extra, retry_cut=False))
        except AgentOutputError as exc:
            failures.append(f"{exc} (JSON 으로 다시 답하세요)")
            continue
        except LinerAPIError:  # a cut stream or a failed call: one failed attempt, then the template (never dead-ends)
            failures.append(CUT_OFF)
            continue
        result = sanitize(str(output.get("html", "")))
        _report_g6(ctx, result)
        if result.valid:
            pictures = requested_images(output, result.html)
            said = output.get("platform") if output.get("platform") in ("app", "web") else None
            return result.html, str_list(output.get("summary")), attempt, failures, result, pictures, said
        failures.append(result.reason)
    return "", [], MAX_ATTEMPTS, failures, None, [], None


def _today() -> str:
    """Sample dates in the prototype start here (11-22: the model picked June on its own)."""
    now = datetime.now(KST)
    return f"{now.year}년 {now.month}월 {now.day}일({WEEKDAYS[now.weekday()]})"


def _report_g6(ctx: StageContext, result: Sanitized) -> None:
    for v in result.violations:
        ctx.ws.guardrail("G6", v["action"], f"외부 자원·네트워크 코드 {'제거' if v['action'] == 'stripped' else '거부'}",
                         actor="developer", code=v["code"], snippet=v["detail"])
