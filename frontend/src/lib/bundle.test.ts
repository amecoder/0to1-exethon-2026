import { describe, expect, it } from "vitest";
import { bundleContents, prototypeLabel } from "./bundle";

describe("prototypeLabel", () => {
  it("names the prototype by its form (older prototypes without a form are phone apps)", () => {
    expect(prototypeLabel("app")).toBe("앱 프로토타입");
    expect(prototypeLabel("web")).toBe("웹 프로토타입");
    expect(prototypeLabel(undefined)).toBe("앱 프로토타입");
  });
});

describe("bundleContents", () => {
  it("lists every file the zip carries, with the prototype named by its form", () => {
    const texts = bundleContents("app", true).map((c) => c.text);
    expect(texts[0]).toContain("앱 프로토타입");
    expect(texts.some((t) => t.includes("AGENTS.md"))).toBe(true);
    expect(texts.some((t) => t.includes("제안요약.md"))).toBe(true);
    expect(texts.some((t) => t.includes("역할별 흐름도"))).toBe(true);
  });

  it("leaves out the role flow chart when the designer drew none", () => {
    expect(bundleContents("web", false).some((c) => c.kind === "lanes")).toBe(false);
  });
});
