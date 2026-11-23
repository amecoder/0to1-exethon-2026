import { describe, expect, it } from "vitest";
import type { CheckWarning, Review } from "../../api";
import { approvalBlocker, waiverValues } from "./ReviewNotices";

const gap = (id: string, suggested?: string): CheckWarning => ({
  id, code: "coverage.no_tc", severity: "waivable", target: id, doc: "tests", message: `${id} 테스트 없음`,
  explain: "설명", suggested,
});
const review = (waivable: CheckWarning[]): Review =>
  ({ cp: "CP3", summary: "", answers: [], blocking: [], waivable, notices: [], can_approve: false, consumer_feedback: [] }) as Review;

describe("빈칸 reasons filled in by the team (11-22)", () => {
  it("uses the filled reason until the client edits it", () => {
    const r = review([gap("a", "자동 이유"), gap("b", "자동 이유 2")]);
    expect(waiverValues(r, {})).toEqual({ a: "자동 이유", b: "자동 이유 2" });
    expect(waiverValues(r, { a: "내가 쓴 이유" })).toEqual({ a: "내가 쓴 이유", b: "자동 이유 2" });
  });

  it("lets the client clear a filled reason, which then blocks approval", () => {
    const r = review([gap("a", "자동 이유")]);
    expect(approvalBlocker(r, {})).toBeNull();
    expect(waiverValues(r, { a: "" })).toEqual({});
    expect(approvalBlocker(r, { a: "  " })).toBe("빈칸 1건에 이유를 적으면 승인할 수 있어요");
  });

  it("still asks for a reason when none was filled in", () => {
    expect(approvalBlocker(review([gap("a")]), {})).toBe("빈칸 1건에 이유를 적으면 승인할 수 있어요");
  });
});
