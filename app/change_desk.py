from __future__ import annotations
"""The change lane next to the stage table: FR-21 change request → impact → CP5, FR-22 「아 이거 아닌데?」.

Opens once a version is fixed (CP2 approved) and the team is idle at CP3 / CP4 or after completion.
One open item at a time. Mapping and classification are agent work (PM / QA via the coordinator);
the impact, the re-check list, the G2 gate and the complaint guard are code.

changes[]    status: mapping → awaiting_cp5 → approved | rejected   (or unmapped | unrelated | no_change | failed)
complaints[] status: checking → classified                           (or unmatched | unrelated | failed)
Small talk, requests for what is already so, repeats and reversals: app/request_hygiene.py.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.korean import josa
from app.agent_runner import AgentOutputError, AgentRunner
from app.bus import MessageBus
from app.checks import normalize_key, requirement_text
from app.config import LinerKeyMissingError
from app.decisions import COMPLAINT_QUESTION, complaint_state, min_confidence, needs_human, read_choice
from app.definitions import TeamDef
from app.errors import ConfirmationRequiredError, PipelineStateError
from app.policy import guard_purpose
from app.request_hygiene import (NO_CHANGE, REPEATED_CHANGE, REPEATED_COMPLAINT, UNRELATED_CHANGE,
                                  UNRELATED_CLASS, UNRELATED_COMPLAINT, UNRELATED_TARGET, change_history,
                                  repeat_of, same_words)
from app.guardrails import G3_PROMPT, sensitive_labels
from app.change_revision import direct_ids
from app.impact import impacted, owners_of
from app.liner import LinerAPIError, LinerConfigError
from app.limits import LimitReachedError, stop_message
from app.schemas import CHANGE_MAPPING, COMPLAINT_CHECK
from app.stage_common import StageContext, g3_check, masked_output, str_list
from app.workspace import SNAPSHOT_KINDS, Workspace

OPEN_STATES = {"changes": ("mapping", "awaiting_cp5"), "complaints": ("checking",)}
BUSY_STATES = {"changes": ("mapping",), "complaints": ("checking",)}
LANE_STAGES = ("CP3", "CP4")
# After a CP5 approval: the first stage built on requirements, and the deliverables that must be redone.
REWORK_STAGE = "S5"
RECHECK_KINDS = ("documents", "screens", "tests", "prototype")
MAX_TEXT = 300
RERANK_TOP = 5  # 제안: candidates handed to the PM
FAILURES = (AgentOutputError, LinerAPIError, LinerConfigError, LinerKeyMissingError)
INTERRUPTED = "서버가 다시 시작되어 처리가 중단되었어요. 같은 말을 다시 보내 주세요"
UNMAPPED = "어느 요구사항을 바꾸는 말씀인지 찾지 못했어요. 무엇을 어떻게 바꾸고 싶은지 조금 더 구체적으로 적어 주세요"
UNMATCHED = "확정된 요구사항 중 어느 것에 대한 말씀인지 찾지 못했어요. 어떤 화면·기능인지 함께 적어 주세요"

TASK_MAP = (
    "발주사의 변경 요청(추가 입력의 '변경 요청')이 공유 원본의 요구사항(requirements) 중 어느 하나를 바꾸는 것인지 "
    "골라 그 ID 를 target 에 적어라. 추가 입력의 '후보(재정렬 점수)' 가 있으면 참고하되 정하는 것은 너다. "
    "그 요구사항의 진술(statement)을 변경 요청대로 고친 한 문장을 after_statement 에, "
    "무엇이 바뀌는지 한 문장을 summary 에, 왜 그 요구사항을 골랐는지 한 문장을 rationale 에 적어라. "
    "원문(sources)은 고치지 않는다. 영향 범위는 시스템이 계산한다. "
    f"변경 요청이 요구사항 어느 것과도 관련이 없으면(인사·잡담·제품과 무관한 부탁) target 을 '{UNRELATED_TARGET}' 로 적고 "
    "나머지는 빈칸으로 둬라. 억지로 가장 비슷한 요구사항을 고르지 않는다."
)
TASK_COMPLAINT = (
    "발주사가 결과물을 보고 불만을 말했다(추가 입력의 '발주사 말'). 추가 입력의 '확정 요구사항'(사람이 컨펌해 고정한 버전)과 "
    "맞춰 보고, 그 말이 어느 요구사항에 대한 것인지 requirement_ids 에 적어라. 발주사가 원하는 것을 짧은 말로 requested 에 "
    "적어라. 원하는 것이 확정된 문장과 같은데 결과물이 다르면 '합의 위반', 확정된 것과 다른 것을 원하면 '새 변경 요청'으로 "
    "classification 을 정하고, 이유를 reason 에 한 문장으로 적어라. "
    f"제품과 관련 없는 말(인사·잡담·다른 부탁)이면 requirement_ids 를 비우고 classification 을 '{UNRELATED_CLASS}' 으로 적어라."
)


class UnmappedChangeError(ValueError):
    """The PM's target is not a requirement in the shared source."""


