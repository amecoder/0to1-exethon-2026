import { describe, expect, it } from "vitest";
import { codeMeaning, refAnchor, refCatalog } from "./refCatalog";
import { nameIds, namedParts } from "./summarize";

const SOURCE = {
  requirements: [{ id: "REQ-01", title: "자동결제", statement: "매주 카드로 결제한다", status: "확정",
    acceptance: { given: "구독 고객이", when: "결제일이 되면", then: "결제된다" } }],
  screens: [{ id: "SCR-01", title: "구독 신청", purpose: "사이즈를 고른다" }],
  tests: [{ id: "TC-01", title: "신청 완료", objective: "신청하면 구독이 생긴다", requirement_refs: ["REQ-01"] }],
  decisions: [{ id: "DEC-01", topic: "요일은?", chosen: "토요일", status: "확정", superseded_by: "CHG-01" }],
  sources: [{ id: "SRC-01", text: "토요일에 보내 주세요." }],
  evidence: [{ id: "EV-01", title: "결제 관행", fact: "3일 안에 재시도", url: "https://example.com" }],
};

describe("refCatalog", () => {
  it("says what each ID is and which document lists it", () => {
    const refs = refCatalog(SOURCE);
    expect(refs["REQ-01"]).toMatchObject({ kind: "요구사항", title: "자동결제", doc: "prd" });
    expect(refs["REQ-01"].lines).toContainEqual({ label: "확인 기준", value: "구독 고객이 → 결제일이 되면 → 결제된다" });
    expect(refs["SCR-01"]).toMatchObject({ kind: "화면", doc: "screens" });
    expect(refs["TC-01"].lines).toContainEqual({ label: "요구사항", value: "REQ-01" });
    expect(refs["DEC-01"].lines).toContainEqual({ label: "상태", value: "확정 (나중에 CHG-01로 바뀜)" });
    expect(refs["SRC-01"]).toMatchObject({ kind: "발주사 원문", title: "토요일에 보내 주세요.", doc: null });
    expect(refs["EV-01"].lines.map((l) => l.label)).toEqual(["사실", "링크"]); // empty quote left out
    expect(refCatalog(null)["CP5"]).toMatchObject({ kind: "변경 체크포인트", title: "바꿀 때마다 1번" });
  });
  it("explains every process code and records confirmations", () => {
    const refs = refCatalog({ confirmations: [{ id: "CF-01", cp: "CP1", approved: false, who: "발주사", reason: "범위 더" }] });
    for (const code of ["CP1", "CP2", "CP3", "CP4", "CP5", "S1", "S7", "G1", "G8"]) expect(refs[code]?.lines[0].value).toBeTruthy();
    expect(refs["CF-01"]).toMatchObject({ kind: "확인 기록", title: "CP1 반려" });
  });
  it("gives each listed row a stable anchor", () => {
    expect(refAnchor("prd", "REQ-01")).toBe("ref-prd-REQ-01");
  });
});

describe("namedParts (client view links)", () => {
  it("names known IDs as link parts and drops unknown ones like nameIds", () => {
    const titles = { "REQ-01": "자동결제" };
    const text = "REQ-01 을 확인한다 (SRC-09)";
    const parts = namedParts(text, titles);
    expect(parts).toEqual([{ text: "「자동결제」", id: "REQ-01" }, { text: "을 확인한다" }]);
    expect(parts.map((p) => p.text).join("")).toBe(nameIds(text, titles));
  });
  it("leaves no bare separators where unknown IDs were dropped", () => {
    const parts = namedParts("SRC-02, SRC-03, REQ-01", { "REQ-01": "자동결제" });
    expect(parts).toEqual([{ text: "「자동결제」", id: "REQ-01" }]);
  });
});

describe("codeMeaning", () => {
  it("explains every code family a reader meets, and nothing else", () => {
    expect(codeMeaning("SRC-05")?.kind).toBe("발주사 원문");
    expect(codeMeaning("SRC-05")?.about).toContain("한 문장씩");
    expect(codeMeaning("CF-01")?.kind).toBe("확인 기록");
    expect(codeMeaning("CP5")?.kind).toBe("확인 단계");
    expect(codeMeaning("S3")?.kind).toBe("작업 단계");
    expect(codeMeaning("G7")?.kind).toBe("안전장치");
    for (const id of ["REQ-1", "SCR-1", "TC-1", "EV-1", "DEC-1", "Q-1", "OPEN-1", "FND-1", "PROTO-1", "CHG-1", "CMP-1", "ANS-1", "ALT-1"]) {
      expect(codeMeaning(id), id).not.toBeNull();
    }
    expect(codeMeaning("v1")).toBeNull();
    expect(codeMeaning("ABC-1")).toBeNull();
  });
});

describe("우리 시스템 목록", () => {
  it("names each listed system and explains SYS codes", () => {
    const refs = refCatalog({ systems: [{ id: "SYS-01", name: "주문관리 시스템", about: "주문 상태를 갖고 있어요" }] });
    expect(refs["SYS-01"]).toMatchObject({ kind: "우리 시스템", title: "주문관리 시스템", doc: null });
    expect(refs["SYS-01"].lines).toEqual([{ label: "하는 일", value: "주문 상태를 갖고 있어요" }]);
    expect(codeMeaning("SYS-02")?.kind).toBe("우리 시스템");
  });
});

describe("운영 확인 항목", () => {
  it("lists OPS items from the test plan in the test case document", () => {
    const refs = refCatalog({ test_plan: [{ ops_checks: [{ id: "OPS-01", title: "CS 문의 절반", how: "4주 뒤 집계", requirement_refs: ["REQ-10"] }] }] });
    expect(refs["OPS-01"]).toMatchObject({ kind: "운영 확인 항목", title: "CS 문의 절반", doc: "tests" });
    expect(codeMeaning("OPS-03")?.kind).toBe("운영 확인 항목");
  });
});
