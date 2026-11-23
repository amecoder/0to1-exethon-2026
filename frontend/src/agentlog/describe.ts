// Plain Korean wording for one agent-log entry: Liner calls, writes and the recorded decisions.
import type { AppEvent } from "../api";
import { formatUsd } from "../lib/credits";
import { SCHEMA_ACTION, type View } from "../lib/labels";
import { nameIds, stripIds } from "../lib/summarize";
import type { LogKind } from "./model";

interface Described {
  kind: LogKind;
  title: string;
  lines: string[];
  itemId?: string;
}

type Item = Record<string, any>;

const EXTRA_IDS = /\b(?:CHG|CMP|FB|PROTO|FLOW|FND|PS|SCOPE|BRD|PRD|QAC)-\d+\b/g;

// Team view keeps the ids; the client view names requirements/screens/tests by title and drops the rest.
export function plain(text: string, view: View, titles: Record<string, string>): string {
  if (view === "team") return text;
  return stripIds(nameIds(text, titles).replace(EXTRA_IDS, "")).replace(/\s{2,}/g, " ").trim();
}

const KIND_NAME: Record<string, string> = {
  sources: "원문",
  problem_statement: "문제 진술",
  scope: "범위",
  evidence: "근거",
  requirements: "요구사항",
  findings: "지적",
  questions: "질문 카드",
  decisions: "고른 답",
  screens: "화면",
  screen_spec: "화면설계서 요약",
  tests: "테스트",
  test_plan: "테스트 계획 요약",
  brd: "BRD",
  prd: "PRD",
  flow_chart: "흐름도",
  feedback: "고객 의견",
  prototype: "프로토타입",
  qa_checklist: "체크리스트",
  changes: "변경 요청",
  complaints: "「아 이거 아닌데?」",
};

// Kinds drawn in the lineage map (a write of these links to its node).
const LINEAGE_KINDS = new Set(["sources", "evidence", "decisions", "requirements", "screens", "flow_chart", "tests", "prototype", "changes", "complaints"]);

function seconds(ms: unknown): string | null {
  return typeof ms === "number" ? `걸린 시간 ${(ms / 1000).toFixed(1)}초` : null;
}

function cost(value: unknown): string | null {
  if (typeof value !== "number") return null;
  return `비용 ${value > 0 && value < 0.0001 ? "$0.0001 미만" : formatUsd(value)}`;
}

function percent(value: unknown): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
}

const CHOICE_KO: Record<string, string> = { violation: "합의 위반", new_change: "새 변경 요청" };

export function linerEntry(e: AppEvent, view: View): Described {
  const d = e.data ?? {};
  const model = d.answered_model || d.model;
  const common = [model ? `답한 모델 ${model}` : null, seconds(d.duration_ms), cost(d.cost), d.error ? "실패 — 결과 없이 진행" : null];
  const team = view === "team";
  switch (e.type) {
    case "liner_chat":
      return {
        kind: "liner",
        title: `Liner 모델 — ${SCHEMA_ACTION[d.schema] ?? "응답 생성"}`,
        lines: [...common, team && d.routing_strategy ? `라우팅 ${d.routing_strategy}` : null].filter(Boolean) as string[],
      };
    case "liner_search":
      return {
        kind: "liner",
        title: `Liner ${d.api === "ai_search" ? "AI 검색" : "웹 검색"} “${d.query ?? ""}”`,
        lines: [`결과 ${d.result_count ?? 0}건`, ...common, d.fallback ? "웹 검색으로 다시 찾음" : null].filter(Boolean) as string[],
      };
    case "liner_decision": {
      const answer = d.answers?.kind;
      const probs = answer?.probabilities
        ? Object.entries(answer.probabilities as Record<string, number>).map(([k, v]) => `${CHOICE_KO[k] ?? k} ${percent(v)}`).join(" · ")
        : null;
      const noul = d.answers && d.purpose !== "complaint"
        ? Object.values(d.answers as Record<string, { noul?: number }>).map((a) => a?.noul).filter((v): v is number => typeof v === "number")
        : [];
      return {
        kind: "liner",
        title: `Liner 판정 — ${d.purpose === "complaint" ? "불만이 합의 위반인지 새 요청인지" : "근거가 문장을 뒷받침하는지"}`,
        lines: [
          probs ? `확률 ${probs} · 확신도 ${percent(answer?.confidence)}` : null,
          noul.length ? `뒷받침 확률 가장 낮은 값 ${percent(Math.min(...noul))} (${noul.length}문장)` : null,
          ...common,
        ].filter(Boolean) as string[],
      };
    }
    case "liner_rerank":
      return { kind: "liner", title: `Liner 재정렬 — 바뀔 요구사항 후보 ${d.documents ?? 0}개를 점수로 줄 세움`, lines: common.filter(Boolean) as string[] };
    case "liner_image":
      return { kind: "liner", title: `Liner 이미지 생성 — 프로토타입 사진 「${d.slot ?? ""}」`, lines: [d.prompt ? `프롬프트: ${d.prompt}` : null, ...common].filter(Boolean) as string[] };
    default:
      return { kind: "liner", title: "Liner 시각화 — 사용자 흐름도", lines: common.filter(Boolean) as string[] };
  }
}

