import { Check, CheckCheck, ChevronLeft, ChevronRight, LoaderCircle, PenLine, Send, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ReqReviews, Requirement } from "../../api";
import { RequirementBody } from "./RequirementSection";

type Verdict = "ok" | "fix" | null;
type Filter = "all" | "open" | "fix" | "ok";
export type Review = (reqId: string, verdict: "ok" | "fix" | "clear", note?: string) => Promise<void>;

const FILTERS: [Filter, string][] = [
  ["all", "전체"],
  ["open", "남은 것"],
  ["fix", "고칠 점"],
  ["ok", "확정"],
];

// CP2 one card at a time: 확정 or a 고칠 점 note per requirement, filter by state, send the notes for one
// rework, and repeat until every card is 확정 — only then the final approval opens (ConfirmCard).
export default function RequirementDeck({ requirements, reviews, onReview, onSendFixes, onConfirmRest }: {
  requirements: Requirement[];
  reviews: ReqReviews;
  onReview: Review;
  onSendFixes: () => Promise<void>;
  onConfirmRest?: () => Promise<unknown>; // every card not looked at yet becomes 확정; 고칠 점 cards stay
}) {
  const verdict = useMemo(() => Object.fromEntries(reviews.items.map((i) => [i.id, i])), [reviews]);
  const stateOf = (id: string): Verdict => verdict[id]?.verdict ?? null;
  const [filter, setFilter] = useState<Filter>("all");
  const shown = requirements.filter((r) => filter === "all" || (filter === "open" ? stateOf(r.id) === null : stateOf(r.id) === filter));
  const [currentId, setCurrentId] = useState<string | null>(() => requirements.find((r) => stateOf(r.id) === null)?.id ?? requirements[0]?.id ?? null);
  const index = Math.max(0, shown.findIndex((r) => r.id === currentId));
  const current = shown[index];
  const [writing, setWriting] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [askingRest, setAskingRest] = useState(false);
  const restLabel = confirmRestLabel(reviews);

  useEffect(() => {
    setWriting(false);
    setNote(current ? verdict[current.id]?.note ?? "" : "");
  }, [current?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = (step: number) => {
    if (shown.length === 0) return;
    setCurrentId(shown[(index + step + shown.length) % shown.length].id);
  };
  // After a verdict, move to the next card nobody has looked at yet (in list order, wrapping around).
  const nextOpen = (fromId: string) => {
    const order = requirements.map((r) => r.id);
    const start = order.indexOf(fromId);
    const rest = [...order.slice(start + 1), ...order.slice(0, start)];
    return rest.find((id) => stateOf(id) === null && id !== fromId) ?? fromId;
  };
  const mark = async (v: "ok" | "fix" | "clear") => {
    if (!current) return;
    setBusy(v);
    try {
      await onReview(current.id, v, v === "fix" ? note.trim() : undefined);
      setWriting(false);
      if (v !== "clear") {
        setFilter("all");
        setCurrentId(nextOpen(current.id));
      }
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && ["INPUT", "TEXTAREA"].includes(e.target.tagName);
      if (typing) return;
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });

  const state = current ? stateOf(current.id) : null;
  const count = { all: reviews.total, open: reviews.open, fix: reviews.fix, ok: reviews.ok };

  return (
    <section className="flex flex-col gap-4" aria-label="요구사항 카드 확인">
      <div className="flex flex-col gap-2">
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-base font-semibold text-foreground">
          요구사항 {reviews.total}건
          <span className="text-sm font-normal text-muted-foreground">
            확정 <b className="text-cyan">{reviews.ok}</b> · 고칠 점 <b className="text-warning">{reviews.fix}</b> · 남은 것 <b className="text-foreground">{reviews.open}</b>
          </span>
        </p>
        <div className="flex h-1.5 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
          <span className="bg-cyan transition-[width]" style={{ width: `${(reviews.ok / Math.max(1, reviews.total)) * 100}%` }} />
          <span className="bg-warning transition-[width]" style={{ width: `${(reviews.fix / Math.max(1, reviews.total)) * 100}%` }} />
        </div>
        <div role="tablist" aria-label="카드 걸러 보기" className="flex flex-wrap gap-1.5">
          {FILTERS.map(([f, label]) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={filter === f}
              disabled={count[f] === 0 && f !== "all"}
              onClick={() => {
                setFilter(f);
                const first = requirements.find((r) => f === "all" || (f === "open" ? stateOf(r.id) === null : stateOf(r.id) === f));
                if (first) setCurrentId(first.id);
              }}
              className={cn(
                "rounded-full border px-3 py-1 text-sm transition-colors disabled:opacity-40",
                filter === f ? "border-primary-text bg-primary-soft text-foreground" : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {label} {count[f]}
            </button>
          ))}
        </div>
      </div>

      {current ? (
        <div
          className={cn(
            "rounded-2xl border px-5 py-4",
            state === "ok" ? "border-cyan/50 bg-cyan-soft" : state === "fix" ? "border-warning/50 bg-warning-soft" : "border-border bg-white/[0.025]",
          )}
        >
          <p className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
            {index + 1} / {shown.length}
            {state === "ok" && <span className="text-cyan">· 확정했어요</span>}
            {state === "fix" && <span className="text-warning">· 고칠 점을 남겼어요</span>}
            {state === null && <span>· 아직 안 봤어요</span>}
          </p>
          <RequirementBody r={current} quietConfirmed />
          {state === "fix" && !writing && verdict[current.id]?.note && (
            <p className="mt-3 rounded-xl bg-white/[0.05] px-3 py-2 text-sm break-keep text-soft">
              <span className="mr-1 text-xs font-semibold text-warning">내 의견</span>
              {verdict[current.id]?.note}
            </p>
          )}
          {writing && (
            <form
              className="mt-3 flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (note.trim()) void mark("fix");
              }}
            >
              <label htmlFor="req-note" className="text-sm font-medium text-soft">
                이 요구사항에서 고칠 점을 적어 주세요
              </label>
              <textarea
                id="req-note"
                autoFocus
                rows={2}
                maxLength={300}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="예) 알림을 확인 안 하면 1시간 뒤에 한 번 더 보내 주세요"
                className="w-full resize-y rounded-xl border border-border bg-white/[0.03] px-3 py-2 text-base text-foreground outline-none placeholder:text-faint focus-visible:border-primary-text/60"
              />
              <div className="flex gap-2">
                <Button type="submit" size="sm" disabled={busy !== null || !note.trim()}>
                  {busy === "fix" ? <LoaderCircle className="animate-spin" /> : <PenLine />} 의견 남기기
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setWriting(false)}>
                  취소
                </Button>
              </div>
            </form>
          )}
          {!writing && (
            <div className="mt-4 flex flex-wrap gap-2">
              {state !== "ok" && (
                <Button size="sm" onClick={() => mark("ok")} disabled={busy !== null}>
                  {busy === "ok" ? <LoaderCircle className="animate-spin" /> : <Check />} 확정
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => setWriting(true)} disabled={busy !== null}>
                <PenLine /> {state === "fix" ? "의견 고치기" : "고칠 점 적기"}
              </Button>
              {state !== null && (
                <Button size="sm" variant="ghost" onClick={() => mark("clear")} disabled={busy !== null}>
                  {busy === "clear" ? <LoaderCircle className="animate-spin" /> : <Undo2 />} {state === "ok" ? "확정 취소" : "의견 지우기"}
                </Button>
              )}
            </div>
          )}
        </div>
      ) : (
        <p className="rounded-2xl border border-dashed border-border px-5 py-6 text-center text-sm text-muted-foreground">이 조건에 맞는 카드가 없어요.</p>
      )}

      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={() => go(-1)} disabled={shown.length < 2} aria-label="이전 카드">
          <ChevronLeft /> 이전
        </Button>
        <div className="flex flex-wrap justify-center gap-1" aria-label="카드 목록">
          {requirements.map((r, i) => {
            const v = stateOf(r.id);
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => {
                  setFilter("all");
                  setCurrentId(r.id);
                }}
                aria-label={`${i + 1}번 ${r.title} · ${v === "ok" ? "확정" : v === "fix" ? "고칠 점" : "남음"}`}
                aria-current={r.id === current?.id}
                className={cn(
                  "size-2.5 rounded-full transition-transform",
                  v === "ok" ? "bg-cyan" : v === "fix" ? "bg-warning" : "bg-white/25",
                  r.id === current?.id && "scale-150 ring-2 ring-primary-text/60",
                )}
              />
            );
          })}
        </div>
        <Button variant="ghost" size="sm" onClick={() => go(1)} disabled={shown.length < 2} aria-label="다음 카드">
          다음 <ChevronRight />
        </Button>
      </div>

      {onConfirmRest && restLabel && (
        <div className="flex flex-col gap-2 rounded-2xl border border-border bg-white/[0.025] px-5 py-4">
          {askingRest ? (
            <>
              <p className="text-sm break-keep text-soft" role="status">
                아직 안 본 카드 {reviews.open}건을 모두 확정할까요?{reviews.fix > 0 && ` 고칠 점을 적은 ${reviews.fix}건은 그대로 둬요.`}
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={busy !== null}
                  onClick={async () => {
                    setBusy("rest");
                    try {
                      await onConfirmRest();
                      setAskingRest(false);
                    } finally {
                      setBusy(null);
                    }
                  }}
                >
                  {busy === "rest" ? <LoaderCircle className="animate-spin" /> : <CheckCheck />} 네, 모두 확정
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setAskingRest(false)} disabled={busy !== null}>
                  취소
                </Button>
              </div>
            </>
          ) : (
            <Button size="sm" variant="outline" className="self-start" onClick={() => setAskingRest(true)} disabled={busy !== null}>
              <CheckCheck /> {restLabel}
            </Button>
          )}
        </div>
      )}

      {reviews.fix > 0 && (
        <div className="flex flex-col gap-2 rounded-2xl border border-warning/40 bg-warning-soft px-5 py-4">
          <p className="text-sm break-keep text-soft">
            고칠 점 {reviews.fix}건을 팀에 보내면 그 요구사항만 고쳐서 다시 보여 드려요. 확정한 카드는 내용이 그대로면 확정이 유지돼요.
          </p>
          <Button
            size="sm"
            className="self-start"
            disabled={busy !== null}
            onClick={async () => {
              setBusy("send");
              try {
                await onSendFixes();
              } finally {
                setBusy(null);
              }
            }}
          >
            {busy === "send" ? <LoaderCircle className="animate-spin" /> : <Send />} 고칠 점 {reviews.fix}건 보내기
          </Button>
        </div>
      )}
    </section>
  );
}

// The bulk button's label; null when no card is left to settle.
export function confirmRestLabel(reviews: ReqReviews): string | null {
  return reviews.open > 0 ? `남은 ${reviews.open}건 모두 확정` : null;
}

// What still stands between the client and the final CP2 approval (null: every card is 확정).
export function deckBlocker(reviews: ReqReviews | undefined): string | null {
  if (!reviews || reviews.total === 0) return null;
  if (reviews.fix > 0) return `고칠 점 ${reviews.fix}건을 먼저 보내 주세요`;
  if (reviews.open > 0) return `요구사항 ${reviews.open}건이 아직 확정 전이에요. 카드를 넘기며 확정해 주세요`;
  return null;
}
