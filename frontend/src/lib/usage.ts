// Liner usage per API kind and the team's relation counters, read from the event log. Pure, unit-tested.
import type { AppEvent } from "../api";

export type UsageKind = "chat" | "decisions" | "ai_search" | "search" | "rerank" | "visualization" | "transcription" | "images";

export interface UsageRow {
  kind: UsageKind;
  label: string;
  calls: number;
  cost: number | null; // sum of the per-call cost Liner reported; null when no call reported one
  models: string[]; // answering models (router) or the model asked
  // Token sums from each call's `usage` (null when no call of this kind reported that count).
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
}

function addCount(sum: number | null, value: unknown): number | null {
  return typeof value === "number" ? (sum ?? 0) + value : sum;
}

const ORDER: [UsageKind, string][] = [
  ["chat", "모델·라우터 (에이전트 발화)"],
  ["decisions", "Decisions (판정)"],
  ["ai_search", "AI 검색"],
  ["search", "웹 검색"],
  ["rerank", "Rerank (재정렬)"],
  ["visualization", "Visualization (흐름도)"],
  ["transcription", "받아쓰기"],
  ["images", "Images (프로토타입 사진)"],
];

function kindOf(e: AppEvent): UsageKind | null {
  switch (e.type) {
    case "liner_chat":
      return "chat";
    case "liner_decision":
      return "decisions";
    case "liner_search":
      return e.data?.api === "ai_search" ? "ai_search" : "search";
    case "liner_rerank":
      return "rerank";
    case "liner_visualization":
      return "visualization";
    case "liner_transcription":
      return "transcription";
    case "liner_image":
      return "images";
    default:
      return null;
  }
}

export function linerUsage(events: AppEvent[]): UsageRow[] {
  const rows = new Map<UsageKind, UsageRow>();
  for (const e of events) {
    const kind = kindOf(e);
    if (!kind) continue;
    const row = rows.get(kind) ?? { kind, label: ORDER.find(([k]) => k === kind)![1], calls: 0, cost: null, models: [],
      promptTokens: null, completionTokens: null, totalTokens: null };
    const cost = typeof e.data?.cost === "number" ? e.data.cost : null;
    const model = e.data?.answered_model || e.data?.model;
    rows.set(kind, {
      ...row,
      calls: row.calls + 1,
      cost: cost === null ? row.cost : (row.cost ?? 0) + cost,
      models: model && !row.models.includes(String(model)) ? [...row.models, String(model)].sort() : row.models,
      promptTokens: addCount(row.promptTokens, e.data?.prompt_tokens),
      completionTokens: addCount(row.completionTokens, e.data?.completion_tokens),
      totalTokens: addCount(row.totalTokens, e.data?.total_tokens),
    });
  }
  return ORDER.map(([k]) => rows.get(k)).filter((r): r is UsageRow => Boolean(r));
}

// "1,234 (입력 1,200 · 출력 34)", "10", or "—" when no tokens were reported.
export function tokenText(row: UsageRow): string {
  if (row.totalTokens == null) return "—";
  const n = (v: number) => v.toLocaleString("en-US");
  const parts = [
    row.promptTokens != null ? `입력 ${n(row.promptTokens)}` : null,
    row.completionTokens != null ? `출력 ${n(row.completionTokens)}` : null,
  ].filter(Boolean);
  return parts.length ? `${n(row.totalTokens)} (${parts.join(" · ")})` : n(row.totalTokens);
}

export interface RelationCounters {
  rerouted: number; // messages with no relation line, sent through the coordinator instead
  rejected: number; // writes refused by the write-permission table
  pair: { from: string; to: string } | null; // latest direct handoff
}

export function relationCounters(events: AppEvent[]): RelationCounters {
  let rerouted = 0;
  let rejected = 0;
  let pair: RelationCounters["pair"] = null;
  for (const e of events) {
    if (e.type === "message_rerouted") rerouted += 1;
    else if (e.type === "write_rejected") rejected += 1;
    else if (e.type === "agent_message" && e.data?.from && e.data?.to) pair = { from: String(e.data.from), to: String(e.data.to) };
  }
  return { rerouted, rejected, pair };
}
