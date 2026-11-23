import type { DocId } from "../api";

// What an ID inside a document points to, so a click can say what it is and where it lives.
// Built from the shared source; pure so it can be tested without a DOM.

export interface RefInfo {
  id: string;
  kind: string; // 요구사항, 화면, …
  title: string;
  lines: { label: string; value: string }[]; // the few facts worth reading in a popover
  doc: DocId | null; // the document whose table lists this item (null: not listed in a document)
}

type Item = Record<string, unknown>;

const text = (v: unknown): string => (typeof v === "string" ? v : Array.isArray(v) ? v.filter((x) => typeof x === "string").join(", ") : "");
const line = (label: string, v: unknown) => ({ label, value: text(v) });
const kept = (lines: { label: string; value: string }[]) => lines.filter((l) => l.value.trim());

function items(source: Record<string, unknown>, kind: string): Item[] {
  const v = source[kind];
  return Array.isArray(v) ? (v.filter((x) => x && typeof x === "object") as Item[]) : [];
}

// Process codes (fixed for every project): the five confirmations, the seven stages, the eight guardrails.
export const GLOSSARY: [string, string, string, string][] = [
  ["CP1", "체크포인트 1", "문제·범위 확인", "팀이 정리한 문제와 범위가 맞는지 발주사가 확인해요. 승인해야 질문 단계로 넘어가요."],
  ["CP2", "체크포인트 2", "요구사항 확인", "고른 답이 요구사항에 그대로 들어갔는지 보고 v1로 고정해요. 답과 다른 요구사항이 있으면 승인할 수 없어요."],
  ["CP3", "체크포인트 3", "문서 4종 확인 · 프로토타입 작성", "BRD·PRD·화면설계서·테스트 케이스를 보고 프로토타입 작성을 승인해요. 빈칸이 있으면 이유를 적어야 승인돼요."],
  ["CP4", "체크포인트 4", "프로토타입 인수", "프로토타입을 직접 눌러 보고 받을지 정해요. 승인하면 결과물 내려받기가 열려요."],
  ["CP5", "변경 체크포인트", "바꿀 때마다 1번", "확정한 뒤 바꾸고 싶을 때마다 한 번 거쳐요. 바뀌는 요구사항·화면·테스트를 미리 보고 반영할지 정해요. 승인하면 문서와 프로토타입을 다시 만들고 CP3·CP4를 다시 받아요."],
  ["S1", "단계 1", "입력 받기", "메모·대화·음성을 문장 단위 원문(SRC)으로 나눠 고정해요."],
  ["S2", "단계 2", "문제 인식", "FDE 리드가 문제와 범위를 정리하고, 리서처가 Liner 검색으로 근거와 기존 제품을 찾아요."],
  ["S3", "단계 3", "구체화", "PM이 요구사항 후보를 만들고, QA가 빈틈을 찾고, 조율자가 질문 카드로 바꿔요."],
  ["S4", "단계 4", "원본 확정", "발주사의 답을 반영해 요구사항을 확정해요."],
  ["S5", "단계 5", "문서화", "화면설계서·테스트 케이스·BRD·PRD와 흐름도를 만들어요."],
  ["S6", "단계 6", "프로토타입 작성", "개발자가 프로토타입을 만들고, QA가 테스트와 맞춰 보고, 고객 역할이 눌러 봐요."],
  ["S7", "단계 7", "내려받기", "문서·프로토타입·공유 원본을 zip 하나로 내려받아요."],
  ["G1", "안전장치 1", "근거 검사", "모든 문장의 인용이 원문·출처에 글자 그대로 있는지 확인해요. 없으면 「미확인」으로 둬요."],
  ["G2", "안전장치 2", "승인 관문", "확인을 받지 않으면 다음 단계로 가지 않아요. 고른 답과 다른 요구사항이 있으면 승인을 막아요."],
  ["G3", "안전장치 3", "민감정보 보호", "개인정보·비밀값을 저장하거나 Liner로 보내기 전에 막거나 가려요."],
  ["G4", "안전장치 4", "원문 보호", "발주사 원문은 처음에 고정되고, 에이전트는 고칠 수 없어요."],
  ["G5", "안전장치 5", "가정 표시", "근거 없이 채운 값은 「가정」으로 표시해요."],
  ["G6", "안전장치 6", "격리 미리보기", "프로토타입과 흐름도는 바깥과 통신할 수 없는 칸 안에서만 열려요."],
  ["G7", "안전장치 7", "비용·시간 상한", "호출 수·단계 시간·비용 상한에 닿으면 멈추고 「계속」할지 물어요."],
  ["G8", "안전장치 8", "화면 수 상한", "화면이 너무 많으면 먼저 만들 화면을 발주사가 골라요."],
  ["G9", "안전장치 9", "용도 검사", "무기·전쟁·폭력·성인물·불법이 목적인 서비스는 팀이 시작하기 전에 막아요. 단어가 아니라 제품이 하는 일로 판단해요."],
];

