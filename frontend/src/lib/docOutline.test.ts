import { describe, expect, it } from "vitest";
import type { DocView } from "../api";
import { docMeta, formatDate, markedItems, sectionAnchor, splitIds, statusColumn, tocOf } from "./docOutline";

const approvals = [
  { id: "CF-02", cp: "CP2", who: "발주사", at: "2026-11-15T09:00:00+00:00", version: "v1" },
  { id: "CF-03", cp: "CP3", who: "발주사", at: "2026-11-16T12:16:14+00:00", version: "v2" },
];

function doc(over: Partial<DocView> = {}): DocView {
  return {
    id: "prd",
    title: "PRD — 무엇을 만드나",
    header: { owner_agent: "pm", owner_name: "PM·기획자", version: "v2", approvals },
    summary: [],
    sections: [
      { id: "totals", title: "1. 요구사항 총괄표", blocks: [{ type: "table", columns: ["상태", "개수"], rows: [["가정", "1"]] }] },
      {
        id: "requirements",
        title: "2. 요구사항 상세 표",
        blocks: [
          {
            type: "table",
            columns: ["ID", "이름", "상태"],
            rows: [["REQ-01", "배송 요일", "확정"], ["REQ-02", "자동결제", "가정"], ["REQ-03", "쿠폰", "미결"]],
          },
        ],
      },
    ],
    warnings: [],
    ...over,
  };
}

describe("docMeta", () => {
  it("reads version, the approval that froze it and its date", () => {
    expect(docMeta(doc())).toEqual({ version: "v2", draft: false, approval: { cp: "CP3", who: "발주사", version: "v2" }, date: "2026. 11. 16." });
  });

  it("has no approval when the latest one froze an older version, and knows a draft", () => {
    const d = doc({ header: { owner_agent: "pm", owner_name: "PM", version: "작업본(미고정)", approvals: [] } });
    expect(docMeta(d)).toMatchObject({ draft: true, approval: null, date: null });
    expect(docMeta(doc({ header: { ...doc().header, version: "v3" } })).approval).toBeNull();
  });
});

describe("outline", () => {
  it("builds a table of contents with stable anchors", () => {
    expect(tocOf(doc()).map((t) => t.anchor)).toEqual(["doc-prd-totals", "doc-prd-requirements"]);
    expect(sectionAnchor("screens", "SCR-01")).toBe("doc-screens-SCR-01");
  });

  it("collects 가정·미결 rows but not the count table", () => {
    expect(statusColumn({ type: "table", columns: ["상태", "개수"], rows: [] })).toBe(-1);
    expect(markedItems(doc())).toEqual([
      { mark: "가정", id: "REQ-02", label: "자동결제", anchor: "doc-prd-requirements" },
      { mark: "미결", id: "REQ-03", label: "쿠폰", anchor: "doc-prd-requirements" },
    ]);
  });

  it("splits IDs out of text for chips and formats dates", () => {
    expect(splitIds("REQ-01 과 SCR-02 연결")).toEqual([
      { text: "REQ-01", id: true },
      { text: " 과 ", id: false },
      { text: "SCR-02", id: true },
      { text: " 연결", id: false },
    ]);
    expect(splitIds("ID 없음")).toEqual([{ text: "ID 없음", id: false }]);
    expect(formatDate("nope")).toBeNull();
  });
});
