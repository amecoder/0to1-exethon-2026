import { describe, expect, it } from "vitest";
import type { AppEvent } from "../api";
import { formatUsd, spentUsd } from "./credits";
import { progressOf, STEPS, withObject, withSubject } from "./labels";
import { extractScenes, nextSceneStep, prevSceneStep, sceneAt } from "./scenes";
import { briefMessage, currentActivity, latestMessage, nameIds, plainAcceptance, stripIds, summarizeEvent } from "./summarize";

const NAMES: Record<string, string> = { coordinator: "조율자", fde_lead: "FDE 리드", researcher: "리서처", pm: "PM·기획자", client: "발주사" };
const label = (id: string) => NAMES[id] ?? id;

let seq = 0;
function ev(type: string, data: Record<string, unknown>, actor = "system", stage: string | null = null): AppEvent {
  seq += 1;
  return { seq, ts: "2026-11-15T00:00:00Z", stage, type, actor, data };
}

describe("progressOf", () => {
  it("marks the current step and counts the confirmations still ahead", () => {
    const p = progressOf("S3", "running");
    expect(STEPS[p.current].key).toBe("questions");
    expect(p.states.slice(0, 4)).toEqual(["done", "done", "done", "current"]);
    expect(p.remainingConfirmations).toBe(3);
  });

  it("counts the confirmation being asked now", () => {
    expect(progressOf("CP4", "awaiting_confirmation").remainingConfirmations).toBe(1);
  });

  it("has nothing left once completed", () => {
    const p = progressOf("CP4", "completed");
    expect(p.remainingConfirmations).toBe(0);
    expect(p.states.every((s) => s === "done")).toBe(true);
  });

  it("starts at input when there is no pipeline yet", () => {
    expect(progressOf(undefined, undefined).current).toBe(0);
  });
});

describe("Korean particles", () => {
  it("picks 이/가 and 을/를 by the final consonant", () => {
    expect(withSubject("조율자")).toBe("조율자가");
    expect(withSubject("디자인팀")).toBe("디자인팀이");
    expect(withSubject("QA")).toBe("QA가");
    expect(withObject("프로토타입")).toBe("프로토타입을");
    expect(withObject("화면설계서")).toBe("화면설계서를");
  });
});

describe("summarizeEvent", () => {
  it("summarizes an intake triage round with the missing slots", () => {
    expect(summarizeEvent(ev("intake_triage", { case: "insufficient", missing: ["pain", "done"], by: "model" }), label, "client").text).toBe(
      "접수 확인: 정보가 모자라 되물음 (무엇이 불편한지 · 무엇이 되면 끝인지)",
    );
    expect(summarizeEvent(ev("intake_triage", { case: "garbled", missing: [], by: "code" }), label, "client").text).toBe(
      "접수 확인: 읽을 수 없는 글이라 다시 써 달라고 함 · 코드 사전 검사",
    );
  });

  it("shortens a coordinator assignment to its task name", () => {
    const e = ev("agent_message", {
      from: "coordinator", to: "fde_lead",
      content: "단계 S2 문제 인식: 발주사 원문(sources)만 근거로 문제 진술(누가 who, …)을 정리하라.",
    });
    expect(summarizeEvent(e, label, "client").text).toBe("조율자 → FDE 리드: 문제 인식 작업 지시");
  });

  it("tells what a Liner image generation made, or that it failed", () => {
    const ok = ev("liner_image", { slot: "hero", model: "qwen/qwen-image-2.1-turbo", error: null }, "developer");
    expect(summarizeEvent(ok, label, "client").text).toBe("Liner 이미지 생성으로 프로토타입 사진 1장 만듦");
    const bad = ev("liner_image", { slot: "hero", error: "실패" }, "developer");
    expect(summarizeEvent(bad, label, "client").text).toBe("Liner 이미지 생성 실패 — 사진 자리는 그림으로 둠");
  });

  it("never shows raw English event or schema names", () => {
    const chat = ev("liner_chat", { schema: "problem_scope", model: "fake-model" }, "fde_lead");
    expect(summarizeEvent(chat, label, "client").text).toBe("Liner 모델로 문제와 범위를 정리");
    expect(summarizeEvent(chat, label, "team").text).toContain("fake-model");
    const unknown = ev("something_new", {});
    expect(summarizeEvent(unknown, label, "team").text).toBe("기타 활동");
  });

  it("translates guardrail ids and outcomes, keeping the id only for the team", () => {
    const g = ev("guardrail", { id: "G1", outcome: "flagged", detail: "인용문이 원문에 없습니다" });
    expect(summarizeEvent(g, label, "client").text).toBe("사실 확인 표시: 인용문이 원문에 없습니다");
    expect(summarizeEvent(g, label, "team").text).toBe("사실 확인 G1 표시: 인용문이 원문에 없습니다");
  });

  it("hides question ids from the client", () => {
    const a = ev("question_answered", { question_id: "Q-01", value: "수·토 중 고름", status: "확정" }, "client");
    expect(summarizeEvent(a, label, "client").text).toBe("발주사 답: “수·토 중 고름”");
    expect(summarizeEvent(a, label, "team").text).toContain("Q-01");
  });

  it("names confirmations by their stage title", () => {
    const c = ev("confirmation", { cp: "CP2", approved: true, version: "v1" }, "client");
    expect(summarizeEvent(c, label, "client").text).toBe("요구사항 원본 확인 승인");
  });
});

