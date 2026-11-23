// Demo opening: the client's memo as messenger bubbles, with the two sentences the team later found in
// conflict. Everything comes from the recorded events (sources, QA findings, question cards) — no fixed text.
import type { AppEvent } from "../api";

export interface MemoLine {
  id: string;
  text: string;
  conflict: boolean;
}

export interface MemoBubble {
  time: string | null;
  lines: MemoLine[];
}

export interface OpeningMemo {
  bubbles: MemoBubble[];
  conflict: { ids: string[]; note: string } | null;
}

// "**[월 오전 10:12]** …" → "월 오전 10:12"
const STAMP = /^\*{0,2}\[([^\]]+)\]\*{0,2}/;

function written(events: AppEvent[], kind: string): Record<string, any>[] {
  const byId = new Map<string, Record<string, any>>();
  for (const e of events) {
    if (e.type === "item_written" && e.data?.kind === kind && e.data.item?.id) byId.set(String(e.data.item.id), e.data.item);
  }
  return [...byId.values()];
}

function findConflict(events: AppEvent[]): { ids: string[]; note: string } | null {
  const finding = written(events, "findings").find((f) => f.type === "conflict" && (f.source_refs ?? []).length >= 2);
  if (finding) return { ids: finding.source_refs.slice(0, 2), note: String(finding.note ?? "") };
  const question = written(events, "questions").find((q) => (q.source_refs ?? []).length >= 2);
  if (question) return { ids: question.source_refs.slice(0, 2), note: String(question.why ?? question.question ?? "") };
  return null;
}

export function openingMemo(events: AppEvent[]): OpeningMemo {
  const conflict = findConflict(events);
  const marked = new Set(conflict?.ids ?? []);
  const bubbles: MemoBubble[] = [];
  for (const s of written(events, "sources")) {
    const stamp = STAMP.exec(String(s.raw ?? ""));
    const line: MemoLine = { id: String(s.id), text: String(s.text ?? ""), conflict: marked.has(String(s.id)) };
    const last = bubbles[bubbles.length - 1];
    if (stamp || !last) bubbles.push({ time: stamp ? stamp[1].trim() : null, lines: [line] });
    else last.lines.push(line);
  }
  return { bubbles, conflict };
}
