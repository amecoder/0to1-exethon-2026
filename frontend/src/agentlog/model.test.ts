import { describe, expect, it } from "vitest";
import type { AppEvent } from "../api";
import { agentLog, filterLog, LOG_KIND_KO, type LogEntry } from "./model";

const NAMES: Record<string, string> = { client: "발주사", pm: "PM", designer: "디자이너", qa: "QA", researcher: "리서처", coordinator: "조율자", developer: "개발자", consumer: "소비자" };
const label = (id: string) => NAMES[id] ?? id;
const TITLES = { "REQ-01": "배송 요일", "REQ-02": "자동결제", "SCR-01": "구독 신청" };

let seq = 0;
function ev(type: string, actor: string, data: Record<string, unknown>, stage: string): AppEvent {
  seq += 1;
  return { seq, ts: `2026-11-16T00:00:${String(seq).padStart(2, "0")}Z`, stage, type, actor, data };
}
const msg = (from: string, to: string, content: string, stage: string, extra: Record<string, unknown> = {}) =>
  ev("agent_message", from, { from, to, content, ...extra }, stage);

const CHANGE = {
  id: "CHG-01", utterance: "일시정지는 하루 전까지", status: "awaiting_cp5", target: "REQ-01", title: "배송 요일",
  summary: "REQ-01 진술을 고친다", rationale: "배송 일정 이야기라 배송 요일 요구사항",
  impact: { requirements: ["REQ-01", "REQ-02"], screens: ["SCR-01"], tests: [] },
  candidates: [{ id: "REQ-01", title: "배송 요일", score: 0.81 }, { id: "REQ-02", title: "자동결제", score: 0.12 }],
};
const COMPLAINT = {
  id: "CMP-01", text: "일요일엔 왜 안 돼요?", status: "classified", classification: "합의 위반", model_classification: "새 변경 요청",
  requirement_ids: ["REQ-01"], reason: "확정된 요일에 일요일이 없습니다",
  guard: { applied: true, detail: "요청 값이 확정 문장에 있어 합의 위반" },
  decision: { label: "새 변경 요청", probabilities: { violation: 0.3, new_change: 0.7 }, confidence: 0.55, threshold: 0.6 },
  needs_human: false,
};

const EVENTS: AppEvent[] = [
  ev("stage_started", "system", { stage: "S3" }, "S3"),
  msg("coordinator", "pm", "단계 S3 구체화: 요구사항 후보를 만들어라", "S3"),
  ev("liner_chat", "pm", { api: "model", model: "liner-claude-router", answered_model: "claude-sonnet-5.5", schema: "requirement_candidates", cost: 0.0021, duration_ms: 4200, routing_strategy: "balanced" }, "S3"),
  ev("item_written", "pm", { kind: "requirements", item: { id: "REQ-01", title: "배송 요일" } }, "S3"),
  ev("write_rejected", "pm", { kind: "sources", reason: "pm 에게 sources 쓰기 권한이 없습니다" }, "S3"),
  msg("pm", "qa", "요구사항 후보 2건 검토 요청", "S3"),
  ev("message_rerouted", "pm", { from: "pm", to: "developer", via: "coordinator", reason: "관계선 없음 → 조율자 경유" }, "S3"),
  msg("pm", "coordinator", "REQ-02 를 개발자에게", "S3", { relay: "developer" }),
  msg("coordinator", "developer", "REQ-02 를 개발자에게", "S3", { relay: "pm" }),
  ev("stage_started", "system", { stage: "S5" }, "S5"),
  ev("check_result", "coordinator", { check: "coverage", outcome: "flagged", items: ["coverage.no_tc:REQ-02"], details: ["REQ-02 를 확인할 테스트 케이스가 없습니다"] }, "S5"),
  ev("guardrail", "developer", { id: "G6", outcome: "stripped", detail: "외부 자원 제거", code: "external_link" }, "S6"),
  ev("prototype_built", "developer", { origin: "template", attempts: 2, failures: ["외부 요청"], missing_screens: [] }, "S6"),
  ev("item_written", "consumer", { kind: "feedback", item: { id: "FB-01", screen_id: "SCR-01", kind: "불편", comment: "카드 번호가 귀찮아요" } }, "S5"),
  msg("coordinator", "pm", "변경 요청: 일시정지는 하루 전까지", "CP4"),
  ev("liner_rerank", "pm", { api: "rerank", query: "일시정지는 하루 전까지", documents: 2, results: [], model: "cohere/rerank-5-fast", cost: 6.6e-7, duration_ms: 310, error: null }, "CP4"),
  ev("item_written", "coordinator", { kind: "changes", item: CHANGE }, "CP4"),
  msg("pm", "coordinator", "REQ-01 를 바꾸는 요청입니다", "CP4"),
  ev("liner_decision", "qa", { api: "decisions", purpose: "complaint", answers: { kind: { choice: "new_change", confidence: 0.55, probabilities: { violation: 0.3, new_change: 0.7 } } }, model: "typesafe/jev-1.13", cost: 1.7e-5, duration_ms: 900, error: null }, "CP4"),
  ev("check_result", "coordinator", { check: "complaint_guard", outcome: "flagged", items: ["REQ-01"], details: ["요청 값이 확정 문장에 있어 합의 위반"] }, "CP4"),
  ev("item_written", "coordinator", { kind: "complaints", item: COMPLAINT }, "CP4"),
];

