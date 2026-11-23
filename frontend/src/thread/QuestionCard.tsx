import { ArrowLeft, ArrowUp, Check, ChevronDown, ExternalLink, LoaderCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { Todo } from "../api";
import { acceptsFreeText, quoteOption } from "../lib/questionCard";
import { stripIds } from "../lib/summarize";
import { RefId, useView } from "../ui/view";
import { questionPosition } from "./model";

type QuestionTodo = Extract<Todo, { kind: "question" }>;
type Answer = { kind: "choice" | "unknown" | "free_text"; value?: string };

// Toss-style single task: one question, big tappable answers, the rest tucked away.
// `onBack`: go to the previous answered card. `editing`: re-answering a card (its current answer is marked;
// `onCancel` keeps it). Both work only until the client presses 「이대로 진행」 on the review card.
export default function QuestionCard({ todo, totalCards, onAnswer, onBack, editing, onCancel }: {
  todo: QuestionTodo;
  totalCards: number;
  onAnswer?: (answer: Answer) => Promise<void>; // absent in demo replay: shown read-only
  onBack?: () => void;
  editing?: { index: number; current: QuestionTodo["question"]["answer"] };
  onCancel?: () => void;
}) {
  const view = useView();
  const [pending, setPending] = useState<string | null>(null);
  const [text, setText] = useState("");
  const q = todo.question;
  const pos = editing ? { index: editing.index, total: totalCards } : questionPosition(totalCards, todo.remaining);
  const current = editing?.current;
  const chosen = (option: string) => current?.kind !== "unknown" && current?.value === option;
  const send = async (key: string, answer: Answer) => {
    if (!onAnswer) return;
    setPending(key);
    try {
      await onAnswer(answer);
      setText("");
    } finally {
      setPending(null);
    }
  };
  const busy = pending !== null || !onAnswer;

  return (
    <Card className="animate-rise px-8 pt-7 pb-6" aria-labelledby="question-title">
      <div className="flex items-center gap-2 text-sm font-semibold text-primary-text">
        질문 {pos.index} / {pos.total}
        {editing && <span className="font-normal text-muted-foreground">· 답 고치는 중</span>}
        {view === "team" && <RefId id={q.id} />}
        {onBack && !editing && (
          <button type="button" onClick={onBack} disabled={busy} className="ml-auto inline-flex items-center gap-1 font-medium text-muted-foreground hover:text-foreground disabled:opacity-50">
            <ArrowLeft className="size-4" aria-hidden="true" /> 이전 질문
          </button>
        )}
        {editing && onCancel && (
          <button type="button" onClick={onCancel} disabled={pending !== null} className="ml-auto font-medium text-muted-foreground hover:text-foreground">
            고치지 않고 돌아가기
          </button>
        )}
      </div>
      {current && (
        <p className="mt-2 text-sm break-keep text-muted-foreground">
          지금 답: <b className="text-soft">{current.value}</b>{current.status === "가정" && " (잘 모르겠어요 · 기본값으로 가정)"} — 다른 답을 고르면 바뀌어요
        </p>
      )}
      <h2 id="question-title" className="mt-3 text-title font-bold tracking-[-0.02em] text-balance break-keep text-foreground">
        {q.question}
      </h2>
      <p className="mt-2 text-base break-keep text-muted-foreground">{view === "team" ? q.why : stripIds(q.why)}</p>

      <div className="mt-6 flex flex-col gap-2" role="group" aria-label="답 고르기">
        {q.options.map((option) => (
          <OptionButton key={option} readOnly={!onAnswer} disabled={busy} pending={pending === option} selected={chosen(option)} onClick={() => send(option, { kind: "choice", value: option })}>
            {option}
          </OptionButton>
        ))}
        <OptionButton quiet readOnly={!onAnswer} disabled={busy} pending={pending === "__unknown"} selected={current?.kind === "unknown"} onClick={() => send("__unknown", { kind: "unknown" })}>
          {q.unknown_option}
          <span className="mt-0.5 block text-sm font-normal text-muted-foreground">
            고르시면 {quoteOption(q.default_option)}로 가정하고 표시해 둘게요
          </span>
        </OptionButton>
      </div>

      {!onAnswer && (
        <p className="mt-3 text-sm text-muted-foreground">녹화 당시 발주사가 여기서 답을 골랐어요. 고른 답은 다음 장면에서 보여요.</p>
      )}
      <form
        hidden={!onAnswer || !acceptsFreeText(q)}
        className="mt-3 flex items-center gap-2 rounded-2xl border border-border bg-white/[0.03] py-1.5 pr-1.5 pl-4 focus-within:border-primary-text/60"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) void send("__free", { kind: "free_text", value: text });
        }}
      >
        <label htmlFor="free-answer" className="sr-only">
          직접 답하기
        </label>
        <input
          id="free-answer"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="원하는 답이 없으면 직접 적어 주세요"
          className="h-10 min-w-0 flex-1 border-0 bg-transparent p-0 text-base outline-none placeholder:text-faint focus-visible:outline-none"
        />
        <Button type="submit" size="icon" disabled={busy || !text.trim()} aria-label="직접 적은 답 보내기">
          {pending === "__free" ? <LoaderCircle className="animate-spin" /> : <ArrowUp />}
        </Button>
      </form>

      {(todo.sources.length > 0 || todo.evidence.length > 0) && (
        <Grounds key={view} todo={todo} defaultOpen={view === "team"} />
      )}
    </Card>
  );
}

