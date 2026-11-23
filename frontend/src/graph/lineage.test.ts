import { describe, expect, it } from "vitest";
import type { AppEvent } from "../api";
import {
  buildLineage,
  COLUMNS,
  describePath,
  fixedText,
  highlightOf,
  layoutLineage,
  nodeName,
  pathsOf,
  traceOf,
} from "./lineage";

const NAMES: Record<string, string> = { client: "발주사", pm: "PM", designer: "디자이너", qa: "QA", researcher: "리서처", coordinator: "조율자", developer: "개발자" };
const label = (id: string) => NAMES[id] ?? id;

let seq = 0;
function ev(type: string, actor: string, data: Record<string, unknown>, stage = "S5"): AppEvent {
  seq += 1;
  return { seq, ts: `2026-11-16T00:00:${String(seq).padStart(2, "0")}Z`, stage, type, actor, data };
}
const wrote = (actor: string, kind: string, id: string, stage: string) => ev("item_written", actor, { kind, item: { id } }, stage);

const SOURCE = {
  sources: [
    { id: "SRC-01", text: "고객이 일주일에 한 번 꽃을 받는 거예요" },
    { id: "SRC-02", text: "토요일에 한꺼번에 보내면 편해요" },
    { id: "SRC-03", text: "결제는 매주 자동으로요", origin: "audio" },
    { id: "SRC-04", text: "안녕하세요" },
  ],
  evidence: [{ id: "EV-01", title: "구독 결제 실패 처리", fact: "3일 안에 재시도한다", quote: "3일 안에" }],
  questions: [
    { id: "Q-01", source_refs: ["SRC-01", "SRC-02"], evidence_refs: [] },
    { id: "Q-02", source_refs: ["SRC-03"], evidence_refs: ["EV-01"] },
  ],
  decisions: [
    { id: "DEC-01", question_id: "Q-01", topic: "배송 요일", chosen: "수·토 중 고름", status: "확정", answered_by: "client" },
    { id: "DEC-02", question_id: "Q-02", topic: "결제 실패", chosen: "3일 안에 다시 결제", status: "가정" },
  ],
  requirements: [
    { id: "REQ-01", title: "배송 요일", statement: "수·토 중 고른다", source_refs: ["SRC-01"], evidence_refs: [], decision_refs: ["DEC-01"], depends_on: [], screens: ["SCR-01"], tests: [] },
    { id: "REQ-02", title: "자동결제", statement: "실패하면 3일 안에", source_refs: ["SRC-03"], evidence_refs: ["EV-01"], decision_refs: ["DEC-02"], depends_on: ["REQ-01", "REQ-99"], owner_agent: "pm" },
  ],
  screens: [
    { id: "SCR-01", title: "구독 신청", elements: [{ requirement_refs: ["REQ-01"] }] },
    { id: "SCR-02", title: "결제 안내", requirement_refs: ["REQ-02"] },
  ],
  flow_chart: [{ id: "FLOW-01", description: "사용자 흐름", based_on: ["SCR-01", "SCR-02"] }],
  tests: [
    { id: "TC-01", title: "요일 고르고 신청", requirement_refs: ["REQ-01"], screen_refs: ["SCR-01"] },
    { id: "TC-02", title: "결제 실패", requirement_refs: ["REQ-02"], screen_refs: ["SCR-02"] },
  ],
  prototype: [{ id: "PROTO-01", html: "<html></html>" }],
  changes: [
    { id: "CHG-01", utterance: "일시정지는 하루 전까지", status: "approved", target: "REQ-01", title: "배송 요일", summary: "REQ-01 진술을 고친다", impact: { requirements: ["REQ-01", "REQ-02"], screens: ["SCR-01"], tests: ["TC-01"] } },
  ],
  complaints: [{ id: "CMP-01", text: "일요일엔 왜 안 돼요?", status: "classified", requirement_ids: ["REQ-01"] }],
};

const EVENTS: AppEvent[] = [
  wrote("system", "sources", "SRC-01", "S1"),
  wrote("researcher", "evidence", "EV-01", "S2"),
  wrote("coordinator", "decisions", "DEC-01", "S3"),
  wrote("pm", "requirements", "REQ-01", "S4"),
  wrote("pm", "requirements", "REQ-02", "S4"),
  ev("version_created", "system", { version: "v1" }, "CP2"),
  wrote("designer", "screens", "SCR-01", "S5"),
  wrote("designer", "screens", "SCR-02", "S5"),
  wrote("designer", "flow_chart", "FLOW-01", "S5"),
  wrote("qa", "tests", "TC-01", "S5"),
  wrote("qa", "tests", "TC-02", "S5"),
  ev("version_created", "system", { version: "v2" }, "CP3"),
  wrote("developer", "prototype", "PROTO-01", "S6"),
  wrote("coordinator", "changes", "CHG-01", "CP4"),
  wrote("pm", "requirements", "REQ-01", "CP4"),
  ev("version_created", "system", { version: "v3" }, "CP4"),
  wrote("coordinator", "complaints", "CMP-01", "CP4"),
];

