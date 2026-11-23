import { ArrowUpRight, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { CheckWarning, DocId, DocView } from "../../api";
import { stripIds } from "../../lib/summarize";
import { DOC_NAME, DOC_ORDER, DOC_PLAIN, type PanelTarget } from "../../panel/types";
import { useView } from "../../ui/view";

// CP3: the four documents as tiles — name, what it is for, its first summary line, its warnings.
// A tile opens the document in the side panel.
export default function DocTiles({ docs, onOpen }: { docs: Record<DocId, DocView> | null; onOpen: (t: PanelTarget) => void }) {
  const team = useView() === "team";
  return (
    <section aria-label="문서 4종">
      <h3 className="text-base font-semibold text-foreground">문서 4종</h3>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {DOC_ORDER.map((id) => {
          const doc = docs?.[id];
          const line = doc?.summary[0];
          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => onOpen({ tab: "docs", doc: id })}
                className="group flex h-full w-full cursor-pointer flex-col gap-1.5 rounded-2xl border border-border bg-white/[0.03] p-4 text-left transition-colors hover:border-primary-text/50 hover:bg-primary-soft focus-visible:ring-[3px] focus-visible:ring-primary-ring focus-visible:outline-none"
              >
                <span className="flex w-full items-center gap-2">
                  <FileText className="size-4 text-primary-text" aria-hidden="true" />
                  <span className="text-base font-semibold text-foreground">{DOC_NAME[id]}</span>
                  {doc && <WarningCount warnings={doc.warnings} />}
                  <ArrowUpRight className="ml-auto size-4 text-faint transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-foreground" aria-hidden="true" />
                </span>
                <span className="text-xs text-muted-foreground">{DOC_PLAIN[id]}</span>
                <span className="line-clamp-2 text-sm break-keep text-soft">
                  {!doc ? "불러오는 중이에요…" : line ? (team ? line : stripIds(line)) : "아직 요약이 없어요"}
                </span>
                <span className="sr-only">— 옆 창에서 열기</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function WarningCount({ warnings }: { warnings: CheckWarning[] }) {
  if (warnings.length === 0) return null;
  const variant = warnings.some((w) => w.severity === "block")
    ? "danger"
    : warnings.some((w) => w.severity === "waivable")
      ? "warning"
      : "secondary";
  const word = variant === "danger" ? "막는 경고" : variant === "warning" ? "빈칸" : "참고";
  return (
    <Badge variant={variant} aria-label={`${word} ${warnings.length}건`}>
      {word} {warnings.length}
    </Badge>
  );
}
