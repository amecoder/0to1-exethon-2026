// Korean labels for internal values (stage ids, pipeline status, event types, guardrails, schemas)
// and the 9-step progress model. Pure data + functions so they can be unit-tested.

export type View = "client" | "team";

export const STAGE_TITLE: Record<string, string> = {
  S1: "요구 입력",
  S2: "문제 인식",
  CP1: "문제·범위 확인",
  S3: "구체화",
  S4: "원본 확정",
  CP2: "요구사항 원본 확인",
  S5: "문서화",
  CP3: "문서 4종 확인",
  S6: "프로토타입 작성",
  CP4: "프로토타입 인수",
  CP5: "변경 체크포인트(CP5)",
};

export const STATUS_KO: Record<string, string> = {
  awaiting_input: "입력 기다림",
  running: "팀 작업 중",
  awaiting_answers: "답 기다림",
  awaiting_confirmation: "확인 기다림",
  awaiting_scope: "범위 고르기 기다림",
  stopped: "상한에 닿아 멈춤",
  failed: "작업 실패",
  completed: "완료",
  closed: "기존 제품 쓰기로 마침",
};

export const EVENT_TYPE_KO: Record<string, string> = {
  stage_started: "단계 시작",
  stage_completed: "단계 완료",
  pipeline: "진행 상태",
  agent_message: "메시지",
  message_rerouted: "중계",
  liner_chat: "Liner 모델",
  liner_search: "Liner 검색",
  liner_decision: "Liner 판정",
  liner_rerank: "Liner 재정렬",
  liner_visualization: "Liner 시각화",
  liner_transcription: "Liner 받아쓰기",
  liner_image: "Liner 이미지 생성",
  credits: "크레딧",
  guardrail: "가드레일",
  item_written: "기록",
  write_rejected: "쓰기 거부",
  question_answered: "답변",
  confirmation: "확인",
  version_created: "버전 고정",
  check_result: "검사",
  ref_dropped: "참조 정리",
  run_interrupted: "중단",
  run_retried: "다시 시도",
  recheck_required: "다시 확인 필요",
  recheck_cleared: "다시 확인 끝",
  change_revised: "변경 반영",
  bundle_cleared: "다시 쓰기",
  prototype_built: "프로토타입",
};

export const GUARDRAIL_KO: Record<string, string> = {
  G1: "사실 확인",
  G2: "확인 절차",
  G3: "민감 정보 차단",
  G4: "원문 보호",
  G5: "가정 표시",
  G6: "생성 코드 격리",
  G7: "비용·시간 상한",
  G8: "입력 범위 제한",
  G9: "용도 검사",
};

export const OUTCOME_KO: Record<string, string> = {
  flagged: "표시",
  masked: "가림",
  blocked: "막음",
  stripped: "제거",
  rejected: "거부",
  passed: "통과",
  resumed: "계속",
  resolved: "해결",
  skipped: "건너뜀",
};

// liner_chat `schema` → what the agent was doing.
export const SCHEMA_ACTION: Record<string, string> = {
  problem_scope: "문제와 범위를 정리",
  intake_triage: "요청 접수 상태를 판정",
  research_evidence: "검색 결과에서 근거를 추리",
  requirement_candidates: "요구사항 후보를 작성",
  qa_findings: "빠진 예외와 충돌을 점검",
  question_cards: "질문 카드를 정리",
  requirements_final: "답을 반영해 요구사항을 확정",
  screen_spec: "화면설계서를 작성",
  test_cases: "테스트 케이스를 작성",
  document_content: "BRD·PRD를 작성",
  prototype: "프로토타입을 작성",
  consumer_feedback: "고객 입장에서 의견을 정리",
  change_mapping: "변경 요청이 바꾸는 요구사항을 확인",
  complaint_check: "확정 기록과 불만을 대조",
};

