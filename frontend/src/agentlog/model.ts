// One agent's detailed log from the event stream: messages in and out, Liner calls, items written or
// refused, guardrails on its output and its decisions with the reasons the system recorded. Grouped by
// stage, time-ordered. Pure functions (no React) so grouping and wording can be unit-tested.
import type { AppEvent } from "../api";
import { STAGE_TITLE, type View } from "../lib/labels";
import { briefMessage, summarizeEvent, type Label } from "../lib/summarize";
import { changeDecision, complaintDecision, linerEntry, plain, prototypeDecision, writeEntry } from "./describe";

export type LogKind = "message" | "liner" | "write" | "decision" | "guard";

export const LOG_KIND_KO: Record<LogKind, string> = {
  message: "메시지",
  liner: "Liner 호출",
  write: "작성",
  decision: "판정",
  guard: "가드레일",
};

export interface LogEntry {
  seq: number;
  ts: string;
  stage: string;
  kind: LogKind;
  title: string;
  lines: string[];
  itemId?: string; // a lineage node this entry can select
  direction?: "in" | "out";
  raw: AppEvent;
}

export interface LogGroup {
  key: string;
  stage: string;
  title: string;
  entries: LogEntry[];
}

export interface CoordinatorSummary {
  handoffs: { agent: string; sent: number; received: number }[];
  reroutes: number;
  stages: string[];
  pending: { label: string; count: number }[];
}

export interface AgentLog {
  groups: LogGroup[];
  summary: CoordinatorSummary | null;
  total: number;
}

const ITEM_ID = /\b[A-Z]{2,6}-\d+\b/g;

function writtenBy(events: AppEvent[], agent: string): Set<string> {
  const out = new Set<string>();
  for (const e of events) {
    if (e.type === "item_written" && e.actor === agent && typeof e.data?.item?.id === "string") out.add(e.data.item.id);
  }
  return out;
}

// Ids an event talks about (guardrail / check items like "coverage.no_tc:REQ-02").
function mentioned(e: AppEvent): string[] {
  const d = e.data ?? {};
  const raw = [...(Array.isArray(d.items) ? d.items : []), d.item, d.target].filter((v) => typeof v === "string") as string[];
  return raw.flatMap((s) => s.match(ITEM_ID) ?? []);
}

function entriesFor(e: AppEvent, agent: string, mine: Set<string>, label: Label, view: View, titles: Record<string, string>): LogEntry[] {
  const d = e.data ?? {};
  const base = { seq: e.seq, ts: e.ts, stage: e.stage ?? "", raw: e };
  const p = (text: string) => plain(text, view, titles);
  // Task instructions are long and full of schema words: one plain line for the client, in full for the team.
  const said = (text: string) => (view === "team" ? text : p(briefMessage(text)));
  const touchesMine = mentioned(e).some((id) => mine.has(id));
  switch (e.type) {
    case "agent_message": {
      const relay = d.relay ? ` (${label(String(d.relay))} ${d.from === agent ? "에게 전할 말" : "에게서 온 말"} 중계)` : "";
      if (d.from === agent) return [{ ...base, kind: "message", direction: "out", title: `${label(d.to)}에게 보냄${relay}`, lines: [said(String(d.content ?? ""))] }];
      if (d.to === agent) return [{ ...base, kind: "message", direction: "in", title: `${label(d.from)}에게서 받음${relay}`, lines: [said(String(d.content ?? ""))] }];
      return [];
    }
    case "message_rerouted":
      if (d.via === agent) {
        return [{ ...base, kind: "decision", title: `${label(d.from)} → ${label(d.to)} 메시지를 중계하기로 함`, lines: [`이유: 두 사람 사이에 관계선이 없어 조율자를 거쳐야 함`] }];
      }
      if (d.from === agent) return [{ ...base, kind: "message", direction: "out", title: `${label(d.to)}에게 바로 보낼 수 없어 조율자를 거침`, lines: ["관계선이 없는 상대라 조율자가 대신 전했어요"] }];
      return [];
    case "liner_chat":
    case "liner_search":
    case "liner_decision":
    case "liner_rerank":
    case "liner_visualization":
    case "liner_image":
      return e.actor === agent ? [{ ...base, ...linerEntry(e, view) }] : [];
    case "item_written":
      if (e.actor === agent) return [{ ...base, ...writeEntry(e, view, titles) }];
      // Calls recorded on items another actor wrote: the PM's change mapping, QA's complaint check.
      if (agent === "pm" && d.kind === "changes" && d.item?.status === "awaiting_cp5" && d.item?.target) {
        return [{ ...base, ...changeDecision(d.item, view, titles) }];
      }
      if (agent === "qa" && d.kind === "complaints" && d.item?.status === "classified") {
        return [{ ...base, ...complaintDecision(d.item, view, titles) }];
      }
      return [];
    case "write_rejected":
      if (e.actor !== agent) return [];
      return [{ ...base, kind: "guard", title: "쓰기 권한이 없는 곳이라 기록이 거부됨", lines: view === "team" ? [String(d.reason ?? d.kind ?? "")] : [] }];
    case "guardrail":
      if (e.actor !== agent && !touchesMine) return [];
      return [{ ...base, kind: "guard", title: summarizeEvent(e, label, view).text.split(":")[0], lines: [p(String(d.detail ?? ""))].filter(Boolean) }];
    case "check_result":
      if (agent !== "coordinator" && !touchesMine) return [];
      return [{
        ...base,
        kind: "decision",
        title: summarizeEvent(e, label, "client").text,
        lines: (Array.isArray(d.details) ? d.details : []).map((x: unknown) => p(String(x))),
      }];
    case "prototype_built":
      return e.actor === agent ? [{ ...base, ...prototypeDecision(d) }] : [];
    default:
      return [];
  }
}

