from __future__ import annotations
"""Pipeline endpoints: S1 input, answers, CP confirmations, retry. Agent work runs as a background task."""

import asyncio
import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.agent_runner import SYSTEM_ACTOR, AgentRunner
from app.attachments import MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS, AttachmentError, check_attachment
from app.audio import MAX_AUDIO_BYTES, AudioFileError, AudioTooLargeError, check_audio, read_limited
from app.change_desk import ChangeDesk, lane
from app.company import company_enabled, company_items
from app.definitions import AgentDef, TeamDef
from app.intake_triage import ACTOR as TRIAGE_ACTOR, Answer, SCHEMA_NAME as TRIAGE_SCHEMA
from app.liner import LinerClient
from app.naming import clean_name
from app.stage_common import g3_check
from app.systems import TEXT_MAX as SYSTEMS_TEXT_MAX
from app.orchestrator import Orchestrator, PipelineStateError
from app.recovery import recover_one
from app.store import ProjectStore, StaleRevisionError
from app.workspace import Workspace

log = logging.getLogger(__name__)

CLIENT_NAME = "발주사"
BUSY = "팀이 작업 중입니다. 끝난 뒤 다시 시도하세요"
TOO_LARGE = "파일이 너무 커요. 25MB 이하로 잘라서 올려 주세요"
TRANSCRIBE_TIMEOUT_S = 120.0
TRANSCRIBE_TIMEOUT = "음성을 글로 바꾸는 데 시간이 너무 오래 걸려요. 더 짧은 녹음으로 다시 올려 주세요"
ATTACHMENT_TOO_LARGE = "파일이 너무 커요. 이미지는 5MB, PDF 는 15MB, 글 파일은 1MB 이하만 올릴 수 있어요"
ATTACHMENT_TIMEOUT_S = 180.0
ATTACHMENT_TIMEOUT = "첨부를 읽는 데 시간이 너무 오래 걸려요. 쪽수가 적은 파일로 나눠 다시 올려 주세요"
TRIAGE_TIMEOUT_S = 90.0
TRIAGE_TIMEOUT = "접수 확인이 너무 오래 걸려요. 잠시 뒤 「팀에게 보내기」를 다시 눌러 주세요"


def declared_length(raw: str | None) -> int | None:
    """Content-Length as sent, or None when absent or malformed (the streamed limit still applies)."""
    try:
        value = int(raw or "")
    except ValueError:
        return None
    return value if value >= 0 else None


class InputBody(BaseModel):
    chunks: list[str] = Field(default_factory=list, max_length=20)
    mask: bool = False
    audio: bool = False  # add the transcript uploaded to /input/audio as one more chunk
    attachments: bool = False  # add the text read from /input/attachment uploads, one chunk each
    systems: str = Field(default="", max_length=SYSTEMS_TEXT_MAX)  # 「우리 시스템 목록」, one system per line


class TriageAnswer(BaseModel):
    slot: Literal["who", "pain", "done"]
    question: str = Field(default="", max_length=300)
    answer: str = Field(default="", max_length=500)


class TriageBody(BaseModel):
    """Same text fields as InputBody (what would be sent) plus the answers given in earlier rounds."""
    chunks: list[str] = Field(default_factory=list, max_length=20)
    answers: list[TriageAnswer] = Field(default_factory=list, max_length=9)
    mask: bool = False
    audio: bool = False
    attachments: bool = False


class AnswerBody(BaseModel):
    question_id: str = Field(min_length=1, max_length=20)
    kind: Literal["choice", "unknown", "free_text"]
    value: str | None = Field(default=None, max_length=500)


class SubmitAnswersBody(BaseModel):
    defaults: dict[str, str] = Field(default_factory=dict)


class ScopeBody(BaseModel):
    keep: list[str] = Field(min_length=1, max_length=50)
    keep_all: bool = False  # 11-22: 「모두 만들기」 — every drawn screen, past the G8 limit


class ChangeBody(BaseModel):
    utterance: str = Field(min_length=1, max_length=300)
    complaint_ref: str | None = Field(default=None, max_length=20)


