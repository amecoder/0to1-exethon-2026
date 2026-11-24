from __future__ import annotations
"""Read-only document views (FR-09): JSON for the UI tabs, Markdown and wireframe SVG for export, and each
document as a Word or PDF file to download (11-22)."""

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.doc_docx import to_docx
from app.doc_pdf import to_pdf
from app.documents import DOC_IDS, DocContext, build_documents, to_markdown
from app.export import DOC_FILES
from app.scope_view import scope_view
from app.store import ProjectStore
from app.wireframe import render_wireframe


FILE_TYPES = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "pdf": "application/pdf"}


def document_file(source: Mapping[str, Any], ctx: DocContext, doc_id: str, kind: str) -> Response:
    """One document as Markdown (shown inline) or as a Word / PDF attachment named like the zip's file."""
    if doc_id not in DOC_IDS:
        raise HTTPException(status_code=404, detail=f"문서가 없습니다: {doc_id}")
    doc = build_documents(source, ctx)[doc_id]
    if kind == "md":
        return Response(to_markdown(doc), media_type="text/markdown; charset=utf-8")
    body = to_docx(doc) if kind == "docx" else to_pdf(doc)
    name = f"{DOC_FILES[doc_id].removesuffix('.md')}.{kind}"
    disposition = f"attachment; filename=\"{doc_id}.{kind}\"; filename*=UTF-8''{quote(name)}"
    return Response(body, media_type=FILE_TYPES[kind], headers={"Content-Disposition": disposition})


def build_documents_router(store: ProjectStore, ctx: DocContext) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/documents")

    def source_of(project_id: str) -> dict[str, Any]:
        project = store.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="프로젝트가 없습니다")
        return project["source"]

    @router.get("")
    def documents(project_id: str) -> dict[str, Any]:
        return {"documents": build_documents(source_of(project_id), ctx)}

    @router.get("/wireframes/{screen_id}.svg")
    def wireframe(project_id: str, screen_id: str) -> Response:
        screen = next((s for s in scope_view(source_of(project_id)).get("screens", []) if s["id"] == screen_id), None)
        if screen is None:
            raise HTTPException(status_code=404, detail=f"화면이 없습니다: {screen_id}")
        return Response(render_wireframe(screen), media_type="image/svg+xml")

    @router.get("/{doc_id}.md")
    def markdown(project_id: str, doc_id: str) -> Response:
        return document_file(source_of(project_id), ctx, doc_id, "md")

    @router.get("/{doc_id}.docx")
    def word(project_id: str, doc_id: str) -> Response:
        return document_file(source_of(project_id), ctx, doc_id, "docx")

    @router.get("/{doc_id}.pdf")
    def pdf(project_id: str, doc_id: str) -> Response:
        return document_file(source_of(project_id), ctx, doc_id, "pdf")

    return router
