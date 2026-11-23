import { useCallback, useEffect, useRef, useState } from "react";
import type { Project } from "../api";
import { readWidth, writeWidth } from "./panelSize";
import type { PanelTarget, PanelWidth } from "./types";

export interface PanelState {
  open: boolean;
  target: PanelTarget;
  width: PanelWidth;
  px: number | null; // a dragged width (overrides the toggle width), kept per viewer
  show: (t: PanelTarget) => void;
  toggle: () => void;
  close: () => void;
  setTarget: (t: PanelTarget) => void;
  setWidth: (w: PanelWidth) => void;
  setPx: (px: number) => void;
}

// Side panel state. It opens by itself once when a confirmation needs what it shows (CP3 → the
// documents, CP4 → the prototype); after that the client decides.
export function usePanel(project: Project | null): PanelState {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<PanelTarget>({ tab: "docs" });
  const [width, setWidth] = useState<PanelWidth>("base");
  const [px, setPxState] = useState<number | null>(() => readWidth(store));
  const opened = useRef(new Set<string>());
  const todo = project?.todo;
  const cp = todo?.kind === "confirmation" ? todo.cp : null;

  useEffect(() => {
    if (!cp || opened.current.has(cp)) return;
    if (cp === "CP3" || cp === "CP4") {
      opened.current.add(cp);
      setTarget(cp === "CP3" ? { tab: "docs", doc: "brd" } : { tab: "prototype" });
      setOpen(true);
    }
  }, [cp]);

  // The lineage map needs room for its lanes, so opening it widens the panel.
  const show = useCallback((t: PanelTarget) => {
    setTarget(t);
    if (t.tab === "graph") setWidth("wide");
    setOpen(true);
  }, []);
  return {
    open,
    target,
    width,
    px,
    show,
    toggle: () => setOpen((o) => !o),
    close: () => setOpen(false),
    setTarget: (t: PanelTarget) => {
      setTarget(t);
      if (t.tab === "graph") setWidth("wide");
    },
    // The width toggle picks a preset and drops a dragged width; dragging overrides the preset again.
    setWidth: (w: PanelWidth) => {
      setWidth(w);
      setPxState(null);
      writeWidth(store, null);
    },
    setPx: (next: number) => {
      setPxState(next);
      writeWidth(store, next);
    },
  };
}

const store = () => window.localStorage;

// Item titles by ID (requirements, screens, tests, and decisions as the chosen answer) so client-facing text can name items instead of IDs.
export function titlesOf(project: Project | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!project) return out;
  for (const kind of ["requirements", "screens", "tests"]) {
    for (const item of (project.source[kind] as { id: string; title: string }[] | undefined) ?? []) out[item.id] = item.title;
  }
  for (const d of (project.source.decisions as { id: string; chosen: string }[] | undefined) ?? []) out[d.id] = `고른 답 “${d.chosen}”`;
  return out;
}
