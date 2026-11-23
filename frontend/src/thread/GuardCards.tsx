import { Check, CircleAlert, Gauge, Layers, LayoutGrid, LoaderCircle, Play } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatUsd } from "../lib/credits";
import type { Todo } from "../api";
import { STAGE_TITLE } from "../lib/labels";
import { RefId, useTitles, useView } from "../ui/view";
import { droppedFeatures } from "./scope";

type ScopeTodo = Extract<Todo, { kind: "scope" }>;
type LimitTodo = Extract<Todo, { kind: "limit" }>;

// G8: the designer drew more screens than this prototype takes. The client keeps up to `max`; the
// rest stay out (the coordinator records the choice as a decision). Read-only in demo replay.
export function ScopeCard({ todo, onKeep }: { todo: ScopeTodo; onKeep?: (keep: string[], keepAll?: boolean) => Promise<void> }) {
  const team = useView() === "team";
  const titles = useTitles();
  const [keep, setKeep] = useState<string[]>(() => todo.screens.slice(0, todo.max).map((s) => s.id));
  const [busy, setBusy] = useState(false);
  const full = keep.length >= todo.max;
  const lost = droppedFeatures(todo.screens, keep); // said here, not later as 빈칸 at CP3 (11-22)
  const send = async (ids: string[], all = false) => {
    if (!onKeep) return;
    setBusy(true);
    try {
      await onKeep(ids, all);
    } finally {
      setBusy(false);
    }
  };
  const toggle = (id: string) =>
    setKeep(keep.includes(id) ? keep.filter((k) => k !== id) : full ? keep : [...keep, id]);

  return (
    <Card className="animate-rise px-8 pt-7 pb-7" aria-labelledby="scope-title">
      <p className="flex items-center gap-2 text-sm font-semibold text-primary-text">
        <LayoutGrid className="size-4" aria-hidden="true" /> 범위 조정 · 화면은 {todo.max}개까지
        {team && <RefId id="G8" />}
      </p>
      <h2 id="scope-title" className="mt-3 text-title font-bold tracking-[-0.02em] text-balance break-keep text-foreground">
        화면이 {todo.screens.length}개 나왔어요. 먼저 만들 화면을 골라 주세요
      </h2>
      <p className="mt-2 text-base break-keep text-muted-foreground">
        이번 시제품은 화면 {todo.max}개까지 만들어요. 고르지 않은 화면은 이번 범위에서 빠지고, 고른 내용은 결정 기록에 남아요.
      </p>
      <fieldset className="mt-6 flex flex-col gap-2" disabled={!onKeep || busy}>
        <legend className="sr-only">먼저 만들 화면</legend>
        {todo.screens.map((s) => {
          const on = keep.includes(s.id);
          return (
            <label
              key={s.id}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-2xl border px-4 py-3.5 transition-colors",
                on ? "border-primary-text/50 bg-primary-soft" : "border-border bg-white/[0.025] hover:bg-white/[0.05]",
                !on && full && "cursor-not-allowed opacity-60",
              )}
            >
              <input type="checkbox" className="peer sr-only" checked={on} disabled={!on && full} onChange={() => toggle(s.id)} />
              <span
                className={cn(
                  "mt-0.5 grid size-5 shrink-0 place-items-center rounded-md border peer-focus-visible:ring-[3px] peer-focus-visible:ring-primary-ring",
                  on ? "border-primary bg-primary text-primary-foreground" : "border-border-strong",
                )}
                aria-hidden="true"
              >
                {on && <Check className="size-3.5" />}
              </span>
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-base font-semibold text-foreground">
                  {s.title} <RefId id={s.id} />
                </span>
                {s.purpose && <span className="block text-sm break-keep text-muted-foreground">{s.purpose}</span>}
              </span>
            </label>
          );
        })}
      </fieldset>
      {lost.length > 0 && (
        <div className="mt-4 flex items-start gap-3 rounded-2xl bg-warning-soft px-4 py-3.5" aria-live="polite">
          <CircleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
          <div className="text-sm break-keep text-soft">
            <p className="font-semibold text-foreground">지금 고른 대로면 화면이 없어지는 기능 {lost.length}개</p>
            <p className="mt-1">{lost.map((id) => `「${titles[id] ?? id}」`).join(", ")}</p>
            <p className="mt-1 text-muted-foreground">
              이 기능들은 문서에는 남지만 프로토타입에서는 눌러 볼 수 없어요. 문서 확인 단계에서 「화면 범위를 줄여서 뺐다」는 이유가 자동으로 채워져요.
            </p>
          </div>
        </div>
      )}
      <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-border pt-6">
        {onKeep ? (
          <Button
            size="lg"
            disabled={busy || keep.length === 0}
            onClick={() => send(keep)}
          >
            {busy ? <LoaderCircle className="animate-spin" /> : <Check />} 이 화면들로 진행할게요
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">녹화 당시 발주사가 여기서 화면을 골랐어요.</p>
        )}
        {onKeep && (
          <Button size="lg" variant="outline" disabled={busy} onClick={() => send(todo.screens.map((s) => s.id), true)}>
            <Layers /> 화면 {todo.screens.length}개 모두 만들기
          </Button>
        )}
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {keep.length}/{todo.max}개 골랐어요
        </p>
      </div>
      {onKeep && (
        <p className="mt-3 text-xs break-keep text-faint">
          「모두 만들기」를 고르면 빠지는 기능 없이 다 만들어요. 대신 프로토타입을 만드는 시간과 Liner 비용이 화면 수만큼 늘어나요.
        </p>
      )}
    </Card>
  );
}

