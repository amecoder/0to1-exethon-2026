from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.change_desk import lane
from app.company import company_enabled
from app.flow import DEFAULT_FLOW, load_flow
from app.config import LinerKeyMissingError, Settings, read_env, require_api_key
from app.definitions import load_definitions
from app.guard_catalog import load_guards
from app.liner import LinerClient
from app.documents import DocContext
from app.recovery import recover_interrupted
from app.limits import Limits
from app.routes_catalog import build_catalog_router
from app.routes_delivery import build_delivery_router, build_demo_router
from app.routes_documents import build_documents_router
from app.routes_github import build_github_router
from app.github import GitHubClient
from app.routes_pipeline import build_router
from app.routes_company import build_company_router
from app.store import DEFAULT_COMPANY, ProjectStore
from app.tools import ALL_CALLS, TOOLS
from app.export import delivery_status
from app.views import client_todo
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: Literal["demo", "real"]
    company_id: str = DEFAULT_COMPANY


def create_app(settings: Settings | None = None, liner: LinerClient | None = None,
               github: GitHubClient | None = None) -> FastAPI:
    """App factory. Run with: uvicorn app.main:create_app --factory

    `liner` / `github` let tests inject clients on httpx.MockTransport; by default they read keys per call.
    """
    settings = settings or Settings()
    liner = liner or LinerClient(env_file=settings.env_file)
    github = github or GitHubClient(env_file=settings.env_file)
    agents, teams = load_definitions(settings.definitions_root)
    load_flow(DEFAULT_FLOW, agents)  # a flow naming an unknown agent stops the server here, not mid-run (F5)
    guards = load_guards(settings.definitions_root / "policies" / "guardrails.json", agents)  # E3: G9's tool etc.
    store = ProjectStore(settings.db_path)
    recover_interrupted(store, agents, teams["default"], liner)
    app = FastAPI(title="exethon-2026 0to1(영일)")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        """422 without echoing the input back: an input that is not valid Unicode (a lone surrogate) would make the
        error response itself fail to encode (500, review 11-21)."""
        errors = [{k: v for k, v in e.items() if k not in ("input", "ctx")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/liner/key-status")
    def key_status() -> dict[str, bool]:
        return {"present": read_env("LINER_API_KEY", settings.env_file) is not None}

    @app.get("/api/features")
    def features() -> dict[str, bool]:
        return {"company": company_enabled(settings.env_file)}

    @app.get("/api/agents")
    def list_agents() -> dict[str, list[dict[str, Any]]]:
        return {"agents": [asdict(agent) for agent in agents.values()]}

    @app.get("/api/guardrails")
    def list_guardrails() -> dict[str, list[dict[str, Any]]]:
        return {"guardrails": [g.to_dict() for g in guards]}

    @app.get("/api/tools")
    def list_tools() -> dict[str, list[dict[str, Any]]]:
        """Every Liner call the product can make (app/tools.py) and which agents hold each declared tool."""
        return {"tools": [{"id": name, "title": t.title, "api": t.api, "declared": name in TOOLS,
                           "agents": sorted(a.id for a in agents.values() if name in a.tools)}
                          for name, t in ALL_CALLS.items()]}

    @app.get("/api/teams/{team_id}")
    def get_team(team_id: str) -> dict[str, Any]:
        team = teams.get(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=f"팀 '{team_id}' 이 없습니다")
        return team.to_dict()

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectCreate) -> dict[str, Any]:
        if body.mode == "real":
            try:
                require_api_key(settings.env_file)
            except LinerKeyMissingError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            return store.create(body.name, body.mode, company_id=body.company_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="회사가 없습니다") from exc

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        project = store.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="프로젝트가 없습니다")
        # G7 budget, read per request like the key (read-only; None when EXETHON_MAX_COST_USD is unset).
        budget = Limits.from_env(settings.env_file).max_cost_usd
        source = project["source"]
        return {**project, "todo": client_todo(source), "delivery": delivery_status(source), "lane": lane(source),
                "budget_usd": budget}

    app.include_router(build_catalog_router(store, settings.examples_root))
    app.include_router(build_company_router(store))
    app.include_router(build_router(store, agents, teams["default"], liner))
    doc_ctx = DocContext({a.id: a.name for a in agents.values()},
                         tuple((e.id, e.kind) for e in teams["default"].external))
    app.include_router(build_documents_router(store, doc_ctx))
    app.include_router(build_delivery_router(store, doc_ctx))
    app.include_router(build_github_router(store, doc_ctx, github, liner.secrets))
    app.include_router(build_demo_router(settings.demo_file, doc_ctx))

    @app.middleware("http")
    async def cache_policy(request: Request, call_next: Any) -> Any:
        """index.html must be revalidated on every load, or a browser keeps calling an old build's bundle
        after a deploy; the hashed /assets files never change, so they can be kept."""
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif not path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Built React app (frontend/ -> app/static). Registered last so /api routes win.
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True, check_dir=False), name="static")
    return app
