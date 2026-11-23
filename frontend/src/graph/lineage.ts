// Stream lineage of the shared source: items as nodes in flow-order lanes (원문 → 근거 → 질문·답 → 요구사항 →
// 화면·흐름도 → 테스트 → 프로토타입), directed links from what an item came from to the item, each link
// naming the agent that turned one into the other. Changes and complaints sit in a band under the lanes.
// Pure functions (no React) so mapping, layout and the lineage walk can be unit-tested.
import type { AppEvent } from "../api";
import { prototypeLabel } from "../lib/bundle";
import { STAGE_TITLE, type View } from "../lib/labels";
import type { Label } from "../lib/summarize";

export type NodeKind = "SRC" | "EV" | "DEC" | "REQ" | "SCR" | "FLOW" | "TC" | "PROTO" | "CHG" | "CMP";
export type ColumnKey = "SRC" | "EV" | "DEC" | "REQ" | "SCR" | "TC" | "PROTO";
export type EdgeKind = "ref" | "change" | "complaint";

export const COLUMNS: { key: ColumnKey; title: string }[] = [
  { key: "SRC", title: "원문" },
  { key: "EV", title: "근거" },
  { key: "DEC", title: "질문·답" },
  { key: "REQ", title: "요구사항" },
  { key: "SCR", title: "화면·흐름도" },
  { key: "TC", title: "테스트" },
  { key: "PROTO", title: "프로토타입" },
];

export const KIND_KO: Record<NodeKind, string> = {
  SRC: "원문",
  EV: "Liner 근거",
  DEC: "고른 답",
  REQ: "요구사항",
  SCR: "화면",
  FLOW: "흐름도",
  TC: "테스트",
  PROTO: "프로토타입",
  CHG: "변경 요청",
  CMP: "「아 이거 아닌데?」",
};

export const KIND_COLOR: Record<NodeKind, string> = {
  SRC: "#c7d0f5",
  EV: "#7fe3f0",
  DEC: "#f2b65a",
  REQ: "#b3a8ff",
  SCR: "#ff9ecf",
  FLOW: "#ff9ecf",
  TC: "#5ee0a0",
  PROTO: "#eef0fa",
  CHG: "#ffb86b",
  CMP: "#ff8f8f",
};

export interface LNode {
  id: string;
  kind: NodeKind;
  col: ColumnKey;
  band: "main" | "change";
  title: string; // plain name (the client view shows this instead of the id)
  detail: string; // the real sentence, for the hover card
  author: string | null; // who made it ("client" for memo lines and answers)
  stages: string[]; // stages it was written in, in order
  fixed: { first: string | null; last: string | null }; // versions that fixed it (v1 … ), null if never
  tags: string[];
}

export interface LEdge {
  key: string; // `${from}>${to}`
  from: string;
  to: string;
  kind: EdgeKind;
  agent: string | null; // who turned `from` into `to`
}

export interface LineageGraph {
  nodes: LNode[];
  edges: LEdge[];
}

type Item = Record<string, any>;

const ITEM_KINDS: [string, NodeKind, ColumnKey][] = [
  ["sources", "SRC", "SRC"],
  ["evidence", "EV", "EV"],
  ["decisions", "DEC", "DEC"],
  ["requirements", "REQ", "REQ"],
  ["screens", "SCR", "SCR"],
  ["flow_chart", "FLOW", "SCR"],
  ["tests", "TC", "TC"],
  ["prototype", "PROTO", "PROTO"],
  ["changes", "CHG", "DEC"],
  ["complaints", "CMP", "PROTO"],
];

const NOT_AGENTS = new Set(["system", ""]);
// Where a source sentence came from (SourceSentence.origin) → the tag on its node.
const ORIGIN_TAGS: Record<string, string> = { audio: "음성", image: "이미지", document: "문서" };

