import type { PanelTab, PanelWidth } from "./types";

// Width rules for the artifact side panel: two toggle presets, and a dragged width that overrides them
// (kept per viewer in localStorage). All values are CSS pixels.
export const MIN_WIDTH = 360;
export const MAX_RATIO = 0.8;
export const KEY_STEP = 32;
export const WIDTH_KEY = "artifact-panel-width";

export function maxWidth(viewport: number): number {
  return Math.max(MIN_WIDTH, Math.floor(viewport * MAX_RATIO));
}

export function clampWidth(px: number, viewport: number): number {
  return Math.round(Math.min(maxWidth(viewport), Math.max(MIN_WIDTH, px)));
}

// The toggle widths (2026-11-18: base trimmed to leave the chat column room; wide unchanged): base, and wide (wider still for the trace map, which needs room for its lanes).
export function presetWidth(width: PanelWidth, tab: PanelTab, viewport: number): number {
  if (width === "base") return clampWidth(Math.min(600, viewport * 0.38), viewport);
  return clampWidth(tab === "graph" ? Math.min(1024, viewport * 0.72) : Math.min(1024, viewport * 0.56), viewport);
}

// The handle sits on the panel's left edge and the panel is anchored right, so moving left widens it.
export function dragWidth(startWidth: number, startX: number, x: number, viewport: number): number {
  return clampWidth(startWidth + (startX - x), viewport);
}

export function keyWidth(current: number, key: string, viewport: number): number | null {
  if (key === "ArrowLeft") return clampWidth(current + KEY_STEP, viewport);
  if (key === "ArrowRight") return clampWidth(current - KEY_STEP, viewport);
  return null;
}

type WidthStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

// Storage can be missing or throw (private window, blocked site data): reads fall back to "no saved width"
// and writes are dropped, so the panel always renders.
export function readWidth(store: () => WidthStore): number | null {
  try {
    const n = Number(store().getItem(WIDTH_KEY));
    return Number.isFinite(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

export function writeWidth(store: () => WidthStore, px: number | null): void {
  try {
    if (px === null) store().removeItem(WIDTH_KEY);
    else store().setItem(WIDTH_KEY, String(Math.round(px)));
  } catch {
    // Not saved: the width still applies for this visit.
  }
}

// The flow chart (Liner Visualization) is a page laid out for a wide screen — its steps sit in one row of
// about 900px. It is drawn at FLOW_BASE and scaled to the box: up (at most 2×) when the box is wider; in a
// narrow side panel it keeps real size and scrolls sideways (shrinking it to fit made the text ~6px), while
// full screen shrinks it to fit so the whole chart is in view.
export const FLOW_BASE = 960;
export const FLOW_MAX_SCALE = 2;

export function flowFit(box: number, full: boolean): { scale: number; width: number; scroll: boolean } {
  const width = Math.max(0, box);
  if (width >= FLOW_BASE) return { scale: Math.min(FLOW_MAX_SCALE, width / FLOW_BASE), width: FLOW_BASE, scroll: false };
  if (full && width > 0) return { scale: width / FLOW_BASE, width: FLOW_BASE, scroll: false };
  return { scale: 1, width: FLOW_BASE, scroll: true };
}
