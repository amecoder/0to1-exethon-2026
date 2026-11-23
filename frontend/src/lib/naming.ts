// D1: a project name as the server keeps it (app/naming.py clean_name) — one line, no list separators, ≤ 40.
export const NAME_MAX = 40;

export function cleanName(text: string): string {
  const name = text
    .replace(/\s+/g, " ")
    .replace(/\s*[:：]\s*/g, " ")
    .replace(/\s+[—–-]\s+/g, "-")
    .replace(/\s+/g, " ")
    .trim();
  return name.slice(0, NAME_MAX).trim();
}
