import { describe, expect, it } from "vitest";
import { droppedFeatures } from "./scope";

const screens = [
  { id: "SCR-01", title: "홈", purpose: "", requirement_refs: ["REQ-01", "REQ-02"] },
  { id: "SCR-02", title: "구독 신청", purpose: "", requirement_refs: ["REQ-02", "REQ-03"] },
  { id: "SCR-03", title: "사장용 배송 목록", purpose: "", requirement_refs: ["REQ-04"] },
];

describe("droppedFeatures (11-22: say at once what loses its screen)", () => {
  it("lists the requirements only the unchosen screens show", () => {
    expect(droppedFeatures(screens, ["SCR-01"])).toEqual(["REQ-03", "REQ-04"]);
  });

  it("is empty when every screen stays", () => {
    expect(droppedFeatures(screens, ["SCR-01", "SCR-02", "SCR-03"])).toEqual([]);
  });
});