// What each code prefix means, for a reader who has never seen the codes (tooltips and cards).
export const PREFIXES: Record<string, [string, string]> = {
  SRC: ["발주사 원문", "처음 받은 메모를 한 문장씩 나눠 붙인 번호예요. SRC-05는 다섯 번째 문장이에요."],
  REQ: ["요구사항", "만들어야 할 기능 하나하나에 붙인 번호예요. PRD에 모여 있어요."],
  SCR: ["화면", "화면설계서에 나오는 화면 번호예요."],
  TC: ["테스트 케이스", "잘 만들어졌는지 확인하는 시험 항목 번호예요."],
  EV: ["출처", "리서처가 Liner 검색으로 찾은 근거 자료 번호예요."],
  DEC: ["고른 답", "질문 카드에서 발주사가 고른 답의 번호예요."],
  Q: ["질문 카드", "팀이 발주사에게 물어본 질문 번호예요."],
  OPEN: ["열린 항목", "아직 정하지 못하고 남겨 둔 항목 번호예요."],
  FND: ["QA 지적", "QA가 찾은 빈틈 번호예요."],
  PROTO: ["프로토타입", "개발자가 만든 프로토타입의 판 번호예요."],
  CF: ["확인 기록", "발주사가 확인 단계에서 승인하거나 반려한 기록 번호예요."],
  CHG: ["변경 요청", "확정한 뒤 들어온 변경 요청 번호예요."],
  CMP: ["불만", "「이거 아닌데요」로 들어온 불만 번호예요."],
  ANS: ["질문에 대한 답", "확인 단계에서 남긴 질문에 팀이 답한 번호예요."],
  ALT: ["기존 제품", "이미 나와 있는 비슷한 제품의 번호예요."],
  OPS: ["운영 확인 항목", "화면을 눌러 보는 대신 사람이 업무나 데이터로 확인할 항목이에요. 테스트 케이스 문서에 따로 모여 있어요."],
  SYS: ["우리 시스템", "회사가 이미 운영하는 시스템 목록의 번호예요. 처음에 「우리 시스템 목록」에 적은 순서대로 붙어요."],
  CP: ["확인 단계", "발주사가 결과를 보고 승인하는 관문이에요. CP1~CP4는 한 번씩, CP5는 바꿀 때마다 거쳐요."],
  S: ["작업 단계", "팀이 일하는 7단계(S1~S7) 중 하나예요."],
  G: ["안전장치", "잘못된 결과가 나가지 않게 막는 9가지 장치(G1~G9) 중 하나예요."],
};

export interface CodeMeaning {
  kind: string;
  about: string;
}

// "SRC-05" → 발주사 원문 + what SRC codes are; null for anything that is not a known code shape.
export function codeMeaning(id: string): CodeMeaning | null {
  const m = /^([A-Z]+)-?\d+$/.exec(id);
  const entry = m ? PREFIXES[m[1]] : undefined;
  return entry ? { kind: entry[0], about: entry[1] } : null;
}

