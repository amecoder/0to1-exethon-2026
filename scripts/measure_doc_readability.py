from __future__ import annotations
"""How readable are the documents the product hands off? Renders them from a source.json with the product's own
renderer (no Liner call) and lints them with hanlint.

    uv run python scripts/measure_doc_readability.py SOURCE.json --out OUT_DIR

hanlint does not look inside Markdown table cells, list items or block quotes (measured 2026-11-24), and most of
our text sits there. So besides the normal run, a "cell copy" is linted: every table cell of MIN_CELL characters
or more, every list item and every quoted line becomes its own paragraph (a cell or list line that only lists IDs
is left out: it is a reference, not a sentence)
(the map back to document / section / row / column is kept in OUT_DIR/map.json). `paraFragment` and `sectionNoProse` are artefacts of that copy and are
switched off there; `sectionNoProse` is reported from the normal run.

Each piece of text is 「model」 when it carries a string of the shared source (what the agents wrote) and 「code」
otherwise (headings, intros, fixed phrases). 「model_s5」 is the part of 「model」 written in the document stage
(screens, tests, BRD/PRD content) — what the document-writing prompts govern. Reported per document and origin:
findings, findings per 1,000 characters, and the share of sentences over LONG_WORDS 어절. A proxy for
readability, not a judgement of it.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

HANLINT = ("uvx", "--quiet", "--from", "hanlint==0.0.19", "hanlint")
DOCS = ("BRD.md", "PRD.md", "화면설계서.md", "테스트케이스.md", "AGENTS.md", "제안요약.md", "README.txt")
SCOPE_MARK = "(범위 밖)"
MIN_CELL = 25
MIN_MODEL_STRING = 12
LONG_WORDS = 30
COPY_OFF = ("dash", "paraFragment", "sectionNoProse")
NORMAL_OFF = ("dash",)
S5_KEYS = ("screens", "screen_spec", "tests", "test_plan", "brd", "prd")
GROUPS = ("code", "model", "model_s5")
SKIP_KEYS = ("versions", "prototype", "flow_chart", "events", "meta", "evidence")
_SPLIT_CELL = re.compile(r"(?<!\\)\|")
_SENTENCE = re.compile(r"(?<=[.?!])\s+")
_PAREN = re.compile(r"\([^()]*\)")
_ID_LIST = re.compile(r"[A-Z]{1,6}-\d+")
_LEAD = re.compile(r"^\s*(?:(?:[-*>]|\d+[.)])\s+)+")
_MARKUP = re.compile(r"^(?:[-*>]\s+|#+\s+|\d+[.)]\s+)+|[*_`]")


class Segment(NamedTuple):
    doc: str
    section: str
    kind: str  # heading / prose / list / quote / cell
    row: int  # table row (1-based, header excluded); 0 for prose
    column: str
    text: str
    origin: str  # code / model / model_s5 (model text written in the document stage)
    line: int  # line in the lint copy


def _squash(text: str) -> str:
    """One-line text without the table escape and without the 「(범위 밖)」 mark the renderer adds after an ID."""
    return " ".join(text.replace("\\|", "|").replace(SCOPE_MARK, "").split())


def model_strings(source: Mapping[str, Any], keys: Sequence[str] | None = None) -> tuple[str, ...]:
    """Every string the agents (or the client) wrote, long enough to tell it from a label.
    `keys` narrows it to some collections (S5_KEYS: what the document stage wrote)."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and len(_squash(node)) >= MIN_MODEL_STRING:
            found.add(_squash(node))

    for key, value in source.items():
        if key not in SKIP_KEYS and (keys is None or key in keys):
            walk(value)
    return tuple(sorted(found, key=len, reverse=True))


def _no_gloss(text: str) -> str:
    """Without parentheses: the renderer adds a glossary note after a term, which splits the agent's sentence."""
    return " ".join(_PAREN.sub("", text).split())


def _carries(text: str, strings: Sequence[str]) -> bool:
    plain, bare = _squash(text), _no_gloss(_squash(text))
    return any(s in plain or (len(_no_gloss(s)) >= MIN_MODEL_STRING and _no_gloss(s) in bare) for s in strings)