// What an agent does in a stage (used while it works, before its Liner call is logged).
const STAGE_ACTION: Record<string, Record<string, string>> = {
  S2: { coordinator: "작업을 배정", fde_lead: "문제와 범위를 정리", researcher: "Liner로 근거를 검색" },
  S3: { coordinator: "질문 카드를 정리", pm: "요구사항 후보를 작성", qa: "빠진 예외와 충돌을 점검" },
  S4: { coordinator: "답을 정리", pm: "답을 반영해 요구사항을 확정" },
  S5: { coordinator: "빈칸을 검사", pm: "BRD·PRD를 작성", designer: "화면설계서를 작성", qa: "테스트 케이스를 작성", consumer: "고객 입장에서 화면을 검토" },
  S6: { coordinator: "작업을 배정", designer: "화면을 넘겨줌", developer: "프로토타입을 작성", qa: "체크리스트를 대조", consumer: "고객 입장에서 프로토타입을 검토" },
};

export function stageAction(stage: string, agent: string): string | null {
  return STAGE_ACTION[stage]?.[agent] ?? null;
}

// --- progress bar --------------------------------------------------------------------------------

export interface Step {
  key: string;
  label: string;
  confirm: boolean;
  stages: string[];
}

export const STEPS: Step[] = [
  { key: "input", label: "요구 입력", confirm: false, stages: ["S1"] },
  { key: "problem", label: "문제 정리", confirm: false, stages: ["S2"] },
  { key: "CP1", label: "문제·범위 확인", confirm: true, stages: ["CP1"] },
  { key: "questions", label: "질문·답", confirm: false, stages: ["S3", "S4"] },
  { key: "CP2", label: "요구사항 확인", confirm: true, stages: ["CP2"] },
  { key: "docs", label: "문서 4종", confirm: false, stages: ["S5"] },
  { key: "CP3", label: "프로토타입 작성 확인", confirm: true, stages: ["CP3"] },
  { key: "dev", label: "프로토타입 개발", confirm: false, stages: ["S6"] },
  { key: "CP4", label: "인수 확인", confirm: true, stages: ["CP4"] },
];

export type StepState = "done" | "current" | "todo";

export interface Progress {
  current: number; // index into STEPS; STEPS.length when the run is completed
  states: StepState[];
  remainingConfirmations: number;
}

export function progressOf(stage: string | undefined, status: string | undefined): Progress {
  const completed = status === "completed";
  const found = STEPS.findIndex((s) => s.stages.includes(stage ?? "S1"));
  const current = completed ? STEPS.length : Math.max(found, 0);
  const states = STEPS.map((_, i): StepState => (i < current ? "done" : i === current ? "current" : "todo"));
  const remainingConfirmations = STEPS.filter((s, i) => s.confirm && i >= current).length;
  return { current, states, remainingConfirmations };
}

// --- Korean particles ----------------------------------------------------------------------------

// Latin letters read aloud with a final consonant (엠, 엘, 엔): "PM이", "URL을" but "QA가".
const LATIN_FINAL = new Set(["L", "M", "N"]);

function hasFinalConsonant(word: string): boolean {
  const trimmed = word.trim();
  const ch = trimmed.charAt(trimmed.length - 1);
  if (/[A-Za-z]/.test(ch)) return LATIN_FINAL.has(ch.toUpperCase());
  const last = ch.charCodeAt(0);
  if (last < 0xac00 || last > 0xd7a3) return false;
  return (last - 0xac00) % 28 !== 0;
}

// Generic particle pick for text built from a variable word: josa("프로토타입", "을/를") → "프로토타입을".
// The first form follows a final consonant, the second does not.
export function josa(word: string, pair: "을/를" | "이/가" | "은/는" | "과/와"): string {
  const [withFinal, without] = pair.split("/");
  return word + (hasFinalConsonant(word) ? withFinal : without);
}

// "조율자" → "조율자가", "디자인팀" → "디자인팀이"
export function withSubject(word: string): string {
  return word + (hasFinalConsonant(word) ? "이" : "가");
}

// "프로토타입" → "프로토타입을", "화면설계서" → "화면설계서를"
export function withObject(word: string): string {
  return word + (hasFinalConsonant(word) ? "을" : "를");
}