export function refCatalog(source: Record<string, unknown> | null | undefined): Record<string, RefInfo> {
  const out: Record<string, RefInfo> = {};
  for (const [id, kind, title, about] of GLOSSARY) out[id] = { id, kind, title, lines: [{ label: "하는 일", value: about }], doc: null };
  if (!source) return out;
  const add = (id: unknown, kind: string, title: unknown, lines: { label: string; value: string }[], doc: DocId | null) => {
    if (typeof id === "string" && id) out[id] = { id, kind, title: text(title) || id, lines: kept(lines), doc };
  };
  for (const r of items(source, "requirements")) {
    const a = (r.acceptance ?? {}) as Item;
    const accept = [a.given, a.when, a.then].map(text).filter(Boolean).join(" → ");
    add(r.id, "요구사항", r.title, [line("내용", r.statement), line("상태", r.status), line("확인 기준", accept)], "prd");
  }
  for (const s of items(source, "screens")) add(s.id, "화면", s.title, [line("목적", s.purpose)], "screens");
  for (const t of items(source, "tests")) {
    add(t.id, "테스트 케이스", t.title, [line("확인할 것", t.objective), line("기대 결과", t.expected), line("요구사항", t.requirement_refs)], "tests");
  }
  for (const d of items(source, "decisions")) {
    const replaced = d.superseded_by ? ` (나중에 ${text(d.superseded_by)}로 바뀜)` : "";
    add(d.id, "고른 답", d.chosen, [line("질문", d.topic), line("상태", `${text(d.status)}${replaced}`)], "prd");
  }
  for (const s of items(source, "sources")) add(s.id, "발주사 원문", s.text, [], null);
  for (const e of items(source, "evidence")) add(e.id, "출처", e.title, [line("사실", e.fact), line("인용", e.quote), line("링크", e.url)], null);
  for (const q of items(source, "questions")) add(q.id, "질문 카드", q.question, [line("왜 묻나", q.why), line("답", (q.answer as Item | null)?.value ?? q.status)], null);
  for (const o of items(source, "open_items")) add(o.id, "열린 항목", o.title, [line("이유", o.reason)], null);
  for (const f of items(source, "findings")) add(f.id, "QA 지적", f.note, [line("요구사항", f.requirement_ids)], null);
  for (const c of items(source, "changes")) add(c.id, "변경 요청", c.utterance, [line("상태", c.status)], null);
  for (const c of items(source, "confirmations")) {
    const verdict = c.approved === false ? "반려" : "승인";
    add(c.id, "확인 기록", `${text(c.cp)} ${verdict}`, [line("누가", c.who), line("버전", c.version ?? c.based_on), line("사유", c.reason)], null);
  }
  for (const m of items(source, "complaints")) add(m.id, "불만", m.text, [line("판정", m.classification)], null);
  for (const r of items(source, "replies")) add(r.id, "질문에 대한 답", r.question, [line("답", r.answer)], null);
  for (const a of items(source, "alternatives")) add(a.id, "기존 제품", a.name, [line("되는 것", a.covers), line("안 되는 것", a.lacks)], null);
  for (const plan of items(source, "test_plan")) {
    const ops = Array.isArray(plan.ops_checks) ? (plan.ops_checks as Item[]) : [];
    for (const o of ops) add(o.id, "운영 확인 항목", o.title, [line("확인 방법", o.how), line("요구사항", o.requirement_refs)], "tests");
  }
  for (const sys of items(source, "systems")) add(sys.id, "우리 시스템", sys.name, [line("하는 일", sys.about)], null);
  return out;
}

// The element a document gives a listed item's row, so a link can scroll to it.
export function refAnchor(doc: DocId, id: string): string {
  return `ref-${doc}-${id}`.replace(/[^A-Za-z0-9_-]/g, "_");
}
