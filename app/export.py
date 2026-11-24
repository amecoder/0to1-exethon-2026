from __future__ import annotations
"""S7 / FR-14: one zip with the prototype, the four documents as Markdown and the shared source JSON.

Ready once the documents exist, so the client can take the current state at any point of the talk.
Only a bundle whose latest CP4 approval is still current (G2) is the 확정본; anything else is marked 작업본
on its first README line and on top of every document. Every Markdown file has a short 「아직 확정되지 않은 것」
part with its own items only (requirements in the PRD, screens in 화면설계서, tests in 테스트케이스), and
README.txt holds the counts once. Documents, wireframes and the lane chart are rendered from the scoped view
(app/scope_view.py): what the client cut when narrowing the screens is listed once and not drawn.
"""

import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.korean import josa
from app.doc_html import html_documents
from app.handoff_docs import agents_md, proposal_md
from app.documents import DocContext, build_documents, to_markdown
from app.open_points import MARKED, assumed_counts, blanks, marked_by_kind, open_counts, open_goals
from app.scope_view import has_cut, scope_view
from app.prototype import with_csp
from app.prototype_kit import with_three
from app.prototype_images import extract_images
from app.swimlane import swimlane_page, swimlane_svg
from app.wireframe import render_wireframe

DOC_FILES = {"brd": "BRD.md", "prd": "PRD.md", "screens": "화면설계서.md", "tests": "테스트케이스.md"}
STATUS_KINDS = (("requirements", "요구사항"), ("screens", "화면"), ("tests", "테스트 케이스"))


class DownloadNotReadyError(RuntimeError):
    """Nothing to bundle yet: the documents are made in S5."""


def cp4_approved(source: Mapping[str, Any]) -> bool:
    """The latest CP4 is an approval made after the latest fixed version (a CP5 change needs a new CP4)."""
    confirmations = list(source.get("confirmations", []))
    cp4 = [i for i, c in enumerate(confirmations) if c.get("cp") == "CP4"]
    if not cp4 or confirmations[cp4[-1]].get("approved") is not True:
        return False
    versions = source.get("versions", [])
    fixed_by = versions[-1].get("confirmation_id") if versions else None
    fixed_at = next((i for i, c in enumerate(confirmations) if c.get("id") == fixed_by), -1)
    return cp4[-1] > fixed_at


NOT_READY = "문서를 만든 뒤(단계 5 문서화 이후)에 내려받을 수 있어요"


def delivery_status(source: Mapping[str, Any]) -> dict[str, Any]:
    """{ready, final, note}: whether a zip can be taken now and whether it is the confirmed one."""
    recheck = source.get("meta", {}).get("recheck")
    final = cp4_approved(source) and not recheck
    ready = final or bool(source.get("screens"))
    if final:
        note = "확인을 모두 마친 확정본이에요"
    elif not ready:
        note = NOT_READY
    elif recheck:
        note = (f"변경 {josa(str(recheck.get('change_id')), '을/를')} 확인하는 중이에요. "
                "지금 상태를 작업본으로 받아요 — 확인 3과 CP4를 다시 마치면 확정본이 돼요")
    else:
        note = "아직 확인을 다 마치지 않았어요. 지금 상태를 작업본으로 받아요 — CP4를 승인하면 확정본이 돼요"
    return {"ready": ready, "final": final, "note": note}


def draft_line(status: Mapping[str, Any]) -> str | None:
    return None if status["final"] else f"[작업본] {status['note']}"


def marked_items(source: Mapping[str, Any]) -> dict[str, list[str]]:
    """{가정|미결|미확인: ["ID 제목"]} over what is in scope — the cover of the HTML bundle lists them all."""
    by_kind = marked_by_kind(scope_view(source))
    out = {status: [item for kind, _ in STATUS_KINDS for item in by_kind[kind][status]] for status in MARKED}
    out["미결"] += [f"{i['id']} {i.get('title', '')}".strip() for i in source.get("open_items", [])]
    return out


def _ids(items: Sequence[str]) -> str:
    """The IDs alone, on their own list line (a reference list, kept apart from the sentence above it)."""
    return "  - " + ", ".join(item.split(" ", 1)[0] for item in items)