function list(source: Record<string, unknown>, kind: string): Item[] {
  const value = source[kind];
  return Array.isArray(value) ? (value as Item[]) : [];
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

export function clip(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

function texts(kind: NodeKind, item: Item): { title: string; detail: string } {
  const s = (v: unknown) => (v == null ? "" : String(v));
  switch (kind) {
    case "SRC":
      return { title: s(item.text), detail: s(item.text) };
    case "EV":
      return { title: s(item.title || item.fact || "근거"), detail: [item.fact, item.quote && `“${item.quote}”`].filter(Boolean).join(" — ") };
    case "DEC":
      return { title: s(item.chosen || "답"), detail: `${s(item.topic)} → ${s(item.chosen)}` };
    case "REQ":
      return { title: s(item.title), detail: s(item.statement) };
    case "FLOW":
      return { title: "사용자 흐름도", detail: s(item.description || "화면 순서대로 그린 흐름도") };
    case "PROTO":
      return { title: prototypeLabel(s(item.platform) || undefined), detail: "확정 원본으로 만든 단일 HTML 프로토타입" };
    case "CHG":
      return { title: s(item.utterance), detail: item.title ? `${s(item.utterance)} → 「${s(item.title)}」를 바꿈` : s(item.utterance) };
    case "CMP":
      return { title: s(item.text), detail: [item.text, item.classification && `판정: ${item.classification}`].filter(Boolean).join(" — ") };
    default:
      return { title: s(item.title), detail: s(item.purpose || item.objective || item.title) };
  }
}

interface WriteLog {
  actors: string[];
  stages: string[];
  first: number;
  last: number;
}

function writeLog(events: AppEvent[]): Map<string, WriteLog> {
  const out = new Map<string, WriteLog>();
  for (const e of events) {
    if (e.type !== "item_written") continue;
    const id = e.data?.item?.id;
    if (typeof id !== "string") continue;
    const log = out.get(id) ?? { actors: [], stages: [], first: e.seq, last: e.seq };
    if (!NOT_AGENTS.has(e.actor)) log.actors.push(e.actor);
    if (e.stage && !log.stages.includes(e.stage)) log.stages.push(e.stage);
    log.last = e.seq;
    out.set(id, log);
  }
  return out;
}

function versionAfter(versions: { seq: number; version: string }[], seq: number | undefined): string | null {
  if (seq === undefined) return null;
  return versions.find((v) => v.seq > seq)?.version ?? null;
}

function authorOf(kind: NodeKind, item: Item, log: WriteLog | undefined): string | null {
  if (kind === "SRC" || kind === "CHG" || kind === "CMP") return "client";
  if (kind === "DEC") return typeof item.answered_by === "string" ? item.answered_by : "client";
  const last = log?.actors[log.actors.length - 1];
  if (last) return last;
  return typeof item.owner_agent === "string" ? item.owner_agent : null;
}

export function buildLineage(source: Record<string, unknown>, events: AppEvent[]): LineageGraph {
  const writes = writeLog(events);
  const versions = events
    .filter((e) => e.type === "version_created" && typeof e.data?.version === "string")
    .map((e) => ({ seq: e.seq, version: String(e.data.version) }));
  const nodes = new Map<string, LNode>();
  for (const [kind, nodeKind, col] of ITEM_KINDS) {
    for (const item of list(source, kind)) {
      const id = typeof item.id === "string" ? item.id : null;
      if (!id || nodes.has(id)) continue;
      const log = writes.get(id);
      const tags: string[] = [];
      if (nodeKind === "SRC" && typeof item.origin === "string" && item.origin in ORIGIN_TAGS) tags.push(ORIGIN_TAGS[item.origin]);
      if ((nodeKind === "DEC" || nodeKind === "REQ") && item.status === "가정") tags.push("가정");
      if (nodeKind === "CHG" && item.status === "rejected") tags.push("반려");
      nodes.set(id, {
        id,
        kind: nodeKind,
        col,
        band: nodeKind === "CHG" || nodeKind === "CMP" ? "change" : "main",
        ...texts(nodeKind, item),
        author: authorOf(nodeKind, item, log),
        stages: log?.stages ?? [],
        fixed: { first: versionAfter(versions, log?.first), last: versionAfter(versions, log?.last) },
        tags,
      });
    }
  }

  const edges = new Map<string, LEdge>();
  const add = (from: string, to: string, kind: EdgeKind = "ref", agent?: string | null) => {
    if (from === to || !nodes.has(from) || !nodes.has(to)) return;
    const key = `${from}>${to}`;
    if (!edges.has(key)) edges.set(key, { key, from, to, kind, agent: agent === undefined ? nodes.get(to)!.author : agent });
  };

  const questions = new Map(list(source, "questions").map((q) => [String(q.id), q]));
  for (const dec of list(source, "decisions")) {
    const q = questions.get(String(dec.question_id));
    for (const ref of [...strings(q?.source_refs), ...strings(q?.evidence_refs)]) add(ref, dec.id);
  }
  for (const req of list(source, "requirements")) {
    for (const ref of [...strings(req.source_refs), ...strings(req.evidence_refs), ...strings(req.decision_refs), ...strings(req.depends_on)]) {
      add(ref, req.id);
    }
    for (const scr of strings(req.screens)) add(req.id, scr);
    for (const tc of strings(req.tests)) add(req.id, tc);
  }
  for (const scr of list(source, "screens")) {
    const els = Array.isArray(scr.elements) ? (scr.elements as Item[]) : [];
    for (const ref of [...strings(scr.requirement_refs), ...els.flatMap((el) => strings(el.requirement_refs))]) add(ref, scr.id);
  }
  for (const flow of list(source, "flow_chart")) for (const scr of strings(flow.based_on)) add(scr, flow.id);
  for (const tc of list(source, "tests")) {
    for (const ref of [...strings(tc.requirement_refs), ...strings(tc.screen_refs)]) add(ref, tc.id);
  }
  const screens = list(source, "screens").map((s) => String(s.id));
  for (const proto of list(source, "prototype")) for (const scr of screens) add(scr, proto.id);
  for (const chg of list(source, "changes")) {
    if (typeof chg.target === "string") add(chg.id, chg.target, "change", "pm");
    if (typeof chg.complaint_ref === "string") add(chg.complaint_ref, chg.id, "change", "coordinator");
  }
  for (const cmp of list(source, "complaints")) for (const req of strings(cmp.requirement_ids)) add(req, cmp.id, "complaint", "qa");

  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

// --- naming -------------------------------------------------------------------------------------

// Team view names items by id; the client view by their plain title (ids appear on hover only).
export function nodeName(node: LNode, view: View): string {
  return view === "team" ? node.id : clip(node.title, 24);
}

// Hover/detail wording: "요구사항 확정 → 변경 반영", "v1에 처음 고정 · 지금은 v3".
export function stagesText(node: LNode): string {
  return node.stages.map((s) => STAGE_TITLE[s] ?? s).join(" → ");
}

export function fixedText(node: LNode): string {
  const { first, last } = node.fixed;
  if (!first) return "아직 버전에 고정되지 않음";
  if (!last) return `${first}에 처음 고정 · 마지막 기록은 아직 고정 전`;
  return first === last ? `${first}에 고정` : `${first}에 처음 고정 · 지금은 ${last}`;
}

// --- lineage walk -------------------------------------------------------------------------------

export interface Trace {
  up: Set<string>; // everything the node came from
  down: Set<string>; // everything that depends on it
  edges: Set<string>;
}

function walk(graph: LineageGraph, start: string, forward: boolean, nodes: Set<string>, keys: Set<string>) {
  const queue = [start];
  const seen = new Set([start]);
  while (queue.length) {
    const at = queue.shift()!;
    for (const e of graph.edges) {
      const [from, to] = forward ? [e.from, e.to] : [e.to, e.from];
      if (from !== at) continue;
      keys.add(e.key);
      if (to !== start) nodes.add(to);
      if (!seen.has(to)) {
        seen.add(to);
        queue.push(to);
      }
    }
  }
}

export function traceOf(graph: LineageGraph, id: string): Trace {
  const up = new Set<string>();
  const down = new Set<string>();
  const edges = new Set<string>();
  if (!graph.nodes.some((n) => n.id === id)) return { up, down, edges };
  walk(graph, id, false, up, edges);
  walk(graph, id, true, down, edges);
  return { up, down, edges };
}

// A given set of items lit together (a change request's impacted items) and the links between them.
export function highlightOf(graph: LineageGraph, ids: string[]): Trace {
  const present = new Set(graph.nodes.map((n) => n.id));
  const down = new Set(ids.filter((id) => present.has(id)));
  const edges = new Set(graph.edges.filter((e) => down.has(e.from) && down.has(e.to)).map((e) => e.key));
  return { up: new Set(), down, edges };
}

// Every chain of ids from a root to `id` ("up") or from `id` to a leaf ("down"), at most `limit`.
export function pathsOf(graph: LineageGraph, id: string, dir: "up" | "down", limit = 8): string[][] {
  const next = new Map<string, string[]>();
  for (const e of graph.edges) {
    const [a, b] = dir === "down" ? [e.from, e.to] : [e.to, e.from];
    next.set(a, [...(next.get(a) ?? []), b]);
  }
  const out: string[][] = [];
  const visit = (at: string, chain: string[]) => {
    if (out.length >= limit) return;
    const outs = (next.get(at) ?? []).filter((n) => !chain.includes(n));
    if (outs.length === 0) {
      if (chain.length > 1) out.push(dir === "down" ? chain : [...chain].reverse());
      return;
    }
    for (const n of outs) visit(n, [...chain, n]);
  };
  visit(id, [id]);
  return out;
}

// "SRC-03 → (PM) → REQ-02 → (디자이너) → SCR-02": the agent is named where the maker changes.
export function describePath(graph: LineageGraph, chain: string[], name: (id: string) => string, label: Label): string {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const parts = [name(chain[0])];
  for (let i = 1; i < chain.length; i += 1) {
    const e = graph.edges.find((x) => x.from === chain[i - 1] && x.to === chain[i]);
    if (e?.agent && e.agent !== byId.get(chain[i - 1])?.author) parts.push(`(${label(e.agent)})`);
    parts.push(name(chain[i]));
  }
  return parts.join(" → ");
}

// --- layout -------------------------------------------------------------------------------------

export const NODE_W = 104;
export const NODE_H = 38;
const COL_STEP = 132;
const ROW_STEP = 44;
const PAD_X = 16;
const CHIP_TOP = 26; // lane titles sit above this
export const CHIP_STEP = 22;
const BAND_GAP = 36;

export interface Layout {
  width: number;
  height: number;
  columns: { key: ColumnKey; title: string; x: number }[];
  pos: Map<string, { x: number; y: number }>;
  chips: { agent: string; x: number; y: number }[]; // producing agents, centred in the gap before a lane
  bandY: number | null; // top of the change band
  loose: string[]; // memo lines with no links (hidden unless showLoose)
}

// Deterministic layered layout: fixed lane x, rows ordered by the mean row of each node's upstream
// neighbours (one left-to-right barycenter pass), lanes centred vertically.
export function layoutLineage(graph: LineageGraph, opts: { showLoose?: boolean } = {}): Layout {
  const linked = new Set(graph.edges.flatMap((e) => [e.from, e.to]));
  const loose = graph.nodes.filter((n) => n.kind === "SRC" && !linked.has(n.id)).map((n) => n.id);
  const hidden = new Set(opts.showLoose ? [] : loose);
  const main = graph.nodes.filter((n) => n.band === "main" && !hidden.has(n.id));
  const columns = COLUMNS.filter((c) => main.some((n) => n.col === c.key)).map((c, i) => ({ ...c, x: PAD_X + i * COL_STEP }));
  const colIndex = new Map(columns.map((c, i) => [c.key, i]));

  // Producing agents per lane (who wrote its items from earlier items), stacked in the header gap before it.
  const chips: Layout["chips"] = [];
  let stack = 1;
  columns.forEach((c, i) => {
    if (i === 0) return;
    const agents = [...new Set(main.filter((n) => n.col === c.key).flatMap((n) => [
      n.author,
      ...graph.edges.filter((e) => e.to === n.id && e.kind === "ref").map((e) => e.agent),
    ]).filter((a): a is string => Boolean(a)))].sort();
    stack = Math.max(stack, agents.length);
    agents.forEach((agent, k) => chips.push({ agent, x: c.x - (COL_STEP - NODE_W) / 2, y: CHIP_TOP + k * CHIP_STEP }));
  });
  const top = CHIP_TOP + stack * CHIP_STEP + 8;

  const row = new Map<string, number>();
  const lanes: LNode[][] = columns.map((c) => main.filter((n) => n.col === c.key));
  lanes.forEach((lane, i) => {
    const score = (n: LNode) => {
      const ups = graph.edges.filter((e) => e.to === n.id && row.has(e.from)).map((e) => row.get(e.from)!);
      return ups.length ? ups.reduce((a, b) => a + b, 0) / ups.length : Number.POSITIVE_INFINITY;
    };
    const ordered = i === 0 ? lane : [...lane].sort((a, b) => score(a) - score(b) || a.id.localeCompare(b.id));
    lanes[i] = ordered;
    ordered.forEach((n, r) => row.set(n.id, r));
  });
  const tallest = Math.max(0, ...lanes.map((l) => l.length));
  const pos = new Map<string, { x: number; y: number }>();
  lanes.forEach((lane, i) => {
    const offset = ((tallest - lane.length) * ROW_STEP) / 2;
    lane.forEach((n, r) => pos.set(n.id, { x: columns[i].x, y: top + offset + r * ROW_STEP }));
  });
  const mainBottom = top + tallest * ROW_STEP;

  const band = graph.nodes.filter((n) => n.band === "change");
  let bandY: number | null = null;
  if (band.length && columns.length) {
    bandY = mainBottom + BAND_GAP / 2;
    const reqAt = colIndex.get("REQ");
    const chgX = columns[Math.max(0, (reqAt ?? 1) - 1)].x;
    const cmpX = columns[columns.length - 1].x;
    const counts = { CHG: 0, CMP: 0 };
    for (const n of band) {
      const k = n.kind === "CHG" ? "CHG" : "CMP";
      pos.set(n.id, { x: k === "CHG" ? chgX : cmpX, y: mainBottom + BAND_GAP + counts[k] * ROW_STEP });
      counts[k] += 1;
    }
  }

  const bandRows = Math.max(0, ...["CHG", "CMP"].map((k) => band.filter((n) => n.kind === k).length));
  const height = (bandY === null ? mainBottom : mainBottom + BAND_GAP + bandRows * ROW_STEP) + 8;
  const width = columns.length ? columns[columns.length - 1].x + NODE_W + PAD_X : 0;
  return { width, height, columns, pos, chips, bandY, loose };
}
