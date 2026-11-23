import { describe, expect, it } from "vitest";
import type { AppEvent, Pipeline } from "../api";
import { activityLine, buildThread, compactProgress, questionPosition } from "./model";

const NAMES: Record<string, string> = {
  coordinator: "조율자", fde_lead: "FDE 리드", researcher: "리서처", pm: "PM·기획자", qa: "QA", client: "발주사",
};
const label = (id: string) => NAMES[id] ?? id;

let seq = 0;
function ev(type: string, data: Record<string, unknown>, actor = "system", stage: string | null = null): AppEvent {
  seq += 1;
  return { seq, ts: "2026-11-15T00:00:00Z", stage, type, actor, data };
}

function pipe(stage: string, status: Pipeline["status"], active: string | null = null): Pipeline {
  return { stage, status, active_agent: active, error: null };
}

// S2 (problem) → CP1 approved → S3 (questions) → one answer, like the scripted flower run.
function flowerEvents(): AppEvent[] {
  return [
    ev("stage_started", { stage: "S1" }, "system", "S1"),
    ev("item_written", { kind: "sources", item: { id: "SRC-01" } }, "system", "S1"),
    ev("stage_completed", { stage: "S1" }, "system", "S1"),
    ev("pipeline", { stage: "S2", status: "running" }, "system", "S2"),
    ev("stage_started", { stage: "S2" }, "system", "S2"),
    ev("agent_message", { from: "coordinator", to: "fde_lead", content: "단계 S2 문제 인식: 정리하라" }, "coordinator", "S2"),
    ev("liner_chat", { schema: "problem_scope", model: "m" }, "fde_lead", "S2"),
    ev("agent_message", { from: "fde_lead", to: "researcher", content: "근거 요청: 결제 실패" }, "fde_lead", "S2"),
    ev("liner_search", { query: "결제 실패", result_count: 1 }, "researcher", "S2"),
    ev("item_written", { kind: "evidence", item: { id: "EV-01" } }, "researcher", "S2"),
    ev("stage_completed", { stage: "S2" }, "system", "S2"),
    ev("confirmation", { cp: "CP1", approved: true }, "client", "CP1"),
    ev("stage_started", { stage: "S3" }, "system", "S3"),
    ev("item_written", { kind: "findings", item: { id: "FND-01" } }, "qa", "S3"),
    ev("item_written", { kind: "findings", item: { id: "FND-02" } }, "qa", "S3"),
    ev("item_written", { kind: "questions", item: { id: "Q-01" } }, "coordinator", "S3"),
    ev("item_written", { kind: "questions", item: { id: "Q-02" } }, "coordinator", "S3"),
    ev("stage_completed", { stage: "S3" }, "system", "S3"),
    ev("question_answered", { question_id: "Q-01", value: null, status: "가정" }, "client", "S3"),
  ];
}

const QUESTIONS = [
  { id: "Q-01", question: "고객이 요일을 고르나요?" },
  { id: "Q-02", question: "결제가 실패하면 어떻게 할까요?" },
];

