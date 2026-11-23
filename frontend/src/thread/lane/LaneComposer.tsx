import { ArrowUp, LoaderCircle, MessageSquareWarning, PencilLine } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Lane } from "../../api";

export type Intent = "change" | "complaint";

const INTENTS: { id: Intent; label: string; icon: typeof PencilLine; placeholder: string; hint: string }[] = [
  {
    id: "change",
    label: "바꾸고 싶어요",
    icon: PencilLine,
    placeholder: "예) 일시정지는 배송 하루 전까지 되게 해 주세요",
    hint: "무엇이 영향을 받는지 먼저 보여 드리고, 승인하셔야 바뀌어요.",
  },
  {
    id: "complaint",
    label: "이거 아닌데요",
    icon: MessageSquareWarning,
    placeholder: "예) 일시정지가 아무 때나 돼야 하는데 마감 뒤에는 안 돼요",
    hint: "확정했던 기록과 맞춰 보고, 약속과 다른 건지 새 요청인지 근거와 함께 알려 드려요.",
  },
];

// The quiet composer at the bottom of the thread (after CP2): one line, two intents. FR-21 / FR-22.
export default function LaneComposer({ lane, onSend }: { lane: Lane; onSend: (intent: Intent, text: string) => Promise<void> }) {
  const [intent, setIntent] = useState<Intent>("change");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const current = INTENTS.find((i) => i.id === intent)!;
  const ready = lane.open && text.trim().length > 0 && !busy;

  return (
    <section aria-label="바꾸거나 바로잡기" className="flex animate-rise flex-col gap-2.5 border-t border-white/[0.06] pt-6">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="무엇을 하실지">
        {INTENTS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            aria-pressed={intent === id}
            onClick={() => setIntent(id)}
            className={cn(
              "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring",
              intent === id
                ? "border-primary-text/50 bg-primary-soft text-foreground"
                : "border-border text-muted-foreground hover:bg-white/[0.05] hover:text-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>
      <form
        className="flex items-center gap-2 rounded-2xl border border-border bg-white/[0.03] py-1.5 pr-1.5 pl-4 focus-within:border-primary-text/60"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!ready) return;
          setBusy(true);
          try {
            await onSend(intent, text.trim());
            setText("");
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor="lane-text" className="sr-only">
          {current.label} — 한 줄로 적기
        </label>
        <input
          id="lane-text"
          value={text}
          maxLength={300}
          disabled={!lane.open}
          onChange={(e) => setText(e.target.value)}
          placeholder={lane.open ? current.placeholder : lane.reason ?? ""}
          aria-describedby="lane-hint"
          className="h-10 min-w-0 flex-1 border-0 bg-transparent p-0 text-base text-foreground outline-none placeholder:text-faint focus-visible:outline-none disabled:cursor-not-allowed"
        />
        <Button type="submit" size="icon" aria-label="보내기" disabled={!ready}>
          {busy ? <LoaderCircle className="animate-spin" /> : <ArrowUp />}
        </Button>
      </form>
      <p id="lane-hint" className="px-1 text-sm break-keep text-muted-foreground">
        {lane.open ? current.hint : lane.reason}
      </p>
    </section>
  );
}