class UnrelatedChangeError(UnmappedChangeError):
    """The PM says the words are about no confirmed requirement (small talk, an unrelated favour). A kind of
    unmapped, so callers that only know UnmappedChangeError still count it as a miss."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _open(source: Mapping[str, Any], kind: str) -> list[Mapping[str, Any]]:
    return [i for i in source.get(kind, []) if i.get("status") in OPEN_STATES[kind]]


def open_change(source: Mapping[str, Any]) -> Mapping[str, Any] | None:
    found = _open(source, "changes")
    return found[0] if found else None


def lane(source: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the client may send a change / complaint now, and whether the lane is working."""
    pipeline = source.get("meta", {}).get("pipeline", {})
    busy = any(i.get("status") in BUSY_STATES[k] for k in BUSY_STATES for i in source.get(k, []))
    pending = bool(_open(source, "changes") or _open(source, "complaints"))
    idle = pipeline.get("status") == "completed" or (
        pipeline.get("status") == "awaiting_confirmation" and pipeline.get("stage") in LANE_STAGES)
    fixed = bool(source.get("versions"))
    reason = None
    if not fixed:
        reason = "요구사항을 확정(CP2)한 뒤부터 바꿀 수 있어요"
    elif not idle:
        reason = "팀이 일하는 중이에요. 끝나면 말씀해 주세요"
    elif pending:
        reason = "앞의 요청을 먼저 정해 주세요"
    return {"open": reason is None, "busy": busy, "reason": reason}