def unconfirmed_lines(source: Mapping[str, Any], doc_id: str) -> list[str]:
    """What this one document holds that the client has not confirmed — each item is named in one document only
    (requirements in the PRD, screens in 화면설계서, tests in 테스트케이스); the BRD points at its own tables."""
    view = scope_view(source)
    by_kind, blank, goals = marked_by_kind(view), blanks(view), open_goals(view)
    reqs = by_kind["requirements"]
    if doc_id == "brd":
        lines = [f"- 가정으로 채운 요구사항 {len(reqs['가정'])}건: 「5. 제약과 가정」 표에 있습니다."] if reqs["가정"] else []
        lines += [f"- 숫자 기준이 없는 목표 {len(goals)}개: 「2. 목표와 성공 기준」 표에서 상태가 미결인 줄입니다."] if goals else []
    elif doc_id == "prd":
        opened = [*reqs["미결"], *reqs["미확인"]]
        here = [b for b in blank if b["doc"] == "prd"]
        lines = [f"- 가정 요구사항 {len(reqs['가정'])}건: 「5. 완료 조건」의 가정 표에 있다."] if reqs["가정"] else []
        lines += [f"- 상태가 미결·미확인인 요구사항 {len(opened)}건이다.", _ids(opened)] if opened else []
        lines += [f"- 본문에 미정·빈칸·확인 필요로 남은 요구사항 {len(here)}건: 문장은 「5. 완료 조건」의 미결 표에 있다.",
                  _ids([b["id"] for b in here])] if here else []
    else:
        kind, label = ("screens", "화면") if doc_id == "screens" else ("tests", "테스트 케이스")
        mine = by_kind[kind]
        why = ("확인하는 요구사항이 가정이면 테스트도 함께 가정이 된다. 그래서 요구사항이 확정되면 기대 결과를 다시 확인한다."
               if doc_id == "tests" else "기대는 요구사항이 가정이면 화면도 함께 가정이 된다.")
        lines = [line for status in MARKED if mine[status]
                 for line in (f"- {status} {label} {len(mine[status])}건이다." + (f" {why}" if status == "가정" else ""),
                              _ids(mine[status]))]
        here = [b for b in blank if b["doc"] == doc_id]
        lines += [f"- 빈칸이 남은 화면 요소 {len(here)}곳이다.", *[f"  - {b['id']} {b['title']}" for b in here]] if here else []
    return lines


def status_banner(source: Mapping[str, Any], doc_id: str) -> str:
    """The 「아직 확정되지 않은 것」 part of one Markdown document (a section, so the top of the file stays short)."""
    polite = doc_id == "brd"  # the BRD is the owner's document (합니다체); the others are for developers (한다체)
    lines = unconfirmed_lines(source, doc_id) or ["- 이 문서에는 없습니다." if polite else "- 이 문서에는 없다."]
    intro = ("발주사가 확정하지 않은 항목 가운데 이 문서에 있는 것이며, 묶음 전체의 수는 README.txt에 적었습니다." if polite
             else "발주사가 확정하지 않은 항목 가운데 이 문서에 있는 것이며, 묶음 전체의 수는 README.txt에 적었다.")
    return "\n".join(["## 아직 확정되지 않은 것", "", intro, "", *lines]) + "\n\n"


def count_lines(source: Mapping[str, Any]) -> list[str]:
    """README: how many items are assumed, open or cut — with what each number is made of."""
    view = scope_view(source)
    assumed, opened, cut = assumed_counts(view), open_counts(view), view["out_of_scope"]
    by_kind = marked_by_kind(view)
    unchecked = sum(len(by_kind[kind]["미확인"]) for kind, _ in STATUS_KINDS)
    lines = [f"가정·미결 항목: 가정 {sum(assumed.values())}건 · 미결 {opened['total']}곳 · 미확인 {unchecked}건.",
             f"- 가정 {sum(assumed.values())}건은 요구사항 {assumed['requirements']} · 화면 {assumed['screens']} · "
             f"테스트 케이스 {assumed['tests']}건입니다. 화면과 테스트는 기대는 요구사항이 가정이면 함께 가정이 됩니다. "
             f"그래서 발주사가 확인할 것은 요구사항 {assumed['requirements']}건입니다.",
             f"- 미결 {opened['total']}곳은 상태가 미결·미확인인 항목 {opened['status'] + opened['open_items']} · "
             f"숫자 기준이 없는 목표 {opened['goals']} · 본문에 미정·빈칸·확인 필요로 남은 곳 {opened['blanks']}입니다. "
             "목록은 제안요약.md 「결정이 필요한 것」에 있습니다."]
    if has_cut(view):
        lines.append(f"- 화면 범위를 줄이면서 뺀 것은 요구사항 {len(cut['requirements'])}건 · 화면 {len(cut['screens'])}개 · "
                     f"보류한 테스트 {len(cut['tests'])}건입니다. 만들지 않는 것이기 때문에 위 수에는 넣지 않았고, "
                     "목록은 PRD.md 「2-1. 이번 범위에서 뺀 것」에 있습니다.")
    return [*lines, "- 문서마다 「아직 확정되지 않은 것」 절에 그 문서의 항목만 적었습니다."]


