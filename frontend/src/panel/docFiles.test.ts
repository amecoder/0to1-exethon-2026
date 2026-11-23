import { describe, expect, it } from "vitest";
import { urls } from "../api";
import { docFiles } from "./docFiles";

describe("docFiles (11-22: each document as PDF, Word, Markdown)", () => {
  it("lists PDF, Word and Markdown with the zip's file names", () => {
    const files = docFiles("screens", (doc, kind) => urls.doc("p 1", doc, kind));
    expect(files.map((f) => f.label)).toEqual(["PDF", "Word", "MD"]);
    expect(files.map((f) => f.filename)).toEqual(["화면설계서.pdf", "화면설계서.docx", "화면설계서.md"]);
    expect(files[0].href).toBe("/api/projects/p%201/documents/screens.pdf");
  });

  it("points the demo at the recording step", () => {
    const [pdf] = docFiles("prd", (doc, kind) => urls.demoDoc(12, doc, kind));
    expect(pdf.href).toBe("/api/demo/documents/prd.pdf?step=12");
    expect(pdf.filename).toBe("PRD.pdf");
  });
});
