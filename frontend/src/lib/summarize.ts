// Turns raw activity events into one-line Korean summaries, and derives "who is working on what".
// Pure functions: no React, no fetch.
import type { AppEvent, Pipeline } from "../api";
import { formatUsd } from "./credits";
import {
  GUARDRAIL_KO,
  OUTCOME_KO,
  SCHEMA_ACTION,
  STAGE_TITLE,
  stageAction,
  withObject,
  withSubject,
  type View,
} from "./labels";

export type Label = (id: string) => string;
export type Tone = "message" | "liner" | "guard" | "check" | "client" | "system";

export interface Summary {
  text: string;
  tone: Tone;
}

// Events that only rebuild state; they are not shown in the activity log.
export const HIDDEN_EVENTS = new Set(["pipeline", "item_written", "bundle_cleared"]);

const ID_PATTERN = /\b(?:SYS-\d+\/)?(?:SRC|REQ|SCR|TC|EV|DEC|OPEN|CF|Q|SCRDOC|TCDOC|CMP|FND|SYS)-\d+\b/g;

// Remove internal IDs from a sentence for the client view: "SCR-01 구독 신청 → SCR-02" → "구독 신청 →".
export function stripIds(text: string): string {
  return text
    .replace(/\(\s*(?:(?:SRC|REQ|SCR|TC|EV|DEC|OPEN|CF|Q|CMP|FND|SYS)-\d+\s*[,·]?\s*)+\)/g, "")
    .replace(ID_PATTERN, "")
    .replace(/\s*[—–]\s*(?=[).,]|$)/g, "") // a dash left pointing at a removed id: "일시정지 — CMP-08)"
    .replace(/\s+([,.)])/g, "$1")
    .replace(/(^|\s)[,·]\s*/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

// Client view: replace internal IDs with the item's name — "REQ-02 를 확인할" → "「자동결제」를 확인할".
// Unknown IDs are removed like stripIds does.
export function nameIds(text: string, titles: Record<string, string>): string {
  const named = text.replace(/\b((?:SRC|REQ|SCR|TC|EV|DEC|OPEN|CF|Q)-\d+)\b(\s(?=[을를이가은는의와과에도로]))?/g, (whole, id: string) =>
    titles[id] ? `「${titles[id]}」` : whole,
  );
  return stripIds(named);
}

// Client view with links: like nameIds, but each named item stays a part carrying its ID, so the text can
// show 「name」 as a link. Unknown IDs are dropped exactly as nameIds drops them.
export function namedParts(text: string, titles: Record<string, string>): { text: string; id?: string }[] {
  // Markers hold an index, not the ID itself, so stripIds (which removes bare IDs) leaves them alone.
  const ids: string[] = [];
  const marked = text.replace(/\b((?:SRC|REQ|SCR|TC|EV|DEC|OPEN|CF|Q)-\d+)\b(\s(?=[을를이가은는의와과에도로]))?/g, (whole, id: string) => {
    if (!titles[id]) return whole;
    ids.push(id);
    return `\u0001${ids.length - 1}\u0002`;
  });
  // Dropping unknown IDs can leave bare separators (", , 「이름」"): collapse them.
  const cleaned = stripIds(marked)
    .replace(/(?:\s*[,·]\s*){2,}/g, ", ")
    .replace(/^\s*[,·]\s*/, "")
    .replace(/\s*[,·]\s*$/, "");
  return cleaned
    .split(/\u0001(\d+)\u0002/)
    .map((part, i) => (i % 2 === 1 ? { text: `「${titles[ids[Number(part)]]}」`, id: ids[Number(part)] } : { text: part }))
    .filter((p) => p.text);
}

export function shorten(text: string, max = 60): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

// "단계 S2 문제 인식: 발주사 원문만 근거로 …" → "문제 인식 작업 지시"
export function briefMessage(content: string): string {
  const assignment = /^단계\s+(S\d|CP\d)\s+([^:：]+)[:：]/.exec(content);
  if (assignment) return `${assignment[2].trim()} 작업 지시`;
  return shorten(content, 56);
}

// Given/When/Then → one plain sentence for readers who do not know the format.
export function plainAcceptance(a: { given: string; when: string; then: string }): string {
  return [a.given, a.when, a.then].map((s) => s.trim()).filter(Boolean).join(" ");
}

function stageTitle(stage: unknown): string {
  return STAGE_TITLE[String(stage)] ?? String(stage ?? "");
}

// S1 intake triage round (app/intake_triage.py): one event per 「팀에게 보내기」 before the team gets the request.
const TRIAGE_KO: Record<string, string> = {
  ok: "팀에 넘김",
  insufficient: "정보가 모자라 되물음",
  cannot: "맡을 수 없는 요청이라 돌려보냄",
  garbled: "읽을 수 없는 글이라 다시 써 달라고 함",
};
const SLOT_KO: Record<string, string> = { who: "누가 쓰는지", pain: "무엇이 불편한지", done: "무엇이 되면 끝인지" };

function triageText(d: Record<string, any>): string {
  if (d.error) return "접수 확인 실패 — 발주사가 다시 누르면 다시 확인";
  const missing = Array.isArray(d.missing) && d.missing.length ? ` (${d.missing.map((m: string) => SLOT_KO[m] ?? m).join(" · ")})` : "";
  return `접수 확인: ${TRIAGE_KO[d.case] ?? "판정"}${missing}${d.by === "code" ? " · 코드 사전 검사" : ""}`;
}

export function summarizeEvent(e: AppEvent, label: Label, view: View): Summary {
  const d = e.data ?? {};
  const team = view === "team";
  const id = (value: unknown) => (team && value ? ` ${String(value)}` : "");
  switch (e.type) {
    case "agent_message":
      return {
        tone: d.to === "client" || d.from === "client" ? "client" : "message",
        text: `${label(d.from)} → ${label(d.to)}${d.relay ? " (조율자 중계)" : ""}: ${briefMessage(String(d.content ?? ""))}`,
      };
    case "message_rerouted":
      return { tone: "guard", text: `${label(d.from)} → ${label(d.to)} 관계선이 없어 조율자를 거쳐 전달` };
    case "liner_chat": {
      const action = SCHEMA_ACTION[d.schema] ?? "응답 생성";
      return { tone: "liner", text: `Liner 모델로 ${action}${team ? modelNote(d) : ""}` };
    }
    case "liner_search": {
      const what = d.api === "ai_search" ? "Liner AI 검색" : "Liner 검색";
      if (d.error) return { tone: "liner", text: `${what} 실패 “${d.query}”${d.fallback ? " → 웹 검색으로 바꿈" : ""}` };
      return { tone: "liner", text: `${what} “${d.query}” → ${d.result_count}건` };
    }
    case "liner_decision": {
      const what = d.purpose === "complaint" ? "불만이 합의 위반인지 새 요청인지 판정" : "근거가 문장을 뒷받침하는지 판정";
      return { tone: "liner", text: `Liner 판정으로 ${what}${d.error ? " — 실패" : ""}` };
    }
    case "liner_rerank":
      return { tone: "liner", text: `Liner 재정렬로 바뀔 요구사항 후보 추림${d.error ? " — 실패" : ""}` };
    case "liner_visualization":
      return { tone: "liner", text: `Liner 시각화로 사용자 흐름도 그림${d.error ? " — 실패" : ""}` };
    case "liner_image":
      return { tone: "liner", text: d.error ? "Liner 이미지 생성 실패 — 사진 자리는 그림으로 둠" : "Liner 이미지 생성으로 프로토타입 사진 1장 만듦" };
    case "intake_triage":
      return { tone: "check", text: triageText(d) };
    case "liner_transcription":
      return { tone: "liner", text: d.error ? "Liner 받아쓰기 실패" : `Liner 받아쓰기로 녹음을 글로 바꿈 (${d.chars}자)` };
    case "credits":
      return {
        tone: "system",
        text: d.error
          ? "크레딧 잔액을 읽지 못함 (작업은 계속)"
          : `크레딧 잔액 확인${typeof d.spent_usd === "number" ? ` · 지금까지 ${formatUsd(d.spent_usd)}` : ""}`,
      };
    case "guardrail": {
      const name = GUARDRAIL_KO[d.id] ?? "가드레일";
      const outcome = OUTCOME_KO[d.outcome] ?? "작동";
      return { tone: "guard", text: `${name}${id(d.id)} ${outcome}: ${team ? d.detail : stripIds(String(d.detail ?? ""))}` };
    }
    case "write_rejected":
      return { tone: "guard", text: `쓰기 권한이 없어 거부됨 (${d.reason ?? d.kind})` };
    case "question_answered":
      return {
        tone: "client",
        text: `발주사 답${id(d.question_id)}: “${d.value ?? "잘 모르겠어요"}”${d.status === "가정" ? " (기본값으로 가정)" : ""}`,
      };
    case "confirmation":
      return {
        tone: "client",
        text: `${stageTitle(d.cp)} ${d.approved ? "승인" : `반려 — ${d.reason ?? ""}`}${team && d.version ? ` → ${d.version}` : ""}`,
      };
    case "version_created":
      return { tone: "system", text: `지금 내용을 ${d.version} 로 고정` };
    case "check_result": {
      const count = Array.isArray(d.items) ? d.items.length : 0;
      if (d.check === "consumer_feedback") return { tone: "check", text: "고객 의견을 받지 못해 의견 없이 진행" };
      if (d.check === "change_consistency")
        return { tone: "check", text: d.outcome === "passed" ? "변경 뒤 요구사항 대조: 어긋남 없음" : `변경 뒤 요구사항 대조: 아직 어긋남 ${count}건` };
      if (d.check === "change_impact") return { tone: "check", text: `변경 영향 계산: ${count}개 항목` };
      if (d.check === "complaint_guard") return { tone: "check", text: "확정된 문장과 같은 요청이라 합의 위반으로 바로잡음" };
      if (d.check === "g1_support") {
        if (d.outcome === "skipped") return { tone: "check", text: "근거 뒷받침 판정을 건너뜀 (참고)" };
        return { tone: "check", text: d.outcome === "passed" ? "근거 뒷받침 판정: 모두 통과" : `근거 뒷받침 판정: 참고 ${count}건` };
      }
      if (d.check === "problem_done")
        return { tone: "check", text: d.outcome === "updated" ? "고른 답에 맞춰 성공 기준 문장을 다시 씀" : d.outcome === "skipped" ? "성공 기준 문장을 다시 쓰지 못해 그대로 둠 (참고)" : "성공 기준 문장이 답과 맞아 그대로 둠" };
      if (d.check === "rerank") return { tone: "check", text: "후보 재정렬 없이 PM이 전체에서 고름" };
      if (d.check === "visualization") return { tone: "check", text: d.outcome === "failed" ? "사용자 흐름도를 만들지 못함 (참고)" : "사용자 흐름도 완성" };
      const what = d.check === "coverage" ? "빈칸 검사" : "고른 답과 요구사항 대조";
      return { tone: "check", text: `${what}: ${d.outcome === "passed" ? "통과" : `경고 ${count}건`}` };
    }
    case "ref_dropped":
      return { tone: "check", text: team ? `없는 ID 참조 제거: ${d.item} → ${d.ref}` : "없는 항목을 가리키는 연결 하나를 지움" };
    case "run_interrupted":
      return { tone: "system", text: `${d.crash ? "예상하지 못한 오류로" : "서버가 다시 시작되어"} ${stageTitle(d.stage)} 작업이 멈춤` };
    case "run_retried":
      return { tone: "system", text: `${stageTitle(d.stage)} 다시 시도` };
    case "change_revised": {
      const ids = Array.isArray(d.requirements) ? d.requirements.map((r: { id: string }) => r.id) : [];
      return { tone: "system", text: `변경 ${d.change_id}에 맞춰 요구사항 ${ids.length}건을 고침${team && ids.length ? ` (${ids.join(", ")})` : ""}` };
    }
    case "recheck_required":
      return { tone: "system", text: `변경 ${d.change_id} 반영(${d.version}) — 문서·프로토타입을 다시 만들고 확인 3·4를 다시 받음` };
    case "recheck_cleared":
      return { tone: "system", text: `변경 ${d.change_id} 반영본을 다시 인수 — 내려받기 열림` };
    case "stage_started":
      return { tone: "system", text: `${stageTitle(d.stage)} 시작` };
    case "stage_completed":
      return { tone: "system", text: `${stageTitle(d.stage)} 완료` };
    case "prototype_built": {
      const missing = Array.isArray(d.missing_screens) ? d.missing_screens.length : 0;
      const what = d.origin === "template" ? "템플릿 대체본" : "프로토타입";
      return { tone: "system", text: `${what} 완성 (시도 ${d.attempts}회${missing ? `, 빠진 화면 ${missing}개` : ""})` };
    }
    case "pipeline":
      return { tone: "system", text: `${stageTitle(d.stage)} 진행 상태 바뀜` };
    case "item_written":
      return { tone: "system", text: `${label(e.actor)} 공유 원본에 기록${id(d.item?.id)}` };
    case "bundle_cleared":
      return { tone: "system", text: `${label(e.actor)} 묶음을 새로 씀` };
    default:
      return { tone: "system", text: "기타 활동" };
  }
}

// Team view: "· 답한 모델 claude-sonnet-5.5 (liner-claude-router · balanced)". liner-mark does not say who answered.
export function modelNote(d: Record<string, any>): string {
  if (d.answered_model) {
    const via = [d.model, d.routing_strategy].filter(Boolean).join(" · ");
    return ` · 답한 모델 ${d.answered_model}${via ? ` (${via})` : ""}`;
  }
  return d.model ? ` · ${d.model}` : "";
}

// --- who is working on what ------------------------------------------------------------------------

export interface MessageEdge {
  seq: number;
  from: string;
  to: string;
  rerouted: boolean;
}

// The most recent handoff between two parties (drives the graph highlight).
export function latestMessage(events: AppEvent[]): MessageEdge | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type === "agent_message" || e.type === "message_rerouted") {
      return { seq: e.seq, from: String(e.data.from), to: String(e.data.to), rerouted: e.type === "message_rerouted" };
    }
  }
  return null;
}

export interface Activity {
  agent: string | null;
  sentence: string;
}

// "지금 리서처가 Liner로 근거를 검색 중" from the pipeline state and the latest events.
export function currentActivity(pipeline: Pipeline | undefined, events: AppEvent[], label: Label): Activity {
  const stage = pipeline?.stage ?? "S1";
  const agent = pipeline?.active_agent ?? null;
  if (agent) {
    const action = stageAction(stage, agent) ?? lastSchemaAction(events, agent) ?? `${STAGE_TITLE[stage] ?? stage} 작업`;
    return { agent, sentence: `지금 ${withSubject(label(agent))} ${action} 중` };
  }
  const msg = latestMessage(events);
  if (msg && msg.to !== "client") {
    return { agent: msg.to, sentence: `${withSubject(label(msg.from))} ${withObject(label(msg.to))} 부르는 중` };
  }
  return { agent: null, sentence: `팀이 ${withObject(STAGE_TITLE[stage] ?? "다음 단계")} 준비하는 중` };
}

function lastSchemaAction(events: AppEvent[], agent: string): string | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type === "liner_chat" && e.actor === agent) return SCHEMA_ACTION[e.data.schema] ?? null;
  }
  return null;
}
