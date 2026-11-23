import type { DocView, TableBlock } from "../api";

// Pure helpers behind the document view: header facts, table of contents, items still not confirmed,
// and ID chips. Kept out of the components so they can be tested without a DOM.

export const MARKS = ["가정", "미결", "미확인"] as const;
export type Mark = (typeof MARKS)[number];
const DRAFT_PREFIX = "작업본";
// Item IDs plus process codes (CP1–5 confirmations, S1–7 stages, G1–8 guardrails) — all of them open a detail card.
const ID_RE = /\b(?:(?:SRC|REQ|SCR|TC|EV|DEC|OPEN|CF|Q|FND|PROTO|CHG|CMP|ANS|ALT)-\d+|CP[1-5]|S[1-7]|G[1-8])\b/g;
const NAME_COLUMNS = ["이름", "화면명", "목표", "질문", "목적"];

export interface DocMeta {
  version: string;
  draft: boolean;
  approval: { cp: string; who: string; version: string } | null;
  date: string | null;
}

export function formatDate(iso: string | null | undefined): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? "");
  return m ? `${m[1]}. ${Number(m[2])}. ${Number(m[3])}.` : null;
}

export function docMeta(doc: DocView): DocMeta {
  const { version, approvals } = doc.header;
  const last = approvals.length ? approvals[approvals.length - 1] : null;
  return {
    version,
    draft: version.startsWith(DRAFT_PREFIX),
    approval: last && last.version === version ? { cp: last.cp, who: last.who, version: last.version } : null,
    date: formatDate(last?.at),
  };
}

export function sectionAnchor(docId: string, sectionId: string): string {
  return `doc-${docId}-${sectionId}`.replace(/[^A-Za-z0-9_-]/g, "_");
}

export function tocOf(doc: DocView): { anchor: string; title: string }[] {
  return doc.sections.map((s) => ({ anchor: sectionAnchor(doc.id, s.id), title: s.title }));
}

/** Column that holds a row's status (가정·미결 …) — not a count table where 상태 is the first column. */
export function statusColumn(table: TableBlock): number {
  const at = table.columns.indexOf("상태");
  return at > 0 ? at : -1;
}

export function isMark(value: string | undefined): value is Mark {
  return MARKS.includes((value ?? "").trim() as Mark);
}

export interface MarkedItem {
  mark: Mark;
  id: string;
  label: string;
  anchor: string;
}

export function markedItems(doc: DocView): MarkedItem[] {
  const out: MarkedItem[] = [];
  for (const s of doc.sections) {
    for (const b of s.blocks) {
      const tables = b.type === "table" ? [b] : b.type === "screen" ? [b.elements] : [];
      for (const t of tables) {
        const col = statusColumn(t);
        if (col < 0) continue;
        const nameAt = t.columns.findIndex((c) => NAME_COLUMNS.includes(c));
        for (const row of t.rows) {
          const mark = row[col]?.trim();
          if (!isMark(mark)) continue;
          out.push({ mark, id: row[0] ?? "", label: row[nameAt >= 0 ? nameAt : 0] ?? "", anchor: sectionAnchor(doc.id, s.id) });
        }
      }
    }
  }
  return out;
}

/** Text split into plain parts and ID tokens, so IDs can be shown as chips. */
export function splitIds(text: string): { text: string; id: boolean }[] {
  const parts: { text: string; id: boolean }[] = [];
  let at = 0;
  for (const m of text.matchAll(ID_RE)) {
    const start = m.index ?? 0;
    if (start > at) parts.push({ text: text.slice(at, start), id: false });
    parts.push({ text: m[0], id: true });
    at = start + m[0].length;
  }
  if (at < text.length) parts.push({ text: text.slice(at), id: false });
  return parts;
}
