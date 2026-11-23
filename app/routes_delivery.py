from __future__ import annotations
"""S7 download, isolated prototype preview (FR-13, G6) and demo-mode replay (FR-16). Read-only endpoints."""

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from app.demo import SUMMARY_FIELDS, DemoFileError, load_recording, replay
from app.documents import DocContext, build_documents
from app.export import DownloadNotReadyError, build_bundle
from app.routes_documents import document_file
from app.prototype import PREVIEW_CSP, preview_page
from app.swimlane import swimlane_svg
from app.store import ProjectStore
from app.views import client_todo
from app.trace import otlp_trace

ZIP_NAME = "에이전트팀_결과물.zip"
DEMO_ZIP_NAME = "시연_결과물.zip"
PREVIEW_HEADERS = {"Content-Security-Policy": PREVIEW_CSP, "X-Content-Type-Options": "nosniff",
                   "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def preview_response(source: dict[str, Any], kind: str = "prototype") -> HTMLResponse:
    """G6 isolated preview of the latest prototype, or of the S5 user-flow chart (`kind="flow_chart"`)."""
    items = source.get(kind) or []
    if not items:
        missing = "아직 프로토타입이 없습니다" if kind == "prototype" else "아직 사용자 흐름도가 없습니다"
        raise HTTPException(status_code=404, detail=missing)
    return HTMLResponse(preview_page(items[-1]["html"], kit=kind == "prototype"), headers=PREVIEW_HEADERS)


def lanes_response(source: dict[str, Any]) -> Response:
    """The role swimlane as an SVG image (shown with <img>, so no script can run), same headers as the preview."""
    lanes = (source.get("screen_spec") or [{}])[-1].get("swimlane")
    if not lanes:
        raise HTTPException(status_code=404, detail="아직 역할별 흐름도가 없습니다")
    return Response(swimlane_svg(lanes, source.get("screens", [])), media_type="image/svg+xml",
                    headers=PREVIEW_HEADERS)


def build_delivery_router(store: ProjectStore, ctx: DocContext) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}")

    def source_of(project_id: str) -> dict[str, Any]:
        project = store.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="프로젝트가 없습니다")
        return project["source"]

    @router.get("/prototype/preview", response_class=HTMLResponse)
    def prototype_preview(project_id: str) -> HTMLResponse:
        return preview_response(source_of(project_id))

    @router.get("/flow/preview", response_class=HTMLResponse)
    def flow_preview(project_id: str) -> HTMLResponse:
        return preview_response(source_of(project_id), "flow_chart")

    @router.get("/flow/lanes")
    def flow_lanes(project_id: str) -> Response:
        return lanes_response(source_of(project_id))

    @router.get("/trace")
    def trace(project_id: str) -> dict[str, Any]:
        """E2: the event log as an OTLP/JSON trace (shape only — no collector import tested; no text bodies)."""
        project = store.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="프로젝트가 없습니다")
        return otlp_trace(project_id, project["source"].get("events", []))

    @router.get("/download")
    def download(project_id: str) -> Response:
        try:
            project = store.get(project_id) or {}
            body = build_bundle(source_of(project_id), ctx, str(project.get("name", "")))
        except DownloadNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return zip_response(body, ZIP_NAME)

    return router


def zip_response(body: bytes, name: str) -> Response:
    disposition = f"attachment; filename=\"bundle.zip\"; filename*=UTF-8''{quote(name)}"
    return Response(body, media_type="application/zip", headers={"Content-Disposition": disposition})


def demo_marker(rec: dict[str, Any]) -> str:
    kind = "실제 실행 기록" if rec.get("kind") == "real" else "가짜 응답 녹화"
    return f"[시연 녹화본 · {kind}] {rec.get('notice') or ''} (녹화 {rec.get('recorded_at')})".rstrip()


def build_demo_router(demo_file: Path, ctx: DocContext) -> APIRouter:
    """Replays the recorded events. Nothing here can reach Liner: no client is passed in."""
    router = APIRouter(prefix="/api/demo")

    def recording() -> dict[str, Any]:
        try:
            return load_recording(demo_file)
        except DemoFileError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def bounded(step: int, total: int) -> int:
        return max(0, min(step, total))

    @router.get("")
    def demo_meta() -> dict[str, Any]:
        rec = recording()
        keys = ("format", "kind", "notice", "recorded_at", "model", "project_name", *SUMMARY_FIELDS, "max_cost_usd",
                "operator_note")
        return {k: rec.get(k) for k in keys} | {"total": len(rec["events"])}

    @router.get("/state")
    def demo_state(step: int = Query(0, ge=0)) -> dict[str, Any]:
        events = recording()["events"]
        n = bounded(step, len(events))
        source = replay(events[:n])
        docs = build_documents(source, ctx) if source.get("screens") else None
        return {"step": n, "total": len(events), "event": events[n - 1] if n else None,
                "source": source, "documents": docs, "todo": client_todo(source)}

    @router.get("/download")
    def demo_download() -> Response:
        """The printable bundle rebuilt from the whole recording (read-only), marked as a demo recording."""
        rec = recording()
        try:
            body = build_bundle(replay(rec["events"]), ctx, str(rec.get("project_name") or ""),
                                marker=demo_marker(rec))
        except DownloadNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return zip_response(body, DEMO_ZIP_NAME)

    @router.get("/documents/{doc_id}.{kind}")
    def demo_document(doc_id: str, kind: str, step: int = Query(0, ge=0)) -> Response:
        """One document of the recording at `step`, as Markdown, Word or PDF (11-22)."""
        events = recording()["events"]
        source = replay(events[:bounded(step, len(events)) or len(events)])
        if kind not in ("md", "docx", "pdf") or not source.get("screens"):
            raise HTTPException(status_code=404, detail="아직 이 문서를 받을 수 없어요")
        return document_file(source, ctx, doc_id, kind)

    @router.get("/prototype/preview", response_class=HTMLResponse)
    def demo_preview(step: int = Query(0, ge=0)) -> HTMLResponse:
        events = recording()["events"]
        n = bounded(step, len(events)) or len(events)
        return preview_response(replay(events[:n]))

    @router.get("/flow/preview", response_class=HTMLResponse)
    def demo_flow_preview(step: int = Query(0, ge=0)) -> HTMLResponse:
        events = recording()["events"]
        n = bounded(step, len(events)) or len(events)
        return preview_response(replay(events[:n]), "flow_chart")

    @router.get("/flow/lanes")
    def demo_flow_lanes(step: int = Query(0, ge=0)) -> Response:
        events = recording()["events"]
        n = bounded(step, len(events)) or len(events)
        return lanes_response(replay(events[:n]))

    return router
