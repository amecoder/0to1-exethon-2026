import type { ReactNode } from "react";
import { BadgeCheck, CircleDashed, Download, ListTree, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { DocView } from "../api";
import { docMeta, markedItems, tocOf, type MarkedItem } from "../lib/docOutline";
import { stripIds } from "../lib/summarize";
import { WarningCount } from "../thread/confirm/DocTiles";
import type { DocFile } from "./docFiles";
import { DOC_NAME, DOC_PLAIN } from "./types";

// Moves the panel's scroll to a section without touching the URL hash (the app does not route on it).
export function jumpTo(anchor: string) {
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(anchor)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

// Cover block of one document: name, version, approval state, author agent and date.
export function DocHeader({ doc, team, files }: { doc: DocView; team: boolean; files?: DocFile[] }) {
  const meta = docMeta(doc);
  const id = doc.id as keyof typeof DOC_NAME;
  return (
    <header className="flex flex-col gap-3 border-b border-border pb-5">
      <div className="flex flex-col gap-1">
        <p className="text-xs font-semibold text-primary-text">{DOC_PLAIN[id] ?? ""}</p>
        <h3 className="flex flex-wrap items-center gap-2 text-2xl font-bold tracking-[-0.02em] text-foreground">
          {DOC_NAME[id] ?? doc.title.split("—")[0].trim()}
          <WarningCount warnings={doc.warnings} />
        </h3>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <Fact label="버전">
          <Badge variant={meta.draft ? "outline" : "default"} className="font-mono">{meta.version}</Badge>
        </Fact>
        <Fact label="승인">
          {meta.approval ? (
            <Badge variant="success">
              <BadgeCheck aria-hidden="true" /> 승인됨{team ? ` · ${meta.approval.cp}` : ""}
            </Badge>
          ) : (
            <Badge variant="warning">
              <CircleDashed aria-hidden="true" /> 승인 전
            </Badge>
          )}
        </Fact>
        <Fact label="작성">{doc.header.owner_name}</Fact>
        <Fact label="날짜">{meta.date ?? "—"}</Fact>
      </dl>
      {files && (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="이 문서 내려받기">
          <span className="text-xs text-faint">내려받기</span>
          {files.map((f) => (
            <Button key={f.kind} variant="outline" size="sm" asChild>
              <a href={f.href} download={f.filename}>
                <Download aria-hidden="true" /> {f.label}
              </a>
            </Button>
          ))}
        </div>
      )}
    </header>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="text-xs text-faint">{label}</dt>
      <dd className="m-0 flex min-w-0 items-center text-soft">{children}</dd>
    </div>
  );
}

export function DocToc({ doc, team }: { doc: DocView; team: boolean }) {
  const items = tocOf(doc);
  if (items.length < 2) return null;
  return (
    <nav aria-label="목차" className="rounded-2xl border border-border bg-white/[0.02] p-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
        <ListTree className="size-3.5" aria-hidden="true" /> 목차
      </p>
      <ol className="grid gap-0.5 sm:grid-cols-2">
        {items.map((t) => (
          <li key={t.anchor}>
            <button
              type="button"
              onClick={() => jumpTo(t.anchor)}
              className="w-full cursor-pointer rounded-lg px-2 py-1.5 text-left text-sm break-keep text-soft transition-colors outline-none hover:bg-white/[0.05] hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-primary-ring"
            >
              {team ? t.title : stripIds(t.title)}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}

// Callout listing what the client has not confirmed yet (가정·미결·미확인 rows found in the tables).
export function MarkedCallout({ doc, team, plain }: { doc: DocView; team: boolean; plain: (t: string) => string }) {
  const items = markedItems(doc);
  if (items.length === 0) return null;
  return (
    <aside
      aria-label="확정되지 않은 항목"
      className="rounded-2xl border border-warning/30 bg-warning-soft p-4"
    >
      <p className="flex items-center gap-1.5 text-sm font-semibold text-warning">
        <TriangleAlert className="size-4" aria-hidden="true" /> 아직 확정되지 않은 항목 {items.length}건
      </p>
      <p className="mt-1 text-sm break-keep text-soft">그대로 만들기 전에 발주사와 한 번 더 확인하세요.</p>
      <ul className="mt-3 flex flex-col gap-1.5">
        {items.map((it: MarkedItem, i) => (
          <li key={`${it.id}-${i}`}>
            <button
              type="button"
              onClick={() => jumpTo(it.anchor)}
              className="flex w-full cursor-pointer items-center gap-2 rounded-lg text-left text-sm text-soft outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-primary-ring"
            >
              <Badge variant="warning">{it.mark}</Badge>
              {team && <code className="font-mono text-xs text-primary-text">{it.id}</code>}
              <span className="min-w-0 break-keep">{plain(it.label)}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
