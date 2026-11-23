import { describe, expect, it } from "vitest";
import type { AppEvent } from "../api";
import { budgetModeOn, budgetView } from "./credits";
import { linerUsage, tokenText } from "./usage";

let seq = 0;
function ev(type: string, data: Record<string, unknown>): AppEvent {
  seq += 1;
  return { seq, ts: "2026-11-17T00:00:00Z", stage: null, type, actor: "pm", data };
}

describe("budgetView", () => {
  it("is null without a budget or without a spent reading", () => {
    expect(budgetView(3.2, null)).toBeNull();
    expect(budgetView(3.2, undefined)).toBeNull();
    expect(budgetView(null, 5)).toBeNull();
  });

  it("shows spent against the budget with a percentage line", () => {
    const v = budgetView(3.2, 5)!;
    expect(v.chip).toBe("$3.20 / $5.00");
    expect(v.line).toBe("예산 $5.00 중 $3.20 사용 (64%)");
    expect(v.level).toBe("caution");
    expect(v.ratio).toBeCloseTo(0.64, 6);
    expect(v.over).toBeNull();
  });

  it("picks the level by thresholds 60% and 85%", () => {
    expect(budgetView(2.99, 5)!.level).toBe("normal");
    expect(budgetView(3, 5)!.level).toBe("caution");
    expect(budgetView(4.24, 5)!.level).toBe("caution");
    expect(budgetView(4.25, 5)!.level).toBe("warning");
  });

  it("does not clamp over budget and says by how much", () => {
    const v = budgetView(7.6, 5)!;
    expect(v.chip).toBe("$7.60 / $5.00");
    expect(v.level).toBe("warning");
    expect(v.over).toBeCloseTo(2.6, 6);
    expect(v.line).toBe("예산 $5.00 중 $7.60 사용 (152%) · 예산 초과 $2.60");
  });
});

describe("linerUsage tokens", () => {
  it("sums tokens per API kind and keeps null when none reported", () => {
    const rows = linerUsage([
      ev("liner_chat", { model: "m", prompt_tokens: 10, completion_tokens: 5, total_tokens: 15, cost: 0.002 }),
      ev("liner_chat", { model: "m", prompt_tokens: 20, completion_tokens: 1, total_tokens: 21 }),
      ev("liner_rerank", { model: "r", total_tokens: 10 }),
      ev("liner_search", { api: "search" }),
    ]);
    const chat = rows.find((r) => r.kind === "chat")!;
    expect([chat.promptTokens, chat.completionTokens, chat.totalTokens]).toEqual([30, 6, 36]);
    const rerank = rows.find((r) => r.kind === "rerank")!;
    expect([rerank.promptTokens, rerank.totalTokens]).toEqual([null, 10]);
    const search = rows.find((r) => r.kind === "search")!;
    expect(search.totalTokens).toBeNull();
  });

  it("counts Liner image generations as their own API row with cost", () => {
    const rows = linerUsage([
      ev("liner_image", { model: "qwen/qwen-image-2.1-turbo", slot: "hero", total_tokens: 4218, cost: 0.0184 }),
      ev("liner_image", { model: "qwen/qwen-image-2.1-turbo", slot: "box", total_tokens: 4218, cost: 0.0184 }),
    ]);
    const images = rows.find((r) => r.kind === "images")!;
    expect([images.calls, images.cost, images.totalTokens, images.models]).toEqual([2, 0.0368, 8436, ["qwen/qwen-image-2.1-turbo"]]);
  });

  it("formats tokens as total with in/out when known", () => {
    const [chat] = linerUsage([ev("liner_chat", { prompt_tokens: 1200, completion_tokens: 34, total_tokens: 1234 })]);
    expect(tokenText(chat)).toBe("1,234 (입력 1,200 · 출력 34)");
    const [rerank] = linerUsage([ev("liner_rerank", { total_tokens: 10 })]);
    expect(tokenText(rerank)).toBe("10");
    const [search] = linerUsage([ev("liner_search", {})]);
    expect(tokenText(search)).toBe("—");
  });
});

describe("budgetModeOn", () => {
  it("is on once the G7 budget-mode switch is in the log, off otherwise", () => {
    const chat = ev("liner_chat", { budget_mode: false });
    expect(budgetModeOn([chat])).toBe(false);
    expect(budgetModeOn([ev("guardrail", { id: "G7", outcome: "blocked", limit: "cost" })])).toBe(false);
    expect(budgetModeOn([chat, ev("guardrail", { id: "G7", outcome: "flagged", limit: "budget_mode" })])).toBe(true);
  });
});
