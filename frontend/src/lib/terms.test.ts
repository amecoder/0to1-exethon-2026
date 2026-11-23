import { describe, expect, it } from "vitest";
import { findTerm } from "./terms";

// 11-22 user decision: the screen uses the technical word; a dotted underline opens its plain explanation.
describe("findTerm", () => {
  it("finds the screen's technical words with a plain explanation", () => {
    for (const name of ["인수 조건", "성공 기준", "체크포인트"]) {
      const t = findTerm(name);
      expect(t?.plain, name).toBeTruthy();
      expect(t?.example, name).toBeTruthy();
    }
  });
  it("also finds a term by another spelling", () => {
    expect(findTerm("완료 기준")?.term).toBe("인수 조건");
    expect(findTerm("CP")?.term).toBe("체크포인트");
  });
  it("is undefined for a word the glossary does not have", () => {
    expect(findTerm("없는 말")).toBeUndefined();
  });
});
