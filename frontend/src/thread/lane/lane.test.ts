import { describe, expect, it } from "vitest";
import type { ChangeItem, ComplaintItem, SharedSourceData } from "../../api";
import { buildLineage, highlightOf } from "../../graph/lineage";
import { diffWords, sides } from "../../lib/diff";
import { convertible, impactCount, laneBusy, laneEntries, laneSignature, layeredRequirements, pendingChange, recheckView } from "./model";

function change(id: string, status: ChangeItem["status"], at: string, extra: Partial<ChangeItem> = {}): ChangeItem {
  return { id, utterance: "바꿔 주세요", status, created_at: at, based_on: "v2", complaint_ref: null, ...extra };
}
function complaint(id: string, status: ComplaintItem["status"], at: string, extra: Partial<ComplaintItem> = {}): ComplaintItem {
  return { id, text: "이거 아닌데요", status, created_at: at, against: "v2", ...extra };
}
function source(changes: ChangeItem[], complaints: ComplaintItem[]): SharedSourceData {
  return { meta: {}, sources: [], evidence: [], requirements: [], questions: [], problem_statement: [], scope: [], open_items: [], events: [], changes, complaints };
}

describe("diffWords", () => {
  it("marks removed and added words and keeps the rest", () => {
    const parts = diffWords("일시정지는 주문 마감 전까지 된다", "일시정지는 배송 하루 전까지 된다");
    expect(parts.filter((p) => p.kind === "del").map((p) => p.text.trim())).toEqual(["주문 마감"]);
    expect(parts.filter((p) => p.kind === "add").map((p) => p.text.trim())).toEqual(["배송 하루"]);
    const { before, after } = sides(parts);
    expect(before.map((p) => p.text).join("")).toBe("일시정지는 주문 마감 전까지 된다");
    expect(after.map((p) => p.text).join("")).toBe("일시정지는 배송 하루 전까지 된다");
  });

  it("handles an empty side", () => {
    expect(diffWords("", "새 문장")).toEqual([{ text: "새 문장", kind: "add" }]);
    expect(diffWords("같다", "같다")).toEqual([{ text: "같다", kind: "same" }]);
  });
});

describe("lane model", () => {
  it("orders changes and complaints by time and tracks busy / pending", () => {
    const entries = laneEntries(source([change("CHG-01", "approved", "2026-11-16T01:00:00Z"), change("CHG-02", "mapping", "2026-11-16T03:00:00Z")],
      [complaint("CMP-01", "classified", "2026-11-16T02:00:00Z")]));
    expect(entries.map((e) => e.item.id)).toEqual(["CHG-01", "CMP-01", "CHG-02"]);
    expect(laneBusy(entries)).toBe(true);
    expect(pendingChange(entries)?.id).toBe("CHG-02");
    expect(laneSignature(entries)).toBe("CHG-01:approved|CMP-01:classified|CHG-02:mapping");
  });

  it("offers converting a new-change complaint once", () => {
    const item = complaint("CMP-01", "classified", "a", { classification: "새 변경 요청" });
    expect(convertible(item, laneEntries(source([], [item])))).toBe(true);
    const done = laneEntries(source([change("CHG-01", "mapping", "b", { complaint_ref: "CMP-01" })], [item]));
    expect(convertible(item, done)).toBe(false);
    expect(convertible({ ...item, classification: "합의 위반" }, [])).toBe(false);
  });

  it("counts impacted ids", () => {
    expect(impactCount({ requirements: ["REQ-06"], screens: ["SCR-02"], tests: ["TC-08", "TC-09"] })).toBe(4);
    expect(impactCount(undefined)).toBe(0);
  });
});

describe("highlightOf", () => {
  it("lights the impacted items and the links among them only", () => {
    const src = {
      requirements: [
        { id: "REQ-01", title: "a", statement: "", depends_on: [], screens: ["SCR-01"], tests: ["TC-01"] },
        { id: "REQ-02", title: "b", statement: "", depends_on: ["REQ-01"], screens: ["SCR-02"], tests: [] },
        { id: "REQ-03", title: "c", statement: "", depends_on: [], screens: [], tests: ["TC-03"] },
      ],
      screens: [{ id: "SCR-01", title: "s1", owner_agent: "designer" }, { id: "SCR-02", title: "s2" }],
      tests: [{ id: "TC-01", title: "t1" }, { id: "TC-03", title: "t3" }],
    };
    const graph = buildLineage(src, []);
    const lit = highlightOf(graph, ["REQ-01", "REQ-02", "SCR-01", "SCR-02", "TC-01", "TC-404"]);
    expect([...lit.down].sort()).toEqual(["REQ-01", "REQ-02", "SCR-01", "SCR-02", "TC-01"]);
    expect(lit.edges.has("REQ-01>REQ-02")).toBe(true);
    expect([...lit.edges].some((k) => k.includes("REQ-03") || k.includes("TC-03"))).toBe(false);
  });
});

describe("recheckView (download locked after a CP5 change)", () => {
  const recheck = { change_id: "CHG-01", version: "v3", stage: "S5", kinds: ["documents", "screens", "tests", "prototype"], items: ["REQ-01"] };

  it("says why download is locked and what comes next at each step", () => {
    const at = (stage: string, status: string) => recheckView(recheck, { stage, status });
    expect(at("S5", "running").title).toContain("CHG-01");
    expect(at("S5", "running").title).toContain("v3");
    expect(at("S5", "running").next).toContain("문서");
    expect(at("CP3", "awaiting_confirmation").next).toContain("확인 3");
    expect(at("S6", "running").next).toContain("프로토타입");
    expect(at("CP4", "awaiting_confirmation").next).toContain("확인 4");
    expect(at("S5", "failed").next).toContain("다시 시도");
    expect(at("S5", "running").redo).toEqual(["문서 4종", "화면설계", "테스트 케이스", "프로토타입"]);
  });
});

describe("layeredRequirements", () => {
  it("puts the target first, then direct dependents, then the transitive tail", () => {
    const impact = { requirements: ["REQ-01", "REQ-03", "REQ-05", "REQ-12"], screens: [], tests: [] };
    const rows = layeredRequirements({ target: "REQ-03", direct: ["REQ-03", "REQ-05"], impact });
    expect(rows).toEqual([
      { id: "REQ-03", layer: "target" },
      { id: "REQ-05", layer: "direct" },
      { id: "REQ-01", layer: "transitive" },
      { id: "REQ-12", layer: "transitive" },
    ]);
  });

  it("treats every non-target as direct when an older item has no direct list", () => {
    const impact = { requirements: ["REQ-01", "REQ-02"], screens: [], tests: [] };
    expect(layeredRequirements({ target: "REQ-01", impact }).map((r) => r.layer)).toEqual(["target", "direct"]);
  });
});
