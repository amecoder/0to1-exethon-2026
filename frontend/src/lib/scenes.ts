// Demo-player scenes: key moments of a recorded run, found from its events.
// Replay step N shows the state after the first N events, so an event with seq N is visible at step N.
import type { AppEvent } from "../api";

export type SceneKind =
  | "input" | "team" | "CP1" | "question" | "CP2" | "documents" | "CP3" | "prototype" | "CP4" | "done"
  | "change" | "CP5" | "rework" | "complaint" | "verdict";

export interface Scene {
  step: number;
  kind: SceneKind;
  label: string;
  caption: string;
}

const CONFIRM: Record<string, { label: string; caption: string }> = {
  CP1: { label: "CP1 문제·범위", caption: "발주사가 팀이 정리한 문제와 범위를 보고 맞다고 확인해요" },
  CP2: { label: "CP2 요구사항", caption: "내가 고른 답이 요구사항에 그대로 들어갔는지 나란히 비교하고 고정해요 — 이제 합의가 기록으로 남아요" },
  CP3: { label: "CP3 프로토타입 작성", caption: "문서 4종을 옆 창에서 열어 보고, 빈칸에 이유를 적고 프로토타입 작성을 승인해요" },
  CP4: { label: "CP4 인수", caption: "안전한 칸 안에서 프로토타입을 직접 눌러 보고 인수해요" },
};

// The same kinds come back during rework after an approved change; they get their own names there.
const REWORK: Partial<Record<SceneKind, { label: string; caption: string }>> = {
  documents: { label: "문서 다시 쓰기", caption: "바뀐 요구사항이 닿는 문서만 다시 써요 — 영향받은 담당이 다시 확인해요" },
  CP3: { label: "CP3 다시 확인", caption: "변경을 반영한 문서 4종을 다시 확인해요" },
  prototype: { label: "프로토타입 다시 만들기", caption: "바뀐 문서로 프로토타입을 다시 만들었어요" },
  CP4: { label: "CP4 다시 인수", caption: "새 프로토타입을 인수하면 내려받기가 다시 열려요" },
  done: { label: "재작업 완료", caption: "변경까지 반영해 다시 인수했어요 — 바뀐 내용도 기록에 남았어요" },
};

