import { Check, ClipboardPaste, CornerDownRight, Orbit } from "lucide-react";
import { GOTO_MESSAGE } from "../panel/notice";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { api, type DocId, type DocView, type Project, type QuestionCard as QuestionCardData, type Todo } from "../api";
import LineageMap from "../graph";
import type { View } from "../lib/labels";
import type { OpeningMemo } from "../lib/opening";
import { formatDuration, MEASURED_ON, MEDIAN_CALL_S, stageTiming } from "../lib/timing";
import type { PanelTarget } from "../panel/types";
import type { TeamInfo } from "../ui/useTeam";
import ConfirmCard from "./confirm/ConfirmCard";
import DecisionStatusCard from "./DecisionStatusCard";
import { ClosedCard, DownloadCard, FailedCard } from "./EndCards";
import { LimitCard, ScopeCard } from "./GuardCards";
import ChangeCard from "./lane/ChangeCard";
import ComplaintCard from "./lane/ComplaintCard";
import LaneComposer from "./lane/LaneComposer";
import RecheckNotice from "./lane/RecheckNotice";
import { convertible, laneEntries, laneSignature, pendingChange } from "./lane/model";
import { activityLine, buildThread, type AnswerItem, type ConfirmItem } from "./model";
import AnswersReview from "./AnswersReview";
import QuestionCard from "./QuestionCard";
import MemoMessenger from "./MemoMessenger";
import RequestBubble from "./RequestBubble";
import RequestComposer from "./RequestComposer";
import StepGroup from "./StepGroup";
import TeamGraph from "./TeamGraph";
import WorkingRow from "./WorkingRow";

// A confirmation todo is only real at a CP stage (replay can pass through a transient S-stage state).
function visibleTodo(todo: Todo | undefined): Todo {
  if (!todo) return { kind: "none" };
  if (todo.kind === "confirmation" && !todo.cp.startsWith("CP")) return { kind: "none", status: "running" };
  return todo;
}

