import { describe, expect, it } from "vitest";
import { addAnswers, answersChunk, canRecheck, keepsVerdict, missingSlots, withAnswersChunk } from "./intake";

describe("answersChunk", () => {
  it("writes one line per answer under its slot name, leaving the question (and its examples) out", () => {
    const chunk = answersChunk([
      { slot: "who", question: "누가 쓰나요?", answer: "꽃집 단골 고객" },
      { slot: "pain", question: "무엇이 불편한가요?", answer: "  " },
      { slot: "done", question: "무엇이 되면 끝인가요?", answer: " 앱으로 신청받으면 " },
    ]);
    expect(chunk).toBe("접수 대화에서 받은 답:\n- 누가 쓰는지: 꽃집 단골 고객\n- 무엇이 되면 끝인지: 앱으로 신청받으면");
  });

  it("is null when nothing was answered", () => {
    expect(answersChunk([])).toBeNull();
    expect(answersChunk([{ slot: "who", question: "누가?", answer: "" }])).toBeNull();
  });

  it("is appended as one more chunk only when there is one", () => {
    expect(withAnswersChunk(["메모", " "], [])).toEqual(["메모"]);
    expect(withAnswersChunk(["메모"], [{ slot: "who", question: "누가?", answer: "사장" }])).toEqual(["메모", "접수 대화에서 받은 답:\n- 누가 쓰는지: 사장"]);
  });
});

describe("missingSlots", () => {
  it("lists the empty slots in who · pain · done order", () => {
    expect(missingSlots({ who: "고객", pain: " ", done: "" })).toEqual(["pain", "done"]);
    expect(missingSlots({ who: "고객", pain: "불편", done: "끝" })).toEqual([]);
  });
});

describe("addAnswers / canRecheck", () => {
  const questions = [
    { slot: "pain" as const, question: "무엇이 불편한가요?" },
    { slot: "done" as const, question: "무엇이 되면 끝인가요?" },
  ];

  it("keeps earlier answers and adds this round's drafts", () => {
    const earlier = [{ slot: "who" as const, question: "누가?", answer: "사장" }];
    const next = addAnswers(earlier, questions, { pain: " 전화 주문 누락 ", done: "앱 신청" });
    expect(next).toEqual([
      { slot: "who", question: "누가?", answer: "사장" },
      { slot: "pain", question: "무엇이 불편한가요?", answer: "전화 주문 누락" },
      { slot: "done", question: "무엇이 되면 끝인가요?", answer: "앱 신청" },
    ]);
    expect(earlier).toHaveLength(1);
  });

  it("needs an answer for every question asked this round", () => {
    expect(canRecheck(questions, { pain: "전화 주문 누락" })).toBe(false);
    expect(canRecheck(questions, { pain: "전화 주문 누락", done: "  " })).toBe(false);
    expect(canRecheck(questions, { pain: "전화 주문 누락", done: "앱 신청" })).toBe(true);
    expect(canRecheck([], {})).toBe(false);
  });
});

describe("keepsVerdict (11-22: a refusal card stayed on screen into the next memo)", () => {
  const verdict = (c: "ok" | "cannot" | "garbled" | "insufficient") =>
    ({ blocked: false, case: c, reason: "", slots: { who: "", pain: "", done: "" }, questions: [] }) as const;
  it("drops a refusal or unreadable verdict once the memo changes or is sent again", () => {
    expect(keepsVerdict(verdict("cannot"))).toBe(false);
    expect(keepsVerdict(verdict("garbled"))).toBe(false);
  });
  it("keeps the questions of a thin request, which the client is answering", () => {
    expect(keepsVerdict(verdict("insufficient"))).toBe(true);
    expect(keepsVerdict(null)).toBe(false);
  });
});
