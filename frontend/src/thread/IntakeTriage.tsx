import { Ban, Check, CircleAlert, CircleHelp, LoaderCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TriageAnswer, TriageVerdict } from "../api";
import { canRecheck, type Drafts, SLOT_LABEL, SLOTS } from "./intake";

const TITLE = {
  insufficient: "팀에 넘기기 전에 몇 가지만 여쭤볼게요",
  cannot: "이 팀이 맡을 수 없는 요청이에요",
  garbled: "요청을 읽기 어려워요",
} as const;

// The S1 intake conversation shown under the memo box: questions for the empty slots, or why it cannot go on.
export default function IntakeTriage({
  verdict,
  answers,
  drafts,
  busy,
  onDraft,
  onRecheck,
  onRestart,
}: {
  verdict: TriageVerdict;
  answers: TriageAnswer[];
  drafts: Drafts;
  busy: boolean;
  onDraft: (slot: TriageAnswer["slot"], value: string) => void;
  onRecheck: () => void;
  onRestart: () => void;
}) {
  if (verdict.case === "ok") return null;
  const asking = verdict.case === "insufficient";
  const Icon = asking ? CircleHelp : verdict.case === "cannot" ? Ban : CircleAlert;
  return (
    <section aria-label="접수 확인" aria-live="polite" className="flex flex-col gap-4 rounded-2xl border border-border bg-white/[0.025] px-5 py-4">
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 size-5 shrink-0 ${asking ? "text-cyan" : "text-warning"}`} aria-hidden="true" />
        <div>
          <p className="font-semibold text-foreground">{TITLE[verdict.case]}</p>
          <p className="text-sm break-keep text-soft">{verdict.reason}</p>
          {!asking && <p className="mt-1 text-xs text-muted-foreground">위 메모 칸을 고쳐서 「팀에게 보내기」를 다시 눌러 주세요.</p>}
        </div>
      </div>
      {asking && (
        <>
          <ul aria-label="지금까지 확인한 것" className="flex flex-col gap-1.5 text-sm">
            {SLOTS.map((slot) => {
              const value = verdict.slots[slot];
              return (
                <li key={slot} className="flex items-start gap-2">
                  {value ? (
                    <Check className="mt-0.5 size-4 shrink-0 text-cyan" aria-label="확인됨" />
                  ) : (
                    <span className="mt-1.5 size-2 shrink-0 rounded-full border border-faint" aria-label="아직 없음" />
                  )}
                  <span className="shrink-0 font-semibold text-foreground">{SLOT_LABEL[slot]}</span>
                  <span className={`break-keep ${value ? "text-soft" : "text-faint"}`}>{value || "아직 없어요"}</span>
                </li>
              );
            })}
          </ul>
          {verdict.questions.map((q) => (
            <div key={q.slot} className="flex flex-col gap-1.5">
              <label htmlFor={`triage-${q.slot}`} className="text-sm font-semibold break-keep text-foreground">
                {q.question}
              </label>
              <textarea
                id={`triage-${q.slot}`}
                rows={2}
                maxLength={500}
                value={drafts[q.slot] ?? ""}
                onChange={(e) => onDraft(q.slot, e.target.value)}
                className="block w-full resize-y rounded-xl border-0 bg-white/[0.03] px-3 py-2.5 text-sm leading-relaxed text-foreground outline-none placeholder:text-faint"
              />
            </div>
          ))}
          {answers.length > 0 && <p className="text-xs text-muted-foreground">앞서 답한 {answers.length}개도 함께 팀에 보내요.</p>}
        </>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {asking && (
          <Button size="sm" disabled={busy || !canRecheck(verdict.questions, drafts)} onClick={onRecheck}>
            {busy && <LoaderCircle className="animate-spin" />} 답하고 다시 확인하기
          </Button>
        )}
        <Button variant="ghost" size="sm" disabled={busy} onClick={onRestart}>
          <RotateCcw /> 처음부터 다시 쓰기
        </Button>
      </div>
    </section>
  );
}