// G7: a Liner call cap or a stage time cap was reached; nothing more is sent until the client says 「계속」.
export function LimitCard({ todo, onContinue }: { todo: LimitTodo; onContinue?: () => Promise<void> }) {
  const team = useView() === "team";
  const [busy, setBusy] = useState(false);
  const what = todo.limit === "time" ? "시간 상한" : todo.limit === "cost" ? "비용 상한" : "호출 상한";
  return (
    <Card className="animate-rise border-[rgb(242_182_90/0.3)] px-8 pt-7 pb-7" role="alert" aria-labelledby="limit-title">
      <p className="flex items-center gap-2 text-sm font-semibold text-warning">
        <Gauge className="size-4" aria-hidden="true" /> {what}에 닿았어요
        {team && <RefId id="G7" />}
      </p>
      <h2 id="limit-title" className="mt-3 text-title font-bold tracking-[-0.02em] text-balance break-keep text-foreground">
        비용이 커지지 않게 잠시 멈췄어요
      </h2>
      <p className="mt-2 text-base break-keep text-muted-foreground">{todo.message}</p>
      {team && (
        <p className="mt-4 rounded-2xl border border-border bg-white/[0.03] px-4 py-3 text-sm break-keep text-soft">
          <span className="mr-1.5 text-xs font-semibold text-muted-foreground">기록 · {STAGE_TITLE[todo.stage] ?? todo.stage}</span>
          {todo.limit === "time"
            ? `경과 ${todo.used}초 / 상한 ${todo.max}초`
            : todo.limit === "cost"
              ? `쓴 비용 ${formatUsd(todo.used ?? 0)} / 상한 ${formatUsd(todo.max ?? 0)}`
              : `Liner 호출 ${todo.used}회 / 상한 ${todo.max}회`}
          {" "}— 상한 값은 제안값이에요(실측 전).
        </p>
      )}
      {onContinue ? (
        <Button
          size="lg"
          className="mt-6"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onContinue();
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <LoaderCircle className="animate-spin" /> : <Play />} 계속
        </Button>
      ) : (
        <p className="mt-6 text-sm text-muted-foreground">녹화 당시 발주사가 여기서 「계속」을 눌렀어요.</p>
      )}
    </Card>
  );
}
