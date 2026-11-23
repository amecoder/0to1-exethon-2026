import { describe, expect, it } from "vitest";
import type { AppEvent } from "../api";
import { agentScores, exchanges, linerCalls, packetsSince, pairCounts, pairKey, relationName, scoreVerdict, talkMatrix, teamFeed } from "./model";

let seq = 0;
function ev(type: string, data: Record<string, unknown>, actor = "system", stage = "S3"): AppEvent {
  seq += 1;
  return { seq, ts: `2026-11-20T10:00:${String(seq).padStart(2, "0")}Z`, type, actor, stage, data } as unknown as AppEvent;
}
const msg = (from: string, to: string, content: string, stage = "S3") => ev("agent_message", { from, to, content }, from, stage);
const label = (id: string) => ({ pm: "PM", qa: "QA", coordinator: "조율자", client: "발주사" })[id] ?? id;

describe("messages the team graph animates", () => {
  it("lists agent messages in order with sender, receiver and text", () => {
    const events = [msg("pm", "qa", "요구사항 후보 17건 검토 요청"), ev("liner_chat", {}, "qa"), msg("qa", "pm", "지적 28건")];
    expect(exchanges(events).map((x) => [x.from, x.to, x.text])).toEqual([
      ["pm", "qa", "요구사항 후보 17건 검토 요청"],
      ["qa", "pm", "지적 28건"],
    ]);
  });

  it("replays the last few on first look, then only what is new, never more than the cap", () => {
    const all = exchanges(Array.from({ length: 10 }, (_, i) => msg("pm", "qa", `m${i}`)));
    expect(packetsSince(all, null, 3).map((x) => x.text)).toEqual(["m7", "m8", "m9"]);
    expect(packetsSince(all, all[8].seq, 3).map((x) => x.text)).toEqual(["m9"]);
    expect(packetsSince(all, all[9].seq, 3)).toEqual([]);
  });
});

describe("how each agent is doing, from the record", () => {
  const events = [
    msg("coordinator", "pm", "단계 S3 구체화: 요구사항 후보를 만들어라"),
    ev("liner_chat", { duration_ms: 1000 }, "pm"),
    ev("liner_chat", { duration_ms: 3000 }, "pm"),
    ev("item_written", { kind: "requirements", item: { id: "REQ-01" } }, "pm"),
    ev("item_written", { kind: "requirements", item: { id: "REQ-02" } }, "pm"),
    msg("pm", "qa", "검토 요청"),
    ev("liner_search", { error: "timeout", duration_ms: 500 }, "qa"),
    ev("guardrail", { id: "G3", outcome: "masked" }, "qa"),
    ev("write_rejected", { reason: "not yours" }, "qa"),
  ];
  const scores = agentScores(events, ["coordinator", "pm", "qa", "designer"]);
  const pm = scores.find((s) => s.id === "pm")!;
  const qa = scores.find((s) => s.id === "qa")!;

  it("counts work in and out, Liner calls with average time, and items written", () => {
    expect(pm).toMatchObject({ received: 1, sent: 1, liner: 2, linerFailed: 0, avgMs: 2000, written: 2, rejected: 0 });
    expect(qa).toMatchObject({ received: 1, sent: 0, liner: 1, linerFailed: 1, masked: 1, rejected: 1 });
  });

  it("knows who still holds a request (received after their last reply)", () => {
    expect(qa.holding).toBe(true);
    expect(pm.holding).toBe(false);
  });

  it("says plainly what to look at, and calls an idle agent idle", () => {
    expect(scoreVerdict(pm)).toEqual({ tone: "ok", text: "문제 없음" });
    expect(scoreVerdict(qa).tone).toBe("bad");
    expect(scoreVerdict(qa).text).toContain("Liner 실패 1");
    expect(scoreVerdict(qa).text).toContain("쓰기 거부 1");
    expect(scoreVerdict(scores.find((s) => s.id === "designer")!)).toEqual({ tone: "idle", text: "아직 맡은 일 없음" });
  });

  it("flags a blocked guardrail or a flagged check as something to look at", () => {
    const s = agentScores([ev("guardrail", { id: "G9", outcome: "blocked" }, "coordinator"), ev("check_result", { check: "coverage", outcome: "flagged" }, "coordinator")], ["coordinator"])[0];
    expect(s).toMatchObject({ blocked: 1, flagged: 1 });
    expect(scoreVerdict(s).tone).toBe("warn");
  });
});