class ComplaintBody(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class DecisionBody(BaseModel):
    approved: bool
    reason: str | None = Field(default=None, max_length=200)


class ExistingBody(BaseModel):
    alternative_id: str = Field(min_length=1, max_length=20)


class ReqReviewBody(BaseModel):
    verdict: Literal["ok", "fix", "clear"]
    note: str | None = Field(default=None, max_length=300)


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ConfirmBody(BaseModel):
    cp: Literal["CP1", "CP2", "CP3", "CP4"]
    approved: bool
    reason: str | None = Field(default=None, max_length=200)
    # FR-10: one-line reason per waivable warning id (e.g. "coverage.no_tc:REQ-02")
    waivers: dict[str, str] = Field(default_factory=dict, max_length=100)


def build_router(store: ProjectStore, agents: Mapping[str, AgentDef], team: TeamDef,
                 liner: LinerClient) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}")
    # S1 transcripts wait here (memory only) until /input runs the G3 check — nothing unchecked is stored.
    transcripts: dict[str, dict[str, str]] = {}
    attached: dict[str, list[dict[str, str]]] = {}  # same for attachment text, at most MAX_ATTACHMENTS each

    def open_workspace(project_id: str, save: bool = True) -> Workspace:
        """The project's workspace. `save=False` gives a detached copy whose changes stay in memory."""
        project = store.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="프로젝트가 없습니다")
        if project["mode"] != "real":
            raise HTTPException(status_code=400, detail="시연 모드는 실행 기록 재생 전용입니다. 실제 모드 프로젝트를 만드세요")
        saver = store.saver(project_id, project["revision"]) if save else None
        ws = Workspace(project["source"], agents, on_change=saver)
        # One writer at a time: the stage table and the change lane never run at once.
        if ws.pipeline["status"] == "running" or lane(ws.source)["busy"]:
            raise HTTPException(status_code=409, detail=BUSY)
        return ws

    @contextmanager
    def run_lock(project_id: str, tasks: BackgroundTasks | None = None) -> Iterator[list[Callable[[], Any]]]:
        """Hold the project's run lock for this request and for the work it queues (append to the yielded list).

        The queued work runs as one background task; the lock is released when it ends (or fails).
        A save that lost a race (StaleRevisionError) or a wrong state becomes 409.
        """
        token = store.acquire_run(project_id)
        if token is None:
            if store.get(project_id) is None:
                raise HTTPException(status_code=404, detail="프로젝트가 없습니다")
            raise HTTPException(status_code=409, detail=BUSY)
        queued: list[Callable[[], Any]] = []
        handed_over = False
        try:
            orphaned(project_id)  # inside the try: the lock is released even if this fails
            yield queued
            if queued and tasks is not None:
                tasks.add_task(run_then_release, list(queued), project_id, token)
                handed_over = True
        except (StaleRevisionError, PipelineStateError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            if not handed_over:
                store.release_run(project_id, token)

    def orphaned(project_id: str) -> None:
        """Holding the lock means no background work runs for this project. A pipeline still `running` (or a lane
        item still busy) was left by work that died without recovery (L1): fail it the way a crash does."""
        project = store.get(project_id)
        if project is None:
            return
        source = project["source"]
        if source.get("meta", {}).get("pipeline", {}).get("status") == "running" or lane(source)["busy"]:
            log.warning("프로젝트 %s 는 일하는 작업 없이 running 이라 실패로 바꿉니다", project_id)
            recover_one(store, project_id, agents, team, liner, crash="Orphaned")

    def run_then_release(work: list[Callable[[], Any]], project_id: str, token: str) -> None:
        try:
            for fn in work:
                fn()
        except Exception as exc:  # any crash: the project must not stay `running` until a restart (X1)
            log.exception("프로젝트 %s 의 배경 작업이 멈췄습니다", project_id)
            try:
                recover_one(store, project_id, agents, team, liner, crash=type(exc).__name__)
            except Exception:
                log.exception("프로젝트 %s 를 실패로 바꾸지 못했습니다", project_id)
        finally:
            store.release_run(project_id, token)

    def company_material(project_id: str) -> tuple[list[dict[str, Any]], dict[str, str] | None, list[dict[str, Any]]]:
        """The project's company material as CMP- items and the services the company already built
        (copied at S1; later edits do not reach this project)."""
        project = store.get(project_id)
        company = store.get_company(project["company_id"]) if project else None
        if company is None or not company_enabled(liner.env_file):  # EXETHON_COMPANY=off: as before companies
            return [], None, []
        items = company_items(company, store.past_decisions(company["id"], exclude_project=project_id))
        return items, {"id": company["id"], "name": company["name"]}, store.services(company["id"], project_id)

    def make_orchestrator(ws: Workspace) -> Orchestrator:
        return Orchestrator(ws, team, AgentRunner(liner, agents, ws))

    def make_desk(ws: Workspace) -> ChangeDesk:
        return ChangeDesk(ws, team, AgentRunner(liner, agents, ws))

    def act(project_id: str, action: Callable[[Orchestrator], Any], tasks: BackgroundTasks) -> Any:
        with run_lock(project_id, tasks) as later:
            orch = make_orchestrator(open_workspace(project_id))
            result = action(orch)
            later.append(orch.advance)
        return result

    @router.post("/input", status_code=202)
    def submit_input(project_id: str, body: InputBody, tasks: BackgroundTasks) -> Any:
        audio = transcripts.get(project_id) if body.audio else None
        if body.audio and audio is None:
            raise HTTPException(status_code=409, detail="받아 적은 음성이 없어요. 녹음 파일을 다시 올려 주세요")
        files = attached.get(project_id, []) if body.attachments else []
        if body.attachments and not files:
            raise HTTPException(status_code=409, detail="읽어 둔 첨부가 없어요. 파일을 다시 올려 주세요")
        if not audio and not files and not any(c.strip() for c in body.chunks):
            raise HTTPException(status_code=422, detail="요청 메모를 붙여 넣거나 회의 녹음·파일을 올려 주세요")
        company, company_ref, services = company_material(project_id)
        result = act(project_id, lambda o: o.ingest(
            body.chunks, mask=body.mask, audio=audio, systems=body.systems, attachments=files, company=company,
            company_ref=company_ref, services=services), tasks)
        if result.blocked:
            return JSONResponse({"blocked": True, "message": result.message, "kinds": list(result.kinds),
                                 "guard": result.guard})
        transcripts.pop(project_id, None)
        if body.attachments:
            attached.pop(project_id, None)
        return {"blocked": False}

    @router.post("/input/triage")
    async def triage_input(project_id: str, body: TriageBody) -> Any:
        """S1 intake triage before /input: ok · cannot · garbled · insufficient (with one question per empty slot).
        G3 runs before any text goes to Liner; nothing is stored as a source."""
        audio = transcripts.get(project_id) if body.audio else None
        files = attached.get(project_id, []) if body.attachments else []
        answers = [Answer(a.slot, a.question, a.answer) for a in body.answers]
        timeout_event = {"type": "liner_chat", "actor": TRIAGE_ACTOR, "data": {
            "api": "model", "schema": TRIAGE_SCHEMA, "error": "시간 초과", "duration_ms": int(TRIAGE_TIMEOUT_S * 1000)}}
        result = await run_unlocked(project_id, lambda o: o.triage(
                                        body.chunks, answers, mask=body.mask, audio=audio, attachments=files),
                                    TRIAGE_TIMEOUT_S, TRIAGE_TIMEOUT, timeout_event)
        if result.blocked:
            return JSONResponse({"blocked": True, "message": result.message, "kinds": list(result.kinds),
                                 "guard": result.guard})
        if result.error is not None:
            raise HTTPException(status_code=502, detail=result.error)
        return {"blocked": False, **result.verdict.to_dict()}

    @router.post("/input/audio")
    async def upload_audio(project_id: str, request: Request,
                           filename: str = Query(min_length=1, max_length=200)) -> dict[str, Any]:
        """S1: raw audio bytes in the body (no multipart dependency). Returns the transcript to show."""
        declared = declared_length(request.headers.get("content-length"))
        if declared is not None and declared > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail=TOO_LARGE)
        try:
            data = await read_limited(request.stream(), MAX_AUDIO_BYTES)
        except AudioTooLargeError as exc:
            raise HTTPException(status_code=413, detail=TOO_LARGE) from exc
        try:
            check_audio(filename, data)
        except AudioFileError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        timeout_event = {"type": "liner_transcription", "actor": SYSTEM_ACTOR, "data": {
            "api": "audio", "filename": filename, "bytes": len(data), "error": "시간 초과",
            "duration_ms": int(TRANSCRIBE_TIMEOUT_S * 1000)}}
        transcript = await run_unlocked(project_id, lambda o: o.transcribe(filename, data),
                                        TRANSCRIBE_TIMEOUT_S, TRANSCRIBE_TIMEOUT, timeout_event)
        transcripts[project_id] = transcript
        return {"filename": filename, "text": transcript["text"], "chars": len(transcript["text"])}

    @router.post("/input/attachment")
    async def upload_attachment(project_id: str, request: Request,
                                filename: str = Query(min_length=1, max_length=200),
                                purpose: Literal["memo", "systems"] = "memo") -> dict[str, Any]:
        """S1: one image or document as raw bytes. memo → text kept until /input; systems → lines, not kept."""
        declared = declared_length(request.headers.get("content-length"))
        if declared is not None and declared > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail=ATTACHMENT_TOO_LARGE)
        try:
            data = await read_limited(request.stream(), MAX_ATTACHMENT_BYTES)
        except AudioTooLargeError as exc:
            raise HTTPException(status_code=413, detail=ATTACHMENT_TOO_LARGE) from exc
        try:
            found = check_attachment(filename, data)
        except AttachmentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        kept = attached.get(project_id, [])
        if purpose == "memo" and len(kept) >= MAX_ATTACHMENTS and all(a["filename"] != filename for a in kept):
            raise HTTPException(status_code=400, detail=f"첨부는 {MAX_ATTACHMENTS}개까지 올릴 수 있어요. 하나를 빼고 올려 주세요")
        timeout_event = {"type": "liner_attachment", "actor": SYSTEM_ACTOR, "data": {
            "api": "model", "purpose": purpose, "filename": filename, "kind": found.kind, "bytes": len(data),
            "error": "시간 초과", "duration_ms": int(ATTACHMENT_TIMEOUT_S * 1000)}}
        result = await run_unlocked(project_id, lambda o: o.read_attachment(filename, data, purpose),
                                    ATTACHMENT_TIMEOUT_S, ATTACHMENT_TIMEOUT, timeout_event)
        if purpose == "systems":
            return result
        others = [a for a in attached.get(project_id, []) if a["filename"] != filename]
        attached[project_id] = [*others, result]
        return {**result, "chars": len(result["text"])}

    @router.delete("/input/attachment")
    def remove_attachment(project_id: str, filename: str = Query(min_length=1, max_length=200)) -> dict[str, bool]:
        kept = attached.get(project_id, [])
        if all(a["filename"] != filename for a in kept):
            raise HTTPException(status_code=404, detail="그 첨부가 없어요")
        attached[project_id] = [a for a in kept if a["filename"] != filename]
        return {"removed": True}

    async def run_unlocked(project_id: str, call: Callable[[Orchestrator], Any], timeout_s: float,
                           timeout_detail: str, timeout_event: Mapping[str, Any]) -> Any:
        """The Liner call runs on a detached copy without the run lock (it can take long);
        its events (the counted call, G7) are then saved under a short lock."""
        detached = open_workspace(project_id, save=False)
        known = len(detached.log.events)
        orch = make_orchestrator(detached)
        try:
            result = await asyncio.wait_for(run_in_threadpool(call, orch), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            record(project_id, [timeout_event])
            raise HTTPException(status_code=504, detail=timeout_detail) from exc
        except PipelineStateError as exc:
            record(project_id, detached.log.events[known:])
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record(project_id, detached.log.events[known:])
        return result

    def record(project_id: str, events: list[Mapping[str, Any]]) -> None:
        if not events:
            return
        with run_lock(project_id):
            ws = open_workspace(project_id)
            for event in events:
                ws.emit(event["type"], event["actor"], event["data"])

    @router.post("/answers", status_code=202)
    def submit_answer(project_id: str, body: AnswerBody, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.answer(body.question_id, body.kind, body.value), tasks)
        return {"accepted": True}

    @router.post("/answers/submit", status_code=202)
    def submit_answers(project_id: str, tasks: BackgroundTasks, body: SubmitAnswersBody | None = None) -> dict[str, bool]:
        changes = body.defaults if body is not None else {}  # 11-22: the client's changes to the team's defaults
        act(project_id, lambda o: o.submit_answers(changes), tasks)
        return {"accepted": True}

    @router.post("/requirements/{req_id}/review")
    def review_requirement(project_id: str, req_id: str, body: ReqReviewBody, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.review_requirement(req_id, body.verdict, body.note, CLIENT_NAME), tasks)
        return {"accepted": True}

    @router.post("/requirements/confirm-rest")
    def confirm_remaining_requirements(project_id: str, tasks: BackgroundTasks) -> dict[str, Any]:
        count = act(project_id, lambda o: o.confirm_remaining_requirements(CLIENT_NAME), tasks)
        return {"accepted": True, "count": count}

    @router.post("/requirements/fixes", status_code=202)
    def send_requirement_fixes(project_id: str, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.send_requirement_fixes(CLIENT_NAME), tasks)
        return {"accepted": True}

    @router.post("/confirmations", status_code=202)
    def submit_confirmation(project_id: str, body: ConfirmBody, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.confirm(body.cp, body.approved, CLIENT_NAME, body.reason, body.waivers), tasks)
        return {"accepted": True}

    @router.post("/use-existing", status_code=202)
    def use_existing(project_id: str, body: ExistingBody, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.use_existing(body.alternative_id, CLIENT_NAME), tasks)
        return {"accepted": True}

    @router.post("/alternatives/{alternative_id}/gap", status_code=202)
    def build_gap(project_id: str, alternative_id: str, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.build_gap(alternative_id, CLIENT_NAME), tasks)
        return {"accepted": True}

    @router.put("/name")
    def rename(project_id: str, body: NameBody) -> dict[str, str]:
        """D1: the client names the project; S2 never overwrites a name the client gave."""
        try:
            body.name.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HTTPException(status_code=422, detail="이름에 읽을 수 없는 글자가 있어요") from exc
        name = clean_name(body.name)
        if not name:
            raise HTTPException(status_code=422, detail="이름에 글자를 적어 주세요")
        with run_lock(project_id):
            ws = open_workspace(project_id)
            g3_check(ws, [name], "프로젝트 이름")
            ws.set_name(name, "client")
        return {"name": name}

    @router.post("/retry", status_code=202)
    def retry(project_id: str, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.retry(), tasks)
        return {"accepted": True}

    @router.post("/scope", status_code=202)
    def narrow_scope(project_id: str, body: ScopeBody, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.narrow_scope(body.keep, CLIENT_NAME, body.keep_all), tasks)
        return {"accepted": True}

    @router.post("/limits/continue", status_code=202)
    def continue_after_limit(project_id: str, tasks: BackgroundTasks) -> dict[str, bool]:
        act(project_id, lambda o: o.continue_after_limit(), tasks)
        return {"accepted": True}

    # --- change lane (FR-21 · FR-22) ---------------------------------------------------------------
    @router.post("/changes", status_code=202)
    def request_change(project_id: str, body: ChangeBody, tasks: BackgroundTasks) -> dict[str, Any]:
        with run_lock(project_id, tasks) as later:
            desk = make_desk(open_workspace(project_id))
            item = desk.open_change(body.utterance, body.complaint_ref)
            later.append(lambda: desk.map_change(item["id"]))
        return {"id": item["id"]}

    @router.post("/changes/{change_id}/decision", status_code=202)
    def decide_change(project_id: str, change_id: str, body: DecisionBody, tasks: BackgroundTasks) -> dict[str, bool]:
        """CP5. An approval sends the deliverables back through S5 → CP3 → S6 → CP4 (run in the background)."""
        with run_lock(project_id, tasks) as later:
            ws = open_workspace(project_id)
            make_desk(ws).decide(change_id, body.approved, CLIENT_NAME, body.reason)
            if ws.pipeline["status"] == "running":
                later.append(make_orchestrator(ws).advance)
        return {"accepted": True}

    @router.post("/complaints", status_code=202)
    def complain(project_id: str, body: ComplaintBody, tasks: BackgroundTasks) -> dict[str, Any]:
        with run_lock(project_id, tasks) as later:
            desk = make_desk(open_workspace(project_id))
            item = desk.open_complaint(body.text)
            later.append(lambda: desk.check_complaint(item["id"]))
        return {"id": item["id"]}

    return router