describe("text helpers", () => {
  it("strips internal ids", () => {
    expect(stripIds("화면은 SCR-01 구독 신청 → SCR-02 결제 안내 순서로 이어집니다.")).toBe(
      "화면은 구독 신청 → 결제 안내 순서로 이어집니다.",
    );
    expect(stripIds("배송 요일 (SRC-04, SRC-15) 선택")).toBe("배송 요일 선택");
  });

  it("turns Given/When/Then into one sentence", () => {
    expect(plainAcceptance({ given: "구독 고객이", when: "요일을 고르면", then: "저장된다" })).toBe(
      "구독 고객이 요일을 고르면 저장된다",
    );
  });

  it("keeps short free messages", () => {
    expect(briefMessage("출처 1건 저장")).toBe("출처 1건 저장");
  });
});

describe("activity", () => {
  it("describes the working agent from the pipeline", () => {
    const pipeline = { stage: "S2", status: "running" as const, active_agent: "researcher", error: null };
    expect(currentActivity(pipeline, [], label).sentence).toBe("지금 리서처가 Liner로 근거를 검색 중");
  });

  it("falls back to the latest handoff", () => {
    const events = [ev("agent_message", { from: "coordinator", to: "pm", content: "x" })];
    const pipeline = { stage: "S3", status: "running" as const, active_agent: null, error: null };
    expect(currentActivity(pipeline, events, label).sentence).toBe("조율자가 PM·기획자를 부르는 중");
    expect(latestMessage(events)).toMatchObject({ from: "coordinator", to: "pm", rerouted: false });
  });
});

describe("extractScenes", () => {
  seq = 0;
  const events = [
    ev("stage_started", { stage: "S1" }),
    ev("stage_started", { stage: "S2" }),
    ev("pipeline", { stage: "CP1", status: "awaiting_confirmation" }),
    ev("confirmation", { cp: "CP1", approved: true }),
    ev("pipeline", { stage: "S3", status: "awaiting_confirmation" }), // transient state while advancing
    ev("pipeline", { stage: "S3", status: "awaiting_answers" }),
    ev("question_answered", { question_id: "Q-01" }),
    ev("agent_message", { from: "client", to: "coordinator", content: "답" }),
    ev("question_answered", { question_id: "Q-02" }),
    ev("pipeline", { stage: "S4", status: "running" }),
    ev("pipeline", { stage: "CP2", status: "awaiting_confirmation" }),
    ev("stage_completed", { stage: "S5" }),
    ev("pipeline", { stage: "CP3", status: "awaiting_confirmation" }),
    ev("prototype_built", { origin: "agent", attempts: 1, missing_screens: [] }),
    ev("pipeline", { stage: "CP4", status: "awaiting_confirmation" }),
    ev("pipeline", { stage: "CP4", status: "completed" }),
  ];
  const scenes = extractScenes(events);

  it("finds every key moment in order, one per question card", () => {
    expect(scenes.map((s) => s.kind)).toEqual([
      "input", "team", "CP1", "question", "question", "CP2", "documents", "CP3", "prototype", "CP4", "done",
    ]);
    expect(scenes.filter((s) => s.kind === "question").map((s) => s.step)).toEqual([6, 7]);
    expect(scenes.every((s) => s.caption.length > 0)).toBe(true);
  });

  it("moves between scenes", () => {
    expect(sceneAt(scenes, 8)?.label).toBe("질문 2");
    expect(nextSceneStep(scenes, 7)).toBe(11);
    expect(prevSceneStep(scenes, 7)).toBe(6);
    expect(prevSceneStep(scenes, 1)).toBeNull();
    expect(nextSceneStep(scenes, 99)).toBeNull();
  });
});