function OptionButton({ children, onClick, disabled, pending, quiet, readOnly, selected }: {
  children: ReactNode;
  onClick: () => void;
  disabled: boolean;
  pending: boolean;
  selected?: boolean; // the answer given before (shown while re-answering)
  quiet?: boolean;
  readOnly?: boolean; // demo replay: shown at full strength, not as a disabled control
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "group flex min-h-14 w-full cursor-pointer items-center justify-between gap-4 rounded-2xl border px-5 py-3.5 text-left text-lg font-semibold break-keep transition-[background-color,border-color,transform] duration-150 active:scale-[0.99] disabled:cursor-default",
        quiet ? "border-dashed border-border-strong bg-transparent text-soft" : "border-border bg-white/[0.03] text-foreground",
        "hover:border-primary-text/60 hover:bg-primary-soft focus-visible:border-primary-text focus-visible:ring-[3px] focus-visible:ring-primary-ring focus-visible:outline-none",
        (pending || selected) && "border-primary-text bg-primary-soft",
        disabled && !pending && !readOnly && "opacity-50",
        readOnly && "cursor-default hover:border-border hover:bg-white/[0.03]",
      )}
    >
      <span className="min-w-0">{children}</span>
      <span
        className={cn(
          "flex size-6 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
          pending || selected ? "border-primary-text" : "border-border-strong group-hover:border-primary-text",
          selected && !pending && "bg-primary-text",
        )}
        aria-hidden="true"
      >
        {pending && <LoaderCircle className="size-4 animate-spin text-primary-text" />}
        {selected && !pending && <Check className="size-4 text-primary-foreground" />}
      </span>
    </button>
  );
}

function Grounds({ todo, defaultOpen }: { todo: QuestionTodo; defaultOpen: boolean }) {
  const view = useView();
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mt-5 border-t border-border pt-4">
      <CollapsibleTrigger className="group inline-flex cursor-pointer items-center gap-1.5 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground">
        왜 이 질문이 나왔나요?
        <span className="font-normal text-muted-foreground">
          받은 메모 {todo.sources.length}줄 · Liner 근거 {todo.evidence.length}건
        </span>
        <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-3 flex flex-col gap-2">
          {todo.sources.map((s) => (
            <li key={s.id} className="rounded-xl bg-white/[0.04] px-4 py-3 text-sm break-keep text-soft">
              <span className="mr-1.5 text-xs font-semibold text-muted-foreground">받은 메모</span>“{s.text}” {view === "team" && <RefId id={s.id} />}
            </li>
          ))}
          {todo.evidence.map((e) => (
            <li key={e.id} className="rounded-xl bg-cyan-soft px-4 py-3 text-sm break-keep text-soft">
              <span className="mr-1.5 text-xs font-semibold text-cyan">Liner 근거</span>“{e.quote}” {view === "team" && <RefId id={e.id} />}{" "}
              <a href={e.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-cyan hover:underline">
                출처 <ExternalLink className="size-3" aria-hidden="true" />
              </a>
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}