const lin = buildLineage(SOURCE, EVENTS);
const node = (id: string) => lin.nodes.find((n) => n.id === id)!;
const edge = (from: string, to: string) => lin.edges.find((e) => e.from === from && e.to === to);

describe("buildLineage", () => {
  it("puts each kind in its flow-order lane, with changes and complaints in the change band", () => {
    expect(COLUMNS.map((c) => c.key)).toEqual(["SRC", "EV", "DEC", "REQ", "SCR", "TC", "PROTO"]);
    expect(node("SRC-01").col).toBe("SRC");
    expect(node("EV-01").col).toBe("EV");
    expect(node("DEC-01").col).toBe("DEC");
    expect(node("FLOW-01").col).toBe("SCR");
    expect(node("PROTO-01").col).toBe("PROTO");
    expect(node("CHG-01").band).toBe("change");
    expect(node("CMP-01").band).toBe("change");
    expect(node("REQ-01").band).toBe("main");
  });

  it("links upstream → downstream along every source-link field and drops unknown ids", () => {
    for (const [a, b] of [
      ["SRC-01", "REQ-01"], ["DEC-01", "REQ-01"], ["EV-01", "REQ-02"], ["REQ-01", "REQ-02"],
      ["REQ-01", "SCR-01"], ["REQ-02", "SCR-02"], ["SCR-01", "TC-01"], ["REQ-02", "TC-02"],
      ["SRC-02", "DEC-01"], ["EV-01", "DEC-02"], ["SCR-01", "FLOW-01"], ["SCR-02", "PROTO-01"],
    ]) {
      expect(edge(a, b), `${a} → ${b}`).toBeDefined();
    }
    expect(lin.edges.some((e) => e.from === "REQ-99" || e.to === "REQ-99")).toBe(false);
    expect(edge("CHG-01", "REQ-01")?.kind).toBe("change");
    expect(edge("REQ-01", "CMP-01")?.kind).toBe("complaint");
    expect(node("CHG-01").detail).not.toMatch(/REQ-\d/); // the client view shows this sentence as is
  });

  it("names the agent that turned each input into its output", () => {
    expect(edge("SRC-01", "REQ-01")?.agent).toBe("pm");
    expect(edge("REQ-01", "SCR-01")?.agent).toBe("designer");
    expect(edge("SCR-01", "TC-01")?.agent).toBe("qa");
    expect(edge("SRC-02", "DEC-01")?.agent).toBe("client"); // the client chose the answer
    expect(edge("CHG-01", "REQ-01")?.agent).toBe("pm");
    expect(edge("REQ-01", "CMP-01")?.agent).toBe("qa");
    expect(node("SRC-01").author).toBe("client");
    expect(node("REQ-02").author).toBe("pm"); // owner_agent when no event
  });

  it("records the stages each item was written in and the versions that fixed it", () => {
    expect(node("REQ-01").stages).toEqual(["S4", "CP4"]);
    expect(node("REQ-01").fixed).toEqual({ first: "v1", last: "v3" });
    expect(node("SCR-01").fixed).toEqual({ first: "v2", last: "v2" });
    expect(node("CMP-01").fixed).toEqual({ first: null, last: null });
    expect(fixedText(node("REQ-01"))).toBe("v1에 처음 고정 · 지금은 v3");
    expect(fixedText({ ...node("CHG-01"), fixed: { first: "v3", last: null } })).toBe("v3에 처음 고정 · 마지막 기록은 아직 고정 전");
  });

  it("tags voice transcripts and assumed answers", () => {
    expect(node("SRC-03").tags).toContain("음성");
    expect(node("DEC-02").tags).toContain("가정");
    expect(node("DEC-01").tags).not.toContain("가정");
  });

  it("tags sentences read from attached images and documents", () => {
    const graph = buildLineage({ sources: [
      { id: "SRC-01", text: "신청하기 버튼", origin: "image" },
      { id: "SRC-02", text: "배송 지역은 서울", origin: "document" },
    ] }, []);
    const tags = (id: string) => graph.nodes.find((n) => n.id === id)?.tags;
    expect(tags("SRC-01")).toContain("이미지");
    expect(tags("SRC-02")).toContain("문서");
  });

  it("is empty for an empty source", () => {
    expect(buildLineage({}, [])).toEqual({ nodes: [], edges: [] });
  });
});

