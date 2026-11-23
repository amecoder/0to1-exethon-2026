import { describe, expect, it } from "vitest";
import type { AppEvent } from "../api";
import { compactProgress } from "../thread/model";
import { josa } from "./labels";
import { openingMemo } from "./opening";
import { extractScenes } from "./scenes";
import { formatDuration, stageTiming } from "./timing";
import { linerUsage, relationCounters } from "./usage";

let seq = 0;
function ev(type: string, data: Record<string, unknown>, actor = "system", stage: string | null = null, ts = "2026-11-16T00:00:00Z"): AppEvent {
  seq += 1;
  return { seq, ts, stage, type, actor, data };
}
const src = (id: string, text: string, raw = text) => ev("item_written", { kind: "sources", item: { id, text, raw } }, "system", "S1");

describe("josa", () => {
  it("picks the particle from the last syllable", () => {
    expect(josa("프로토타입", "을/를")).toBe("프로토타입을");
    expect(josa("화면설계서", "을/를")).toBe("화면설계서를");
    expect(josa("발주사", "이/가")).toBe("발주사가");
    expect(josa("PM", "이/가")).toBe("PM이");
    expect(josa("QA", "이/가")).toBe("QA가");
  });
});

describe("openingMemo", () => {
  seq = 0;
  const events = [
    ev("stage_started", { stage: "S1" }),
    src("SRC-01", "요일은 고객이 골라요.", "**[월 오전 10:12]** 요일은 고객이 골라요."),
    src("SRC-02", "꼭이요."),
    src("SRC-03", "토요일에 한꺼번에 보내요.", "**[월 오후 2:40]** 토요일에 한꺼번에 보내요."),
    ev("item_written", { kind: "findings", item: { id: "FND-01", type: "missing_exception", note: "x", source_refs: ["SRC-02"] } }, "qa", "S3"),
    ev("item_written", { kind: "findings", item: { id: "FND-02", type: "conflict", note: "요일 선택과 토요일 일괄이 부딪혀요", source_refs: ["SRC-01", "SRC-03"] } }, "qa", "S3"),
  ];

  it("groups sentences into timed messenger bubbles from the recorded sources", () => {
    const memo = openingMemo(events);
    expect(memo.bubbles.map((b) => b.time)).toEqual(["월 오전 10:12", "월 오후 2:40"]);
    expect(memo.bubbles[0].lines.map((l) => l.id)).toEqual(["SRC-01", "SRC-02"]);
  });

  it("marks the two sentences of the first recorded conflict", () => {
    const memo = openingMemo(events);
    expect(memo.conflict).toEqual({ ids: ["SRC-01", "SRC-03"], note: "요일 선택과 토요일 일괄이 부딪혀요" });
    expect(memo.bubbles.flatMap((b) => b.lines).filter((l) => l.conflict).map((l) => l.id)).toEqual(["SRC-01", "SRC-03"]);
  });

  it("falls back to a question citing two sentences when no conflict finding exists", () => {
    const qs = [
      src("SRC-01", "가"),
      src("SRC-02", "나"),
      ev("item_written", { kind: "questions", item: { id: "Q-01", question: "어느 쪽인가요?", why: "두 문장이 달라요", source_refs: ["SRC-01", "SRC-02"] } }, "coordinator", "S3"),
    ];
    expect(openingMemo(qs).conflict).toEqual({ ids: ["SRC-01", "SRC-02"], note: "두 문장이 달라요" });
    expect(openingMemo([src("SRC-01", "가")]).conflict).toBeNull();
  });
});

describe("compactProgress with the change lane", () => {
  it("does not say every step is done while a CP5 change waits", () => {
    const p = compactProgress("CP4", "completed", { pendingChange: true });
    expect(p.done).toBe(false);
    expect(p.label).toBe("변경 체크포인트(CP5)");
    expect(p.remaining).toBe(1);
  });

  it("counts the re-confirmations after an approved change", () => {
    const p = compactProgress("S5", "running", { recheck: true });
    expect(p.done).toBe(false);
    expect(p.remaining).toBe(2);
  });

  it("is still done with no pending change", () => {
    expect(compactProgress("CP4", "completed", { pendingChange: false }).done).toBe(true);
  });
});

