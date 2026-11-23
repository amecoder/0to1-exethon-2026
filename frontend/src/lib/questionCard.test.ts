import { describe, expect, it } from "vitest";
import { acceptsFreeText, quoteOption } from "./questionCard";

describe("question card helpers", () => {
  it("hides free text only when the card refuses it", () => {
    expect(acceptsFreeText({ allow_free_text: false })).toBe(false);
    expect(acceptsFreeText({ allow_free_text: true })).toBe(true);
    expect(acceptsFreeText({})).toBe(true); // older cards have no flag: free text as before
  });

  it("does not wrap an option that already carries 「」 in another pair", () => {
    expect(quoteOption("매주 토요일")).toBe("「매주 토요일」");
    expect(quoteOption("「꽃님 정기구독 1차」 안에 넣는다")).toBe("‘「꽃님 정기구독 1차」 안에 넣는다’");
  });
});