function itemName(item: Item): string {
  const s = item.title || item.text || item.chosen || item.utterance || item.comment || item.question || item.who || item.fact || "";
  return String(s);
}

export function writeEntry(e: AppEvent, view: View, titles: Record<string, string>): Described {
  const kind = String(e.data?.kind ?? "");
  const item: Item = e.data?.item ?? {};
  const name = plain(itemName(item), view, titles);
  const lines: string[] = [];
  if (kind === "feedback") lines.push(`등급: ${item.kind ?? "의견"}`);
  if (kind === "decisions" && item.status === "가정") lines.push("발주사가 모른다고 해 기본값으로 가정");
  if (item.status === "가정" && kind === "requirements") lines.push("가정으로 채움");
  const id = typeof item.id === "string" ? item.id : undefined;
  return {
    kind: "write",
    title: `${KIND_NAME[kind] ?? "기록"} 작성${view === "team" && id ? ` ${id}` : ""}${name ? `: ${name.slice(0, 60)}` : ""}`,
    lines,
    itemId: id && LINEAGE_KINDS.has(kind) ? id : undefined,
  };
}

// PM, FR-21: which requirement a change request changes, and why.
export function changeDecision(item: Item, view: View, titles: Record<string, string>): Described {
  const team = view === "team";
  const target = String(item.target);
  const name = item.title || titles[target] || target;
  const impact = item.impact ?? {};
  const n = (k: string) => (Array.isArray(impact[k]) ? impact[k].length : 0);
  const candidates = Array.isArray(item.candidates) ? (item.candidates as Item[]) : [];
  return {
    kind: "decision",
    title: `변경 요청${team ? ` ${item.id}` : ""} → ${team ? `${target} ` : ""}「${name}」를 바꾸는 요청으로 판단`,
    lines: [
      item.rationale ? `이유: ${plain(String(item.rationale), view, titles)}` : "이유: 기록 없음 (이 버전의 출력에는 이유 칸이 없었어요)",
      item.summary ? `무엇이 바뀌나: ${plain(String(item.summary), view, titles)}` : null,
      candidates.length
        ? `참고한 후보 점수: ${candidates.map((c) => `${team ? `${c.id} ` : ""}${c.title} ${Number(c.score).toFixed(2)}`).join(" · ")}`
        : "후보 재정렬 없이 전체에서 고름",
      `코드가 계산한 영향: 요구사항 ${n("requirements")} · 화면 ${n("screens")} · 테스트 ${n("tests")}`,
    ].filter(Boolean) as string[],
    itemId: target,
  };
}

// QA, FR-22: the complaint call, the Decisions probabilities and whether the code guard overrode it.
export function complaintDecision(item: Item, view: View, titles: Record<string, string>): Described {
  const decision: Item = item.decision ?? {};
  const probs = decision.probabilities
    ? Object.entries(decision.probabilities as Record<string, number>).map(([k, v]) => `${CHOICE_KO[k] ?? k} ${percent(v)}`).join(" · ")
    : null;
  const ids: string[] = Array.isArray(item.requirement_ids) ? item.requirement_ids : [];
  const low = typeof decision.confidence === "number" && typeof decision.threshold === "number" && decision.confidence < decision.threshold;
  return {
    kind: "decision",
    title: `불만 판정: ${item.classification}${item.model_classification && item.model_classification !== item.classification ? ` (QA 의견은 ${item.model_classification})` : ""}`,
    lines: [
      item.reason ? `QA 이유: ${plain(String(item.reason), view, titles)}` : null,
      `대조한 요구사항: ${ids.map((id) => (view === "team" ? id : `「${titles[id] ?? "요구사항"}」`)).join(", ")}`,
      probs ? `Liner 판정 확률: ${probs} · 확신도 ${percent(decision.confidence)}` : decision.error ? "Liner 판정을 받지 못함" : null,
      item.guard?.applied ? `코드 가드가 판정을 바로잡음: ${plain(String(item.guard.detail ?? ""), view, titles)}` : null,
      item.needs_human ? "확신이 낮아 사람 판단이 필요하다고 표시" : low && item.guard?.applied ? "확신도가 문턱보다 낮았지만 코드 가드가 정함" : null,
    ].filter(Boolean) as string[],
    itemId: ids[0],
  };
}

// Developer, S6: retries and the template fallback.
export function prototypeDecision(d: Item): Described {
  const failures: string[] = Array.isArray(d.failures) ? d.failures.map(String) : [];
  const missing = Array.isArray(d.missing_screens) ? d.missing_screens.length : 0;
  return {
    kind: "decision",
    title: `프로토타입 완성 — 시도 ${d.attempts ?? 1}회`,
    lines: [
      d.origin === "template" ? "결과가 검사를 넘지 못해 템플릿 대체본을 씀" : "에이전트가 쓴 결과를 그대로 씀",
      failures.length ? `다시 시도한 이유: ${failures.join(", ")}` : null,
      missing ? `빠진 화면 ${missing}개` : null,
    ].filter(Boolean) as string[],
  };
}
