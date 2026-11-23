// Who is talking to whom, and how each agent is doing, read from the event log. Pure functions (no React)
// so the team graph's packets, the per-agent scoreboard and the live feed can be unit-tested.
import type { AppEvent } from "../api";
import type { View } from "../lib/labels";
import { briefMessage, summarizeEvent, type Label } from "../lib/summarize";

export interface Exchange {
  seq: number;
  ts: string;
  stage: string;
  from: string;
  to: string;
  text: string;
}

export function exchanges(events: AppEvent[]): Exchange[] {
  return events
    .filter((e) => e.type === "agent_message" && e.data?.from && e.data?.to)
    .map((e) => ({ seq: e.seq, ts: e.ts, stage: e.stage ?? "", from: String(e.data.from), to: String(e.data.to), text: String(e.data.content ?? "") }))
    .sort((a, b) => a.seq - b.seq);
}

// Messages to fly across the graph: on first look (`after` null) the last `cap` replay so the picture moves
// even on a finished project; afterwards only messages newer than `after`, still at most `cap` (a burst
// after a long gap should not queue a minute of animation).
export function packetsSince(all: Exchange[], after: number | null, cap: number): Exchange[] {
  const fresh = after === null ? all : all.filter((x) => x.seq > after);
  return fresh.slice(-cap);
}

export interface AgentScore {
  id: string;
  received: number;
  sent: number;
  holding: boolean; // got a message after its last one out: working on it (or stuck)
  liner: number;
  linerFailed: number;
  avgMs: number | null;
  written: number;
  masked: number; // sensitive values hidden before recording (protection, not a fault)
  flagged: number; // guardrails or checks that flagged its work
  blocked: number;
  rejected: number;
  lastTs: string | null;
}

const LINER = new Set(["liner_chat", "liner_search", "liner_decision", "liner_rerank", "liner_visualization", "liner_image", "liner_transcription"]);

export function agentScores(events: AppEvent[], ids: string[]): AgentScore[] {
  const sorted = [...events].sort((a, b) => a.seq - b.seq);
  return ids.map((id) => {
    let received = 0, sent = 0, lastIn = -1, lastOut = -1, liner = 0, linerFailed = 0, ms = 0, timed = 0;
    let written = 0, masked = 0, flagged = 0, blocked = 0, rejected = 0;
    let lastTs: string | null = null;
    for (const e of sorted) {
      const d = e.data ?? {};
      const mine = e.actor === id;
      if (e.type === "agent_message") {
        if (d.to === id) { received += 1; lastIn = e.seq; lastTs = e.ts; }
        if (d.from === id) { sent += 1; lastOut = e.seq; lastTs = e.ts; }
        continue;
      }
      if (!mine) continue;
      if (LINER.has(e.type)) {
        liner += 1;
        if (d.error) linerFailed += 1;
        if (typeof d.duration_ms === "number") { ms += d.duration_ms; timed += 1; }
      } else if (e.type === "item_written") written += 1;
      else if (e.type === "write_rejected") rejected += 1;
      else if (e.type === "guardrail") {
        if (d.outcome === "masked") masked += 1;
        else if (d.outcome === "flagged") flagged += 1;
        else if (d.outcome === "blocked") blocked += 1;
      } else if (e.type === "check_result" && (d.outcome === "flagged" || d.outcome === "failed")) flagged += 1;
      else continue;
      lastTs = e.ts;
    }
    return {
      id, received, sent, holding: lastIn > lastOut, liner, linerFailed,
      avgMs: timed ? Math.round(ms / timed) : null,
      written, masked, flagged, blocked, rejected, lastTs,
    };
  });
}

export type Tone = "ok" | "warn" | "bad" | "idle" | "info";

// One plain verdict per agent. Faults it caused (failed calls, refused writes) are "bad"; things the
// guardrails or checks caught in its work are "warn" — the system stopped them, a person should look.
export function scoreVerdict(s: AgentScore): { tone: Tone; text: string } {
  if (s.lastTs === null) return { tone: "idle", text: "아직 맡은 일 없음" };
  const bad = [s.linerFailed && `Liner 실패 ${s.linerFailed}`, s.rejected && `쓰기 거부 ${s.rejected}`].filter(Boolean);
  if (bad.length) return { tone: "bad", text: `살펴볼 것: ${bad.join(" · ")}` };
  const warn = [s.flagged && `지적 ${s.flagged}`, s.blocked && `차단 ${s.blocked}`].filter(Boolean);
  if (warn.length) return { tone: "warn", text: `걸린 것: ${warn.join(" · ")}` };
  return { tone: "ok", text: "문제 없음" };
}

