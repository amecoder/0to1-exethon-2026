import type { DocId } from "../api";
import type { View } from "../lib/labels";
import { DOC_ORDER, type PanelTab, type PanelTarget } from "./types";

// The artifact panel can open in its own browser window: the address carries the project and what to show,
// and App renders only the panel when it sees `artifact=` in the query.
const TABS: PanelTab[] = ["docs", "flow", "prototype", "graph", "team"];

export interface Popout {
  id: string;
  target: PanelTarget;
  view: View;
  step?: number; // demo replay: the step the player was on when the window opened
}

export function popoutUrl(id: string, target: PanelTarget, view: View, step?: number): string {
  const q = new URLSearchParams({ artifact: id, tab: target.tab });
  if (target.tab === "docs" && target.doc) q.set("doc", target.doc);
  q.set("view", view);
  if (step !== undefined) q.set("step", String(step));
  return `/?${q.toString()}`;
}

export function readPopout(search: string): Popout | null {
  const q = new URLSearchParams(search);
  const id = q.get("artifact");
  if (!id) return null;
  const tab = TABS.find((t) => t === q.get("tab")) ?? "docs";
  const doc = DOC_ORDER.find((d) => d === q.get("doc")) as DocId | undefined;
  const target: PanelTarget = tab === "docs" && doc ? { tab, doc } : { tab };
  const out: Popout = { id, target, view: q.get("view") === "team" ? "team" : "client" };
  const step = /^\d+$/.test(q.get("step") ?? "") ? Number(q.get("step")) : undefined;
  return step === undefined ? out : { ...out, step };
}

// Opens (or reuses) one window per project.
export function openPopout(id: string, target: PanelTarget, view: View, step?: number): void {
  window.open(popoutUrl(id, target, view, step), `0to1-artifact-${id}`, "popup,width=1280,height=900");
}

// The demo player and its pop-out talk over a same-origin BroadcastChannel: the player announces every step
// it shows, and a newly opened window asks once which step that is.
export const DEMO_CHANNEL = "0to1-demo";
export const DEMO_STEP = "0to1:demo-step";
export const DEMO_ASK = "0to1:demo-ask";

export function readDemoStep(data: unknown): number | null {
  if (!data || typeof data !== "object") return null;
  const m = data as { type?: unknown; step?: unknown };
  return m.type === DEMO_STEP && typeof m.step === "number" && Number.isInteger(m.step) && m.step >= 0 ? m.step : null;
}
