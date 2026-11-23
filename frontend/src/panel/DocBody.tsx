import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Notice, NoticeList } from "@/components/ui/notice";
import { cn } from "@/lib/utils";
import type { Block, CheckWarning, DocId, DocView, TableBlock } from "../api";
import { isMark, sectionAnchor, splitIds, statusColumn } from "../lib/docOutline";
import { refAnchor } from "../lib/refCatalog";
import { nameIds, namedParts } from "../lib/summarize";
import { RefLink } from "../ui/refs";
import { WarningText } from "../thread/confirm/ReviewNotices";
import { WarningCount } from "../thread/confirm/DocTiles";
import { useTitles, useView } from "../ui/view";
import { DocHeader, DocToc, MarkedCallout } from "./DocHeader";
import type { DocFile } from "./docFiles";

const ID_CELL = /^(?:SRC|REQ|SCR|TC|EV|DEC|OPEN|CF|Q)-\d+$/;
type Plain = (t: string) => string;
type Say = (t: string) => ReactNode;

// One document in two layers (format spec P1·P9): a cover header, 「한눈에 보기」, what is still unconfirmed,
// a table of contents, then the detail tables. Client view: IDs become names and ID-only columns are hidden.
// Team view: everything, IDs shown as chips.
export default function DocBody({ doc, wide = false, files }: { doc: DocView; wide?: boolean; files?: DocFile[] }) {
  const team = useView() === "team";
  const titles = useTitles();
  const plain: Plain = (text) => (team ? text : nameIds(text, titles));
  // Every ID becomes a link: a chip in the team view, the item's 「name」 in the client view.
  const say: Say = (text) => (team ? <Rich text={text} /> : <Named text={text} titles={titles} />);
  const byTarget = groupWarnings(doc.warnings);
  return (
    // Fills the panel; the panel gives the side margins. Wide (full screen) only caps very long lines.
    <article className={cn("mx-auto flex w-full flex-col gap-6", wide && "max-w-[110rem]")}>
      <DocHeader doc={doc} team={team} files={files} />
      <DocWarnings warnings={doc.warnings} />

      <section className="rounded-2xl border border-primary-text/25 bg-[linear-gradient(135deg,rgb(101_83_245/0.14),rgb(127_227_240/0.05))] p-4" aria-label="한눈에 보기">
        <h4 className="flex items-center gap-1.5 text-sm font-semibold text-primary-text">
          <Sparkles className="size-4" aria-hidden="true" /> 한눈에 보기
        </h4>
        {doc.summary.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">아직 요약이 없어요.</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1.5">
            {doc.summary.map((line, i) => (
              <li key={i} className="flex gap-2 text-base leading-relaxed break-keep text-foreground">
                <span className="mt-2.5 size-1 shrink-0 rounded-full bg-primary-text" aria-hidden="true" />
                <span>{say(line)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <MarkedCallout doc={doc} team={team} plain={plain} />
      <DocToc doc={doc} team={team} />

      {doc.sections.map((s) => (
        <section key={s.id} id={sectionAnchor(doc.id, s.id)} className="flex scroll-mt-4 flex-col gap-3" aria-label={s.title}>
          <h4 className="border-t border-border pt-5 text-lg font-bold tracking-[-0.01em] break-keep text-foreground">
            {team ? s.title : plain(s.title)}
          </h4>
          {s.blocks.map((b, i) => (
            <BlockView key={i} block={b} doc={doc.id as DocId} warnings={byTarget} plain={plain} say={say} team={team} />
          ))}
        </section>
      ))}
    </article>
  );
}

function DocWarnings({ warnings }: { warnings: CheckWarning[] }) {
  const of = (sev: CheckWarning["severity"]) => warnings.filter((w) => w.severity === sev);
  const block = of("block");
  const waivable = of("waivable");
  const info = of("info");
  return (
    <>
      {block.length > 0 && (
        <Notice kind="block" title={`고쳐야 하는 곳 ${block.length}건`}>
          <NoticeList items={block.map((w) => <WarningText key={w.id} w={w} />)} />
        </Notice>
      )}
      {waivable.length > 0 && (
        <Notice kind="reason" title={`빈칸 ${waivable.length}건 — 확인 카드에서 이유를 적을 수 있어요`}>
          <NoticeList items={waivable.map((w) => <WarningText key={w.id} w={w} />)} />
        </Notice>
      )}
      {info.length > 0 && (
        <Notice kind="info" title={`알아 두시면 좋은 점 ${info.length}건`}>
          <NoticeList items={info.map((w) => <WarningText key={w.id} w={w} />)} />
        </Notice>
      )}
    </>
  );
}

function groupWarnings(list: CheckWarning[]): Record<string, CheckWarning[]> {
  const out: Record<string, CheckWarning[]> = {};
  for (const w of list) (out[w.target] ??= []).push(w);
  return out;
}

// Text with every ID shown as a chip that opens what it is (team view).
function Rich({ text }: { text: string }) {
  return (
    <>
      {splitIds(text).map((p, i) => (p.id ? <RefLink key={i} id={p.text} /> : <span key={i}>{p.text}</span>))}
    </>
  );
}

// Client view: IDs read as the item's name, and the name is the link.
function Named({ text, titles }: { text: string; titles: Record<string, string> }) {
  return (
    <>
      {namedParts(text, titles).map((p, i) => (p.id ? <RefLink key={i} id={p.id} label={p.text} /> : <span key={i}>{p.text}</span>))}
    </>
  );
}

function BlockView({ block, doc, warnings, plain, say, team }: {
  block: Block;
  doc: DocId;
  warnings: Record<string, CheckWarning[]>;
  plain: Plain;
  say: Say;
  team: boolean;
}) {
  switch (block.type) {
    case "paragraph":
      return <p className="text-base leading-relaxed break-keep text-soft">{say(block.text)}</p>;
    case "list":
      return (
        <ul className="flex flex-col gap-1.5">
          {block.items.map((item, i) => (
            <li key={i} className="flex gap-2 text-sm leading-relaxed break-keep text-soft">
              <span className="mt-2.5 size-1 shrink-0 rounded-full bg-faint" aria-hidden="true" />
              <span>{say(item)}</span>
            </li>
          ))}
        </ul>
      );
    case "table":
      return <Table table={block} doc={doc} warnings={warnings} say={say} team={team} />;
    case "screen":
      return (
        <div id={refAnchor(doc, block.id)} className="flex scroll-mt-4 flex-col gap-3 rounded-2xl border border-border bg-white/[0.02] p-3">
          {/* SVG is generated server-side from the element list; all text is XML-escaped there. */}
          <div
            className="wireframe overflow-x-auto rounded-xl bg-deep p-3 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
            role="img"
            aria-label={`${block.title} 화면 그림`}
            dangerouslySetInnerHTML={{ __html: block.svg }}
          />
          {block.purpose && <p className="text-sm text-muted-foreground">목적 · {plain(block.purpose)}</p>}
          <Table table={block.elements} doc={doc} warnings={warnings} say={say} team={team} />
          <Table table={block.states} doc={doc} warnings={warnings} say={say} team={team} />
        </div>
      );
  }
}

function StatusBadge({ value }: { value: string }) {
  if (isMark(value)) return <Badge variant="warning">{value}</Badge>;
  if (value === "확정") return <Badge variant="success">{value}</Badge>;
  return <>{value}</>;
}

function Table({ table, doc, warnings, say, team }: {
  table: TableBlock;
  doc: DocId;
  warnings: Record<string, CheckWarning[]>;
  say: Say;
  team: boolean;
}) {
  if (table.rows.length === 0) return <p className="text-sm text-faint">항목이 없어요</p>;
  // Client view drops columns that hold nothing but IDs.
  const keep = table.columns.map((_, j) => team || !table.rows.every((r) => ID_CELL.test((r[j] ?? "").trim()) || !(r[j] ?? "").trim()));
  const first = keep.indexOf(true);
  const status = statusColumn(table);
  const cell = (value: string, j: number) => {
    if (j === status) return <StatusBadge value={value.trim()} />;
    if (team && ID_CELL.test(value.trim())) return <RefLink id={value.trim()} />;
    return say(value);
  };
  return (
    <div className="max-h-[32rem] overflow-auto rounded-xl border border-border">
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr>
            {table.columns.map((c, j) =>
              keep[j] ? (
                <th key={c} scope="col" className="sticky top-0 z-[1] border-b border-border bg-deep px-3 py-2.5 text-xs font-semibold whitespace-nowrap text-muted-foreground">
                  {c}
                </th>
              ) : null,
            )}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => {
            const flagged = warnings[row[0]] ?? [];
            const marked = status >= 0 && isMark(row[status]);
            return (
              <tr
                key={i}
                id={ID_CELL.test((row[0] ?? "").trim()) ? refAnchor(doc, row[0].trim()) : undefined}
                className={cn(
                  "scroll-mt-12",
                  "border-t border-border align-top even:bg-white/[0.025]",
                  (flagged.length > 0 || marked) && "bg-[rgb(242_182_90/0.07)] even:bg-[rgb(242_182_90/0.07)]",
                )}
              >
                {row.map((value, j) =>
                  keep[j] ? (
                    <td key={j} className={cn("min-w-[5.5rem] px-3 py-2.5 leading-relaxed break-keep text-soft [overflow-wrap:anywhere]", value.length > 24 && "min-w-[12rem]", j === first && marked && "shadow-[inset_3px_0_0_var(--warning)]")}>
                      {cell(value, j)}
                      {j === first && flagged.length > 0 && (
                        <span className="ml-1.5" title={flagged.map((w) => w.message).join("\n")}>
                          <WarningCount warnings={flagged} />
                        </span>
                      )}
                    </td>
                  ) : null,
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
