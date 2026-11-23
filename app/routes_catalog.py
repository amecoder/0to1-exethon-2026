from __future__ import annotations
"""Read-only catalog endpoints: the example request memo (「예제 메모 채우기」) and the recent real projects."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.store import ProjectStore

EXAMPLE_MEMO = "request_memo.md"
MISSING_EXAMPLE = "예제 메모 파일이 없어요. 저장소의 예제 메모(request_memo.md)를 확인해 주세요"
RECENT_LIMIT = 20
ALL_LIMIT = 1000  # 「전체 보기」: every project is kept; one page is enough for a PoC


def memo_body(markdown: str) -> str:
    """Everything below the first line that is exactly '---' (the header block explains the file, not the request)."""
    lines = markdown.splitlines()
    cut = next((i for i, line in enumerate(lines) if line.strip() == "---"), None)
    body = lines[cut + 1:] if cut is not None else lines
    return "\n".join(body).strip()


def build_catalog_router(store: ProjectStore, examples_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/sample-memo")
    def example_memo() -> dict[str, str]:
        path = examples_root / EXAMPLE_MEMO
        if not path.is_file():
            raise HTTPException(status_code=404, detail=MISSING_EXAMPLE)
        return {"name": EXAMPLE_MEMO, "text": memo_body(path.read_text(encoding="utf-8"))}

    @router.get("/projects")
    def recent_projects(limit: int = Query(RECENT_LIMIT, ge=1, le=ALL_LIMIT),
                        company: str | None = Query(None, max_length=64)) -> dict[str, Any]:
        """Newest first; `total` says how many exist so the start screen can offer 「전체 N개 보기」.
        `company`: only that company's projects (the start screen always sends the chosen one)."""
        return {"projects": store.summaries("real", limit, company_id=company),
                "total": store.count("real", company_id=company)}

    return router
