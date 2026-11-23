import { describe, expect, it } from "vitest";
import type { Project } from "../api";
import { osNoticeToShow, pendingNotice, type Notice } from "./notice";

function project(todo: unknown, changes: unknown[] = []): Project {
  return { todo, source: { changes, complaints: [] } } as unknown as Project;
}

describe("what the pop-out window tells the client to handle", () => {
  it("is null while the team is working or nothing waits", () => {
    expect(pendingNotice(project({ kind: "none", status: "running" }))).toBeNull();
    expect(pendingNotice(project(undefined))).toBeNull();
  });

  it("names a question card with how many are left", () => {
    const n = pendingNotice(project({ kind: "question", question: { id: "Q-03" }, remaining: 4 }));
    expect(n).toMatchObject({ key: "question:Q-03", target: "todo" });
    expect(n?.text).toContain("4");
  });

  it("names a confirmation by its title, but not a transient non-CP stage", () => {
    expect(pendingNotice(project({ kind: "confirmation", cp: "CP3", title: "문서 4종 확인" }))).toMatchObject({
      key: "confirmation:CP3",
      target: "todo",
    });
    expect(pendingNotice(project({ kind: "confirmation", cp: "S4", title: "x" }))).toBeNull();
  });

  it("covers the answer review, scope and limit cards", () => {
    expect(pendingNotice(project({ kind: "answers_review", questions: [] }))?.key).toBe("answers_review");
    expect(pendingNotice(project({ kind: "scope", screens: [], max: 5 }))?.key).toBe("scope");
    expect(pendingNotice(project({ kind: "limit", limit: "cost" }))?.key).toBe("limit");
  });

  it("points at a change request waiting for CP5", () => {
    const changes = [
      { id: "CHG-1", status: "applied", created_at: "1" },
      { id: "CHG-2", status: "awaiting_cp5", created_at: "2" },
    ];
    expect(pendingNotice(project({ kind: "download" }, changes))).toMatchObject({ key: "change:CHG-2", target: "change:CHG-2" });
  });

  it("does not nag about the finished download or a closed project", () => {
    expect(pendingNotice(project({ kind: "download" }))).toBeNull();
    expect(pendingNotice(project({ kind: "closed", chosen: null, alternative: null }))).toBeNull();
  });
});

describe("when the operating system is asked to show a notice", () => {
  const ask: Notice = { key: "question:Q-01", text: "질문에 답해 주세요 · 남은 질문 3개", target: "todo" };
  const seen = { hidden: true, permission: "granted" as NotificationPermission };

  it("shows a new thing to handle while the window is out of sight", () => {
    expect(osNoticeToShow(null, ask, seen)).toEqual(ask);
    expect(osNoticeToShow("confirmation:CP1", ask, seen)).toEqual(ask);
  });

  it("stays quiet on first load, for the same thing again, and when nothing waits", () => {
    expect(osNoticeToShow(undefined, ask, seen)).toBeNull();
    expect(osNoticeToShow("question:Q-01", ask, seen)).toBeNull();
    expect(osNoticeToShow("question:Q-01", null, seen)).toBeNull();
  });

  it("leaves it to the page when the window is in view, and never shows without permission", () => {
    expect(osNoticeToShow(null, ask, { ...seen, hidden: false })).toBeNull();
    expect(osNoticeToShow(null, ask, { ...seen, permission: "default" })).toBeNull();
    expect(osNoticeToShow(null, ask, { ...seen, permission: "denied" })).toBeNull();
  });
});
