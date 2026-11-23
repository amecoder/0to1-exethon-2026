from __future__ import annotations
"""GitHub 연동 endpoints: per-browser sign-in state (device flow) and pushing a project's bundle as one commit.

Every /api/github request carries an opaque session cookie; a browser without a live one gets a new one, so
each browser signs in to — and pushes with — its own GitHub account. Errors: 401 when this browser is not
(or no longer) signed in, 409 for everything else the user can fix."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.documents import DocContext
from app.export import DownloadNotReadyError, bundle_files, delivery_status
from app.github import SESSION_COOKIE, GitHubClient, GitHubError, GitHubSignedOut
from app.store import ProjectStore

COOKIE_PATH = "/api/github"


class PushBody(BaseModel):
    repo: str = Field(min_length=1, max_length=201)
    private: bool = True


def leaked(files: dict[str, str | bytes], secrets: tuple[str, ...]) -> list[str]:
    """G3 before a push: files holding a configured secret verbatim. Exact values, not patterns — the pattern
    scan flags CSS names and encoded strings in every bundle (326 hits on a real run), and the documents
    were already masked when the agents wrote them."""
    out = []
    for name, content in files.items():
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        if any(s and s.encode("utf-8") in data for s in secrets):
            out.append(name)
    return out


def build_github_router(store: ProjectStore, ctx: DocContext, github: GitHubClient,
                        liner_secrets: Any) -> APIRouter:
    router = APIRouter(prefix=COOKIE_PATH)

    def session_id(request: Request, response: Response) -> str:
        given = request.cookies.get(SESSION_COOKIE)
        sid = github.session(given)
        if sid != given:
            # No max-age: the cookie ends with the browser; the server drops it after SESSION_TTL idle.
            response.set_cookie(SESSION_COOKIE, sid, path=COOKIE_PATH, httponly=True, samesite="lax")
        return sid

    def guarded(action: Any) -> dict[str, Any]:
        try:
            return action()
        except GitHubSignedOut as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except GitHubError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/status")
    def status(sid: str = Depends(session_id)) -> dict[str, Any]:
        return guarded(lambda: github.status(sid))

    @router.post("/connect")
    def connect(sid: str = Depends(session_id)) -> dict[str, Any]:
        return guarded(lambda: github.start(sid))

    @router.post("/poll")
    def poll(sid: str = Depends(session_id)) -> dict[str, Any]:
        return guarded(lambda: github.poll(sid))

    @router.post("/disconnect")
    def disconnect(sid: str = Depends(session_id)) -> dict[str, Any]:
        return guarded(lambda: github.disconnect(sid))

    @router.post("/projects/{project_id}/push")
    def push(project_id: str, body: PushBody, sid: str = Depends(session_id)) -> dict[str, Any]:
        project = store.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="프로젝트가 없습니다")
        source, name = project["source"], str(project.get("name", ""))
        try:
            files = bundle_files(source, ctx, name)
        except DownloadNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        blocked = leaked(files, (*liner_secrets(), *github.secrets()))
        if blocked:
            raise HTTPException(status_code=409, detail=f"G3: 비밀값이 들어 있어 올리지 않았어요 ({', '.join(blocked)})")
        final = delivery_status(source)["final"]
        at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        message = f"{name or '기획서 묶음'} {'확정본' if final else '작업본'} ({at})"
        result = guarded(lambda: github.push(sid, body.repo, files, message, body.private))
        return {**result, "final": final, "message": message}

    return router