describe("nameIds", () => {
  it("names known items and drops unknown ids for the client", () => {
    const titles = { "REQ-02": "자동결제" };
    expect(nameIds("REQ-02 를 확인할 테스트 케이스가 없습니다", titles)).toBe("「자동결제」를 확인할 테스트 케이스가 없습니다");
    expect(nameIds("SCR-09 화면이 없습니다", titles)).toBe("화면이 없습니다");
  });
});

describe("Liner features in the activity log", () => {
  it("names the model that answered behind a router, for the team only", () => {
    const chat = ev("liner_chat", {
      schema: "screen_spec", model: "liner-claude-router", answered_model: "claude-sonnet-5.5", routing_strategy: "quality",
    }, "designer");
    expect(summarizeEvent(chat, label, "team").text).toBe(
      "Liner 모델로 화면설계서를 작성 · 답한 모델 claude-sonnet-5.5 (liner-claude-router · quality)",
    );
    expect(summarizeEvent(chat, label, "client").text).toBe("Liner 모델로 화면설계서를 작성");
  });

  it("tells AI search, its web fallback, decisions and credits apart", () => {
    const failed = ev("liner_search", { api: "ai_search", query: "꽃", error: "503", fallback: true }, "researcher");
    expect(summarizeEvent(failed, label, "client").text).toBe("Liner AI 검색 실패 “꽃” → 웹 검색으로 바꿈");
    const ok = ev("liner_search", { api: "ai_search", query: "꽃", result_count: 8 }, "researcher");
    expect(summarizeEvent(ok, label, "client").text).toBe("Liner AI 검색 “꽃” → 8건");
    const decide = ev("liner_decision", { purpose: "complaint" }, "qa");
    expect(summarizeEvent(decide, label, "client").text).toContain("합의 위반인지 새 요청인지");
    const credits = ev("credits", { point: "after S2", balance_usd: 199.99, spent_usd: 0.0123 });
    expect(summarizeEvent(credits, label, "client").text).toBe("크레딧 잔액 확인 · 지금까지 $0.0123");
  });
});

describe("spentUsd", () => {
  it("is the first balance minus the latest, ignoring failed reads", () => {
    const events = [
      ev("credits", { balance_usd: 200 }),
      ev("credits", { balance_usd: null, error: "x" }),
      ev("liner_chat", {}),
      ev("credits", { balance_usd: 199.9875 }),
    ];
    expect(spentUsd(events)).toBeCloseTo(0.0125, 6);
    expect(spentUsd([ev("liner_chat", {})])).toBeNull();
    expect(formatUsd(0.0125)).toBe("$0.0125");
    expect(formatUsd(3.5)).toBe("$3.50");
  });
});


describe("run_interrupted wording (Fable review M5, 11-21)", () => {
  const label = (id: string) => id;
  it("says a crash, not a restart, when the event carries one", () => {
    expect(summarizeEvent(ev("run_interrupted", { stage: "S2", crash: "KeyError" }), label, "client").text).toBe(
      "예상하지 못한 오류로 문제 인식 작업이 멈춤",
    );
    expect(summarizeEvent(ev("run_interrupted", { stage: "S2" }), label, "client").text).toBe("서버가 다시 시작되어 문제 인식 작업이 멈춤");
  });
});