describe("extractScenes — change and complaint lane", () => {
  seq = 0;
  const change = (status: string) => ({ kind: "changes", item: { id: "CHG-01", status, utterance: "일시정지는 하루 전까지" } });
  const complaint = (status: string, cls?: string) => ({ kind: "complaints", item: { id: "CMP-01", status, text: "일요일은 왜 안 돼요?", classification: cls } });
  const events = [
    ev("stage_started", { stage: "S1" }),
    ev("pipeline", { stage: "CP4", status: "awaiting_confirmation" }),
    ev("pipeline", { stage: "CP4", status: "completed" }),
    ev("item_written", change("mapping"), "coordinator"),
    ev("pipeline", { stage: "CP4", status: "completed", active_agent: "pm" }),
    ev("item_written", change("awaiting_cp5"), "coordinator"),
    ev("recheck_required", { change_id: "CHG-01" }),
    ev("stage_completed", { stage: "S5" }),
    ev("pipeline", { stage: "CP3", status: "awaiting_confirmation" }),
    ev("prototype_built", {}),
    ev("pipeline", { stage: "CP4", status: "awaiting_confirmation" }),
    ev("recheck_cleared", { change_id: "CHG-01" }),
    ev("pipeline", { stage: "CP4", status: "completed" }),
    ev("item_written", complaint("checking"), "coordinator"),
    ev("pipeline", { stage: "CP4", status: "completed", active_agent: "qa" }),
    ev("item_written", complaint("classified", "새 변경 요청"), "coordinator"),
  ];
  const scenes = extractScenes(events);

  it("adds the change, CP5, rework, complaint and verdict scenes", () => {
    expect(scenes.map((s) => s.kind)).toEqual([
      "input", "CP4", "done", "change", "CP5", "rework", "documents", "CP3", "prototype", "CP4", "done", "complaint", "verdict",
    ]);
  });

  it("never repeats a label and captions carry the recorded words", () => {
    const labels = scenes.map((s) => s.label);
    expect(new Set(labels).size).toBe(labels.length);
    expect(scenes.find((s) => s.kind === "change")?.caption).toContain("일시정지는 하루 전까지");
    expect(scenes.find((s) => s.kind === "complaint")?.label).toBe("「아 이거 아닌데?」");
    expect(scenes.find((s) => s.kind === "verdict")?.caption).toContain("새 변경 요청");
    expect(scenes.find((s) => s.kind === "CP5")?.label).toBe("변경 영향(CP5)");
    expect(scenes.find((s) => s.kind === "rework")?.label).toBe("다시 만들기(재작업)");
  });
});

describe("linerUsage", () => {
  it("counts calls and cost per Liner API kind with the answering models", () => {
    seq = 0;
    const usage = linerUsage([
      ev("liner_chat", { api: "model", model: "liner-claude-router", answered_model: "claude-x", cost: 0.01 }),
      ev("liner_chat", { api: "model", model: "liner-claude-router", answered_model: "claude-y", cost: 0.02 }),
      ev("liner_chat", { api: "model", model: "liner-mark-1.3", answered_model: null, cost: null }),
      ev("liner_search", { api: "ai_search" }),
      ev("liner_search", { api: "search" }),
      ev("liner_decision", { cost: 0.001 }),
      ev("liner_rerank", { cost: 0.0005 }),
      ev("liner_visualization", {}),
      ev("liner_transcription", { cost: 0.003 }),
      ev("credits", { balance_usd: 1 }),
    ]);
    const chat = usage.find((u) => u.kind === "chat")!;
    expect(chat.calls).toBe(3);
    expect(chat.cost).toBeCloseTo(0.03, 6);
    expect(chat.models).toEqual(["claude-x", "claude-y", "liner-mark-1.3"]);
    expect(usage.map((u) => u.kind)).toEqual(["chat", "decisions", "ai_search", "search", "rerank", "visualization", "transcription"]);
    expect(usage.find((u) => u.kind === "visualization")?.cost).toBeNull();
  });
});

describe("relationCounters", () => {
  it("counts relayed off-relation messages, write refusals and the latest pair", () => {
    seq = 0;
    const c = relationCounters([
      ev("agent_message", { from: "coordinator", to: "pm" }),
      ev("message_rerouted", { from: "qa", to: "developer", via: "coordinator" }),
      ev("write_rejected", {}),
      ev("write_rejected", {}),
      ev("agent_message", { from: "pm", to: "designer" }),
    ]);
    expect(c).toEqual({ rerouted: 1, rejected: 2, pair: { from: "pm", to: "designer" } });
  });
});

describe("stageTiming", () => {
  it("measures from the current stage start and gives the typical hint", () => {
    seq = 0;
    const events = [
      ev("stage_started", { stage: "S2" }, "system", "S2", "2026-11-16T00:00:00Z"),
      ev("stage_started", { stage: "S3" }, "system", "S3", "2026-11-16T00:01:00Z"),
    ];
    const t = stageTiming(events, "S3", Date.parse("2026-11-16T00:01:42Z"));
    expect(t?.elapsedS).toBe(42);
    expect(t?.typical?.calls).toBeGreaterThan(0);
    expect(stageTiming(events, "S6", Date.parse("2026-11-16T00:02:00Z"))).toBeNull();
    expect(formatDuration(42)).toBe("42초");
    expect(formatDuration(130)).toBe("2분 10초");
  });
});
