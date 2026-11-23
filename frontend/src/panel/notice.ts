import type { Project } from "../api";
import { laneEntries, pendingChange } from "../thread/lane/model";

// What the client has to handle right now, for the banner in the artifact pop-out window.
// `key` changes whenever a new thing waits (so a dismissed banner comes back for the next one);
// `target` says where the main window should scroll: the task card, or one change request in the lane.
export interface Notice {
  key: string;
  text: string;
  target: "todo" | `change:${string}`;
}

export function pendingNotice(project: Project): Notice | null {
  const todo = project.todo;
  switch (todo?.kind) {
    case "question":
      return { key: `question:${todo.question.id}`, text: `질문에 답해 주세요 · 남은 질문 ${todo.remaining}개`, target: "todo" };
    case "answers_review":
      return { key: "answers_review", text: "고른 답을 한 번 확인하고 보내 주세요", target: "todo" };
    case "confirmation":
      if (!todo.cp.startsWith("CP")) break; // replay can pass through a transient S-stage state
      return { key: `confirmation:${todo.cp}`, text: `${todo.title} — 확인하고 승인해 주세요`, target: "todo" };
    case "scope":
      return { key: "scope", text: `화면이 많아요 · 먼저 만들 화면 ${todo.max}개를 골라 주세요`, target: "todo" };
    case "limit":
      return { key: "limit", text: "정해 둔 한도에 닿아 멈췄어요 · 계속할지 정해 주세요", target: "todo" };
  }
  const change = pendingChange(laneEntries(project.source));
  if (change?.status === "awaiting_cp5") {
    return { key: `change:${change.id}`, text: "변경 요청의 영향을 확인하고 승인해 주세요", target: `change:${change.id}` };
  }
  return null;
}

// The pop-out asks its opener (the main window) to bring this into view. Same-origin messages only.
export const GOTO_MESSAGE = "0to1:goto";

// The operating-system notice: only for something new (`prev` is the key last seen; undefined = first load, so
// opening a project never pops one), only while the window is out of sight, and only with permission.
export function osNoticeToShow(prev: string | null | undefined, notice: Notice | null,
  { hidden, permission }: { hidden: boolean; permission: NotificationPermission }): Notice | null {
  if (prev === undefined || !notice || notice.key === prev || !hidden || permission !== "granted") return null;
  return notice;
}
