from __future__ import annotations
"""Prototype design kit: one CSS + one tiny script inlined into EVERY prototype after generation.

The developer agent is told the class names (CHEATSHEET) but never has to copy the kit itself:
ensure_kit() injects it when missing, so a model answer and the template fallback look the same.
Nothing here loads anything from outside (no fonts, no CDN) — the preview CSP would block it anyway.
"""

import re
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data"
KIT_CSS = "".join((_DATA / f).read_text(encoding="utf-8")
                  for f in ("prototype_kit.css", "prototype_web.css", "prototype_fx.css"))
KIT_JS = "".join((_DATA / f).read_text(encoding="utf-8") for f in ("prototype_kit.js", "prototype_fx.js"))
STYLE_ID = "proto-kit"
SCRIPT_ID = "proto-kit-js"
THREE_ID = "proto-three"
# three.js r159 (MIT, app/data/vendor/three.LICENSE): the last classic build that sets window.THREE.
# Its first statement is a deprecation console.warn; dropped so the prototype's console stays clean.
_THREE_RAW = (_DATA / "vendor" / "three.min.js").read_text(encoding="utf-8")
_THREE_WARN = re.match(r"console\.warn\('[^']*'\),", _THREE_RAW)
THREE_JS = "void 0," + _THREE_RAW[_THREE_WARN.end():] if _THREE_WARN else _THREE_RAW
PLATFORMS = ("app", "web")
# A 3D part in the markup (an element carrying data-fx3d), not the selector text inside the kit's own CSS/JS.
_USES_3D = re.compile(r"<[a-zA-Z][^<>]*\sdata-fx3d\s*=")
_WEB_WORDS = ("웹", "홈페이지", "사이트", "pc", "데스크톱", "데스크탑", "관리자 페이지", "대시보드", "브라우저", "어드민")
_APP_WORDS = ("앱", "어플", "모바일", "스마트폰", "폰에서")
DEFAULT_ACCENT = "#3157e0"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Domain words → an accent that keeps white button text at 4.5:1 or better.
ACCENTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("꽃", "플라워", "화원", "정원", "flower"), "#c2255c"),
    (("카페", "커피", "베이커리", "빵", "디저트"), "#8a4b1f"),
    (("병원", "의료", "건강", "약국", "진료"), "#0b7285"),
    (("교육", "학원", "학습", "강의", "수업"), "#6741d9"),
    (("여행", "숙박", "호텔", "항공"), "#1864ab"),
    (("음식", "식당", "배달", "레스토랑", "밀키트"), "#c2410c"),
    (("운동", "피트니스", "헬스", "요가"), "#087f5b"),
    (("금융", "은행", "투자", "보험", "결제"), DEFAULT_ACCENT),
)

CHEATSHEET = (
    "디자인 키트(시스템이 CSS·JS 를 자동으로 넣는다 — 키트를 복사하지 말고 클래스만 써라): "
    "<div class=\"app\"> 안에 <header class=\"appbar\"><button class=\"appbar-back\" data-back aria-label=\"뒤로\">‹</button>"
    "<h1 class=\"appbar-title\">앱 이름</h1></header>, <main class=\"main\">, 화면마다 "
    "<section class=\"screen\" data-scr=\"SCR-01\" data-title=\"화면 이름\">(첫 화면만 class 에 is-active), "
    "맨 아래 <nav class=\"tabbar\"><button class=\"tab\" data-go=\"SCR-01\">이름</button></nav>. "
    "이동은 data-go=\"SCR-02\", 완료 알림은 data-toast=\"문구\", 하단 시트는 data-sheet=\"시트id\" + "
    "<div class=\"sheet\" id=\"시트id\" hidden><button class=\"sheet-backdrop\" data-close aria-label=\"닫기\"></button>"
    "<div class=\"sheet-panel\">…</div></div>. 구성 요소: .hero>.title+.subtitle · .section-head>h3 · .card(.flat/.accent) · "
    ".list>.row>.row-main>.row-title+.row-sub (+.row-end) · 세그먼트 <div class=\"seg\" role=\"radiogroup\">"
    "<label><input type=\"radio\" name=\"n\" checked><span>수요일</span></label></div> · "
    ".chips>label.chip>input+span · 선택 카드 .choice-grid>label.choice>input+.choice-title+.choice-desc+.choice-price · "
    ".stepper[data-min][data-max]>button[data-step=-1]+output+button[data-step=1] · "
    ".field>label.label+input/select+.help+.error-text(.field.is-error 로 오류 표시) · "
    ".btn.btn-primary/.btn-secondary/.btn-ghost/.btn-danger(.btn-block) · 화면 맨 끝 고정 버튼 .cta-bar>.btn.btn-primary.btn-block · "
    ".badge(-accent/-success/-warn/-danger) · .banner.banner-info/-warn/-danger/-success · "
    ".empty>.empty-title+.empty-text · 영수증 <dl class=\"summary\"><div class=\"summary-row\"><dt>항목</dt><dd>값</dd></div>"
    "(마지막 줄 .summary-total)</dl> · .skeleton.line · .divider · 미정 값 옆 <span class=\"sample\">예시</span> · "
    "규칙 설명 <details class=\"help\"><summary>자세히</summary><p>…</p></details> · 표 .table-wrap>table.table · "
    ".kpis>.kpi>.kpi-num+.kpi-label · 사진 <img data-img=\"슬롯\" alt=\"…\">(src 없이, .thumb 은 작은 사진). "
    "공유 상태(메모리만, 저장소 금지): 입력에 data-store=\"키\"(라디오는 name 이 키), 다른 화면에서 <span data-bind=\"키\">기본값</span> "
    "· 조건 표시 data-show-if=\"키=값\"(앞에 ! 는 반대) · 버튼 data-set=\"키=값\" · 처음 값 "
    "<script type=\"application/json\" id=\"proto-seed\">{\"키\":\"값\"}</script>. "
    "단계 흐름: <div class=\"flow\" data-flow><div class=\"flow-step\" data-title=\"단계 이름\">필드…"
    "<div class=\"flow-nav\"><button class=\"btn btn-ghost\" data-prev>이전</button><button class=\"btn btn-primary\" data-next>다음</button>"
    "</div></div>…</div>(진행 막대는 키트가 그림, 필수 입력에 required 를 달면 다음 단계 전에 .field.is-error 로 막음). "
    "강조색은 <style>:root{--accent:#hex}</style> 하나로 정한다(업종에 맞게)."
)


