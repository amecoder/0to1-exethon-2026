import type { DocId } from "../api";

// What the artifact side panel shows.
export type PanelTab = "docs" | "flow" | "prototype" | "graph" | "team";
export type PanelWidth = "base" | "wide";
export interface PanelTarget {
  tab: PanelTab;
  doc?: DocId;
  highlight?: string[]; // trace map: item ids to light together (a change request's impacted lineage)
  focus?: string; // trace map: select this item (a link from an agent's log)
}

export const DOC_ORDER: DocId[] = ["brd", "prd", "screens", "tests"];

export const DOC_NAME: Record<DocId, string> = {
  brd: "BRD",
  prd: "PRD",
  screens: "화면설계서",
  tests: "테스트 케이스",
};

// One plain line under each document name, for readers who do not know the acronyms.
export const DOC_PLAIN: Record<DocId, string> = {
  brd: "왜 만드는지 — 문제와 목표",
  prd: "무엇을 만드는지 — 요구사항",
  screens: "어떻게 보이는지 — 화면",
  tests: "다 됐는지 확인하는 법",
};
