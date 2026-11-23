import { ArrowRight, LoaderCircle, Pencil } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { QuestionCard } from "../api";
import { changedDefaults, type TeamDefault } from "./teamDefaults";

// After the last card: every answer at a glance, each one fixable, and nothing moves on until
// 「이대로 진행」 — the team fixes the requirements (S4) from exactly these answers.
export default function AnswersReview({ questions, defaults = [], onEdit, onSubmit }: {
  questions: QuestionCard[];
  defaults?: TeamDefault[]; // 11-22: what the cards did not ask, with the team's default answer
  onEdit?: (id: string) => void;
  onSubmit?: (changes: Record<string, string>) => Promise<void>; // absent in demo replay
}) {
  const [busy, setBusy] = useState(false);
  const [edits, setEdits] = useState<Record<string, string>>({});
  return (
    <Card className="animate-rise px-8 pt-7 pb-6" aria-labelledby="review-title">
      <p className="text-sm font-semibold text-primary-text">
        {questions.length > 0 ? `질문 ${questions.length}개에 모두 답했어요` : "카드로 물을 질문은 없었어요"}
      </p>
      <h2 id="review-title" className="mt-3 text-title font-bold tracking-[-0.02em] break-keep text-foreground">
        고른 답을 한 번 확인해 주세요
      </h2>
      <p className="mt-2 text-base break-keep text-muted-foreground">
        잘못 고른 답이 있으면 「고치기」로 다시 고를 수 있어요. 「이대로 진행」을 누르면 이 답으로 요구사항을 확정해요.
      </p>
      <ol className="mt-5 flex flex-col gap-2">
        {questions.map((q, i) => (
          <li key={q.id} className="flex items-start gap-3 rounded-2xl border border-border bg-white/[0.025] px-4 py-3">
            <span className="mt-0.5 text-sm font-semibold text-muted-foreground tabular-nums">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm break-keep text-muted-foreground">{q.question}</p>
              <p className="mt-1 text-base font-semibold break-keep text-foreground">
                {q.answer?.value ?? "아직 답하지 않았어요"}
                {q.answer?.status === "가정" && <span className="ml-1.5 text-sm font-normal text-muted-foreground">· 잘 모르겠어요(기본값으로 가정)</span>}
              </p>
            </div>
            {onEdit && (
              <Button variant="ghost" size="sm" onClick={() => onEdit(q.id)} disabled={busy} aria-label={`${i + 1}번 질문 답 고치기`}>
                <Pencil /> 고치기
              </Button>
            )}
          </li>
        ))}
      </ol>
      {defaults.length > 0 && <TeamDefaults defaults={defaults} edits={edits} onEdit={onSubmit && !busy ? setEdits : undefined} />}
      {onSubmit ? (
        <Button
          size="lg"
          className="mt-6"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onSubmit(changedDefaults(defaults, edits));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <LoaderCircle className="animate-spin" /> : <ArrowRight />} 이대로 진행
        </Button>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">녹화 당시 발주사가 여기서 답을 확인하고 진행했어요.</p>
      )}
    </Card>
  );
}

// The points the cards did not ask: the team's default and why, each line editable; untouched lines are kept as is.
function TeamDefaults({ defaults, edits, onEdit }: {
  defaults: TeamDefault[];
  edits: Record<string, string>;
  onEdit?: (edits: Record<string, string>) => void;
}) {
  return (
    <section className="mt-6 border-t border-border pt-6" aria-labelledby="team-defaults-title">
      <h3 id="team-defaults-title" className="text-base font-bold break-keep text-foreground">
        카드로 묻지 않은 점 {defaults.length}개 — 팀이 정한 기본값
      </h3>
      <p className="mt-1 text-sm break-keep text-muted-foreground">
        원문이나 흔한 방식으로 팀이 먼저 정했어요. 다르게 하고 싶은 줄만 고쳐 주세요. 그대로 두면 이 기본값으로 진행해요.
      </p>
      <ol className="mt-4 flex flex-col gap-2">
        {defaults.map((d) => (
          <li key={d.id} className="rounded-2xl border border-border bg-white/[0.025] px-4 py-3">
            <p className="text-sm break-keep text-muted-foreground">{d.title}</p>
            {onEdit ? (
              <input
                aria-label={`${d.title} — 팀 기본값`}
                className="mt-1.5 block w-full rounded-xl border-0 bg-white/[0.04] px-3 py-2 text-base font-semibold text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring"
                maxLength={500}
                value={edits[d.id] ?? d.team_default}
                onChange={(e) => onEdit({ ...edits, [d.id]: e.target.value })}
              />
            ) : (
              <p className="mt-1 text-base font-semibold break-keep text-foreground">{d.team_default}</p>
            )}
            {d.team_why && <p className="mt-1.5 text-xs break-keep text-faint">왜: {d.team_why}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}