describe("the live feed beside the thread", () => {
  const events = [
    msg("coordinator", "pm", "단계 S3 구체화: 요구사항 후보를 만들어라. 필드는 id, 제목"),
    ev("check_result", { check: "coverage", outcome: "flagged", details: ["REQ-14가 아직 미결 상태입니다"] }, "coordinator"),
    ev("message_rerouted", { from: "qa", to: "client", via: "coordinator" }, "qa"),
    ev("pipeline", { status: "running" }),
    ev("guardrail", { id: "G3", outcome: "masked", detail: "Liner 응답의 민감 정보를 가린 뒤 기록" }, "qa"),
  ];

  it("keeps messages and the checks on them, drops plumbing events", () => {
    expect(teamFeed(events, label, "team").map((f) => f.kind)).toEqual(["message", "check", "reroute", "guard"]);
  });

  it("shows the whole instruction to the team, one plain line to the client", () => {
    expect(teamFeed(events, label, "team")[0].text).toContain("필드는 id");
    expect(teamFeed(events, label, "client")[0].text).toBe("구체화 작업 지시");
  });

  it("marks a flagged check as a warning and a passed one as fine", () => {
    const feed = teamFeed([...events, ev("check_result", { check: "answer_consistency", outcome: "passed" }, "coordinator")], label, "team");
    expect(feed[1]).toMatchObject({ tone: "warn" });
    expect(feed[feed.length - 1]).toMatchObject({ kind: "check", tone: "ok" });
  });
});

describe("the ontology graph and the who-to-whom chart", () => {
  const events = [msg("coordinator", "pm", "a"), msg("pm", "coordinator", "b"), msg("pm", "qa", "c"), msg("client", "coordinator", "d")];

  it("counts messages per relation in both directions", () => {
    const counts = pairCounts(exchanges(events));
    expect(counts.get(pairKey("pm", "coordinator"))).toBe(2);
    expect(counts.get(pairKey("coordinator", "pm"))).toBe(2);
    expect(counts.get(pairKey("qa", "pm"))).toBe(1);
  });

  it("builds a sender × receiver matrix whose cells add up to every message", () => {
    const m = talkMatrix(exchanges(events), ["coordinator", "pm", "qa", "client"]);
    expect(m.cells[m.ids.indexOf("pm")][m.ids.indexOf("qa")]).toBe(1);
    expect(m.cells.flat().reduce((a, b) => a + b, 0)).toBe(4);
    expect(m.max).toBe(1);
  });

  it("names a relation by its first phrase", () => {
    expect(relationName("작업 배정, 결과 취합, 결정 기록")).toBe("작업 배정");
    expect(relationName("PRD → 화면설계서, 화면에서 나온 빈칸")).toBe("PRD → 화면설계서");
  });
});

describe("the X-View style scatter of Liner calls", () => {
  it("turns each timed Liner call into a dot: who, which API, how long, failed or not", () => {
    const events = [
      ev("liner_chat", { duration_ms: 1200, schema: "requirements" }, "pm"),
      ev("liner_search", { duration_ms: 500, error: "timeout" }, "researcher"),
      ev("liner_chat", {}, "qa"),
      ev("agent_message", { from: "pm", to: "qa", content: "x" }, "pm"),
    ];
    expect(linerCalls(events).map((c) => [c.actor, c.kind, c.ms, c.failed])).toEqual([
      ["pm", "모델", 1200, false],
      ["researcher", "검색", 500, true],
    ]);
  });
});