def rerank_candidates(ctx: StageContext, utterance: str, reqs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Liner Rerank of current REQ texts against the utterance (top 5 + scores). Fail-open: [] and a note."""
    if not reqs:
        return []
    docs = [f"{r['id']} {r.get('title', '')}: {r.get('statement', '')}" for r in reqs]
    try:
        body = ctx.runner.rerank("pm", utterance, docs, min(RERANK_TOP, len(docs)))
    except (LinerAPIError, LinerConfigError, LinerKeyMissingError) as exc:
        ctx.ws.emit("check_result", "coordinator", {"check": "rerank", "outcome": "skipped", "items": [],
                                                    "details": [f"후보 재정렬을 못 해 PM 이 전체에서 고릅니다: {exc}"]})
        return []
    out = []
    for row in body.get("results") or []:
        index = row.get("index") if isinstance(row, Mapping) else None
        if isinstance(index, int) and 0 <= index < len(reqs) and isinstance(row.get("relevance_score"), (int, float)):
            req = reqs[index]
            out.append({"id": req["id"], "title": req.get("title", ""), "score": round(float(row["relevance_score"]), 4)})
    return out[:RERANK_TOP]


def propose_change(ctx: StageContext, utterance: str) -> dict[str, Any]:
    """PM maps the utterance to one REQ; code computes the impact and who must re-check. No source change."""
    ctx.bus.send("coordinator", "pm", f"변경 요청: {utterance} — 어느 요구사항인지 찾아 고친 문장을 주세요")
    reqs = list(ctx.ws.items("requirements"))
    candidates = rerank_candidates(ctx, utterance, reqs)
    extra: dict[str, Any] = {"변경 요청": utterance}
    if candidates:
        extra["후보(재정렬 점수)"] = candidates
    out = masked_output(ctx, "pm", ctx.runner.ask("pm", TASK_MAP, "change_mapping", CHANGE_MAPPING, extra))
    target = str(out.get("target", "")).strip()
    if target.upper() == UNRELATED_TARGET:
        raise UnrelatedChangeError(UNRELATED_CHANGE)
    req = next((r for r in reqs if r["id"] == target), None)
    if req is None:
        ctx.ws.emit("ref_dropped", "pm", {"item": "change", "ref": target, "reason": "공유 원본에 없는 요구사항 ID"})
        raise UnmappedChangeError(UNMAPPED)
    impact = impacted(reqs, target)
    ctx.ws.emit("check_result", "coordinator", {
        "check": "change_impact", "outcome": "computed", "items": [*impact["requirements"], *impact["screens"],
                                                                   *impact["tests"]],
        "details": [f"{josa(target, '와/과')} 그에 기대는 요구사항, 연결된 화면·테스트"]})
    ctx.bus.send("pm", "coordinator", f"{josa(target, '을/를')} 바꾸는 요청입니다 — 영향 {sum(map(len, impact.values()))}건")
    after = str(out.get("after_statement", "")).strip()
    return {"target": target, "title": req.get("title", ""), "before": req.get("statement", ""),
            "after": after, "summary": str(out.get("summary", "")).strip(),
            **change_history(ctx.ws.items("versions"), req, after),
            "rationale": str(out.get("rationale", "")).strip(), "impact": impact, "direct": direct_ids(reqs, target),
            "recheck": owners_of(impact), "candidates": candidates}


class ChangeDesk:
    def __init__(self, workspace: Workspace, team: TeamDef, runner: AgentRunner) -> None:
        self._ws = workspace
        self._ctx = StageContext(workspace, MessageBus(team, workspace), runner)

    # --- opening ---------------------------------------------------------------------------------
    def _check_text(self, text: str) -> str:
        text = (text or "").strip()
        if not text or "\n" in text or len(text) > MAX_TEXT:
            raise PipelineStateError(f"한 줄로, {MAX_TEXT}자 이내로 적어 주세요")
        labels = sensitive_labels([text])
        if labels:
            self._ws.guardrail("G3", "blocked", "변경·불만 입력의 민감 정보 — 저장하지 않음", kinds=labels)
            raise PipelineStateError(G3_PROMPT.format(kinds=", ".join(labels)))
        state = lane(self._ws.source)
        if not state["open"]:
            raise PipelineStateError(state["reason"])
        return text

    def _check_purpose(self, text: str) -> None:
        """G9 on a change request: a harmless product can still be steered into a harmful one later."""
        try:
            verdict = guard_purpose(self._ws, self._ctx.runner, [text], "변경 요청")
        except LimitReachedError as exc:  # G7 at the G9 call: the stop card, not a 500
            raise PipelineStateError(stop_message(exc, "변경 요청", self._ctx.runner.limits.max_calls, lane=True)) from exc
        if verdict.blocked:
            raise PipelineStateError(verdict.message())

    def _version(self) -> str:
        versions = self._ws.items("versions")
        return versions[-1]["version"] if versions else "작업본"

    def open_change(self, utterance: str, complaint_ref: str | None = None) -> dict[str, Any]:
        text = self._check_text(utterance)
        done = repeat_of(self._ws.items("changes"), text, "utterance", ("approved",))
        if done is not None:
            raise PipelineStateError(REPEATED_CHANGE.format(id=done["id"], version=done.get("version") or "반영됨"))
        self._check_purpose(text)
        item = {"id": self._ws.next_id("changes", "CHG"), "utterance": text, "status": "mapping",
                "created_at": _now(), "based_on": self._version(), "complaint_ref": complaint_ref}
        self._ctx.bus.send("client", "coordinator", f"변경 요청 {item['id']}: {text}")
        self._ws.write("coordinator", "changes", item)
        return item

    def open_complaint(self, text: str) -> dict[str, Any]:
        said = self._check_text(text)
        seen = repeat_of(self._ws.items("complaints"), said, "text", ("classified",))
        if seen is not None:
            raise PipelineStateError(REPEATED_COMPLAINT.format(id=seen["id"], label=seen.get("classification", "")))
        item = {"id": self._ws.next_id("complaints", "CMP"), "text": said, "status": "checking",
                "created_at": _now(), "against": self._version()}
        self._ctx.bus.send("client", "coordinator", f"「아 이거 아닌데?」 {item['id']}: {said}")
        self._ws.write("coordinator", "complaints", item)
        return item

    # --- FR-21 -----------------------------------------------------------------------------------
    def map_change(self, change_id: str) -> None:
        item = self._item("changes", change_id, "mapping")
        try:
            proposal = propose_change(self._ctx, item["utterance"])
        except UnrelatedChangeError as exc:
            self._update("changes", item, status="unrelated", error=str(exc))
            self._ctx.bus.send("coordinator", "client", str(exc))
            return
        except UnmappedChangeError as exc:
            self._update("changes", item, status="unmapped", error=str(exc))
            self._ctx.bus.send("coordinator", "client", str(exc))
            return
        except LimitReachedError as exc:
            self._update("changes", item, status="failed", error=stop_message(exc, "변경 요청", self._ctx.runner.limits.max_calls, lane=True), limit=True)
            return
        except FAILURES as exc:
            self._update("changes", item, status="failed", error=str(exc))
            return
        finally:
            self._ws.set_pipeline(active_agent=None)
        if same_words(proposal["after"], proposal["before"]):
            message = NO_CHANGE.format(target=proposal["target"])
            self._update("changes", item, status="no_change", error=message, **proposal)
            self._ctx.bus.send("coordinator", "client", message)
            return
        self._update("changes", item, status="awaiting_cp5", **proposal)
        self._ctx.bus.send("coordinator", "client", f"{change_id} 영향 범위를 확인하고 반영 여부를 정해 주세요 (CP5)")

    def decide(self, change_id: str, approved: bool, who: str, reason: str | None = None) -> None:
        """CP5. Approve → G2 record, PM rewrites the target, new version. Reject → nothing in the source changes."""
        item = self._item("changes", change_id, "awaiting_cp5")
        reason = (reason or "").strip()
        if not approved and (not reason or "\n" in reason):
            raise PipelineStateError("반려할 때는 사유를 한 줄로 적어 주세요")
        g3_check(self._ws, [reason], "CP5 반려 사유")
        version = f"v{len(self._ws.items('versions')) + 1}" if approved else None
        record = self._ws.add_confirmation("CP5", approved, who, reason or None, version, change_id=change_id)
        decided = {"confirmation_id": record["id"], "who": who, "at": record["at"], "reason": reason or None}
        if not approved:
            self._update("changes", item, status="rejected", decided=decided)
            self._ctx.bus.send("coordinator", "pm", f"{change_id} 반려 — 원본은 그대로입니다")
            return
        self._apply(item)
        self._ws.add_version(version, record["id"], SNAPSHOT_KINDS)
        self._update("changes", self._ws.get("changes", change_id), status="approved", version=version, decided=decided)
        for owner in item["recheck"]:
            self._ctx.bus.send("coordinator", owner["agent"],
                               f"{change_id} 반영({version}): 다시 확인할 항목 {', '.join(owner['items'])}")
        self._rework(item, version)
        self._ctx.bus.send("coordinator", "client",
                           f"{josa(change_id, '을/를')} 반영해 {josa(version, '으로/로')} 고정했어요. 어긋나는 요구사항부터 고쳐 문서를 다시 만들고, 확인 3·4를 다시 받을게요")

    def _rework(self, item: Mapping[str, Any], version: str) -> None:
        """The delivered work was built on the old version: mark it stale and redo it from S5, which first lets
        the PM revise the affected requirements (app/change_revision.py). CP3 and CP4 are asked again."""
        impact = item.get("impact", {})
        self._ws.set_recheck({
            "change_id": item["id"], "version": version, "stage": REWORK_STAGE, "kinds": list(RECHECK_KINDS),
            "items": [*impact.get("requirements", []), *impact.get("screens", []), *impact.get("tests", [])]})
        self._ws.set_pipeline(stage=REWORK_STAGE, status="running", active_agent=None, error=None,
                              feedback=None, resume=None)

    def _apply(self, item: Mapping[str, Any]) -> None:
        """G2: the requirement changes only with an approved CP5 record for this change."""
        records = [c for c in self._ws.items("confirmations") if c["cp"] == "CP5" and c.get("change_id") == item["id"]]
        if not records or records[-1]["approved"] is not True:
            detail = f"CP5 승인 기록 없이 {josa(item['id'], '을/를')} 반영할 수 없습니다"
            self._ws.guardrail("G2", "blocked", detail)
            raise ConfirmationRequiredError(detail)
        req = self._ws.get("requirements", item["target"])
        self._ws.write("pm", "requirements", {**req, "statement": item["after"],
                                              "change_refs": [*req.get("change_refs", []), item["id"]]})
        for dec_id in req.get("decision_refs", []):
            dec = self._ws.get("decisions", dec_id)
            if dec is not None and not dec.get("superseded_by"):
                self._ws.write("coordinator", "decisions", {**dec, "superseded_by": item["id"]})

    # --- FR-22 -----------------------------------------------------------------------------------
    def check_complaint(self, complaint_id: str) -> None:
        item = self._item("complaints", complaint_id, "checking")
        label, reqs, confirmation = self._confirmed()
        self._ctx.bus.send("coordinator", "qa", f"발주사 불만 {complaint_id}: {item['text']} — 확정 {josa(label, '와/과')} 맞춰 봐 주세요")
        try:
            out = masked_output(self._ctx, "qa", self._ctx.runner.ask(
                "qa", TASK_COMPLAINT, "complaint_check", COMPLAINT_CHECK,
                {"발주사 말": item["text"], "확정 버전": label,
                 "확정 요구사항": [{k: r.get(k) for k in ("id", "title", "statement", "acceptance")} for r in reqs]}))
        except LimitReachedError as exc:
            self._update("complaints", item, status="failed", error=stop_message(exc, "불만 대조", self._ctx.runner.limits.max_calls, lane=True), limit=True)
            return
        except FAILURES as exc:
            self._update("complaints", item, status="failed", error=str(exc))
            return
        finally:
            self._ws.set_pipeline(active_agent=None)
        if out.get("classification") == UNRELATED_CLASS:
            self._update("complaints", item, status="unrelated", error=UNRELATED_COMPLAINT)
            return
        by_id = {r["id"]: r for r in reqs}
        ids = [i for i in dict.fromkeys(str_list(out.get("requirement_ids"))) if i in by_id]
        if not ids:
            self._update("complaints", item, status="unmatched", error=UNMATCHED)
            return
        model = out.get("classification") if out.get("classification") in ("합의 위반", "새 변경 요청") else "새 변경 요청"
        requested = str(out.get("requested", "")).strip()
        guard = complaint_guard(requested, [by_id[i] for i in ids])
        try:
            decision = self._decide_complaint([by_id[i] for i in ids], confirmation, item["text"])
        finally:
            self._ws.set_pipeline(active_agent=None)
        voted = decision.get("label") or model
        final = "합의 위반" if guard["applied"] else voted
        human = needs_human(decision, decision["threshold"]) and not guard["applied"]
        if guard["applied"] and voted != final:
            self._ws.emit("check_result", "coordinator", {"check": "complaint_guard", "outcome": "flagged",
                                                          "items": ids, "details": [guard["detail"]]})
        evidence = [{"requirement": {k: by_id[i].get(k) for k in ("id", "title", "statement", "acceptance", "status")},
                     "confirmation": confirmation} for i in ids]
        self._update("complaints", item, status="classified", classification=final, model_classification=model,
                     requirement_ids=ids, requested=requested, reason=str(out.get("reason", "")).strip(),
                     evidence=evidence, guard=guard, decision=decision, needs_human=human)
        self._ctx.bus.send("qa", "coordinator", f"{complaint_id}: {final} ({', '.join(ids)})")
        self._ctx.bus.send("coordinator", "client", f"{josa(complaint_id, '은/는')} {josa(final, '으로/로')} 보여요 — 근거를 확인해 주세요")

    def _decide_complaint(self, reqs: Sequence[Mapping[str, Any]], confirmation: Mapping[str, Any] | None,
                          text: str) -> dict[str, Any]:
        """Decisions `choice` violation/new_change. Fail-open: the error is kept and a person must judge."""
        threshold = min_confidence(self._ctx.runner.client.env_file)
        try:
            body = self._ctx.runner.decide("qa", "complaint", complaint_state(reqs, confirmation, text),
                                           {"kind": COMPLAINT_QUESTION})
            answers = body.get("answers") if isinstance(body.get("answers"), Mapping) else {}
            return {**read_choice(answers.get("kind")), "model": body.get("model"), "threshold": threshold,
                    "error": None}
        except LimitReachedError as exc:
            return {"choice": None, "label": None, "probabilities": {}, "confidence": None, "threshold": threshold,
                    "error": stop_message(exc, "불만 대조", self._ctx.runner.limits.max_calls, lane=True)}
        except (LinerAPIError, LinerConfigError, LinerKeyMissingError, ValueError) as exc:
            return {"choice": None, "label": None, "probabilities": {}, "confidence": None, "threshold": threshold,
                    "error": f"판정 확률을 받지 못했어요: {exc}"}

    def _confirmed(self) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        """Latest fixed version: its label, its requirement snapshot (or current ones) and who confirmed it."""
        versions = self._ws.items("versions")
        if not versions:
            return "작업본", list(self._ws.items("requirements")), None
        latest = versions[-1]
        reqs = latest.get("snapshot", {}).get("requirements") or list(self._ws.items("requirements"))
        cf = next((c for c in self._ws.items("confirmations") if c["id"] == latest["confirmation_id"]), None)
        confirmation = {k: cf.get(k) for k in ("id", "cp", "who", "at", "version")} if cf else None
        return latest["version"], list(reqs), confirmation

    # --- shared ----------------------------------------------------------------------------------
    def _item(self, kind: str, item_id: str, status: str) -> dict[str, Any]:
        item = self._ws.get(kind, item_id)
        if item is None or item.get("status") != status:
            raise PipelineStateError(f"지금 처리할 수 있는 항목이 아닙니다: {item_id}")
        return item

    def _update(self, kind: str, item: Mapping[str, Any], **changes: Any) -> None:
        self._ws.write("coordinator", kind, {**item, **changes})

    def mark_interrupted(self, error: str = INTERRUPTED) -> list[str]:
        """Startup: a lane item left working by a restart becomes failed (like a stage)."""
        done = []
        for kind, states in BUSY_STATES.items():
            for item in self._ws.items(kind):
                if item.get("status") in states:
                    self._update(kind, item, status="failed", error=error)
                    done.append(item["id"])
        return done


def complaint_guard(requested: str, reqs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """FR-22 deterministic guard: asking for exactly what was confirmed cannot be a new change request."""
    key = normalize_key(requested)
    hit = next((r for r in reqs if key and key in normalize_key(requirement_text(r))), None)
    if hit is None:
        return {"applied": False, "detail": None}
    return {"applied": True, "requirement_id": hit["id"],
            "detail": f"원하신 「{requested}」은 확정된 {hit['id']} 문장에 이미 있어요 — 새 변경 요청이 아니라 합의 위반입니다"}