const SOURCE = {
  questions: [{ id: "Q-01" }, { id: "Q-02" }],
  decisions: [{ id: "DEC-01", question_id: "Q-01" }],
  requirements: [{ id: "REQ-01", status: "확정" }, { id: "REQ-02", status: "가정" }],
  changes: [CHANGE],
  complaints: [COMPLAINT],
};

const all = (groups: { entries: LogEntry[] }[]) => groups.flatMap((g) => g.entries);

describe("agentLog", () => {
  it("groups an agent's entries by stage in time order with messages in and out", () => {
    const log = agentLog(EVENTS, SOURCE, "pm", label, "team", TITLES);
    expect(log.groups.map((g) => g.stage)).toEqual(["S3", "CP4"]);
    const entries = all(log.groups);
    expect(entries.map((e) => e.seq)).toEqual([...entries.map((e) => e.seq)].sort((a, b) => a - b));
    const received = entries.find((e) => e.kind === "message" && e.direction === "in")!;
    expect(received.title).toContain("조율자");
    expect(entries.find((e) => e.kind === "message" && e.direction === "out")!.title).toContain("QA");
  });

  it("shows each Liner call's endpoint, answering model, duration and cost", () => {
    const entries = all(agentLog(EVENTS, SOURCE, "pm", label, "team", TITLES).groups).filter((e) => e.kind === "liner");
    expect(entries).toHaveLength(2);
    const chat = entries[0];
    expect(chat.title).toContain("Liner 모델");
    expect(chat.lines.join(" ")).toMatch(/claude-sonnet-5\.5/);
    expect(chat.lines.join(" ")).toMatch(/4\.2초/);
    expect(chat.lines.join(" ")).toMatch(/\$0\.0021/);
    expect(entries[1].title).toContain("재정렬");
  });

  it("lists written items with a link to the lineage, and rejected writes", () => {
    const entries = all(agentLog(EVENTS, SOURCE, "pm", label, "team", TITLES).groups);
    expect(entries.find((e) => e.kind === "write")!.itemId).toBe("REQ-01");
    expect(entries.find((e) => e.kind === "guard")!.title).toContain("쓰기 권한");
  });

  it("explains the PM's change decision with rationale, rerank candidates and impact", () => {
    const decision = all(agentLog(EVENTS, SOURCE, "pm", label, "team", TITLES).groups).find((e) => e.kind === "decision")!;
    expect(decision.title).toContain("REQ-01");
    const text = decision.lines.join("\n");
    expect(text).toContain("배송 일정 이야기라 배송 요일 요구사항");
    expect(text).toContain("0.81");
    expect(text).toMatch(/요구사항 2.*화면 1/);
    expect(decision.itemId).toBe("REQ-01");
  });

  it("explains QA's complaint call with probabilities, confidence and the code-guard override", () => {
    const entries = all(agentLog(EVENTS, SOURCE, "qa", label, "team", TITLES).groups);
    const decision = entries.find((e) => e.kind === "decision")!;
    const text = [decision.title, ...decision.lines].join("\n");
    expect(text).toContain("합의 위반");
    expect(text).toContain("확정된 요일에 일요일이 없습니다");
    expect(text).toMatch(/새 변경 요청 70%/);
    expect(text).toMatch(/확신도 55%/);
    expect(text).toContain("코드 가드");
    expect(entries.some((e) => e.kind === "liner" && e.title.includes("판정"))).toBe(true);
  });

  it("records retries, guardrails on an agent's output and the consumer's grade", () => {
    const dev = all(agentLog(EVENTS, SOURCE, "developer", label, "team", TITLES).groups);
    expect(dev.some((e) => e.kind === "guard" && e.title.includes("생성 코드 격리"))).toBe(true);
    expect(dev.find((e) => e.kind === "decision")!.title).toMatch(/시도 2회/);
    const consumer = all(agentLog(EVENTS, SOURCE, "consumer", label, "team", TITLES).groups);
    expect(consumer[0].lines.join(" ")).toContain("불편");
  });

  it("gives the coordinator a summary: handoffs per counterpart, reroutes, stages and what is pending", () => {
    const log = agentLog(EVENTS, SOURCE, "coordinator", label, "team", TITLES);
    expect(log.summary).not.toBeNull();
    const pm = log.summary!.handoffs.find((h) => h.agent === "pm")!;
    expect(pm).toEqual({ agent: "pm", sent: 2, received: 2 });
    expect(log.summary!.reroutes).toBe(1);
    expect(log.summary!.stages).toEqual(["S3", "S5"]);
    expect(log.summary!.pending).toEqual(expect.arrayContaining([
      { label: "답을 기다리는 질문", count: 1 },
      { label: "가정으로 채운 요구사항", count: 1 },
      { label: "결정을 기다리는 변경 요청", count: 1 },
    ]));
    const entries = all(log.groups);
    expect(entries.some((e) => e.kind === "decision" && e.title.includes("중계"))).toBe(true);
    expect(entries.some((e) => e.kind === "decision" && e.title.includes("빈칸 검사"))).toBe(true);
    expect(agentLog(EVENTS, SOURCE, "pm", label, "team", TITLES).summary).toBeNull();
  });

  it("hides raw ids and English event names in the client view", () => {
    const log = agentLog(EVENTS, SOURCE, "pm", label, "client", TITLES);
    const text = all(log.groups).map((e) => [e.title, ...e.lines].join(" ")).join("\n");
    expect(text).not.toMatch(/\b(REQ|SCR|TC|CHG|CMP)-\d+/);
    expect(text).not.toMatch(/liner_chat|item_written|agent_message|awaiting_cp5|requirement_candidates/);
    expect(text).toContain("배송 요일");
    // long task instructions shrink to one plain line for the client; the team sees them in full
    expect(text).toContain("구체화 작업 지시");
    expect(text).not.toContain("요구사항 후보를 만들어라");
    const team = all(agentLog(EVENTS, SOURCE, "pm", label, "team", TITLES).groups).map((e) => e.lines.join(" ")).join("\n");
    expect(team).toContain("요구사항 후보를 만들어라");
  });
});

describe("filterLog", () => {
  const log = agentLog(EVENTS, SOURCE, "pm", label, "team", TITLES);
  it("keeps only chosen kinds and drops empty stages", () => {
    const only = filterLog(log.groups, new Set(["liner"]), "");
    expect(all(only).every((e) => e.kind === "liner")).toBe(true);
    expect(only.every((g) => g.entries.length > 0)).toBe(true);
  });
  it("searches titles and lines", () => {
    expect(all(filterLog(log.groups, new Set(Object.keys(LOG_KIND_KO) as never), "검토 요청"))).toHaveLength(1);
  });
});
