import { stripIds } from "./summarize";
import type { CompanySummary } from "../api";

// The company workspace this browser chose last (no login: a convenience, not access control).
export const COMPANY_KEY = "company-id";

export function rememberedCompany(): string | null {
  try {
    return localStorage.getItem(COMPANY_KEY);
  } catch {
    return null;
  }
}

export function rememberCompany(id: string): void {
  try {
    localStorage.setItem(COMPANY_KEY, id);
  } catch {
    // storage blocked: the first company is chosen next time
  }
}

export function chooseCompany(companies: CompanySummary[], remembered: string | null): string | null {
  if (companies.some((c) => c.id === remembered)) return remembered;
  return companies[0]?.id ?? null;
}

// Which projects the start screen lists: the chosen company's while the workspace is on (null = not chosen yet),
// every project when it is switched off for the contest submission (EXETHON_COMPANY=off).
export function listFilter(companyOn: boolean, company: string | null): string | null | undefined {
  if (!companyOn) return undefined;
  return company;
}

// The browser remembers the last 「우리 시스템 목록」 per company, so one company's list never prefills another's.
export function systemsKey(companyId: string | undefined): string {
  return companyId ? `our-systems:${companyId}` : "our-systems";
}

// 「우리 시스템 목록」 for a new request: what the user already typed stays; else the company's list, else the
// one this browser remembered for this company.
export function systemsToPrefill(companySystems: string, remembered: string, typed = ""): string {
  if (typed.trim()) return typed;
  return companySystems.trim() ? companySystems : remembered;
}

// Same rule as the server (app/company.py note_lines): one note per non-empty line, '#' lines are headings.
export function noteCount(notes: string): number {
  return notes.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).length;
}

// CP2 answer rows: an answer the company material settled (S3) is not one the client picked — say so.
export function answeredByLabel(row: { answered_by?: string; company_ref?: string | null }, showRef = true): string | null {
  if (row.answered_by !== "company") return null;
  return row.company_ref && showRef ? `회사 자료로 정함 · ${row.company_ref}` : "회사 자료로 정함";
}

/** A company decision's question is the QA finding it settled, full of internal ids: the client view leaves it out. */
export function clientQuestion(text: string): string | null {
  return stripIds(text) === text.trim() ? text : null;
}
