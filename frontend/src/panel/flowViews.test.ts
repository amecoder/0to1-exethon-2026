import { describe, expect, it } from "vitest";
import type { FlowChart, Swimlane } from "../api";
import { flowViews, shownView } from "./flowViews";

const lanes: Swimlane = {
  lanes: ["고객", "앱"],
  steps: [{ id: "a", lane: "고객", label: "신청", screen_ref: "", after: [], kind: "normal", note: "" }],
};
const flow: FlowChart = { id: "FLOW-01", html: "<p></p>", description: "", based_on: [], violations: [] };

describe("flowViews", () => {
  it("puts the role swimlane first when it exists", () => {
    expect(flowViews(lanes, flow)).toEqual(["lanes", "liner"]);
    expect(shownView(flowViews(lanes, flow), null)).toBe("lanes");
  });
  it("behaves as before without a swimlane", () => {
    expect(flowViews(undefined, flow)).toEqual(["liner"]);
    expect(flowViews({ lanes: ["고객"], steps: [] }, flow)).toEqual(["liner"]);
    expect(flowViews(undefined, undefined)).toEqual([]);
    expect(shownView([], null)).toBeNull();
  });
  it("keeps the picked view while it exists", () => {
    expect(shownView(["lanes", "liner"], "liner")).toBe("liner");
    expect(shownView(["liner"], "lanes")).toBe("liner");
  });
});
