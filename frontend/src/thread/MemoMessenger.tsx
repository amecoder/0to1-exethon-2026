import { MessageCircle, Zap } from "lucide-react";
import { PROBLEM_HEADLINE, PROBLEM_LINE } from "../brand";
import type { OpeningMemo } from "../lib/opening";
import { RefId, useView } from "../ui/view";

// Demo opening: the client's memo as it arrived in the messenger, with the two sentences that later turn
// out to conflict marked. Built from the recording (sources + the team's conflict finding), read-only.
export default function MemoMessenger({ memo }: { memo: OpeningMemo }) {
  const team = useView() === "team";
  const conflictLines = memo.bubbles.flatMap((b) => b.lines).filter((l) => l.conflict);
  return (
    <section className="flex animate-rise flex-col gap-5" aria-labelledby="opening-title">
      <div className="flex flex-col gap-2">
        <h2 id="opening-title" className="text-title font-bold tracking-[-0.02em] text-balance break-keep text-foreground">
          {PROBLEM_HEADLINE}
        </h2>
        <p className="text-base break-keep text-muted-foreground">{PROBLEM_LINE}</p>
      </div>
      {memo.conflict && (
        <div className="flex items-start gap-2 rounded-2xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm break-keep text-warning" role="note">
          <Zap className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div className="flex flex-col gap-1">
            <p className="font-semibold">아래 메모의 두 문장이 서로 부딪혀요{memo.conflict.note ? ` — ${memo.conflict.note}` : ""}</p>
            <ul className="flex flex-col gap-0.5 text-soft">
              {conflictLines.map((l) => (
                <li key={l.id}>“{l.text}”</li>
              ))}
            </ul>
            <p>아무도 기록하지 않으면 나중에 “아 이거 아닌데?”가 돼요.</p>
          </div>
        </div>
      )}
      <div className="glass flex flex-col gap-3 rounded-3xl px-5 py-5" aria-label="발주사가 보낸 메신저 메모">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
          <MessageCircle className="size-3.5 text-cyan" aria-hidden="true" /> 발주사 메신저 · 받은 그대로
        </p>
        <ol className="flex flex-col gap-2.5">
          {memo.bubbles.map((b, i) => (
            <li key={i} className="flex flex-col items-start gap-1">
              {b.time && <span className="pl-1 text-xs tabular-nums text-faint">{b.time}</span>}
              <p className="max-w-[88%] rounded-3xl rounded-tl-lg border border-white/[0.08] bg-white/[0.07] px-4 py-2.5 text-base leading-relaxed break-keep text-foreground">
                {b.lines.map((l) => (
                  <span key={l.id}>
                    {l.conflict ? (
                      <mark className="rounded-md bg-warning-soft px-1 text-warning ring-1 ring-warning/50">{l.text}</mark>
                    ) : (
                      l.text
                    )}
                    {team && <RefId id={l.id} />}{" "}
                  </span>
                ))}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
