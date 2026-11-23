from __future__ import annotations
"""S7 / FR-14: one zip with the prototype, the four documents as Markdown and the shared source JSON.

Ready once the documents exist, so the client can take the current state at any point of the talk.
Only a bundle whose latest CP4 approval is still current (G2) is the 확정본; anything else is marked 작업본
on its first README line and on top of every document. Every Markdown file also starts with the 가정·미결
items so a reader who opens one file still sees what was not confirmed.
"""

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.korean import josa
from app.doc_html import html_documents
from app.handoff_docs import agents_md, proposal_md
from app.documents import DocContext, build_documents, to_markdown
from app.prototype import with_csp
from app.prototype_kit import with_three
from app.prototype_images import extract_images
from app.swimlane import swimlane_page, swimlane_svg
from app.wireframe import render_wireframe

DOC_FILES = {"brd": "BRD.md", "prd": "PRD.md", "screens": "화면설계서.md", "tests": "테스트케이스.md"}
MARKED = ("가정", "미결", "미확인")
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
    out: dict[str, list[str]] = {status: [] for status in MARKED}
    for kind, _ in STATUS_KINDS:
        for item in source.get(kind, []):
            if item.get("status") in out:
                out[item["status"]].append(f"{item['id']} {item.get('title', '')}".strip())
    out["미결"] += [f"{i['id']} {i.get('title', '')}".strip() for i in source.get("open_items", [])]
    return out


def status_banner(source: Mapping[str, Any]) -> str:
    marked = marked_items(source)
    lines = ["> **가정·미결 표시** — 아래 항목은 발주사가 확정하지 않았습니다. 그대로 만들기 전에 확인하세요.  "]
    lines += [f"> - {status}: {', '.join(items) if items else '없음'}  " for status, items in marked.items()]
    return "\n".join(lines) + "\n\n"


def readme_text(source: Mapping[str, Any], at: str, marker: str | None = None) -> str:
    marked = marked_items(source)
    counts = " · ".join(f"{k} {len(v)}건" for k, v in marked.items())
    return "\n".join([
        *([marker, ""] if marker else []),
        "0to1(영일) — 내려받기 묶음",
        f"만든 시각(UTC): {at}",
        "",
        "들어 있는 파일",
        "- prototype.html : 웹 프로토타입 한 파일. 브라우저로 열면 됩니다. 외부 네트워크 요청은 막혀 있습니다. 아직 만들지 않았으면 없습니다.",
        "- BRD.md : 왜 만드나 (사업 요구)",
        "- PRD.md : 무엇을 만드나 (요구사항과 인수 조건)",
        "- 화면설계서.md : 어떻게 보이나 (화면별 구성 요소, 와이어프레임은 wireframes/ 폴더)",
        "- 테스트케이스.md : 어떻게 확인하나",
        "- AGENTS.md : AI 코딩 도구(Claude Code·Codex 등)에게 그대로 넘기는 작업 지시서. 작업 순서·인수 조건·통과할 테스트",
        "- 제안요약.md : 결재권자·고객에게 보여 줄 한 장 요약. 문제·범위·규모·기대 효과·위험·결정할 것",
        "- index.html, BRD.html … : 같은 문서를 꾸민 HTML. 브라우저로 열어 인쇄하면 A4 PDF 로 저장됩니다.",
        "- images/ : 프로토타입에 넣은 상품 이미지(Liner 이미지 생성). 이미지 모델을 설정하지 않았으면 없습니다.",
        "- user_flow.html : 화면 순서를 그린 사용자 흐름도(Liner 시각화, 외부 자원은 지움). 만들지 못했으면 없습니다.",
        "- user_flow_lanes.html : 고객·앱·운영자 같은 역할별로 누가 무엇을 하는지 그린 레인 흐름도. 점선은 실패·취소 같은 예외 갈림입니다. 디자이너가 적지 않았으면 없습니다.",
        "- source.json : 위 문서들이 공통으로 쓰는 공유 원본(요구사항·화면·테스트·결정·확인 기록). 활동 기록은 뺐습니다.",
        "",
        f"가정·미결 항목: {counts}. 각 마크다운 맨 위에 목록이 있습니다.",
        "",
        "주의: 프로토타입과 문서 속 이름·카드번호·주소 같은 데이터는 모두 지어낸 가짜 데이터입니다.",
        "      실제 고객 정보나 회사 자료는 들어 있지 않습니다.",
        "",
    ])


def export_source(source: Mapping[str, Any], at: str) -> dict[str, Any]:
    """Shared source as stored (fixture fields + added fields), without the activity log."""
    data = {k: v for k, v in source.items() if k != "events"}
    return {**data, "meta": {**dict(source.get("meta", {})), "exported_at": at, "events_omitted": True}}


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
    banner = (f"> **{draft}**\n\n" if draft else "") + status_banner(source)
    for doc_id, name in DOC_FILES.items():
        title, _, rest = to_markdown(docs[doc_id]).partition("\n")
        files[name] = f"{title}\n\n{banner}{rest.lstrip()}"
    flows = source.get("flow_chart") or []
    files.update(html_documents(docs, DOC_FILES, marked_items(source),
                                f"{project or '기획서 묶음'}{' (작업본)' if draft else ''}", at, has_flow=bool(flows)))
    if flows:
        files["user_flow.html"] = with_csp(str(flows[-1].get("html", "")))
    lanes = (source.get("screen_spec") or [{}])[-1].get("swimlane")
    if lanes:
        files["user_flow_lanes.html"] = with_csp(swimlane_page(swimlane_svg(lanes, source.get("screens", []))))
    for screen in source.get("screens", []):
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