export interface FeedEntry {
  seq: number;
  ts: string;
  stage: string;
  kind: "message" | "check" | "guard" | "reroute" | "reject";
  tone: Tone;
  from?: string;
  to?: string;
  actor: string;
  text: string;
}

const GOOD = new Set(["passed", "resolved", "computed", "updated", "resumed"]);
const BAD = new Set(["blocked", "failed"]);

// The conversation as it happens, with the checks and guardrails that fired on it.
export function teamFeed(events: AppEvent[], label: Label, view: View): FeedEntry[] {
  const out: FeedEntry[] = [];
  for (const e of [...events].sort((a, b) => a.seq - b.seq)) {
    const d = e.data ?? {};
    const base = { seq: e.seq, ts: e.ts, stage: e.stage ?? "", actor: e.actor ?? "system" };
    switch (e.type) {
      case "agent_message": {
        const content = String(d.content ?? "");
        out.push({ ...base, kind: "message", tone: "info", from: String(d.from), to: String(d.to), text: view === "team" ? content : briefMessage(content) });
        break;
      }
      case "check_result":
      case "guardrail": {
        const outcome = String(d.outcome ?? "");
        const tone: Tone = GOOD.has(outcome) ? "ok" : BAD.has(outcome) ? "bad" : outcome === "masked" ? "info" : "warn";
        out.push({ ...base, kind: e.type === "check_result" ? "check" : "guard", tone, text: summarizeEvent(e, label, view).text });
        break;
      }
      case "message_rerouted":
        out.push({ ...base, kind: "reroute", tone: "info", from: String(d.from), to: String(d.to), text: summarizeEvent(e, label, view).text });
        break;
      case "write_rejected":
        out.push({ ...base, kind: "reject", tone: "bad", text: summarizeEvent(e, label, view).text });
        break;
    }
  }
  return out;
}

// Relations are undirected for counting: "a|b" with the ids in sorted order.
export function pairKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

export function pairCounts(all: Exchange[]): Map<string, number> {
  const out = new Map<string, number>();
  for (const x of all) out.set(pairKey(x.from, x.to), (out.get(pairKey(x.from, x.to)) ?? 0) + 1);
  return out;
}

// Who sent how many messages to whom: rows are senders, columns receivers (ids outside `ids` are dropped).
export function talkMatrix(all: Exchange[], ids: string[]): { ids: string[]; cells: number[][]; max: number } {
  const cells = ids.map(() => ids.map(() => 0));
  for (const x of all) {
    const r = ids.indexOf(x.from);
    const c = ids.indexOf(x.to);
    if (r >= 0 && c >= 0) cells[r][c] += 1;
  }
  return { ids, cells, max: Math.max(0, ...cells.flat()) };
}

// The edge label: a relation's first phrase ("작업 배정, 결과 취합, …" → "작업 배정").
export function relationName(carries: string): string {
  return carries.split(/[,(]/)[0].trim();
}

export interface LinerCall {
  seq: number;
  ts: string;
  actor: string;
  kind: string;
  ms: number;
  failed: boolean;
}

const CALL_KIND: Record<string, string> = {
  liner_chat: "모델",
  liner_search: "검색",
  liner_decision: "판정",
  liner_rerank: "재정렬",
  liner_visualization: "흐름도",
  liner_image: "이미지",
  liner_transcription: "받아쓰기",
};

// One dot per timed Liner call (calls without a recorded duration are left out of the scatter).
export function linerCalls(events: AppEvent[]): LinerCall[] {
  return events
    .filter((e) => CALL_KIND[e.type] && typeof e.data?.duration_ms === "number")
    .sort((a, b) => a.seq - b.seq)
    .map((e) => ({ seq: e.seq, ts: e.ts, actor: e.actor ?? "system", kind: CALL_KIND[e.type], ms: e.data.duration_ms as number, failed: Boolean(e.data.error) }));
}