FX_CHEATSHEET = (
    " 시각 효과(키트가 그린다 — 화면마다 한두 개, 글을 가리지 않게): 첫 화면 <div class=\"hero\" data-fx3d=\"orb\">(3D 장면 "
    "orb 빛나는 구·rings 도는 고리·wave 물결 점·cards 떠 있는 카드 — 넓은 화면에서는 오른쪽, 폰에서는 위쪽에 놓이고 글은 "
    "그 아래·왼쪽) · 첫 화면 대표 사진 <img data-img=\"hero\" class=\"hero-photo\" alt> · 배경만 은은하게 class=\"fx-aurora\" · 그래프 "
    "<div data-chart=\"line|bar|donut\" data-values=\"12,18,9\" data-labels=\"월,화,수\" aria-label=\"설명\"></div> · "
    "숫자 올라가기 <span data-count>1,240</span> · 완료 버튼 data-confetti · 차례로 등장하는 묶음 class=\"stagger\" · "
    "스크롤 등장 .reveal · 기울어지는 카드 .card.tilt · 반투명 카드 .card.glass · 강조 글자 .grad-text · "
    "배치 .grid-2/.grid-3(웹의 넓은 화면에서 2·3열) · .split(웹에서 왼쪽·오른쪽 두 칸, 폰에서는 위아래)."
)


def platform_for(text: str) -> str:
    """The product's form when no agent said it: web words outnumbering app words make it a web site."""
    lowered = text.lower()
    web = sum(lowered.count(w) for w in _WEB_WORDS)
    app = sum(lowered.count(w) for w in _APP_WORDS)
    return "web" if web > app else "app"


def accent_for(text: str) -> str:
    lowered = text.lower()
    for words, color in ACCENTS:
        if any(w in lowered for w in words):
            return color
    return DEFAULT_ACCENT


def has_kit(html: str) -> bool:
    return f'id="{STYLE_ID}"' in html and f'id="{SCRIPT_ID}"' in html


def ensure_kit(html: str, accent: str = DEFAULT_ACCENT, platform: str = "app") -> str:
    """Inline the kit if it is not there yet. The kit goes first in <head> (inside @layer kit), so any
    style the document writes itself still wins; the script goes last in <body>. <html data-platform>
    switches the kit between the phone layout (app) and the responsive site layout (web)."""
    color = accent if _HEX.match(accent) else DEFAULT_ACCENT
    out = _mark_platform(html, platform if platform in PLATFORMS else "app")
    if f'id="{STYLE_ID}"' not in out:
        style = f'<style id="{STYLE_ID}">{KIT_CSS}@layer kit{{:root{{--accent:{color}}}}}</style>'
        out = _after_head_open(out, style)
    if f'id="{SCRIPT_ID}"' not in out:
        out = _before_body_close(out, f'<script id="{SCRIPT_ID}">{KIT_JS}</script>')
    return out


def with_three(html: str) -> str:
    """Only where a 3D part (data-fx3d) is used, and only for showing (preview, download): the stored
    prototype and every agent payload stay without the 668 KB library."""
    if not _USES_3D.search(html) or f'id="{THREE_ID}"' in html:
        return html
    script = f'<script id="{THREE_ID}">{THREE_JS}</script>'
    kit = html.find(f'<script id="{SCRIPT_ID}"')
    return html[:kit] + script + html[kit:] if kit >= 0 else _before_body_close(html, script)


def _mark_platform(html: str, platform: str) -> str:
    tag = re.search(r"<html\b[^>]*>", html, re.I)
    if not tag or "data-platform" in tag.group(0):
        return html
    return html[:tag.start()] + tag.group(0)[:-1].rstrip() + f' data-platform="{platform}">' + html[tag.end():]


def _after_head_open(html: str, snippet: str) -> str:
    """After <meta charset> when there is one: the charset must stay in the first 1024 bytes of a saved file."""
    charset = re.search(r"<meta\b[^>]*\bcharset\s*=[^>]*>", html, re.I)
    if charset:
        return html[:charset.end()] + snippet + html[charset.end():]
    snippet = f'<meta charset="utf-8">{snippet}'
    head = re.search(r"<head\b[^>]*>", html, re.I)
    if head:
        return html[:head.end()] + snippet + html[head.end():]
    tag = re.search(r"<html\b[^>]*>", html, re.I)
    at = tag.end() if tag else 0
    return html[:at] + f"<head>{snippet}</head>" + html[at:]


def _before_body_close(html: str, snippet: str) -> str:
    for closing in (r"</body\s*>", r"</html\s*>"):
        found = list(re.finditer(closing, html, re.I))
        if found:
            at = found[-1].start()
            return html[:at] + snippet + html[at:]
    return html + snippet
