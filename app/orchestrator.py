from __future__ import annotations
"""FR-04: code-defined stage table S1→S2→CP1→S3→S4→CP2→S5→CP3→S6→CP4. The coordinator never picks the order.

Pipeline state lives in source.meta.pipeline: {stage, status, active_agent, error, feedback}.
status: awaiting_input | running | awaiting_answers | awaiting_scope | awaiting_confirmation | stopped |
failed | completed | closed
(completed = CP4 approved; S7 download is enabled. closed = at CP1 the client chose an existing product instead of
building — the project ends there with that decision on record. stopped = G7 limit reached, the client may 「계속」.
awaiting_scope = G8, the designer drew more screens than the limit and the client picks which to keep.)
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.company import masked_service, ranked_service, report_systems_list, service_items, service_line
from app.naming import clean_name
from app.korean import josa
from app.agent_runner import AgentRunner, AgentOutputError
from app.attachments import NOTES as ATTACHMENT_NOTES
from app.attachments import check_attachment, decode_text, system_lines, text_systems
from app.answer_desk import INTENT_LABELS, answer, classify
from app.bus import MessageBus
from app.change_desk import open_change
from app.checks import approval_problems
from app.config import LinerKeyMissingError
from app.credits import record_balance
from app.definitions import TeamDef
from app.errors import ConfirmationRequiredError, PipelineStateError
from app import team_defaults
from app.flow import DEFAULT_FLOW, Flow, StageSpec, load_flow
from app.hooks import APPROVE_HOOKS
from app.runs import PRECHECKS, RUNS
from app.guardrails import G3_PROMPT, mask_sensitive, sensitive_labels
from app.policy import guard_purpose
from app.intake import split_sentences
from app.intake_triage import Answer, TriageResult, run_triage
from app.liner import LinerAPIError, LinerConfigError
from app.limits import LimitReachedError, stop_message, unresolved_block
from app.req_review import NOTE_MAX, VERDICTS, fix_lines, fixes_text, review_summary, signature
from app.stage_common import FIRST_ROUND_MAX_CARDS, UNKNOWN_OPTION, StageContext, g3_check, gap_instruction
from app.stage_documents import RESUME_REST, keep_screens
from app.systems import MAX_SERVICES, NAME_MAX, listed_lines, parse_systems
from app.workspace import SYSTEM, Workspace

__all__ = ["FIRST_ROUND_MAX_CARDS", "UNKNOWN_OPTION", "STAGE_TABLE", "Orchestrator", "ConfirmationRequiredError",
           "PipelineStateError"]

ANSWER_KINDS = ("choice", "unknown", "free_text")
INTERRUPTED = "서버가 다시 시작되어 작업이 중단되었습니다. '다시 시도'를 누르면 이 단계를 처음부터 다시 합니다"
FAILURES = (AgentOutputError, LinerAPIError, LinerConfigError, LinerKeyMissingError)
AUDIO_NOTE = "음성에서 받아 적음"


# The business flow is a file (flows/requirements.json, app/flow.py); the engine below only walks it.
DEFAULT = load_flow(DEFAULT_FLOW)
STAGE_TABLE: tuple[StageSpec, ...] = DEFAULT.stages
COMPLETED = "completed"
CLOSED = "closed"
STAGES = {s.id: s for s in STAGE_TABLE}


@dataclass(frozen=True)
class IngestResult:
    blocked: bool
    message: str = ""
    kinds: tuple[str, ...] = ()
    guard: str | None = None  # which guardrail stopped it: G3 (can be masked and sent) or G9 (cannot)


class Orchestrator:
    def __init__(self, workspace: Workspace, team: TeamDef, runner: AgentRunner, flow: Flow | None = None) -> None:
        self._ws = workspace
        self._ctx = StageContext(workspace, MessageBus(team, workspace), runner)
        self._flow = flow or DEFAULT

    # --- S1 ------------------------------------------------------------------------------------
    def ingest(self, chunks: Sequence[str], mask: bool = False, audio: Mapping[str, str] | None = None,
               systems: str = "", attachments: Sequence[Mapping[str, str]] = (),
               company: Sequence[Mapping[str, Any]] = (), company_ref: Mapping[str, str] | None = None,
               services: Sequence[Mapping[str, Any]] = ()) -> IngestResult:
        """`audio`: a transcript ({text, filename}) from Liner speech-to-text, stored as its own chunk.
        `attachments`: text read from images/documents ({filename, kind, text}), each stored as its own chunk.
        `systems`: the client's own system list (one per line), stored as SYS- items beside the sources.
        `company`: the company material (CMP- items, app/company.py) copied in; `company_ref` = {id, name}.
        `services`: what the company already built with 0to1 — each becomes one more line of the systems list,
        so S2 can say 기능 추가 / 연계 to it instead of building it again (features ordered by Liner Rerank)."""
        self._expect(self._flow.first.id, "awaiting_input")
        chunks = [c for c in chunks if c.strip()]
        marks: dict[int, dict[str, str]] = {}  # chunk number → where those sentences came from
        if audio is not None:
            chunks = [*chunks, audio["text"]]
            marks[len(chunks)] = {"origin": "audio", "origin_note": AUDIO_NOTE, "audio_file": audio["filename"]}
        for item in attachments:
            chunks = [*chunks, item["text"]]
            marks[len(chunks)] = {"origin": item["kind"], "origin_note": ATTACHMENT_NOTES[item["kind"]],
                                  "attachment_file": item["filename"]}
        own = {x["name"] for x in parse_systems(systems)}
        services = [s for s in services if clean_name(str(s.get("name", "")))[:NAME_MAX] not in own]  # client's line wins
        dropped = [mask_sensitive(clean_name(str(s.get("name", "")))) for s in services[:-MAX_SERVICES]]  # keep newest
        services = list(services[-MAX_SERVICES:])
        service_texts = [t for s in services for t in (str(s.get("name", "")), *(str(f.get("title", ""))
                                                                              for f in s.get("features", [])))]
        labels = sensitive_labels([*chunks, systems, *service_texts])
        if labels and not mask:
            self._ws.guardrail("G3", "blocked", "민감 정보 패턴 발견 — 저장하지 않음", kinds=labels)
            return IngestResult(True, G3_PROMPT.format(kinds=", ".join(labels)), tuple(labels), "G3")
        if labels:
            self._ws.guardrail("G3", "masked", "민감 정보를 가린 값으로 저장", kinds=labels)
            chunks = [mask_sensitive(c) for c in chunks]
            systems = mask_sensitive(systems)
            services = [masked_service(s) for s in services]
        draft = "\n".join([*([systems] if systems.strip() else []), *(service_line(s) for s in services)])
        try:
            verdict = guard_purpose(self._ws, self._ctx.runner, [*chunks, *([draft] if draft else [])], "요구 입력")
        except LimitReachedError as exc:  # G7 at the G9 call: the stop card, not a 500
            raise PipelineStateError(stop_message(exc, self._flow.stages[0].title, self._ctx.runner.limits.max_calls)) from exc
        if verdict.blocked:
            return IngestResult(True, verdict.message(), (), "G9")
        # Rerank only after G3 and G9: it sends the (masked) request out and its query is logged.
        request = "\n".join(chunks)
        ranked = [ranked_service(self._ctx, request, s) for s in services]
        sources = split_sentences(chunks)
        sources = [{**s, **marks.get(s["chunk"], {})} for s in sources]
        if not sources:
            raise PipelineStateError("입력된 문장이 없습니다")
        self._ws.emit("stage_started", SYSTEM, {"stage": self._flow.first.id})
        record_balance(self._ws, self._ctx.runner.client, "start")
        self._ws.add_sources(sources)
        own_catalog = parse_systems(systems)
        catalog = [*own_catalog, *service_items(ranked, start=len(own_catalog) + 1)]
        if catalog:
            self._ws.add_systems(catalog)
        report_systems_list(self._ws, listed_lines(systems), len(own_catalog), dropped, ranked)
        if company or company_ref:
            self._ws.add_company(company, company_ref or {})
        self._ws.emit("stage_completed", SYSTEM, {"stage": self._flow.first.id})
        self._enter_next(self._flow.first.id)
        return IngestResult(False)

    def triage(self, chunks: Sequence[str], answers: Sequence[Answer], mask: bool = False,
               audio: Mapping[str, str] | None = None, attachments: Sequence[Mapping[str, str]] = ()) -> TriageResult:
        """S1 intake triage before ingest(): judges the same text ingest() would get. Stores no sources."""
        self._expect(self._flow.first.id, "awaiting_input")
        texts = [*chunks, *([audio["text"]] if audio is not None else []), *(a["text"] for a in attachments)]
        return run_triage(self._ws, self._ctx.runner, texts, answers, mask)

    def transcribe(self, filename: str, data: bytes) -> dict[str, str]:
        """S1 audio: Liner speech-to-text. Nothing is stored until ingest() runs the G3 check on the text."""
        self._expect(self._flow.first.id, "awaiting_input")
        try:
            body = self._ctx.runner.transcribe(filename, data)
        except LimitReachedError as exc:
            raise PipelineStateError(stop_message(exc, self._flow.stages[0].title, self._ctx.runner.limits.max_calls)) from exc
        except (LinerAPIError, LinerConfigError, LinerKeyMissingError) as exc:
            raise PipelineStateError(f"음성을 글로 바꾸지 못했어요: {exc}") from exc
        text = str(body.get("text", "")).strip()
        if not text:
            raise PipelineStateError("음성에서 받아 적은 말이 없어요. 말소리가 들어 있는 파일인지 확인해 주세요")
        return {"text": text, "filename": filename}

    def read_attachment(self, filename: str, data: bytes, purpose: str) -> dict[str, Any]:
        """S1 attachment → {filename, kind, text} (memo) or {filename, kind, lines} (systems).
        Text files are decoded here without a call. Nothing is stored: ingest() runs the G3 check on the text."""
        self._expect(self._flow.first.id, "awaiting_input")
        found = check_attachment(filename, data)
        if found.format == "text":
            text = decode_text(data)
            output: Mapping[str, Any] = {"text": text} if purpose == "memo" else {"lines": text_systems(filename, text)}
        else:
            try:
                answer = self._ctx.runner.read_attachment(filename, found, data, purpose)
            except LimitReachedError as exc:
                raise PipelineStateError(stop_message(exc, self._flow.stages[0].title, self._ctx.runner.limits.max_calls)) from exc
            except FAILURES as exc:
                raise PipelineStateError(f"첨부를 읽지 못했어요: {exc}") from exc
            output = ({"text": str(answer.get("text", "")).strip()} if purpose == "memo"
                      else {"lines": system_lines(answer.get("systems"))})
        if purpose == "memo" and not output["text"]:
            raise PipelineStateError("첨부에서 옮겨 적을 글자를 찾지 못했어요. 글씨나 화면이 보이는 파일인지 확인해 주세요")
        if purpose == "systems" and not output["lines"]:
            raise PipelineStateError("첨부에서 시스템을 찾지 못했어요. 시스템 이름이 적힌 파일인지 확인해 주세요")
        return {"filename": filename, "kind": found.kind, **output}

    # --- running -------------------------------------------------------------------------------
    def advance(self) -> None:
        """Run work stages in table order until a human is needed (answers, confirmation) or failure."""
        while self._ws.pipeline["status"] == "running":
            stage = self._ws.pipeline["stage"]
            if self._flow.stage(stage).kind == "confirm":
                if not self._handle_asked(stage):
                    return
                continue
            try:
                waiting = self.run_stage(stage)
            except LimitReachedError as exc:
                self._ws.set_pipeline(status="stopped", active_agent=None,
                                      error=stop_message(exc, self._flow.stage(stage).title, self._ctx.runner.limits.max_calls))
                return
            except FAILURES as exc:
                self._ws.set_pipeline(status="failed", active_agent=None, error=str(exc))
                return
            if waiting:
                self._ws.set_pipeline(status=waiting, active_agent=None)
                return
            self._enter_next(stage)

    def _handle_asked(self, cp: str) -> bool:
        """What the client wrote instead of approving: answer a question in place, rework for a fix.
        Returns True when a rework stage was entered (the loop continues), False when back at the confirmation."""
        asked = self._ws.pipeline.get("asked") or {}
        if not asked.get("text"):
            self._ws.set_pipeline(status="awaiting_confirmation", active_agent=None, asked=None)
            return False
        text, who = str(asked.get("text", "")), str(asked.get("who", "발주사"))
        try:
            decision = classify(self._ctx, cp, text)
            self._ws.emit("check_result", "coordinator", {
                "check": "client_intent", "outcome": decision["intent"], "items": [cp],
                "details": [f"「{text[:40]}」 → {INTENT_LABELS[decision['intent']]}"
                            + (f" (확신도 {decision['confidence']:.2f})" if decision.get("confidence") is not None else "")
                            + (f" · {decision['fallback']}" if decision.get("fallback") else "")]})
            if decision["intent"] == "question":
                answer(self._ctx, cp, text, decision)
            elif decision["intent"] == "both":
                self._answer_then_rework(cp, text, decision)
        except LimitReachedError as exc:
            self._ws.set_pipeline(status="stopped", active_agent=None,
                                  error=stop_message(exc, self._flow.stage(cp).title, self._ctx.runner.limits.max_calls))
            return False
        except FAILURES as exc:
            # Nothing was changed: back to the same confirmation, and the client can write again.
            self._ws.set_pipeline(status="awaiting_confirmation", active_agent=None, asked=None,
                                  error=f"말씀에 답하지 못했어요. 다시 적어 주세요: {exc}")
            return False
        record_balance(self._ws, self._ctx.runner.client, f"after {cp} 말씀 처리")  # the budget meter moves
        if decision["intent"] == "question":
            self._ws.set_pipeline(status="awaiting_confirmation", active_agent=None, asked=None)
            return False
        self._ws.add_confirmation(cp, False, who, text, None, None)
        self._ws.set_pipeline(stage=self._flow.stage(cp).rework, status="running", feedback=text, asked=None)
        return True

    def _answer_then_rework(self, cp: str, text: str, decision: Mapping[str, Any]) -> None:
        """`both`: the answer is a courtesy — if it fails, the fix request still goes to rework."""
        try:
            answer(self._ctx, cp, text, decision)
        except FAILURES as exc:
            self._ws.emit("check_result", "coordinator", {"check": "client_answer", "outcome": "skipped",
                                                          "items": [cp], "details": [f"답을 쓰지 못했어요: {exc}"]})

    def run_stage(self, stage_id: str) -> str | None:
        """Run one work stage. Returns the waiting status when a human is needed mid-stage, else None."""
        self._gate(stage_id)
        self._ctx.runner.check_stage_budget(stage_id)
        self._ws.set_pipeline(stage=stage_id, status="running")
        spec = self._flow.stage(stage_id)
        self._ws.emit("stage_started", SYSTEM, {"stage": stage_id, "agents": list(spec.agents)})
        waiting = RUNS[spec.run or ""](self._ctx)
        self._ws.emit("stage_completed", SYSTEM, {"stage": stage_id})
        record_balance(self._ws, self._ctx.runner.client, f"after {stage_id}")
        # A G8 pause is mid-stage: keep a rejection reason for the part of S5 that is still ahead.
        self._ws.set_pipeline(active_agent=None, **({} if waiting == "awaiting_scope" else {"feedback": None}))
        return waiting

    def _enter_next(self, stage_id: str) -> None:
        """Stage and status are saved together, so a restart can never leave a CP `running`."""
        nxt = self._flow.next(stage_id)
        if nxt is None:
            self._ws.set_pipeline(status=COMPLETED)
        elif nxt.kind == "confirm":
            self._ws.set_pipeline(stage=nxt.id, status="awaiting_confirmation")
            self._ws.emit("stage_started", SYSTEM, {"stage": nxt.id})
        else:
            self._ws.set_pipeline(stage=nxt.id, status="running")

    def _gate(self, stage_id: str) -> None:
        """G2: every confirmation point before this stage needs an approved latest record."""
        for spec in self._flow.before(stage_id):
            if spec.kind == "confirm" and not self._approved(spec.id):
                self._block(f"{spec.id} 확인 기록 없이 {josa(stage_id, '을/를')} 시작할 수 없습니다")
        why = PRECHECKS[run](self._ctx, stage_id) if (run := self._flow.stage(stage_id).run) in PRECHECKS else None
        if why:
            self._block(why)

    @staticmethod
    def _role(stage: StageSpec | None) -> str:
        """The stage id that plays a role in this flow (a job or a confirmation feature), or a clear refusal."""
        if stage is None:
            raise PipelineStateError("이 업무 흐름에는 그 단계가 없어요")
        return stage.id

    def _block(self, detail: str) -> None:
        self._ws.guardrail("G2", "blocked", detail)
        raise ConfirmationRequiredError(detail)

    def _approved(self, cp: str) -> bool:
        records = [c for c in self._ws.items("confirmations") if c["cp"] == cp]
        return bool(records) and records[-1]["approved"] is True

    # --- recovery ------------------------------------------------------------------------------
    def mark_interrupted(self, error: str = INTERRUPTED, crash: str | None = None) -> None:
        """Startup (or a crashed background task): a run left `running` cannot resume mid-call → failed."""
        self._ws.emit("run_interrupted", SYSTEM, {"stage": self._ws.pipeline["stage"], **({"crash": crash} if crash else {})})
        self._ws.set_pipeline(status="failed", active_agent=None, error=error)

    def restore_confirmation(self, error: str | None = None, crash: str | None = None) -> None:
        """Startup: a confirmation stage only waits for a person, so it is restored instead of failed."""
        data = {"stage": self._ws.pipeline["stage"], "restored": True, **({"crash": crash} if crash else {})}
        self._ws.emit("run_interrupted", SYSTEM, data)
        self._ws.set_pipeline(status="awaiting_confirmation", active_agent=None, error=error,
                              **({"asked": None} if crash else {}))  # the crashed question is not pending any more

    def retry(self) -> None:
        """Re-run the current work stage after a failure (call advance() afterwards)."""
        stage = self._ws.pipeline["stage"]
        if self._ws.pipeline["status"] != "failed" or not self._flow.has(stage) or self._flow.stage(stage).kind != "work":
            raise PipelineStateError("실패한 작업 단계에서만 다시 시도할 수 있습니다")
        self._ws.emit("run_retried", "client", {"stage": stage})
        self._ws.set_pipeline(status="running", error=None)

    def continue_after_limit(self) -> None:
        """G7 「계속」: the client's record grants another batch of calls and restarts the stage clock.

        A stopped pipeline restarts its stage (call advance() afterwards). A limit hit by a change request
        (pipeline not stopped) only needs the record; the client sends the request again.
        """
        block = unresolved_block(self._ws.log.events)
        if block is None:
            raise PipelineStateError("상한에 닿아 멈춘 작업이 없습니다")
        self._ws.guardrail("G7", "resumed", "발주사가 「계속」을 눌러 상한을 한 번 더 늘림", actor="client",
                           limit=block.get("limit"), stage=block.get("stage"))
        if self._ws.pipeline["status"] == "stopped":
            self._ws.set_pipeline(status="running", error=None)

    # --- human input ---------------------------------------------------------------------------
    def confirm(self, cp: str, approved: bool, who: str, reason: str | None = None,
                waivers: Mapping[str, str] | None = None) -> None:
        self._expect(cp, "awaiting_confirmation")
        pending = open_change(self._ws.source)
        if pending is not None:
            raise PipelineStateError(f"변경 요청 {pending['id']} 을(를) 먼저 정해 주세요 (CP5)")
        reason = (reason or "").strip()
        if not approved and (not reason or "\n" in reason):
            raise PipelineStateError("반려할 때는 사유를 한 줄로 적어 주세요")
        waivers = {k: v.strip() for k, v in (waivers or {}).items() if v.strip()}
        g3_check(self._ws, [reason, *waivers.values()], f"{cp} 반려 사유·면제 이유")
        if approved:
            self._check_approvable(cp, waivers)
        if not approved:
            # Sorted in the background (answer_desk): a question is answered without reworking the stage.
            self._ws.emit("client_message", "client", {"cp": cp, "text": reason, "who": who})
            self._ws.set_pipeline(status="running", active_agent=None, error=None, asked={"text": reason, "who": who})
            return
        if self._ws.pipeline.get("error"):
            self._ws.set_pipeline(error=None)  # a failed answer's note must not follow to the next stage
        # What approving does is declared by the flow (on_approve, app/hooks.py): versions, binding, rechecks.
        hooks = [APPROVE_HOOKS[name] for name in self._flow.stage(cp).on_approve]
        fields: dict[str, Any] = {}
        for hook in hooks:
            fields.update(hook.fields(self._ws))
        version = fields.pop("version", None)
        record = self._ws.add_confirmation(cp, approved, who, reason or None, version, waivers or None, **fields)
        for hook in hooks:
            hook.after(self._ws, record)
        self._enter_next(cp)

    def review_requirement(self, req_id: str, verdict: str, note: str | None, who: str) -> None:
        """CP2 card review: 확정 (ok), 고칠 점 (fix + note), or clear the mark. Nothing runs until sent."""
        self._expect(self._role(self._flow.with_feature("requirement_review")), "awaiting_confirmation")
        req = self._ws.get("requirements", req_id)
        if req is None:
            raise PipelineStateError(f"요구사항이 없습니다: {req_id}")
        note = (note or "").strip()
        if verdict == "fix" and not (0 < len(note) <= NOTE_MAX):
            raise PipelineStateError(f"고칠 점을 {NOTE_MAX}자 안으로 적어 주세요")
        if verdict not in (*VERDICTS, "clear"):
            raise PipelineStateError("확정, 고칠 점, 지우기 중 하나만 할 수 있어요")
        if note:
            g3_check(self._ws, [note], f"{req_id} 고칠 점")
        reviews = dict((self._ws.meta.get("req_reviews") or {}))
        if verdict == "clear":
            reviews.pop(req_id, None)
        else:
            reviews[req_id] = {"verdict": verdict, "note": note if verdict == "fix" else None,
                               "sig": signature(req), "who": who}
        self._ws.set_req_reviews(reviews)
        self._ws.emit("requirement_reviewed", "client", {"requirement_id": req_id, "verdict": verdict,
                                                         "note": note or None})

    def confirm_remaining_requirements(self, who: str) -> int:
        """「남은 카드 모두 확정」: every card without a current mark becomes 확정; 고칠 점 notes stay as they are."""
        self._expect(self._role(self._flow.with_feature("requirement_review")), "awaiting_confirmation")
        reqs = {r["id"]: r for r in self._ws.items("requirements")}
        rest = [i["id"] for i in review_summary(self._ws.source)["items"] if i["verdict"] is None]
        if not rest:
            raise PipelineStateError("남은 카드가 없어요")
        reviews = dict((self._ws.meta.get("req_reviews") or {}))
        reviews.update({rid: {"verdict": "ok", "note": None, "sig": signature(reqs[rid]), "who": who} for rid in rest})
        self._ws.set_req_reviews(reviews)
        self._ws.emit("requirements_reviewed", "client", {"requirement_ids": rest, "verdict": "ok"})
        return len(rest)

    def send_requirement_fixes(self, who: str) -> None:
        """All 고칠 점 notes go back as one PM pass (S4); 확정 marks on unchanged requirements stay."""
        cp = self._role(self._flow.with_feature("requirement_review"))
        finalize = self._role(self._flow.running("finalize"))
        self._expect(cp, "awaiting_confirmation")
        text = fixes_text(self._ws.source)
        if text is None:
            raise PipelineStateError("고칠 점이 적힌 요구사항이 없어요")
        lines = fix_lines(self._ws.source)
        said = f"요구사항 {len(lines)}건 고쳐 주세요 · " + " / ".join(lines)
        self._ctx.bus.send("client", "coordinator", said)
        self._ws.add_confirmation(cp, False, who, said, None, None)
        kept = {rid: m for rid, m in (self._ws.meta.get("req_reviews") or {}).items() if m.get("verdict") == "ok"}
        self._ws.set_req_reviews(kept)
        # S4 only (the answers stand): a plain CP2 rejection reruns S3 and may ask new questions.
        self._ws.set_pipeline(stage=finalize, status="running", feedback=text, asked=None, error=None)

    def use_existing(self, alternative_id: str, who: str) -> None:
        """CP1 build-or-buy: the client takes an existing product (ALT-) and the project stops before S3."""
        self._expect(self._role(self._flow.with_feature("build_or_buy")), "awaiting_confirmation")
        alt = self._ws.get("alternatives", alternative_id)
        if alt is None:
            raise PipelineStateError(f"목록에 있는 기존 제품을 골라 주세요: {alternative_id}")
        others = [a["name"] for a in self._ws.items("alternatives") if a["id"] != alternative_id]
        self._ctx.bus.send("client", "coordinator", f"기존 제품을 쓸게요: {alt['name']}")
        self._ws.write("coordinator", "decisions", {
            "id": self._ws.next_id("decisions", "DEC"), "kind": "build_or_buy", "topic": "만들기 전에: 기존 제품으로 충분한가",
            "chosen": alt["name"], "answer_kind": "build_or_buy", "rejected": ["새로 만들기", *others],
            "status": "확정", "answered_by": "client", "who": who, "alternative_ref": alternative_id,
            "evidence_refs": alt.get("evidence_refs", []),
        })
        self._ws.set_pipeline(status=CLOSED, active_agent=None, feedback=None)

    def build_gap(self, alternative_id: str, who: str) -> None:
        """CP1 「모자란 부분만 만들기」: the client uses the product (ALT-) and only what it lacks is built.
        Scope is updated by code (no model call), then CP1 is approved and the pipeline moves on to S3."""
        cp = self._role(self._flow.with_feature("build_or_buy"))
        self._expect(cp, "awaiting_confirmation")
        alt = self._ws.get("alternatives", alternative_id)
        if alt is None:
            raise PipelineStateError(f"목록에 있는 기존 제품을 골라 주세요: {alternative_id}")
        pending = open_change(self._ws.source)
        if pending is not None:
            raise PipelineStateError(f"변경 요청 {pending['id']} 을(를) 먼저 정해 주세요 (CP5)")
        self._check_approvable(cp, {})
        name, covers, lacks = alt["name"], alt.get("covers", ""), alt.get("lacks", "")
        others = [a["name"] for a in self._ws.items("alternatives") if a["id"] != alternative_id]
        self._ctx.bus.send("client", "coordinator", f"{josa(name, '을/를')} 쓰고 모자란 부분만 만들게요")
        self._ws.write("coordinator", "decisions", {
            "id": self._ws.next_id("decisions", "DEC"), "kind": "build_or_buy", "topic": "만들기 전에: 기존 제품으로 충분한가",
            "chosen": f"{name} + 모자란 부분만", "answer_kind": "build_or_buy",
            "rejected": ["새로 만들기", *others, "제품만 쓰고 끝내기"], "status": "확정", "answered_by": "client",
            "who": who, "alternative_ref": alternative_id, "evidence_refs": alt.get("evidence_refs", []),
            "instruction": gap_instruction(name, covers, lacks),
        })
        scope = dict((self._ws.items("scope") or [{"id": "SCOPE-01", "in": [], "out": []}])[0])
        decided = {"text": f"{name}이(가) 이미 해 주는 것: {covers}", "refs": [], "quote": "", "status": "확인",
                   "decided_by": "client", "alternative_ref": alternative_id}
        self._ws.write("fde_lead", "scope", {**scope, "out": [*scope.get("out", []), decided]})
        self.confirm(cp, True, who)

    def _check_approvable(self, cp: str, waivers: Mapping[str, str]) -> None:
        """Answer consistency blocks; FR-10 coverage needs a reason per warning (G2 record of refusal).
        At CP2 an unsent 고칠 점 also blocks: the client asked for a change, so it cannot be fixed as is."""
        problems = approval_problems(self._ws.source, cp, waivers)
        if "requirement_review" in self._flow.stage(cp).features and review_summary(self._ws.source)["fix"]:
            problems = [*problems, "고칠 점을 적은 요구사항이 있어요. 먼저 보내서 고친 뒤 확정해 주세요"]
        if problems:
            self._ws.guardrail("G2", "blocked", f"{cp} 승인 불가", problems=problems)
            raise PipelineStateError(f"{josa(cp, '을/를')} 승인할 수 없습니다: " + " / ".join(problems))

    def narrow_scope(self, keep: Sequence[str], who: str, keep_all: bool = False) -> None:
        """G8 answer: the client keeps at most `max_screens` screens; S5 then continues without redrawing.
        `keep_all` (11-22, 「모두 만들기」): every drawn screen stays, past the limit — `keep` must name them all."""
        self._expect(self._role(self._flow.running("documents")), "awaiting_scope")
        screens = {s["id"]: s for s in self._ws.items("screens")}
        limit = self._ctx.runner.limits.max_screens
        chosen = [s for s in dict.fromkeys(keep)]
        if keep_all and set(chosen) != set(screens):
            raise PipelineStateError("「모두 만들기」는 그린 화면을 모두 남겨요. 화면 목록을 다시 불러와 주세요")
        if not keep_all and (not chosen or len(chosen) > limit or any(k not in screens for k in chosen)):
            raise PipelineStateError(f"남길 화면을 1개 이상 {limit}개 이하로, 목록에 있는 화면에서 골라 주세요")
        titles = [screens[k]["title"] for k in screens if k in chosen]
        kept_refs = {r for k in chosen for r in screens[k].get("requirement_refs", [])}
        dropped = sorted({r for k, s in screens.items() if k not in chosen for r in s.get("requirement_refs", [])}
                         - kept_refs)  # 11-22: their 빈칸 at CP3 gets the scope reason
        said = f"화면 {len(chosen)}개 모두 만들기" if keep_all else f"먼저 만들 화면: {' · '.join(titles)}"
        self._ctx.bus.send("client", "coordinator", said)
        self._ws.write("coordinator", "decisions", {
            "id": self._ws.next_id("decisions", "DEC"), "kind": "scope", "topic": "화면 범위 줄이기 (G8)",
            "chosen": f"모두 만들기 — {' · '.join(titles)}" if keep_all else " · ".join(titles), "answer_kind": "scope",
            "rejected": [s["title"] for k, s in screens.items() if k not in chosen],
            "status": "확정", "answered_by": "client", "who": who, "screens_kept": [k for k in screens if k in chosen],
            "dropped_requirements": dropped,
        })
        self._ctx.bus.send("coordinator", "designer", f"고른 화면 {len(chosen)}개만 남깁니다")
        keep_screens(self._ctx, chosen)
        self._ws.guardrail("G8", "resolved", f"발주사가 화면 {len(chosen)}개를 남김", actor="coordinator",
                           count=len(chosen), max=limit)
        self._ws.set_pipeline(status="running", resume=RESUME_REST)

    def answer(self, question_id: str, kind: str, value: str | None = None) -> None:
        """Answer a card, or change an earlier answer while the cards are still open (same DEC id kept).
        Nothing moves on by itself: S4 starts only when the client submits the whole set (submit_answers)."""
        self._expect(self._role(self._flow.running("requirements")), "awaiting_answers")
        card = self._ws.get("questions", question_id)
        if card is None or card["status"] not in ("pending", "answered"):
            raise PipelineStateError(f"답할 수 있는 질문 카드가 아닙니다: {question_id}")
        if kind == "free_text" and card.get("allow_free_text") is False:  # e.g. which app (placement): pick one
            raise PipelineStateError("이 질문은 고른 답만 받을 수 있어요. 선택지 중 하나를 골라 주세요")
        if kind == "free_text":
            g3_check(self._ws, [value], "질문 카드 직접 입력")
        answer = self._answer_value(card, kind, (value or "").strip())
        previous = next((d for d in self._ws.items("decisions") if d.get("question_id") == question_id), None)
        verb = "답 변경" if previous else "답"
        self._ctx.bus.send("client", "coordinator", f"{question_id} {verb}: {answer['value']}")
        self._ws.write("coordinator", "questions", {**card, "status": "answered", "answer": answer})
        self._ws.write("coordinator", "decisions", {
            "id": previous["id"] if previous else self._ws.next_id("decisions", "DEC"),
            "question_id": question_id, "topic": card["question"],
            "chosen": answer["value"], "answer_kind": answer["kind"],
            "rejected": [o for o in card["options"] if o != answer["value"]],
            "status": answer["status"], "answered_by": "client",
            **{k: card[k] for k in ("kind", "system_ref") if card.get(k)},  # a code-made card (placement)
        })
        self._ws.emit("question_answered", "client", {"question_id": question_id, **answer,
                                                      "changed": previous is not None})

    def submit_answers(self, defaults: Mapping[str, str] | None = None) -> None:
        """The client checked every answer: S4 fixes the requirements from them. `defaults`: the client's changes
        to the team's default answers (app/team_defaults.py); the rest are kept as the team set them."""
        self._expect(self._role(self._flow.running("requirements")), "awaiting_answers")
        cards = self._ws.items("questions")
        if any(q["status"] == "pending" for q in cards):
            raise PipelineStateError("아직 답하지 않은 질문이 있어요")
        team_defaults.confirm(self._ws, defaults)
        self._ctx.bus.send("client", "coordinator", f"답 {len(cards)}개를 확인했어요. 이대로 진행해 주세요")
        self._ws.emit("answers_submitted", "client", {"count": len(cards)})
        self._ws.set_pipeline(stage=self._role(self._flow.running("finalize")), status="running")

    @staticmethod
    def _answer_value(card: dict, kind: str, value: str) -> dict[str, str]:
        if kind == "choice" and value in card["options"]:
            return {"kind": kind, "value": value, "status": "확정"}
        if kind == "unknown":
            return {"kind": kind, "value": card["default_option"], "status": "가정"}
        if kind == "free_text" and value and len(value) <= 500 and "\n" not in value.strip():
            return {"kind": kind, "value": value, "status": "확정"}
        raise PipelineStateError("선택지 중 하나를 고르거나, '잘 모르겠어요' 또는 직접 입력(한 줄)으로 답해 주세요")

    def _expect(self, stage: str, status: str) -> None:
        pipeline = self._ws.pipeline
        if (pipeline["stage"], pipeline["status"]) != (stage, status):
            raise PipelineStateError(
                f"지금은 {stage} 단계의 {status} 상태가 아닙니다 (현재 {pipeline['stage']} · {pipeline['status']})")
