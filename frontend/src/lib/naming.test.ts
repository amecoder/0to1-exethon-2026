import { describe, expect, it } from "vitest";
import { NAME_MAX, cleanName } from "./naming";

describe("cleanName", () => {
  it("matches the server: no list separators, one line, at most 40", () => {
    expect(cleanName(" 꽃님:  정기구독 — 앱 ")).toBe("꽃님 정기구독-앱");
    expect(cleanName("가".repeat(100))).toHaveLength(NAME_MAX);
    expect(cleanName(" : ")).toBe("");
  });
});
