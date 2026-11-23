import { BookOpen, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { GROUPS, searchTerms, type TermGroup } from "../lib/terms";
import { trapTab } from "./focusTrap";

// 「용어」 button + the glossary window: every word the service uses, explained for a first-time reader,
// with a search box and one tab per group. Esc or the backdrop closes it; focus stays inside while open.
export default function GlossaryButton({ className = "" }: { className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-primary-ring focus-visible:outline-none",
          className,
        )}
        aria-haspopup="dialog"
      >
        <BookOpen className="size-4 text-cyan" aria-hidden="true" /> 용어
      </button>
      {open && createPortal(<GlossaryDialog onClose={() => setOpen(false)} />, document.body)}
    </>
  );
}

function GlossaryDialog({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<TermGroup | "all">("all");
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const found = searchTerms(query, group);

  useEffect(() => {
    const back = document.activeElement as HTMLElement | null;
    input.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && box.current) trapTab(box.current, e);
    };
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("keydown", key);
      back?.focus();
    };
  }, [onClose]);

  const tabs: [TermGroup | "all", string][] = [["all", "전체"], ...GROUPS];
  return (
    <div className="fixed inset-0 z-[80] flex items-start justify-center bg-black/55 p-4 pt-[8vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-labelledby="glossary-title"
        onMouseDown={(e) => e.stopPropagation()}
        className="flex max-h-[84vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-border-strong bg-raised shadow-card"
      >
        <div className="flex flex-col gap-3 border-b border-border px-6 pt-5 pb-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="glossary-title" className="text-lg font-bold text-foreground">용어 사전</h2>
              <p className="text-sm text-muted-foreground">0to1 에서 쓰는 말과 기술을 쉬운 말로 풀었어요. 예시는 이 서비스 안에서 만나는 장면이에요.</p>
            </div>
            <button type="button" onClick={onClose} aria-label="용어 사전 닫기" className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/[0.06] hover:text-foreground">
              <X className="size-5" />
            </button>
          </div>
          <label className="relative block">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" aria-hidden="true" />
            <input
              ref={input}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="찾을 말 (예: PRD, CP2, 격리, AGENTS)"
              aria-label="용어 찾기"
              className="w-full rounded-xl border border-border bg-white/[0.04] py-2 pr-3 pl-9 text-sm text-foreground outline-none placeholder:text-faint focus-visible:ring-[3px] focus-visible:ring-primary-ring"
            />
          </label>
          <div role="tablist" aria-label="용어 묶음" className="flex flex-wrap gap-1.5">
            {tabs.map(([g, label]) => (
              <button
                key={g}
                type="button"
                role="tab"
                aria-selected={group === g}
                onClick={() => setGroup(g)}
                className={cn(
                  "rounded-full border px-3 py-1 text-sm transition-colors",
                  group === g ? "border-primary-text bg-primary-soft text-foreground" : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {label} {searchTerms(query, g).length}
              </button>
            ))}
          </div>
        </div>
        <ul className="flex flex-col gap-2 overflow-y-auto px-6 py-4" aria-live="polite">
          {found.map((t) => (
            <li key={t.term} className="rounded-2xl border border-border bg-white/[0.025] px-4 py-3">
              <p className="flex flex-wrap items-baseline gap-x-2 text-base font-semibold text-foreground">
                {t.term}
                {t.aka && <span className="text-xs font-normal text-faint">{t.aka}</span>}
              </p>
              <p className="mt-1 text-sm break-keep text-soft">{t.plain}</p>
              <p className="mt-1.5 text-sm break-keep text-muted-foreground">
                <span className="mr-1 text-xs font-semibold text-cyan">이 서비스에서는</span>
                {t.example}
              </p>
            </li>
          ))}
          {found.length === 0 && <li className="py-8 text-center text-sm text-faint">찾는 말이 없어요. 다른 낱말로 찾아보세요.</li>}
        </ul>
      </div>
    </div>
  );
}