function summaryOf(events: AppEvent[], source: Record<string, unknown>): CoordinatorSummary {
  const counts = new Map<string, { sent: number; received: number }>();
  const bump = (who: string, key: "sent" | "received") => {
    const c = counts.get(who) ?? { sent: 0, received: 0 };
    counts.set(who, { ...c, [key]: c[key] + 1 });
  };
  for (const e of events) {
    if (e.type !== "agent_message") continue;
    if (e.data.from === "coordinator") bump(String(e.data.to), "sent");
    if (e.data.to === "coordinator") bump(String(e.data.from), "received");
  }
  const handoffs = [...counts.entries()]
    .map(([agent, c]) => ({ agent, ...c }))
    .sort((a, b) => b.sent + b.received - (a.sent + a.received) || a.agent.localeCompare(b.agent));
  const stages = [...new Set(events.filter((e) => e.type === "stage_started").map((e) => String(e.data.stage)))];
  const items = (kind: string) => (Array.isArray(source[kind]) ? (source[kind] as Record<string, any>[]) : []);
  const answered = new Set(items("decisions").map((d) => d.question_id));
  const pending = [
    { label: "답을 기다리는 질문", count: items("questions").filter((q) => !answered.has(q.id)).length },
    { label: "아직 정하지 못한 요구사항", count: items("requirements").filter((r) => r.status === "미결").length },
    { label: "가정으로 채운 요구사항", count: items("requirements").filter((r) => r.status === "가정").length },
    { label: "결정을 기다리는 변경 요청", count: items("changes").filter((c) => c.status === "mapping" || c.status === "awaiting_cp5").length },
    { label: "확인 중인 불만", count: items("complaints").filter((c) => c.status === "checking").length },
    { label: "사람 판단이 필요한 불만", count: items("complaints").filter((c) => c.needs_human).length },
  ].filter((x) => x.count > 0);
  return { handoffs, reroutes: events.filter((e) => e.type === "message_rerouted").length, stages, pending };
}

export function agentLog(
  events: AppEvent[],
  source: Record<string, unknown>,
  agent: string,
  label: Label,
  view: View,
  titles: Record<string, string>,
): AgentLog {
  const mine = writtenBy(events, agent);
  const groups: LogGroup[] = [];
  let total = 0;
  for (const e of [...events].sort((a, b) => a.seq - b.seq)) {
    const entries = entriesFor(e, agent, mine, label, view, titles);
    if (entries.length === 0) continue;
    const stage = e.stage ?? "";
    let group = groups[groups.length - 1];
    if (!group || group.stage !== stage) {
      group = { key: `${stage}-${groups.length}`, stage, title: STAGE_TITLE[stage] ?? (stage || "기타"), entries: [] };
      groups.push(group);
    }
    group.entries.push(...entries);
    total += entries.length;
  }
  return { groups, summary: agent === "coordinator" ? summaryOf(events, source) : null, total };
}

export function filterLog(groups: LogGroup[], kinds: Set<LogKind>, query: string): LogGroup[] {
  const q = query.trim().toLowerCase();
  return groups
    .map((g) => ({
      ...g,
      entries: g.entries.filter(
        (e) => kinds.has(e.kind) && (!q || [e.title, ...e.lines].some((t) => t.toLowerCase().includes(q))),
      ),
    }))
    .filter((g) => g.entries.length > 0);
}
