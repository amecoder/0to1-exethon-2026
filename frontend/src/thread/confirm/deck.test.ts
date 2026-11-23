import { describe, expect, it } from "vitest";
import { confirmRestLabel, deckBlocker } from "./RequirementDeck";

const reviews = (ok: number, fix: number, open: number) => ({ items: [], ok, fix, open, total: ok + fix + open });

describe("deckBlocker", () => {
  it("opens the final approval only when every card is 확정", () => {
    expect(deckBlocker(reviews(3, 0, 0))).toBeNull();
    expect(deckBlocker(reviews(2, 1, 0))).toContain("고칠 점 1건");
    expect(deckBlocker(reviews(1, 0, 2))).toContain("2건이 아직 확정 전");
    expect(deckBlocker(undefined)).toBeNull(); // demo replay / no deck: the old approval stays
  });
});

describe("confirmRestLabel", () => {
  it("names how many open cards one click would settle, and hides when none are left", () => {
    expect(confirmRestLabel(reviews(1, 1, 3))).toBe("남은 3건 모두 확정");
    expect(confirmRestLabel(reviews(2, 1, 0))).toBeNull();
  });
});
