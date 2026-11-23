// Word-level before/after diff for the CP5 card (LCS over whitespace tokens). Pure, unit-tested.
export type DiffKind = "same" | "del" | "add";
export interface DiffPart {
  text: string;
  kind: DiffKind;
}

function tokens(text: string): string[] {
  return text.split(/(\s+)/).filter((t) => t !== "");
}

// Merge neighbours of the same kind so the UI draws one mark per changed run.
function merge(parts: DiffPart[]): DiffPart[] {
  const out: DiffPart[] = [];
  for (const p of parts) {
    const last = out[out.length - 1];
    if (last && last.kind === p.kind) last.text += p.text;
    else out.push({ ...p });
  }
  return out;
}

export function diffWords(before: string, after: string): DiffPart[] {
  const a = tokens(before);
  const b = tokens(after);
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const parts: DiffPart[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      parts.push({ text: a[i], kind: "same" });
      i += 1;
      j += 1;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      parts.push({ text: a[i], kind: "del" });
      i += 1;
    } else {
      parts.push({ text: b[j], kind: "add" });
      j += 1;
    }
  }
  for (; i < a.length; i += 1) parts.push({ text: a[i], kind: "del" });
  for (; j < b.length; j += 1) parts.push({ text: b[j], kind: "add" });
  return runs(parts);
}

// One changed run reads as "removed words → added words": spaces between changed words join the run
// (on both sides), so "주문 마감" → "배송 하루" is one deletion and one addition, not four marks.
function runs(parts: DiffPart[]): DiffPart[] {
  const out: DiffPart[] = [];
  let i = 0;
  while (i < parts.length) {
    if (parts[i].kind === "same") {
      out.push(parts[i]);
      i += 1;
      continue;
    }
    let del = "";
    let add = "";
    while (i < parts.length) {
      const p = parts[i];
      const bridging = p.kind === "same" && /^\s+$/.test(p.text) && i + 1 < parts.length && parts[i + 1].kind !== "same";
      if (p.kind === "del") del += p.text;
      else if (p.kind === "add") add += p.text;
      else if (bridging) {
        del += p.text;
        add += p.text;
      } else break;
      i += 1;
    }
    if (del) out.push({ text: del, kind: "del" });
    if (add) out.push({ text: add, kind: "add" });
  }
  return merge(out);
}

// The two lines of the card: the old sentence (same + deleted) and the new one (same + added).
export function sides(parts: DiffPart[]): { before: DiffPart[]; after: DiffPart[] } {
  return {
    before: merge(parts.filter((p) => p.kind !== "add")),
    after: merge(parts.filter((p) => p.kind !== "del")),
  };
}