def origin_of(text: str, strings: Sequence[str], s5_strings: Sequence[str] = ()) -> str:
    if _carries(text, s5_strings):
        return "model_s5"
    return "model" if _carries(text, strings) else "code"


def only_ids(text: str) -> bool:
    """A cell or list line that only lists IDs (REQ-01, TC-02 …) is a reference, not a sentence to lint."""
    return not _ID_LIST.sub("", text.replace(SCOPE_MARK, "")).strip(" ,·/—-")


def split_row(line: str) -> list[str]:
    return [c.strip() for c in _SPLIT_CELL.split(line.strip().strip("|"))]


def extract(doc: str, markdown: str, strings: Sequence[str], s5_strings: Sequence[str] = ()
            ) -> tuple[list[Segment], str]:
    """Segments of one document and its lint copy (tables replaced by one paragraph per long cell)."""
    segments: list[Segment] = []
    out: list[str] = []
    section, header, row_no = "", [], 0

    def add(kind: str, text: str, row: int = 0, column: str = "") -> None:
        out.append(text)
        segments.append(Segment(doc, section, kind, row, column, text, origin_of(text, strings, s5_strings), len(out)))
        out.append("")

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            header, row_no = [], 0
            continue
        if line.lstrip().startswith("|"):
            cells = split_row(line)
            if not header:
                header = cells
            elif not all(set(c) <= set("-: ") for c in cells):
                row_no += 1
                for i, cell in enumerate(cells):
                    if len(cell) >= MIN_CELL and not only_ids(cell):
                        add("cell", _squash(cell), row_no, header[i] if i < len(header) else "")
            continue
        header, row_no = [], 0
        if line.startswith("#"):
            section = line.lstrip("# ").strip()
            add("heading", line)
        else:
            bare = _LEAD.sub("", line).strip()
            kind = "quote" if line.lstrip().startswith(">") else "list" if bare != line.strip() else "prose"
            if bare and not only_ids(bare):
                add(kind, bare)
    return segments, "\n".join(out) + "\n"


def sentences(text: str) -> list[str]:
    plain = _MARKUP.sub("", text.strip())
    return [s for s in _SENTENCE.split(plain) if s.strip()]


def long_share(segments: Iterable[Segment]) -> tuple[int, int]:
    """(sentences over LONG_WORDS 어절, all sentences) in prose and cells."""
    all_sentences = [s for seg in segments if seg.kind != "heading" for s in sentences(seg.text)]
    return sum(1 for s in all_sentences if len(s.split()) > LONG_WORDS), len(all_sentences)


