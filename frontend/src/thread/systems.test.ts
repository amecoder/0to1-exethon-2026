import { describe, expect, it } from "vitest";
import { appendLines, countSystems } from "./RequestComposer";

describe("countSystems", () => {
  it("counts one system per non-empty line and skips '#' headings, like the server", () => {
    expect(countSystems("# 우리 시스템\n- 주문관리: 주문\n\n알림톡 발송 — 카톡\n  ")).toBe(2);
    expect(countSystems("")).toBe(0);
  });
});

describe("appendLines", () => {
  it("adds lines read from a file under what is already typed", () => {
    expect(appendLines("", ["주문관리: 주문", "알림톡: 발송"])).toBe("주문관리: 주문\n알림톡: 발송");
    expect(appendLines("회원: 가입 정보\n", ["주문관리: 주문"])).toBe("회원: 가입 정보\n주문관리: 주문");
  });
});
