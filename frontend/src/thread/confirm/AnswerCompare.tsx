import { ArrowRight, Check, ChevronDown, OctagonX } from "lucide-react";
import { useState } from "react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { AnswerRow, Review } from "../../api";
import { answeredByLabel, clientQuestion } from "../../lib/company";
import { stripIds } from "../../lib/summarize";
import { RefId, useView } from "../../ui/view";
import { StatusChip } from "../StatusChip";

// 「내가 고른 답 → 반영된 요구사항」: each answer next to the requirement text that carries it.
// CP2 shows it open (that is where the client checks it); later confirmations fold it when all match.
export default function AnswerCompare({ review }: { review: Review }) {
  const allMatch = review.answers.every((a) => a.consistent);
  const [open, setOpen] = useState(review.cp === "CP2" || !allMatch);
  if (review.answers.length === 0) return null;
  const bad = review.answers.filter((a) => !a.consistent).length;
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="flex flex-col gap-3">
      <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-2 rounded-lg text-left">
        <span className="text-base font-semibold text-foreground">내가 고른 답 → 반영된 요구사항</span>
        <span className={cn("text-sm", bad ? "text-destructive" : "text-muted-foreground")}>
          {bad ? `${review.answers.length}개 중 ${bad}개가 달라요` : `${review.answers.length}개 모두 그대로 들어갔어요`}
        </span>
        <ChevronDown className="ml-auto size-4 text-faint transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="flex flex-col gap-2" aria-label="내가 고른 답과 반영된 요구사항">
          {review.answers.map((row) => (
            <CompareRow key={row.decision_id} row={row} />
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}

function CompareRow({ row }: { row: AnswerRow }) {
  const team = useView() === "team";
  const byCompany = answeredByLabel(row, team);
  const plain = (text: string) => (team ? text : stripIds(text)); // the client view shows no internal ids
  const question = team ? row.question : clientQuestion(row.question);
  return (
    <li
      className={cn(
        "grid gap-3 rounded-2xl border p-4 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1.25fr)] sm:items-center",
        row.consistent ? "border-border bg-white/[0.025]" : "border-[rgb(255_138_138/0.35)] bg-[rgb(255_138_138/0.06)]",
      )}
    >
      <div className="min-w-0">
        {question && <p className="text-xs break-keep text-muted-foreground">{question}</p>}
        {byCompany && (
          <p className="mt-1 inline-flex rounded-md border border-cyan/40 bg-cyan-soft px-1.5 py-px text-xs font-semibold text-foreground">
            {byCompany} — 질문 카드로 묻지 않았어요. 다르면 반려 사유에 적어 주세요
          </p>
        )}
        <p className="mt-1 flex flex-wrap items-center gap-1.5 text-base font-semibold break-keep text-foreground">
          “{plain(row.answer)}”{row.status === "가정" && <StatusChip status="가정" />}
          {team && <RefId id={row.decision_id} />}
        </p>
      </div>
      <span
        className={cn("hidden size-7 place-items-center rounded-full sm:grid", row.consistent ? "bg-cyan-soft text-cyan" : "bg-[rgb(255_138_138/0.14)] text-destructive")}
        aria-hidden="true"
      >
        <ArrowRight className="size-3.5" />
      </span>
      <div className="min-w-0">
        {row.requirements.length === 0 ? (
          <p className="text-sm text-muted-foreground">아직 반영된 요구사항이 없어요</p>
        ) : (
          row.requirements.map((r) => (
            <p key={r.id} className="text-sm break-keep text-soft">
              {plain(r.statement)} <StatusChip status={r.status} /> {team && <RefId id={r.id} />}
            </p>
          ))
        )}
        <p className={cn("mt-1.5 inline-flex items-center gap-1 text-xs font-semibold", row.consistent ? "text-cyan" : "text-destructive")}>
          {row.consistent ? <Check className="size-3.5" aria-hidden="true" /> : <OctagonX className="size-3.5" aria-hidden="true" />}
          {row.consistent ? "고른 답 그대로예요" : "고른 답과 다르게 적혀 있어요"}
        </p>
      </div>
    </li>
  );
}