// The conversation-style work thread: request → team steps → the client's one current action
// (question, confirmation, download, or the failure card). `onChanged` is absent in demo replay:
// everything is shown as recorded, read-only.
export default function ThreadView({ project, view, team, docs, downloadUrl, onChanged, onOpen, onAgent, opening }: {
  project: Project;
  view: View;
  team: TeamInfo;
  docs: Record<DocId, DocView> | null;
  downloadUrl: string | null;
  onChanged?: () => void;
  onOpen: (t: PanelTarget) => void;
  onAgent?: (agent: string) => void;
  opening?: OpeningMemo | null; // demo: the recorded memo shown as the opening scene, before the team starts
}) {
  const source = project.source;
  const pipeline = source.meta?.pipeline;
  const protos = (source.prototype as { platform?: string }[] | undefined) ?? [];
  const specs = (source.screen_spec as { swimlane?: unknown }[] | undefined) ?? [];
  const finalProto = protos[protos.length - 1];
  const finalSpec = specs[specs.length - 1];
  const questions = (source.questions as QuestionCardData[] | undefined) ?? [];
  const items = useMemo(
    () => buildThread(source.events, questions, team.label, view, pipeline),
    [source.events, questions, team.label, view, pipeline],
  );
  const todo = visibleTodo(project.todo);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const action = useRef<HTMLDivElement>(null);
  const live = Boolean(onChanged);

  const entries = useMemo(() => laneEntries(source), [source]);
  const laneSig = laneSignature(entries);
  const laneEnd = useRef<HTMLLIElement>(null);
  const lastLane = useRef(laneSig);
  const pending = pendingChange(entries);
  const fixed = ((source.versions as unknown[] | undefined) ?? []).length > 0;

  const actionKey = `${todo.kind}:${todo.kind === "question" ? todo.question.id : todo.kind === "confirmation" ? todo.cp : ""}:${items.length}:${laneSig}`;
  useEffect(() => {
    // A new task card scrolls to its top (just under the sticky bar); otherwise follow the latest step.
    // A change in the change lane (new request, CP5 card, result) scrolls to that entry instead.
    const laneMoved = lastLane.current !== laneSig && entries.length > 0;
    lastLane.current = laneSig;
    const target: HTMLElement | null = laneMoved ? laneEnd.current : action.current ?? end.current;
    const smooth = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    target?.scrollIntoView({ block: laneMoved || action.current ? "start" : "end", behavior: smooth ? "smooth" : "auto" });
  }, [actionKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // The artifact pop-out window asks to bring the waiting card (or a change request) into view.
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin || e.data?.type !== GOTO_MESSAGE || typeof e.data.target !== "string") return;
      const target: string = e.data.target;
      const el = target.startsWith("change:") ? document.getElementById(`lane-${target.slice(7)}`) : action.current ?? end.current;
      el?.scrollIntoView({ block: "start", behavior: "smooth" });
      el?.animate?.([{ boxShadow: "0 0 0 3px rgb(101 83 245 / 0.6)" }, { boxShadow: "0 0 0 0 transparent" }], { duration: 1600 });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  const act = async (run: () => Promise<unknown>) => {
    setError(null);
    try {
      await run();
      onChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // Going back over the cards: which answered card is open again (cleared once its new answer is in).
  const [editing, setEditing] = useState<string | null>(null);
  const answering = todo.kind === "question" || todo.kind === "answers_review";
  const editCard = answering && editing ? questions.find((q) => q.id === editing) : undefined;
  const cardTodo = (q: QuestionCardData): Extract<Todo, { kind: "question" }> => ({
    kind: "question", question: q, remaining: 0,
    sources: source.sources.filter((s) => q.source_refs.includes(s.id)),
    evidence: source.evidence.filter((e) => q.evidence_refs.includes(e.id)),
  });
  const previous = todo.kind === "question" ? questions[questions.findIndex((q) => q.id === todo.question.id) - 1] : undefined;

  const status = pipeline?.status;
  const working = todo.kind === "none" && status !== "failed" && status !== "completed" && status !== "closed" && (status === "running" || !live);
  const failed = todo.kind === "none" && status === "failed";
  const activity = activityLine(pipeline, source.events, team.label);
  const now = useNow(live && status === "running");
  const timing = live && status === "running" && pipeline ? stageTiming(source.events, pipeline.stage, now) : null;
  const hasGraph = source.sources.length > 0;

  return (
    <div className="mx-auto flex w-full max-w-[64rem] flex-col gap-6 px-6 pt-10 pb-24">
      {opening ? (
        <MemoMessenger memo={opening} />
      ) : todo.kind === "input" ? (
        live ? (
          <RequestComposer projectId={project.id} companyId={project.company_id} onSent={() => onChanged?.()} />
        ) : (
          <Card className="animate-rise flex items-center gap-4 px-7 py-6">
            <ClipboardPaste className="size-6 shrink-0 text-primary-text" aria-hidden="true" />
            <p className="text-lg font-semibold break-keep text-foreground">발주사가 메신저로 받은 요구 메모를 그대로 붙여 넣는 장면이에요</p>
          </Card>
        )
      ) : (
        <RequestBubble sources={source.sources} />
      )}

      {view === "team" && team.team && source.events.length > 0 && (
        <TeamGraph team={team.team} events={source.events} label={team.label} onOpen={() => onOpen({ tab: "team" })} />
      )}

      {items.length > 0 && (
        <ol className="-mx-3 flex flex-col gap-1" aria-label="팀이 한 일">
          {items.map((item) => (
            <li key={item.key}>
              {item.kind === "step" && (
                <StepGroup
                  key={view}
                  step={item}
                  label={team.label}
                  defaultOpen={view === "team"}
                  live={working && item.state === "active" ? activity.text : null}
                  timing={item.state === "active" && timing ? timingText(timing) : null}
                />
              )}
              {item.kind === "confirm" && <ConfirmRow item={item} />}
              {item.kind === "answer" && <AnswerRow item={item} />}
            </li>
          ))}
        </ol>
      )}

      {working && todo.kind === "none" && !items.some((i) => i.kind === "step" && i.state === "active") && (
        <WorkingRow agent={activity.agent} text={activity.text} />
      )}
      {working && hasGraph && (
        <section className="glass -mt-1 flex animate-rise flex-col overflow-hidden rounded-3xl" aria-label="추적 지도 — 팀이 쓰는 내용이 이어지는 모습">
          <div className="flex items-center gap-2 px-5 pt-4">
            <Orbit className="size-4 text-cyan" aria-hidden="true" />
            <p className="text-sm font-semibold text-foreground">추적 지도</p>
            <p className="truncate text-sm text-muted-foreground">원문에서 오른쪽으로 팀이 쓰는 내용이 이어지고 있어요</p>
            <Button variant="ghost" size="sm" className="ml-auto" onClick={() => onOpen({ tab: "graph" })}>
              크게 보기
            </Button>
          </div>
          <LineageMap
            className="px-3 pt-2 pb-3"
            source={source}
            events={source.events}
            label={team.label}
            view={view}
            variant="hero"
            onAgent={onAgent}
          />
        </section>
      )}
      {working && live && (
        <p className="-mt-2 animate-rise text-sm text-muted-foreground">끝나면 바로 여기서 여쭤볼게요. 화면은 그대로 두셔도 돼요.</p>
      )}

      {project.todo?.recheck && <RecheckNotice recheck={project.todo.recheck} pipeline={pipeline} />}

      {editCard && (
        <div ref={action} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
          <QuestionCard
            key={`edit-${editCard.id}`}
            todo={cardTodo(editCard)}
            totalCards={questions.length}
            editing={{ index: questions.indexOf(editCard) + 1, current: editCard.answer }}
            onCancel={() => setEditing(null)}
            onAnswer={live ? (a) => act(async () => {
              await api.answer(project.id, editCard.id, a.kind, a.value);
              setEditing(null);
            }) : undefined}
          />
        </div>
      )}
      {!editCard && todo.kind === "question" && (
        <div ref={action} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
          <QuestionCard
            key={todo.question.id}
            todo={todo}
            totalCards={questions.length}
            onAnswer={live ? (a) => act(() => api.answer(project.id, todo.question.id, a.kind, a.value)) : undefined}
            onBack={live && previous?.status === "answered" ? () => setEditing(previous.id) : undefined}
          />
        </div>
      )}
      {!editCard && todo.kind === "answers_review" && (
        <div ref={action} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
          <AnswersReview
            questions={todo.questions}
            defaults={todo.defaults ?? []}
            onEdit={live ? setEditing : undefined}
            onSubmit={live ? (changes) => act(() => api.submitAnswers(project.id, changes)) : undefined}
          />
        </div>
      )}
      {todo.kind === "confirmation" && todo.decision_status && <DecisionStatusCard status={todo.decision_status} />}
      {todo.kind === "confirmation" && (
        <div ref={action} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
          <ConfirmCard
            key={`${todo.cp}-${source.events.filter((e) => e.type === "confirmation").length}`}
            todo={todo}
            source={source}
            docs={docs}
            onOpen={onOpen}
            lock={pending ? "위의 변경 요청(확인 5)을 먼저 정해 주세요" : null}
            onDecide={
              live
                ? (approved, reason, waivers) => act(() => api.confirm(project.id, todo.cp, approved, reason, waivers))
                : undefined
            }
            onUseExisting={live && !pending ? (alt) => act(() => api.useExisting(project.id, alt)) : undefined}
            onBuildGap={live && !pending ? (alt) => act(() => api.buildGap(project.id, alt)) : undefined}
            onReview={live ? (req, verdict, note) => act(() => api.reviewRequirement(project.id, req, verdict, note)) : undefined}
            onSendFixes={live ? () => act(() => api.sendRequirementFixes(project.id)) : undefined}
            onConfirmRest={live ? () => act(() => api.confirmRemainingRequirements(project.id)) : undefined}
          />
        </div>
      )}
      {todo.kind === "download" && (
        <div ref={action} className={cn("flex flex-col gap-5", live ? "scroll-mt-20" : "scroll-mt-28")}>
          {todo.decision_status && <DecisionStatusCard status={todo.decision_status} />}
          <DownloadCard
            downloadUrl={downloadUrl}
            demo={!live}
            onOpen={onOpen}
            platform={finalProto?.platform}
            hasLanes={Boolean(finalSpec?.swimlane)}
          />
        </div>
      )}
      {todo.kind === "closed" && (
        <div ref={action} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
          <ClosedCard todo={todo} />
        </div>
      )}
      {todo.kind === "scope" && (
        <div ref={action} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
          <ScopeCard todo={todo} onKeep={live ? (keep, keepAll) => act(() => api.narrowScope(project.id, keep, keepAll)) : undefined} />
        </div>
      )}
      {todo.kind === "limit" && (
        <div ref={action} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
          <LimitCard todo={todo} onContinue={live ? () => act(() => api.continueLimit(project.id)) : undefined} />
        </div>
      )}
      {failed && (
        <div ref={action} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
          <FailedCard pipeline={pipeline} onRetry={live ? () => act(() => api.retry(project.id)) : undefined} />
        </div>
      )}

      {entries.length > 0 && (
        <ol className="flex flex-col gap-5" aria-label="변경 요청과 바로잡기">
          {entries.map((entry, i) => (
            <li key={entry.item.id} id={`lane-${entry.item.id}`} ref={i === entries.length - 1 ? laneEnd : undefined} className={live ? "scroll-mt-20" : "scroll-mt-28"}>
              {entry.kind === "change" ? (
                <ChangeCard
                  item={entry.item}
                  label={team.label}
                  onOpen={onOpen}
                  onDecide={live ? (approved, reason) => act(() => api.decideChange(project.id, entry.item.id, approved, reason)) : undefined}
                  onContinue={
                    live
                      ? () => act(async () => {
                          await api.continueLimit(project.id);
                          await api.requestChange(project.id, entry.item.utterance, entry.item.complaint_ref ?? undefined);
                        })
                      : undefined
                  }
                />
              ) : (
                <ComplaintCard
                  item={entry.item}
                  label={team.label}
                  convertible={convertible(entry.item, entries)}
                  onConvert={live ? () => act(() => api.requestChange(project.id, entry.item.text, entry.item.id)) : undefined}
                  onContinue={
                    live
                      ? () => act(async () => {
                          await api.continueLimit(project.id);
                          await api.complain(project.id, entry.item.text);
                        })
                      : undefined
                  }
                />
              )}
            </li>
          ))}
        </ol>
      )}
      {live && fixed && project.lane && (
        <LaneComposer
          lane={project.lane}
          onSend={(intent, text) =>
            act(() => (intent === "change" ? api.requestChange(project.id, text) : api.complain(project.id, text)))
          }
        />
      )}

      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      {/* In replay the player dock covers the bottom of the screen; keep the latest step above it. */}
      <div ref={end} aria-hidden="true" className={live ? undefined : "scroll-mb-40"} />
    </div>
  );
}

// Ticks once a second while the team works, so the elapsed time on the active step moves.
function useNow(on: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [on]);
  return now;
}

function timingText(t: NonNullable<ReturnType<typeof stageTiming>>): { text: string; hint: string | null } {
  const text = `${formatDuration(t.elapsedS)}째`;
  if (!t.typical) return { text, hint: null };
  return {
    text: `${text} · 보통 ${formatDuration(t.typical.atLeastS)} 이상(어림)`,
    hint: `어림값: 이 단계의 Liner 호출 ${t.typical.calls}회 × 호출 한 번 중간값 ${MEDIAN_CALL_S}초(${MEASURED_ON} liner-claude-router 실측). 문서·HTML 처럼 긴 답은 더 걸려요`,
  };
}

function ConfirmRow({ item }: { item: ConfirmItem }) {
  return (
    <div className="flex justify-end px-3 py-2">
      <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.05] px-3.5 py-1.5 text-sm font-medium break-keep text-soft">
        <Check className={item.approved ? "size-4 shrink-0 text-cyan" : "size-4 shrink-0 text-warning"} aria-hidden="true" />
        {item.text}
      </span>
    </div>
  );
}

function AnswerRow({ item }: { item: AnswerItem }) {
  return (
    <div className="flex flex-col items-end gap-1 px-3 py-2">
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <CornerDownRight className="size-3" aria-hidden="true" />
        {item.question}
      </p>
      <span className="rounded-3xl rounded-tr-lg border border-white/[0.08] bg-white/[0.07] px-4 py-2 text-base text-foreground">
        {item.answer}
        {item.assumed && <span className="ml-1.5 text-sm text-muted-foreground">· 기본값으로 가정</span>}
        {item.changed && <span className="ml-1.5 text-sm text-muted-foreground">· 답을 바꿨어요</span>}
      </span>
    </div>
  );
}
