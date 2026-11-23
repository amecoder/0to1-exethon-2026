import { describe, expect, it } from "vitest";
import type { DecisionStatus } from "../api";
import { decisionHeadline, remainingItems } from "./decisionStatus";

const status = (assumed: number, open: number, planning: boolean): DecisionStatus => {
  const item = (p: string) => (_: unknown, i: number) => ({ id: `${p}-0${i + 1}`, title: `${p} ${i + 1}` });
  const decided = assumed + open === 0;
  return {
    counts: { confirmed: 1, assumed, open },
    items: {
      confirmed: [{ id: "REQ-01", title: "a" }],
      assumed: Array.from({ length: assumed }, item("DEC")),
      open: Array.from({ length: open }, item("OPEN")),
    },
    planning_done: planning,
    decision_done: planning && decided,
    level: planning ? (decided ? "결정 완료" : "기획 완료") : null,
  };
};

describe("decisionHeadline", () => {
  it("separates 기획 완료 (CP4 approved) from 결정 완료 (no 가정·미결 left)", () => {
    expect(decisionHeadline(status(0, 0, true)).title).toBe("결정 완료");
    const planned = decisionHeadline(status(1, 2, true));
    expect(planned.title).toContain("기획 완료");
    expect(planned.note).toContain("3건");
    expect(decisionHeadline(status(1, 0, false)).title).not.toContain("완료");
  });
});

describe("remainingItems", () => {
  it("lists 가정 first, then 미결, each with its label", () => {
    expect(remainingItems(status(1, 1, true)).map((r) => [r.id, r.label])).toEqual([
      ["DEC-01", "가정"],
      ["OPEN-01", "미결"],
    ]);
  });
});
