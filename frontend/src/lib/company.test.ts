import { describe, expect, it } from "vitest";
import { answeredByLabel, chooseCompany, clientQuestion, listFilter, noteCount, systemsKey, systemsToPrefill } from "./company";
import { stripIds } from "./summarize";

const list = [
  { id: "default", name: "기본 회사", created_at: "2026-11-01", projects: 3 },
  { id: "c2", name: "꽃집 체인", created_at: "2026-11-20", projects: 1 },
];

describe("chooseCompany", () => {
  it("keeps the company this browser chose last", () => {
    expect(chooseCompany(list, "c2")).toBe("c2");
  });
  it("falls back to the first company when the remembered one is gone or unset", () => {
    expect(chooseCompany(list, "deleted")).toBe("default");
    expect(chooseCompany(list, null)).toBe("default");
  });
  it("has nothing to choose before the list arrives", () => {
    expect(chooseCompany([], "c2")).toBeNull();
  });
});

describe("systemsToPrefill", () => {
  it("prefers the company's own systems list", () => {
    expect(systemsToPrefill("꽃집 POS", "예전 목록")).toBe("꽃집 POS");
  });
  it("uses what this browser remembered when the company has none", () => {
    expect(systemsToPrefill("  \n", "예전 목록")).toBe("예전 목록");
  });
});

describe("noteCount", () => {
  it("counts one note per line like the server, skipping blanks and # headings", () => {
    expect(noteCount("# 용어\n- 회원 등급은 3단계다\n\n정기구독은 월 단위다")).toBe(2);
  });
});

describe("systemsKey", () => {
  it("keeps each company's remembered systems list apart", () => {
    expect(systemsKey("c2")).toBe("our-systems:c2");
    expect(systemsKey("c2")).not.toBe(systemsKey("default"));
  });
  it("uses the old browser-wide key only without a company", () => {
    expect(systemsKey(undefined)).toBe("our-systems");
  });
});

describe("systemsToPrefill after the user typed", () => {
  it("never replaces what the user already wrote", () => {
    expect(systemsToPrefill("꽃집 POS", "예전 목록", "내가 쓴 목록")).toBe("내가 쓴 목록");
  });
});

describe("answeredByLabel", () => {
  it("marks an answer the company material settled, with the item it came from", () => {
    expect(answeredByLabel({ answered_by: "company", company_ref: "CMP-03" })).toBe("회사 자료로 정함 · CMP-03");
  });
  it("adds nothing to the client's own answers", () => {
    expect(answeredByLabel({ answered_by: "client" })).toBeNull();
    expect(answeredByLabel({})).toBeNull();
  });
});

describe("listFilter", () => {
  it("lists the chosen company's projects while the company workspace is on", () => {
    expect(listFilter(true, "c2")).toBe("c2");
  });
  it("lists every project when the workspace is switched off (EXETHON_COMPANY=off)", () => {
    expect(listFilter(false, "c2")).toBeUndefined();
  });
  it("waits for a company while on", () => {
    expect(listFilter(true, null)).toBeNull();
  });
});

describe("company rows in the client view (11-21 browser check)", () => {
  it("names the company item only in the team view", () => {
    expect(answeredByLabel({ answered_by: "company", company_ref: "CMP-03" }, false)).toBe("회사 자료로 정함");
  });

  it("hides a question that is an internal finding note, strips ids from answers", () => {
    const note = "SRC-07은 언제든 멈추라고 하지만 REQ-09는 마감 규칙 때문에 부딪힌다.";
    expect(clientQuestion(note)).toBeNull();
    expect(clientQuestion("배송 요일은 어떻게 할까요?")).toBe("배송 요일은 어떻게 할까요?");
    expect(stripIds("동의가 없으면 일시정지 (CMP-08)")).toBe("동의가 없으면 일시정지");
    expect(stripIds("다시 시도한다(동의가 없으면 일시정지 — CMP-08).")).toBe("다시 시도한다(동의가 없으면 일시정지).");
    expect(stripIds("FND-03 과 SYS-01/REQ-02 는 같다")).not.toMatch(/FND-|SYS-|REQ-/);
  });
});
