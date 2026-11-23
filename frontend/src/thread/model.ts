// The work thread: the event log rewritten as a short conversation for the AI-studio layout.
// Pure functions (no React, no fetch) so they can be unit-tested.
import type { AppEvent, Pipeline, SharedSourceData } from "../api";
import { progressOf, SCHEMA_ACTION, STEPS, stageAction, withObject, withSubject, type View } from "../lib/labels";
import { HIDDEN_EVENTS, summarizeEvent, type Label, type Tone } from "../lib/summarize";

export interface StepEntry {
  seq: number;
  actor: string;
  text: string;
  tone: Tone;
}

export interface StepItem {
  kind: "step";
  key: string;
  stage: string;
  title: string;
  state: "done" | "active" | "paused";
  agents: string[];
  highlight: string | null;
  facts: string[];
  entries: StepEntry[];
}

export interface ConfirmItem {
  kind: "confirm";
  key: string;
  cp: string;
  approved: boolean;
  text: string;
}

export interface AnswerItem {
  kind: "answer";
  key: string;
  question: string;
  answer: string;
  assumed: boolean;
  changed?: boolean; // a later answer to a card already answered (before 「이대로 진행」)
}

export type ThreadItem = StepItem | ConfirmItem | AnswerItem;

// Team stages shown as step groups (S1 is the client's own request, shown as the request bubble).
const STEP_TITLE: Record<string, { done: string; active: string }> = {
  S2: { done: "팀이 문제와 범위를 정리했어요", active: "팀이 문제와 범위를 정리하고 있어요" },
  S3: { done: "팀이 확인할 질문을 준비했어요", active: "팀이 확인할 질문을 준비하고 있어요" },
  S4: { done: "답을 반영해 요구사항을 다듬었어요", active: "답을 반영해 요구사항을 다듬고 있어요" },
  S5: { done: "팀이 문서 4종을 썼어요", active: "팀이 문서 4종을 쓰고 있어요" },
  S6: { done: "팀이 프로토타입을 만들었어요", active: "팀이 프로토타입을 만들고 있어요" },
};

const CP_SUBJECT: Record<string, string> = { CP1: "문제와 범위", CP2: "요구사항", CP3: "문서 4종", CP4: "프로토타입" };

// Bookkeeping the client does not need to read; the team view keeps it.
const CLIENT_SKIP = new Set(["stage_started", "stage_completed", "version_created", "ref_dropped", "run_retried"]);

// Things a step produced, counted from the items it wrote: [kind, unit-label].
const FACTS: [string, (n: number) => string][] = [
  ["findings", (n) => `짚은 점 ${n}건`],
  ["questions", (n) => `질문 ${n}장`],
  ["requirements", (n) => `요구사항 ${n}건`],
  ["screens", (n) => `화면 ${n}개`],
  ["tests", (n) => `테스트 ${n}건`],
];

const NON_AGENTS = new Set(["system", "client"]);

