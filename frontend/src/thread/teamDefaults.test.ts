import { describe, expect, it } from "vitest";
import { changedDefaults, type TeamDefault } from "./teamDefaults";

const d = (id: string, team_default: string): TeamDefault => ({ id, title: id, team_default, team_why: "", requirement_refs: [] });

describe("changedDefaults", () => {
  it("sends only the lines the client changed", () => {
    const list = [d("OPEN-01", "다음 날 다시 결제"), d("OPEN-02", "알림 없음")];
    expect(changedDefaults(list, { "OPEN-01": "사장님에게 알림", "OPEN-02": "알림 없음" })).toEqual({ "OPEN-01": "사장님에게 알림" });
  });
  it("treats an emptied or space-only line as keeping the default", () => {
    expect(changedDefaults([d("OPEN-01", "다음 날 다시 결제")], { "OPEN-01": "   " })).toEqual({});
  });
});
