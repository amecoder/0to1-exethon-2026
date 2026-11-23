import { ChevronDown, Info, OctagonX, PenLine, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./collapsible";

// The three warning shapes, made for the dark theme: a tinted glass surface with a hairline in the
// warning's hue — not a bright box. block = stops approval (red) · reason = needs a one-line reason
// (amber) · info = does not stop anything (quiet, collapsed by default).
export type NoticeKind = "block" | "reason" | "info";

const STYLE: Record<NoticeKind, { icon: LucideIcon; box: string; icon_: string; tag: string; tagText: string }> = {
  block: {
    icon: OctagonX,
    box: "border-[rgb(255_138_138/0.28)] bg-[linear-gradient(180deg,rgb(255_138_138/0.10),rgb(255_138_138/0.04))]",
    icon_: "text-destructive bg-[rgb(255_138_138/0.12)]",
    tag: "text-destructive",
    tagText: "승인을 막아요",
  },
  reason: {
    icon: PenLine,
    box: "border-[rgb(242_182_90/0.26)] bg-[linear-gradient(180deg,rgb(242_182_90/0.09),rgb(242_182_90/0.03))]",
    icon_: "text-warning bg-warning-soft",
    tag: "text-warning",
    tagText: "이유가 필요해요",
  },
  info: {
    icon: Info,
    box: "border-border bg-white/[0.025]",
    icon_: "text-cyan bg-cyan-soft",
    tag: "text-muted-foreground",
    tagText: "참고",
  },
};

export function Notice({ kind, title, tag, children, defaultOpen, className }: {
  kind: NoticeKind;
  title: ReactNode;
  tag?: string; // replaces the kind's default tag line (e.g. "내려받기 잠김")
  children?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const s = STYLE[kind];
  const Icon = s.icon;
  const head = (
    <>
      <span className={cn("grid size-8 shrink-0 place-items-center rounded-xl", s.icon_)} aria-hidden="true">
        <Icon className="size-4" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className={cn("text-xs font-semibold", s.tag)}>{tag ?? s.tagText}</span>
        <span className="text-base font-semibold break-keep text-foreground">{title}</span>
      </span>
    </>
  );
  if (kind === "info") return <InfoNotice head={head} className={cn(s.box, className)} defaultOpen={defaultOpen}>{children}</InfoNotice>;
  return (
    <section className={cn("rounded-2xl border px-4 py-4", s.box, className)} role={kind === "block" ? "alert" : undefined}>
      <div className="flex items-start gap-3">{head}</div>
      {children && <div className="mt-3 pl-11">{children}</div>}
    </section>
  );
}

function InfoNotice({ head, children, className, defaultOpen }: {
  head: ReactNode;
  children?: ReactNode;
  className: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(Boolean(defaultOpen));
  return (
    <Collapsible open={open} onOpenChange={setOpen} className={cn("rounded-2xl border", className)}>
      <CollapsibleTrigger className="group flex w-full cursor-pointer items-start gap-3 rounded-2xl px-4 py-4 text-left">
        {head}
        <ChevronDown className="mt-2 size-4 shrink-0 text-faint transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
      </CollapsibleTrigger>
      {children && (
        <CollapsibleContent>
          <div className="pr-4 pb-4 pl-15">{children}</div>
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}

// Bulleted lines inside a notice.
export function NoticeList({ items }: { items: ReactNode[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm break-keep text-soft">
          <span className="mt-2.5 size-1 shrink-0 rounded-full bg-faint" aria-hidden="true" />
          <span className="min-w-0">{item}</span>
        </li>
      ))}
    </ul>
  );
}
