import { UserRound } from "lucide-react";
import type { FeedbackItem } from "../../api";
import { josa } from "../../lib/labels";
import { RefId, useTitles, useView } from "../../ui/view";

const KIND_TONE: Record<FeedbackItem["kind"], string> = {
  헷갈림: "bg-primary-soft text-primary-text",
  불편: "bg-cyan-soft text-cyan",
  "포기 위험": "bg-warning-soft text-warning",
};

// FR-20: what the consumer agent (a customer persona) felt on each screen. Opinion only — it never blocks
// approval and does not change requirements; the PM and the client decide what to do with it.
export default function FeedbackChips({ items, cp }: { items: FeedbackItem[]; cp: "CP3" | "CP4" }) {
  const team = useView() === "team";
  const titles = useTitles();
  if (items.length === 0) return null;
  return (
    <section aria-labelledby={`feedback-${cp}`} className="rounded-2xl border border-border bg-white/[0.025] p-4">
      <h3 id={`feedback-${cp}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-base font-semibold text-foreground">
        <span className="grid size-7 place-items-center rounded-lg bg-cyan-soft text-cyan" aria-hidden="true">
          <UserRound className="size-4" />
        </span>
        고객이 {josa(cp === "CP3" ? "화면설계서" : "프로토타입", "을/를")} 보고 남긴 말 {items.length}건
        <span className="text-xs font-medium text-muted-foreground">참고 · 승인을 막지 않아요</span>
      </h3>
      <p className="mt-1 text-xs break-keep text-faint">
        소비자 에이전트의 의견이에요. 요구사항을 바꿀지는 PM과 발주사가 정해요.
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {items.map((f) => (
          <li key={f.id} className="flex flex-col gap-1.5 rounded-xl border border-white/[0.06] bg-deep/50 px-3.5 py-2.5 sm:flex-row sm:items-start sm:gap-3">
            <span className="flex shrink-0 items-center gap-1.5">
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${KIND_TONE[f.kind] ?? KIND_TONE["불편"]}`}>{f.kind}</span>
              <span className="text-xs font-medium text-muted-foreground">{titles[f.screen_id] ?? "화면"}</span>
              <RefId id={f.screen_id} />
              {team && <RefId id={f.id} />}
            </span>
            <span className="min-w-0 text-sm break-keep text-soft">“{f.comment}”</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