export function buildThread(
  events: AppEvent[],
  questions: { id: string; question: string }[],
  label: Label,
  view: View,
  pipeline: Pipeline | undefined,
): ThreadItem[] {
  const items: ThreadItem[] = [];
  const written = new Map<string, Map<string, Set<string>>>(); // step key -> kind -> item ids (rewrites count once)
  const searchers = new Map<string, string>(); // step key -> who searched with Liner

  for (const e of events) {
    if (e.type === "confirmation") {
      const d = e.data;
      const subject = withObject(CP_SUBJECT[d.cp] ?? String(d.cp));
      items.push({
        kind: "confirm",
        key: `cf-${e.seq}`,
        cp: String(d.cp),
        approved: Boolean(d.approved),
        text: d.approved ? `${subject} 승인했어요` : `${subject} 반려했어요${d.reason ? ` — ${d.reason}` : ""}`,
      });
      continue;
    }
    if (e.type === "question_answered") {
      const q = questions.find((x) => x.id === e.data.question_id);
      items.push({
        kind: "answer",
        key: `ans-${e.seq}`,
        question: q?.question ?? String(e.data.question_id ?? ""),
        answer: e.data.value ? String(e.data.value) : "잘 모르겠어요",
        assumed: e.data.status === "가정",
        changed: e.data.changed === true,
      });
      continue;
    }
    const stage = e.stage ?? "";
    if (!STEP_TITLE[stage]) continue;

    let step = items[items.length - 1];
    if (!step || step.kind !== "step" || step.stage !== stage) {
      step = {
        kind: "step", key: `step-${e.seq}`, stage, title: "", state: "paused",
        agents: [], highlight: null, facts: [], entries: [],
      };
      items.push(step);
    }
    if (e.type === "stage_completed") step.state = "done";
    if (!NON_AGENTS.has(e.actor) && !step.agents.includes(e.actor)) step.agents.push(e.actor);
    if (e.type === "item_written") {
      const kinds = written.get(step.key) ?? new Map<string, Set<string>>();
      const kind = String(e.data.kind);
      const ids = kinds.get(kind) ?? new Set<string>();
      ids.add(String(e.data.item?.id ?? e.seq));
      kinds.set(kind, ids);
      written.set(step.key, kinds);
    }
    if (e.type === "liner_search" && !e.data.error) searchers.set(step.key, e.actor);
    if (HIDDEN_EVENTS.has(e.type) || (view === "client" && CLIENT_SKIP.has(e.type))) continue;
    const s = summarizeEvent(e, label, view);
    step.entries.push({ seq: e.seq, actor: e.actor, text: s.text, tone: s.tone });
  }

  const steps = items.filter((i): i is StepItem => i.kind === "step");
  steps.forEach((step, i) => {
    const latest = i === steps.length - 1;
    if (step.state !== "done") {
      step.state = latest && pipeline?.status === "running" && pipeline.stage === step.stage ? "active" : "paused";
    }
    const titles = STEP_TITLE[step.stage];
    const stopped = latest && step.state === "paused" && pipeline?.status === "failed" && pipeline.stage === step.stage;
    step.title = step.state === "active" ? titles.active : stopped ? titles.active.replace(/고 있어요$/, "다가 멈췄어요") : titles.done;
    const kinds = written.get(step.key) ?? new Map<string, Set<string>>();
    const count = (kind: string) => kinds.get(kind)?.size ?? 0;
    const searcher = searchers.get(step.key);
    if (searcher) {
      step.highlight = `${withSubject(label(searcher))} Liner로 근거를 찾았어요 · ${count("evidence")}건`;
    }
    step.facts = FACTS.filter(([kind]) => count(kind) > 0).map(([kind, text]) => text(count(kind)));
  });
  return items;
}

// "지금 리서처가 Liner로 근거를 검색 중" in Toss tone: "리서처가 Liner로 근거를 검색하고 있어요".
export function activityLine(pipeline: Pipeline | undefined, events: AppEvent[], label: Label): {
  agent: string | null;
  text: string;
} {
  const agent = pipeline?.active_agent ?? null;
  const stage = pipeline?.stage ?? "S1";
  if (!agent) return { agent: null, text: "팀이 다음 할 일을 준비하고 있어요" };
  const action = stageAction(stage, agent) ?? lastSchemaAction(events, agent) ?? "일을 처리";
  const polite = action.endsWith("줌") ? `${action.slice(0, -1)}주고 있어요` : `${action}하고 있어요`;
  return { agent, text: `${withSubject(label(agent))} ${polite}` };
}

function lastSchemaAction(events: AppEvent[], agent: string): string | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type === "liner_chat" && e.actor === agent) return SCHEMA_ACTION[e.data.schema] ?? null;
  }
  return null;
}

export interface CompactProgress {
  step: number; // 1-based
  total: number;
  label: string;
  remaining: number; // confirmations still ahead, including the current one
  done: boolean;
}

// The change lane on top of the nine steps: a CP5 waiting, or the re-confirmations an approved change needs.
export interface LaneProgress {
  pendingChange?: boolean;
  recheck?: boolean;
}

export function compactProgress(stage: string | undefined, status: string | undefined, lane: LaneProgress = {}): CompactProgress {
  const p = progressOf(stage, status);
  const done = p.current >= STEPS.length;
  const index = Math.min(p.current, STEPS.length - 1);
  if (lane.pendingChange) {
    return { step: index + 1, total: STEPS.length, label: "변경 체크포인트(CP5)", remaining: p.remainingConfirmations + 1, done: false };
  }
  // After an approved change the run goes back through S5 → CP3 → S6 → CP4; progressOf already counts those.
  return { step: index + 1, total: STEPS.length, label: STEPS[index].label, remaining: p.remainingConfirmations, done: done && !lane.recheck };
}

// The header's progress for a source: the nine steps plus a waiting CP5 or a rework after one.
export function sourceProgress(source: SharedSourceData): CompactProgress {
  const pipeline = source.meta?.pipeline;
  const changes = (source.changes as { status: string }[] | undefined) ?? [];
  const pendingChange = changes.some((c) => c.status === "mapping" || c.status === "awaiting_cp5");
  return compactProgress(pipeline?.stage, pipeline?.status, { pendingChange, recheck: Boolean(source.meta?.recheck) });
}

// Which card this is: `remaining` counts the current card too.
export function questionPosition(totalCards: number, remaining: number): { index: number; total: number } {
  const total = Math.max(totalCards, remaining);
  return { index: total - remaining + 1, total };
}
