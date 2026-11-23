import { Check, ChevronDown, Search } from "lucide-react";
import { useState } from "react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { Label } from "../lib/summarize";
import { AgentAvatar } from "./AgentAvatar";
import { ShimmerText } from "./WorkingRow";
import type { StepItem } from "./model";

// A Perplexity/Cursor-style "step": one line that says what the team did, expandable to the details.
// `live` is the current activity sentence, shown under the title while this step is being worked on.
export default function StepGroup({ step, label, defaultOpen, live, timing }: {
  step: StepItem;
  label: Label;
  defaultOpen?: boolean;
  live?: string | null;
  timing?: { text: string; hint: string | null } | null; // real mode: elapsed time and the usual duration
}) {
  const [open, setOpen] = useState(Boolean(defaultOpen));
  const active = step.state === "active";
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="animate-rise">
      <CollapsibleTrigger
        className="group flex w-full cursor-pointer items-start gap-3 rounded-2xl px-3 py-3 text-left transition-colors hover:bg-white/[0.04]"
      >
        <span
          className={cn(
            "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full",
            active ? "bg-cyan-soft text-cyan" : "bg-secondary text-muted-foreground",
          )}
          aria-hidden="true"
        >
          {active ? <span className="size-2 rounded-full bg-cyan animate-breathe" /> : <Check className="size-3.5" strokeWidth={2} />}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className={cn("text-base font-semibold", active ? "text-foreground" : "text-foreground")}>{step.title}</span>
          {live && (
            <span className="text-sm font-medium" role="status" aria-live="polite">
              <ShimmerText>{live}…</ShimmerText>
            </span>
          )}
          {timing && (
            <span className="text-xs tabular-nums text-muted-foreground" title={timing.hint ?? undefined}>
              {timing.text}
              {timing.hint && <span className="sr-only"> ({timing.hint})</span>}
            </span>
          )}
          {(step.highlight || step.facts.length > 0) && (
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              {step.highlight && (
                <span className="inline-flex items-center gap-1.5 text-soft">
                  <Search className="size-3.5 text-cyan" aria-hidden="true" />
                  {step.highlight}
                </span>
              )}
              {step.highlight && step.facts.length > 0 && <span aria-hidden="true">·</span>}
              {step.facts.join(" · ")}
            </span>
          )}
        </span>
        <span className="mt-0.5 flex shrink-0 items-center gap-2">
          <span className="flex" aria-hidden="true">
            {step.agents.slice(0, 4).map((id) => (
              <AgentAvatar key={id} id={id} size="sm" className="-ml-1 first:ml-0" />
            ))}
          </span>
          <ChevronDown
            className="size-4 text-faint transition-transform duration-200 group-data-[state=open]:rotate-180"
            aria-hidden="true"
          />
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="mb-2 ml-6 border-l border-white/10 pl-6">
          {step.entries.map((e) => (
            <li key={e.seq} className="flex items-start gap-2.5 py-1.5 text-sm text-muted-foreground">
              <AgentAvatar id={e.actor} size="sm" className="mt-px" />
              <span className="min-w-0 break-keep">
                <span className="sr-only">{label(e.actor)}: </span>
                {e.text}
              </span>
            </li>
          ))}
          {step.entries.length === 0 && <li className="py-1.5 text-sm text-muted-foreground">아직 남긴 기록이 없어요</li>}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}