function quoted(text: unknown, max = 40): string {
  const t = String(text ?? "").trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

export function extractScenes(events: AppEvent[]): Scene[] {
  const scenes: Scene[] = [];
  let rework = false;
  const add = (step: number, kind: SceneKind, label: string, caption: string) => {
    const again = kind === "done" && scenes.some((s) => s.kind === "done");
    const named = rework || again ? REWORK[kind] : undefined;
    const final = named ?? { label, caption };
    if (scenes.some((s) => s.label === final.label)) return;
    scenes.push({ step, kind, label: final.label, caption: final.caption });
  };
  const seenStatus = new Map<string, string>();
  let lastStatus: string | undefined;
  let questionNo = 0;
  events.forEach((e, i) => {
    const d = e.data ?? {};
    if (e.type === "stage_started" && d.stage === "S1") {
      add(e.seq, "input", "요구 입력", "발주사가 메신저로 받은 메모예요 — 서로 부딪히는 두 문장이 아무 기록 없이 섞여 있어요");
    } else if (e.type === "stage_started" && d.stage === "S2") {
      add(e.seq, "team", "팀 작업 시작", "FDE 리드가 문제를 정리하고 리서처가 Liner 검색으로 근거를 찾아요 — 추적 지도가 자라나요");
    } else if (e.type === "pipeline" && d.status === "awaiting_answers" && questionNo === 0) {
      questionNo = 1;
      add(e.seq, "question", "질문 1", "메모끼리 부딪히는 곳을 질문 카드로 여쭤봐요 — 발주사는 고르기만 하면 돼요");
    } else if (e.type === "question_answered" && questionNo > 0 && moreAnswersFollow(events, i)) {
      questionNo += 1;
      add(e.seq, "question", `질문 ${questionNo}`, "다음 질문이에요 — 모르면 「잘 모르겠어요」를 고르면 기본값으로 가정해요");
    } else if (e.type === "pipeline" && d.status === "awaiting_confirmation" && CONFIRM[d.stage]) {
      add(e.seq, d.stage as SceneKind, CONFIRM[d.stage].label, CONFIRM[d.stage].caption);
    } else if (e.type === "stage_completed" && d.stage === "S5") {
      add(e.seq, "documents", "문서 4종", "PM·디자이너·QA가 같은 원본으로 문서 4종을 써요 — 요구사항이 화면과 테스트로 이어져요");
    } else if (e.type === "prototype_built") {
      add(e.seq, "prototype", "프로토타입", "개발자 에이전트가 확정된 문서로 프로토타입을 만들었어요");
    } else if (e.type === "pipeline" && d.status === "completed" && lastStatus !== "completed") {
      add(e.seq, "done", "인수 완료", "인수 완료 — 프로토타입과 문서 4종을 zip 하나로 내려받아요");
    } else if (e.type === "recheck_required") {
      rework = true;
      add(e.seq, "rework", "다시 만들기(재작업)", "PM이 변경과 어긋나는 요구사항부터 고치고, 그 요구사항으로 문서·화면·테스트·프로토타입을 다시 만들어요 — 내려받기는 다시 인수할 때까지 잠가요");
    } else if (e.type === "recheck_cleared") {
      rework = false;
    } else if (e.type === "item_written" && (d.kind === "changes" || d.kind === "complaints")) {
      const item = d.item ?? {};
      const key = `${d.kind}:${item.id}`;
      const before = seenStatus.get(key);
      seenStatus.set(key, String(item.status));
      if (before === item.status) return;
      if (d.kind === "changes" && item.status === "mapping") {
        add(e.seq, "change", "변경 요청", `확정 뒤에 발주사가 「${quoted(item.utterance)}」로 바꿔 달라고 해요 — PM이 바뀌는 요구사항을 찾아요`);
      } else if (d.kind === "changes" && item.status === "awaiting_cp5") {
        add(e.seq, "CP5", "변경 영향(CP5)", "바뀌는 요구사항·화면·테스트를 전후로 비교해 보고 확인 5로 정해요");
      } else if (d.kind === "complaints" && item.status === "checking") {
        add(e.seq, "complaint", "「아 이거 아닌데?」", `발주사가 「${quoted(item.text)}」라고 해요 — QA가 확정 기록과 대조해요`);
      } else if (d.kind === "complaints" && item.status === "classified") {
        add(e.seq, "verdict", "판정", `판정: ${item.classification ?? "사람 판단 필요"} — 근거 요구사항과 누가 언제 승인했는지를 함께 보여 줘요`);
      }
    }
    if (e.type === "pipeline") lastStatus = d.status;
  });
  return scenes.sort((a, b) => a.step - b.step);
}

// True when another answer is given before the question round ends (so a next card is showing).
function moreAnswersFollow(events: AppEvent[], index: number): boolean {
  for (let j = index + 1; j < events.length; j += 1) {
    const e = events[j];
    if (e.type === "question_answered") return true;
    if (e.type === "pipeline" && e.data?.status !== "awaiting_answers") return false;
  }
  return false;
}

// The scene being shown at `step` (the last one that started at or before it).
export function sceneAt(scenes: Scene[], step: number): Scene | null {
  let found: Scene | null = null;
  for (const s of scenes) if (s.step <= step) found = s;
  return found;
}

export function nextSceneStep(scenes: Scene[], step: number): number | null {
  return scenes.find((s) => s.step > step)?.step ?? null;
}

export function prevSceneStep(scenes: Scene[], step: number): number | null {
  const before = scenes.filter((s) => s.step < step);
  return before.length ? before[before.length - 1].step : null;
}