def run_hanlint(folder: Path, off: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    """{file name: findings} for the Markdown files of a folder."""
    disable = [part for rule in off for part in ("--disable", rule)]
    cmd = [*HANLINT, str(folder), "--preset", "docs", *disable, "--format", "json"]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode not in (0, 1) or not done.stdout.strip():
        raise RuntimeError(f"hanlint 실행 실패(exit {done.returncode}): {done.stderr.strip()[:300]}")
    return {Path(f["path"]).name: f.get("findings", []) for f in json.loads(done.stdout).get("files", [])}


def per_thousand(findings: int, chars: int) -> float:
    return round(findings * 1000 / chars, 2) if chars else 0.0


def summarize(segments: Sequence[Segment], findings: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Findings of one document's cell copy, split by who wrote the text."""
    by_line = {s.line: s for s in segments}
    out: dict[str, Any] = {}
    for origin in GROUPS:
        mine = [s for s in segments if s.origin == origin or (origin == "model" and s.origin == "model_s5")]
        hits = [f for f in findings if by_line.get(int(f.get("line", 0))) in mine]
        chars = sum(len(s.text) for s in mine)
        long_n, total = long_share(mine)
        out[origin] = {"chars": chars, "findings": len(hits), "per_1000": per_thousand(len(hits), chars),
                       "rules": dict(Counter(f["rule"] for f in hits).most_common()),
                       "sentences": total, "long_sentences": long_n,
                       "long_share": round(long_n / total, 4) if total else 0.0}
    unplaced = [f for f in findings if int(f.get("line", 0)) not in by_line]
    out["unplaced"] = dict(Counter(f["rule"] for f in unplaced))  # document-level findings (no single line)
    return out


def total_of(per_doc: Mapping[str, Mapping[str, Any]], origin: str) -> dict[str, Any]:
    rows = [d[origin] for d in per_doc.values()]
    chars, hits = sum(r["chars"] for r in rows), sum(r["findings"] for r in rows)
    total, long_n = sum(r["sentences"] for r in rows), sum(r["long_sentences"] for r in rows)
    rules: Counter[str] = Counter()
    for r in rows:
        rules.update(r["rules"])
    return {"chars": chars, "findings": hits, "per_1000": per_thousand(hits, chars), "rules": dict(rules.most_common()),
            "sentences": total, "long_sentences": long_n, "long_share": round(long_n / total, 4) if total else 0.0}


def render(source: Mapping[str, Any]) -> dict[str, str]:
    from app.export import bundle_files

    files = bundle_files(source)
    return {name: str(files[name]) for name in DOCS if name in files}


def measure(source: Mapping[str, Any], out_dir: Path, docs: Mapping[str, str] | None = None) -> dict[str, Any]:
    docs = dict(docs) if docs is not None else render(source)
    strings, s5_strings = model_strings(source), model_strings(source, S5_KEYS)
    normal, copy = out_dir / "normal", out_dir / "cells"
    for folder in (normal, copy):
        folder.mkdir(parents=True, exist_ok=True)
    segments: dict[str, list[Segment]] = {}
    for name, text in docs.items():
        stem = Path(name).stem
        (normal / f"{stem}.md").write_text(text, encoding="utf-8")
        segments[stem], lint_copy = extract(name, text, strings, s5_strings)
        (copy / f"{stem}.md").write_text(lint_copy, encoding="utf-8")
    (out_dir / "map.json").write_text(json.dumps(
        {stem: [s._asdict() for s in segs] for stem, segs in segments.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    normal_found, copy_found = run_hanlint(normal, NORMAL_OFF), run_hanlint(copy, COPY_OFF)
    per_doc = {stem: summarize(segs, copy_found.get(f"{stem}.md", [])) for stem, segs in segments.items()}
    bare = {stem: [f.get("quote") or f"line {f.get('line')}" for f in normal_found.get(f"{stem}.md", [])
                   if f["rule"] == "sectionNoProse"] for stem in segments}
    return {"documents": per_doc, "total": {o: total_of(per_doc, o) for o in GROUPS},
            "section_no_prose": {"count": sum(len(v) for v in bare.values()), "by_document": bare},
            "settings": {"hanlint": "0.0.19", "preset": "docs", "min_cell": MIN_CELL, "long_words": LONG_WORDS,
                         "copy_disabled": list(COPY_OFF), "normal_disabled": list(NORMAL_OFF)}}


def report_lines(result: Mapping[str, Any]) -> list[str]:
    lines = ["문서 | 글쓴이 | 글자 | 지적 | 1,000자당 | 30어절 넘는 문장 | 많이 걸린 규칙", "---|---|---|---|---|---|---"]
    rows = [*result["documents"].items(), ("합계", result["total"])]
    for name, doc in rows:
        for origin in GROUPS:
            r = doc[origin]
            top = ", ".join(f"{k} {v}" for k, v in list(r["rules"].items())[:4]) or "—"
            lines.append(f"{name} | {origin} | {r['chars']} | {r['findings']} | {r['per_1000']} | "
                         f"{r['long_sentences']}/{r['sentences']} ({r['long_share'] * 100:.1f}%) | {top}")
    bare = result["section_no_prose"]
    lines += ["", f"설명글 없는 절(sectionNoProse, 보통 실행): {bare['count']}곳 — "
              + ", ".join(f"{k} {len(v)}" for k, v in bare["by_document"].items() if v)]
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="넘겨주는 문서의 읽기 쉬움을 hanlint 로 잰다")
    parser.add_argument("source", type=Path, help="source.json (공유 원본)")
    parser.add_argument("--out", type=Path, required=True, help="린트 사본·지도·결과를 둘 폴더")
    args = parser.parse_args(argv)
    source = json.loads(args.source.read_text(encoding="utf-8"))
    result = measure(source, args.out)
    (args.out / "readability.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(report_lines(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