describe("buildThread", () => {
  it("says a step stopped when the run failed in it, and finished otherwise", () => {
    const started = flowerEvents().slice(0, 9);
    const [failed] = buildThread(started, QUESTIONS, label, "client", pipe("S2", "failed"));
    if (failed.kind !== "step") throw new Error("expected a step");
    expect(failed.title).toBe("팀이 문제와 범위를 정리하다가 멈췄어요");
    const [running] = buildThread(started, QUESTIONS, label, "client", pipe("S2", "running", "fde_lead"));
    if (running.kind !== "step") throw new Error("expected a step");
    expect(running.title).toBe("팀이 문제와 범위를 정리하고 있어요");
  });

  it("turns the event log into steps, the client's confirmation and the client's answer, in order", () => {
    const items = buildThread(flowerEvents(), QUESTIONS, label, "client", pipe("S3", "awaiting_answers"));
    expect(items.map((i) => i.kind)).toEqual(["step", "confirm", "step", "answer"]);
  });

  it("names a finished step in plain 해요체 and credits the Liner search", () => {
    const [problem] = buildThread(flowerEvents(), QUESTIONS, label, "client", pipe("S3", "awaiting_answers"));
    if (problem.kind !== "step") throw new Error("expected a step");
    expect(problem.state).toBe("done");
    expect(problem.title).toBe("팀이 문제와 범위를 정리했어요");
    expect(problem.highlight).toBe("리서처가 Liner로 근거를 찾았어요 · 1건");
    expect(problem.agents).toEqual(["coordinator", "fde_lead", "researcher"]);
  });

  it("counts what a step produced", () => {
    const items = buildThread(flowerEvents(), QUESTIONS, label, "client", pipe("S3", "awaiting_answers"));
    const questions = items[2];
    if (questions.kind !== "step") throw new Error("expected a step");
    expect(questions.facts).toEqual(["짚은 점 2건", "질문 2장"]);
  });

  it("counts an item once even when it is written again (an answer rewrites its question)", () => {
    const base = flowerEvents();
    const events = [
      ...base.slice(0, -1),
      ev("item_written", { kind: "questions", item: { id: "Q-01", status: "확정" } }, "coordinator", "S3"),
      base[base.length - 1],
    ];
    const step = buildThread(events, QUESTIONS, label, "client", pipe("S3", "awaiting_answers"))[2];
    if (step.kind !== "step") throw new Error("expected a step");
    expect(step.facts).toEqual(["짚은 점 2건", "질문 2장"]);
  });

  it("hides stage bookkeeping from the client but shows it to the team", () => {
    const client = buildThread(flowerEvents(), QUESTIONS, label, "client", pipe("S3", "awaiting_answers"))[0];
    const team = buildThread(flowerEvents(), QUESTIONS, label, "team", pipe("S3", "awaiting_answers"))[0];
    if (client.kind !== "step" || team.kind !== "step") throw new Error("expected steps");
    expect(client.entries.some((e) => e.text.includes("시작"))).toBe(false);
    expect(team.entries.some((e) => e.text.includes("시작"))).toBe(true);
  });

  it("marks the step being worked on as active with an -ing title", () => {
    const events = flowerEvents().slice(0, 9);
    const items = buildThread(events, QUESTIONS, label, "client", pipe("S2", "running", "researcher"));
    const last = items[items.length - 1];
    if (last.kind !== "step") throw new Error("expected a step");
    expect(last.state).toBe("active");
    expect(last.title).toBe("팀이 문제와 범위를 정리하고 있어요");
  });

  it("writes the confirmation and the answer in the client's voice", () => {
    const items = buildThread(flowerEvents(), QUESTIONS, label, "client", pipe("S3", "awaiting_answers"));
    expect(items[1]).toMatchObject({ kind: "confirm", text: "문제와 범위를 승인했어요" });
    expect(items[3]).toMatchObject({ kind: "answer", question: "고객이 요일을 고르나요?", answer: "잘 모르겠어요", assumed: true });
  });

  it("starts a new group when a stage runs again after a rejection", () => {
    const events = [
      ...flowerEvents().slice(0, 11),
      ev("confirmation", { cp: "CP1", approved: false, reason: "범위가 넓어요" }, "client", "CP1"),
      ev("stage_started", { stage: "S2" }, "system", "S2"),
    ];
    const items = buildThread(events, QUESTIONS, label, "client", pipe("S2", "running"));
    expect(items.map((i) => i.kind)).toEqual(["step", "confirm", "step"]);
    expect(items[1]).toMatchObject({ text: "문제와 범위를 반려했어요 — 범위가 넓어요" });
  });
});

describe("activityLine", () => {
  it("says who is doing what, politely", () => {
    const a = activityLine(pipe("S2", "running", "researcher"), [], label);
    expect(a).toEqual({ agent: "researcher", text: "리서처가 Liner로 근거를 검색하고 있어요" });
  });

  it("handles a verb that is not a noun + 하다", () => {
    expect(activityLine(pipe("S6", "running", "designer"), [], (id) => (id === "designer" ? "디자이너" : id)).text).toBe(
      "디자이너가 화면을 넘겨주고 있어요",
    );
  });

  it("falls back to the team when nobody is active", () => {
    expect(activityLine(pipe("S3", "running"), [], label)).toEqual({ agent: null, text: "팀이 다음 할 일을 준비하고 있어요" });
  });
});

describe("compactProgress", () => {
  it("reports the step number out of nine and the confirmations left", () => {
    expect(compactProgress("S3", "awaiting_answers")).toEqual({ step: 4, total: 9, label: "질문·답", remaining: 3, done: false });
  });

  it("is done after the last confirmation", () => {
    expect(compactProgress("CP4", "completed")).toMatchObject({ step: 9, done: true, remaining: 0 });
  });
});

describe("questionPosition", () => {
  it("counts the current card among all cards", () => {
    expect(questionPosition(2, 2)).toEqual({ index: 1, total: 2 });
    expect(questionPosition(2, 1)).toEqual({ index: 2, total: 2 });
  });
});