describe("traceOf", () => {
  it("follows a requirement up to where it came from and down to what depends on it", () => {
    const t = traceOf(lin, "REQ-02");
    expect([...t.up].sort()).toEqual(["CHG-01", "DEC-01", "DEC-02", "EV-01", "REQ-01", "SRC-01", "SRC-02", "SRC-03"].sort());
    expect([...t.down].sort()).toEqual(["PROTO-01", "FLOW-01", "SCR-02", "TC-02"].sort());
    expect(t.up.has("SCR-01")).toBe(false); // a sibling branch is neither
    expect(t.edges.has("REQ-01>REQ-02")).toBe(true);
  });

  it("shows where a change request propagated", () => {
    const t = traceOf(lin, "CHG-01");
    expect([...t.down]).toEqual(expect.arrayContaining(["REQ-01", "REQ-02", "SCR-01", "SCR-02", "TC-01", "TC-02", "PROTO-01"]));
  });

  it("is empty for an unknown node", () => {
    const t = traceOf(lin, "nope");
    expect(t.up.size + t.down.size + t.edges.size).toBe(0);
  });
});

describe("highlightOf", () => {
  it("lights the given items and the links between them", () => {
    const h = highlightOf(lin, ["REQ-01", "SCR-01", "TC-01", "NOPE-1"]);
    expect([...h.down].sort()).toEqual(["REQ-01", "SCR-01", "TC-01"]);
    expect(h.edges.has("REQ-01>SCR-01") && h.edges.has("SCR-01>TC-01")).toBe(true);
    expect(h.edges.has("SRC-01>REQ-01")).toBe(false);
  });
});

describe("paths in words", () => {
  it("lists every way into and out of a node", () => {
    const up = pathsOf(lin, "SCR-02", "up");
    expect(up).toContainEqual(["SRC-03", "REQ-02", "SCR-02"]);
    expect(up).toContainEqual(["SRC-01", "REQ-01", "REQ-02", "SCR-02"]);
    const down = pathsOf(lin, "REQ-02", "down");
    expect(down).toContainEqual(["REQ-02", "SCR-02", "TC-02"]);
    expect(pathsOf(lin, "REQ-02", "up", 2)).toHaveLength(2);
  });

  it("writes a path with the agent that did each step, by id for the team and by name for the client", () => {
    const team = (id: string) => nodeName(node(id), "team");
    expect(describePath(lin, ["SRC-03", "REQ-02", "SCR-02", "TC-02"], team, label)).toBe(
      "SRC-03 → (PM) → REQ-02 → (디자이너) → SCR-02 → (QA) → TC-02",
    );
    const client = (id: string) => nodeName(node(id), "client");
    expect(describePath(lin, ["EV-01", "REQ-02"], client, label)).toBe("구독 결제 실패 처리 → (PM) → 자동결제");
  });
});

describe("layoutLineage", () => {
  const layout = layoutLineage(lin);

  it("places lanes left to right in flow order and hides empty lanes", () => {
    const xs = layout.columns.map((c) => c.x);
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
    expect(layout.columns.map((c) => c.key)).toEqual(["SRC", "EV", "DEC", "REQ", "SCR", "TC", "PROTO"]);
    const small = layoutLineage(buildLineage({ sources: SOURCE.sources, requirements: [SOURCE.requirements[0]] }, []));
    expect(small.columns.map((c) => c.key)).toEqual(["SRC", "REQ"]);
  });

  it("makes every main-band link point rightward or stay in its lane", () => {
    for (const e of lin.edges) {
      const a = layout.pos.get(e.from);
      const b = layout.pos.get(e.to);
      if (!a || !b || node(e.from).band !== "main" || node(e.to).band !== "main") continue;
      expect(b.x, `${e.from} → ${e.to}`).toBeGreaterThanOrEqual(a.x);
    }
  });

  it("keeps memo lines with no links out of the way unless asked", () => {
    expect(layout.loose).toEqual(["SRC-04"]);
    expect(layout.pos.has("SRC-04")).toBe(false);
    expect(layoutLineage(lin, { showLoose: true }).pos.has("SRC-04")).toBe(true);
  });

  it("puts the change band below the lanes and the producing agents between lanes", () => {
    const lowest = Math.max(...lin.nodes.filter((n) => n.band === "main" && layout.pos.has(n.id)).map((n) => layout.pos.get(n.id)!.y));
    expect(layout.pos.get("CHG-01")!.y).toBeGreaterThan(lowest);
    const reqCol = layout.columns.find((c) => c.key === "REQ")!;
    const pmChip = layout.chips.find((c) => c.agent === "pm")!;
    expect(pmChip.x).toBeLessThan(reqCol.x);
    expect(layout.chips.find((c) => c.agent === "designer")).toBeDefined();
    expect(layout.chips.find((c) => c.agent === "researcher")).toBeDefined(); // evidence has no inputs, still has a maker
  });

  it("is deterministic", () => {
    expect(layoutLineage(lin)).toEqual(layout);
  });
});