def readme_text(source: Mapping[str, Any], at: str, marker: str | None = None) -> str:
    return "\n".join([
        *([marker, ""] if marker else []),
        "0to1(영일) — 내려받기 묶음",
        f"만든 시각(UTC): {at}",
        "",
        "들어 있는 파일",
        "- prototype.html : 웹 프로토타입 한 파일입니다. 브라우저로 열면 되고, 외부 네트워크 요청은 막혀 있습니다(아직 만들지 않았으면 없습니다).",
        "- BRD.md : 왜 만드나 (사업 요구)",
        "- PRD.md : 무엇을 만드나 (요구사항과 인수 조건)",
        "- 화면설계서.md : 어떻게 보이나 (화면별 구성 요소, 와이어프레임은 wireframes/ 폴더)",
        "- 테스트케이스.md : 어떻게 확인하나",
        "- AGENTS.md : AI 코딩 도구(Claude Code·Codex 등)에게 그대로 넘기는 작업 지시서. 작업 순서·인수 조건·통과할 테스트",
        "- 제안요약.md : 결재권자·고객에게 보여 줄 한 장 요약. 문제·범위·규모·기대 효과·위험·결정할 것",
        "- index.html, BRD.html … : 같은 문서를 꾸민 HTML. 브라우저로 열어 인쇄하면 A4 PDF로 저장됩니다.",
        "- images/ : 프로토타입에 넣은 상품 이미지(Liner 이미지 생성). 이미지 모델을 설정하지 않았으면 없습니다.",
        "- user_flow.html : 화면 순서를 그린 사용자 흐름도(Liner 시각화, 외부 자원은 지움). 만들지 못했으면 없습니다.",
        "- user_flow_lanes.html : 역할별로 누가 무엇을 하는지 그린 레인 흐름도입니다. 점선은 실패·취소 같은 예외 갈림이고, "
        "디자이너가 적지 않았으면 이 파일은 없습니다.",
        "- source.json : 위 문서들이 공통으로 쓰는 공유 원본(요구사항·화면·테스트·결정·확인 기록). 활동 기록은 뺐습니다.",
        "",
        *count_lines(source),
        "",
        "주의: 프로토타입과 문서 속 이름·카드번호·주소 같은 데이터는 모두 지어낸 가짜 데이터입니다.",
        "      실제 고객 정보나 회사 자료는 들어 있지 않습니다.",
        "",
    ])


def export_source(source: Mapping[str, Any], at: str) -> dict[str, Any]:
    """Shared source as stored (fixture fields + added fields), without the activity log. When the client cut
    the scope, `meta.out_of_scope` names the IDs that the documents leave out (the items themselves stay)."""
    data = {k: v for k, v in source.items() if k not in ("events", "out_of_scope")}
    meta = {**dict(source.get("meta", {})), "exported_at": at, "events_omitted": True}
    view = scope_view(source)
    if has_cut(view):
        cut = view["out_of_scope"]
        meta["out_of_scope"] = {"decision": cut["decision"], **{key: [i["id"] for i in cut[key]]
                                                                for key in ("requirements", "screens", "tests")}}
    return {**data, "meta": meta}


def bundle_files(source: Mapping[str, Any], ctx: DocContext | None = None, project: str = "",
                 marker: str | None = None) -> dict[str, str | bytes]:
    """{path: content} of the bundle — the zip and a GitHub push carry exactly these files.

    `marker` is a first README line (the demo download says it was rebuilt from a recording)."""
    status = delivery_status(source)
    if not status["ready"]:
        raise DownloadNotReadyError(NOT_READY)
    draft = draft_line(status)
    marker = "\n".join(m for m in (marker, draft) if m) or None
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    docs = build_documents(source, ctx)
    proto = (source.get("prototype") or [{}])[-1]
    files: dict[str, str | bytes] = {"README.txt": readme_text(source, at, marker)}
    if proto.get("html"):
        files["prototype.html"] = with_csp(with_three(str(proto["html"])))
    for slot, data in extract_images(str(proto.get("html", ""))).items():
        files[f"images/{slot}.jpg"] = data
    view = scope_view(source)
    for doc_id, name in DOC_FILES.items():
        head, mark, rest = to_markdown(docs[doc_id]).partition("## 한눈에 보기")
        title, _, header = head.partition("\n")
        note = f"> **{draft}**\n\n" if draft else ""
        files[name] = f"{title}\n\n{note}{header.lstrip()}{status_banner(source, doc_id)}{mark}{rest}"
    flows = source.get("flow_chart") or []
    by_kind = marked_by_kind(view)
    files.update(html_documents(docs, DOC_FILES, marked_items(source),
                                f"{project or '기획서 묶음'}{' (작업본)' if draft else ''}", at, has_flow=bool(flows),
                                per_doc={"brd": {}, "prd": by_kind["requirements"], "screens": by_kind["screens"],
                                         "tests": by_kind["tests"]}))
    if flows:
        files["user_flow.html"] = with_csp(str(flows[-1].get("html", "")))
    lanes = (view.get("screen_spec") or [{}])[-1].get("swimlane")
    if lanes:
        files["user_flow_lanes.html"] = with_csp(swimlane_page(swimlane_svg(lanes, view.get("screens", []))))
    for screen in view.get("screens", []):
        files[f"wireframes/{screen['id']}.svg"] = render_wireframe(screen)
    files["AGENTS.md"] = agents_md(source)
    files["제안요약.md"] = proposal_md(source)
    files["source.json"] = json.dumps(export_source(source, at), ensure_ascii=False, indent=2)
    return files


def build_bundle(source: Mapping[str, Any], ctx: DocContext | None = None, project: str = "",
                 marker: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in bundle_files(source, ctx, project, marker).items():
            zf.writestr(name, content)
    return buffer.getvalue()
