import { ArrowDownLeft, ArrowUpRight, Gavel, MapPin, PenLine, Search, ShieldAlert, Sparkles, X, type LucideIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AppEvent } from "../api";
import { buildLineage } from "../graph/lineage";
import { STAGE_TITLE, type View } from "../lib/labels";
import type { Label } from "../lib/summarize";
import { AgentAvatar } from "../thread/AgentAvatar";
import { trapTab } from "../ui/focusTrap";
import { agentLog, filterLog, LOG_KIND_KO, type CoordinatorSummary, type LogEntry, type LogKind } from "./model";

const KINDS = Object.keys(LOG_KIND_KO) as LogKind[];
const ICON: Record<LogKind, LucideIcon> = { message: ArrowUpRight, liner: Sparkles, write: PenLine, decision: Gavel, guard: ShieldAlert };

function clock(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// One agent's detailed log in a side drawer (a modal dialog: focus moves in, Tab stays in, Esc closes and
// focus returns to whatever opened it).

export default function AgentLogDrawer({ agent, events, source, label, view, titles, onClose, onSelectItem }: {
  agent: string;
  events: AppEvent[];
  source: Record<string, unknown>;
  label: Label;
  view: View;
  titles: Record<string, string>;
  onClose: () => void;
  onSelectItem?: (id: string) => void;
}) {
  const log = useMemo(() => agentLog(events, source, agent, label, view, titles), [events, source, agent, label, view, titles]);
  const linkable = useMemo(() => new Set(buildLineage(source, events).nodes.map((n) => n.id)), [source, events]);
  const [kinds, setKinds] = useState<Set<LogKind>>(() => new Set(KINDS));
  const [query, setQuery] = useState("");
  const shown = useMemo(() => filterLog(log.groups, kinds, query), [log, kinds, query]);
  const counts = useMemo(() => {
    const out = Object.fromEntries(KINDS.map((k) => [k, 0])) as Record<LogKind, number>;
    for (const g of log.groups) for (const e of g.entries) out[e.kind] += 1;
    return out;
  }, [log]);

  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLElement>("[data-close]")?.focus();
    return () => opener?.focus?.();
  }, []);
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (dialog.current) trapTab(dialog.current, e);
  };
  const toggle = (k: LogKind) =>
    setKinds((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onKeyDown={onKeyDown}>
      <button type="button" className="absolute inset-0 cursor-default bg-[#020a2b]/55" aria-label="활동 기록 닫기" tabIndex={-1} onClick={onClose} />
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-log-title"
        className="relative flex h-full w-[min(34rem,94vw)] animate-rise flex-col border-l border-white/[0.1] bg-deep shadow-card"
      >
        <header className="flex shrink-0 items-center gap-3 border-b border-white/[0.07] px-5 py-4">
          <AgentAvatar id={agent} />
          <div className="min-w-0 flex-1">
            <h2 id="agent-log-title" className="text-base font-semibold text-foreground">{label(agent)} 활동 기록</h2>
            <p className="text-xs text-muted-foreground">단계별 · 시간순 · {log.total}건</p>
          </div>
          <Button data-close variant="ghost" size="icon" aria-label="닫기" onClick={onClose}>
            <X />
          </Button>
        </header>

        <div className="shrink-0 border-b border-white/[0.07] px-5 py-3">
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="종류 거르기">
            {KINDS.map((k) => (
              <button
                key={k}
                type="button"
                aria-pressed={kinds.has(k)}
                onClick={() => toggle(k)}
                className={cn(
                  "inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring",
                  kinds.has(k) ? "border-cyan/50 bg-cyan-soft text-foreground" : "border-border text-muted-foreground",
                )}
              >
                {LOG_KIND_KO[k]} <span className="tabular-nums text-faint">{counts[k]}</span>
              </button>
            ))}
          </div>
          <label className="mt-2 flex h-8 items-center gap-2 rounded-md border border-border bg-white/[0.03] px-2 text-xs focus-within:ring-[3px] focus-within:ring-primary-ring">
            <Search className="size-3.5 text-muted-foreground" aria-hidden="true" />
            <span className="sr-only">기록 검색</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="기록에서 찾기"
              className="h-full min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-faint"
            />
          </label>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {log.summary && <Summary summary={log.summary} label={label} />}
          {shown.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {log.total === 0 ? "이 에이전트가 남긴 기록이 아직 없어요" : "조건에 맞는 기록이 없어요"}
            </p>
          ) : (
            shown.map((g) => (
              <section key={g.key} className="mb-5" aria-label={g.title}>
                <h3 className="sticky top-0 z-10 -mx-1 mb-2 bg-deep/95 px-1 py-1 text-xs font-semibold text-primary-text backdrop-blur">
                  {g.title}
                  {view === "team" && g.stage && <code className="ml-1.5 font-mono text-[11px] text-faint">{g.stage}</code>}
                </h3>
                <ol className="flex flex-col gap-2">
                  {g.entries.map((e, i) => (
                    <Entry key={`${e.seq}-${i}`} entry={e} view={view} linkable={linkable} onSelectItem={onSelectItem} />
                  ))}
                </ol>
              </section>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Entry({ entry, view, linkable, onSelectItem }: { entry: LogEntry; view: View; linkable: Set<string>; onSelectItem?: (id: string) => void }) {
  const Icon = entry.kind === "message" && entry.direction === "in" ? ArrowDownLeft : ICON[entry.kind];
  const canLink = entry.itemId && linkable.has(entry.itemId) && onSelectItem;
  return (
    <li className="rounded-xl border border-white/[0.07] bg-white/[0.03] px-3 py-2">
      <p className="flex items-start gap-2 text-sm">
        <Icon className={cn("mt-0.5 size-3.5 shrink-0", entry.kind === "guard" ? "text-warning" : "text-cyan")} aria-hidden="true" />
        <span className="sr-only">{LOG_KIND_KO[entry.kind]}:</span>
        <span className="min-w-0 flex-1 font-medium break-keep text-foreground">{entry.title}</span>
        <time className="shrink-0 text-[11px] tabular-nums text-faint" dateTime={entry.ts}>{clock(entry.ts)}</time>
      </p>
      {entry.lines.length > 0 && (
        <ul className="mt-1 ml-5.5 flex flex-col gap-0.5">
          {entry.lines.map((line, i) => (
            <li key={i} className="text-xs leading-relaxed break-keep text-soft">{line}</li>
          ))}
        </ul>
      )}
      {(canLink || view === "team") && (
        <div className="mt-1 ml-5.5 flex flex-wrap items-center gap-2">
          {canLink && (
            <Button variant="ghost" size="sm" className="-ml-2 h-6 px-2 text-xs text-cyan" onClick={() => onSelectItem!(entry.itemId!)}>
              <MapPin className="size-3.5" aria-hidden="true" />
              추적 지도에서 보기
            </Button>
          )}
          {view === "team" && (
            <details className="w-full text-xs">
              <summary className="cursor-pointer rounded text-muted-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring">원문 보기</summary>
              <pre className="mt-1 max-h-56 overflow-auto rounded-md bg-black/30 p-2 font-mono text-[11px] whitespace-pre-wrap text-soft">
                {JSON.stringify(entry.raw, null, 2).slice(0, 6000)}
              </pre>
            </details>
          )}
        </div>
      )}
    </li>
  );
}

function Summary({ summary, label }: { summary: CoordinatorSummary; label: Label }) {
  return (
    <section aria-label="조율자 요약" className="mb-5 rounded-2xl border border-primary-text/25 bg-primary-soft px-4 py-3 text-sm">
      <p className="text-xs font-semibold text-primary-text">조율자 요약</p>
      <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-soft">
        {summary.handoffs.map((h) => (
          <li key={h.agent} className="flex justify-between gap-2">
            <span className="text-foreground">{label(h.agent)}</span>
            <span className="tabular-nums">보냄 {h.sent} · 받음 {h.received}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-soft">관계선이 없어 대신 전한 메시지 {summary.reroutes}건</p>
      <p className="mt-1 text-xs break-keep text-soft">거친 단계: {summary.stages.map((s) => STAGE_TITLE[s] ?? s).join(" → ") || "아직 없음"}</p>
      <p className="mt-1 text-xs break-keep text-soft">
        남은 일: {summary.pending.length ? summary.pending.map((p) => `${p.label} ${p.count}`).join(" · ") : "없음"}
      </p>
    </section>
  );
}
