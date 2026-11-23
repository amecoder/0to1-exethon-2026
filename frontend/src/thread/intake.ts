// S1 intake triage (app/intake_triage.py): pure helpers for the conversation before the team gets anything.
import type { TriageAnswer, TriageQuestion, TriageSlot, TriageSlots } from "../api";

export const SLOTS: readonly TriageSlot[] = ["who", "pain", "done"];
export const SLOT_LABEL: Record<TriageSlot, string> = { who: "누가 쓰는지", pain: "무엇이 불편한지", done: "무엇이 되면 끝인지" };
const HEADING = "접수 대화에서 받은 답:";

export type Drafts = Partial<Record<TriageSlot, string>>;

// The answers go to the team as one extra chunk of the request, so S2 reads them beside the memo. Each line is
// the slot name and the client's own words — the question is left out because its examples ("예: …") would
// otherwise be split into source sentences the client never said.
export function answersChunk(answers: readonly TriageAnswer[]): string | null {
  const lines = answers.filter((a) => a.answer.trim()).map((a) => `- ${SLOT_LABEL[a.slot]}: ${a.answer.trim()}`);
  return lines.length ? [HEADING, ...lines].join("\n") : null;
}

export function withAnswersChunk(chunks: readonly string[], answers: readonly TriageAnswer[]): string[] {
  const chunk = answersChunk(answers);
  const kept = chunks.filter((c) => c.trim());
  return chunk ? [...kept, chunk] : kept;
}

export function missingSlots(slots: TriageSlots): TriageSlot[] {
  return SLOTS.filter((s) => !slots[s].trim());
}

// Earlier rounds' answers stay (the model judges all of them); this round's drafts are added.
export function addAnswers(earlier: readonly TriageAnswer[], questions: readonly TriageQuestion[], drafts: Drafts): TriageAnswer[] {
  const added = questions
    .map((q) => ({ slot: q.slot, question: q.question, answer: (drafts[q.slot] ?? "").trim() }))
    .filter((a) => a.answer);
  return [...earlier, ...added];
}

export function canRecheck(questions: readonly TriageQuestion[], drafts: Drafts): boolean {
  return questions.length > 0 && questions.every((q) => (drafts[q.slot] ?? "").trim() !== "");
}

// A refusal or an unreadable verdict is about the memo as it was; once the memo changes or is sent again it
// would only confuse (11-22: the 「맡을 수 없는 요청」 card stayed under the next memo). A thin request's questions stay.
export function keepsVerdict(verdict: { case: string } | null): boolean {
  return verdict?.case === "insufficient";
}
