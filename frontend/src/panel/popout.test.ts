import { describe, expect, it } from "vitest";
import { popoutUrl, readDemoStep, readPopout } from "./popout";

describe("artifact pop-out window address", () => {
  it("round-trips the project, tab, document and view", () => {
    const url = popoutUrl("abc123", { tab: "docs", doc: "prd" }, "team");
    expect(url.startsWith("/?")).toBe(true);
    expect(readPopout(url.slice(1))).toEqual({ id: "abc123", target: { tab: "docs", doc: "prd" }, view: "team" });
  });

  it("keeps a non-document tab without a document", () => {
    const url = popoutUrl("p1", { tab: "prototype" }, "client");
    expect(readPopout(url.slice(1))).toEqual({ id: "p1", target: { tab: "prototype" }, view: "client" });
  });

  it("is null for the normal app address", () => {
    expect(readPopout("")).toBeNull();
    expect(readPopout("?foo=1")).toBeNull();
  });

  it("falls back to safe defaults for unknown tab, document or view", () => {
    expect(readPopout("?artifact=p1&tab=evil&doc=nope&view=admin")).toEqual({ id: "p1", target: { tab: "docs" }, view: "client" });
  });

  it("carries the replay step for the demo window, and only a whole non-negative number", () => {
    const url = popoutUrl("demo", { tab: "team" }, "team", 42);
    expect(readPopout(url.slice(1))).toEqual({ id: "demo", target: { tab: "team" }, view: "team", step: 42 });
    expect(readPopout("?artifact=demo&step=-3")?.step).toBeUndefined();
    expect(readPopout("?artifact=demo&step=abc")?.step).toBeUndefined();
  });

  it("accepts only well-formed step messages from the demo player", () => {
    expect(readDemoStep({ type: "0to1:demo-step", step: 7 })).toBe(7);
    expect(readDemoStep({ type: "0to1:demo-step", step: "7" })).toBeNull();
    expect(readDemoStep({ type: "other", step: 7 })).toBeNull();
    expect(readDemoStep(null)).toBeNull();
  });
});
