import type { DocId } from "../api";

// 11-22: one document as a file. The server builds each from the same document view (app/routes_documents.py).
export type DocKind = "pdf" | "docx" | "md";
export type DocUrl = (doc: DocId, kind: DocKind) => string;
export type DocFile = { kind: DocKind; label: string; href: string; filename: string };

// Same names as the files in the zip (app/export.py DOC_FILES).
const FILE_STEM: Record<DocId, string> = { brd: "BRD", prd: "PRD", screens: "화면설계서", tests: "테스트케이스" };
const KINDS: { kind: DocKind; label: string }[] = [
  { kind: "pdf", label: "PDF" },
  { kind: "docx", label: "Word" },
  { kind: "md", label: "MD" },
];

export function docFiles(doc: DocId, url: DocUrl): DocFile[] {
  return KINDS.map(({ kind, label }) => ({ kind, label, href: url(doc, kind), filename: `${FILE_STEM[doc]}.${kind}` }));
}
