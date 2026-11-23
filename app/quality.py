from __future__ import annotations
"""Format spec section 5: deterministic quality rules. They are proxies for "understood", not a measure.

Word lists live in app/data/*.json (first draft chosen by the author, see their `_note`).
Every rule returns plain values; quality_warnings() turns them into info-level warnings.
"""

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"


def _load(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


AMBIGUOUS_WORDS: tuple[str, ...] = tuple(_load("ambiguous_words.json")["words"])
GLOSSARY: tuple[dict[str, str], ...] = tuple(_load("glossary.json")["terms"])
_PLAIN = _load("plain_language.json")
CLIENT_BANNED: tuple[str, ...] = tuple(_PLAIN["client_banned"])
SOLUTION_WORDS: tuple[str, ...] = tuple(_PLAIN["solution_words"])

# 제안: A4 one page ≈ 1,500 Korean characters (author's assumption), so 2 pages = 3,000.
BRD_MAX_CHARS = 3000
SUMMARY_MAX_LINES = 5

_PARTICLES = "(?:[을를이가은는의과와도에]|으로)?"
_JOIN = re.compile(r"(?<=하고|되고|하며|되며)\s+|\s+(?:그리고|및|또는)\s+")
_PREDICATE = re.compile(r"[가-힣](?:다|고|며)(?=\s|$|[.,])")
_SENTENCE_END = re.compile(r"(?:다|요|까)[.?!]$|[?!]$")


def _word_pattern(word: str) -> re.Pattern[str]:
    if len(word) == 1:  # "등" must not match inside "등록"
        return re.compile(rf"(?<![가-힣]){re.escape(word)}{_PARTICLES}(?![가-힣])")
    return re.compile(rf"(?<![가-힣]){re.escape(word)}")


def _found(words: Sequence[str], text: str) -> list[str]:
    return [w for w in words if _word_pattern(w).search(text)]


# --- expert rules (ISO 29148) ---------------------------------------------------------------------
def singular_violation(statement: str) -> bool:
    """Two or more joined clauses that each carry a predicate → more than one behavior."""
    parts = [p for p in _JOIN.split(statement.strip()) if p.strip()]
    return len(parts) >= 2 and sum(bool(_PREDICATE.search(p)) for p in parts) >= 2


def ambiguous_words(text: str) -> list[str]:
    return _found(AMBIGUOUS_WORDS, text)


def missing_acceptance(req: Mapping[str, Any]) -> bool:
    acceptance = req.get("acceptance") or {}
    return any(not str(acceptance.get(k, "")).strip() for k in ("given", "when", "then"))


def missing_exceptions(req: Mapping[str, Any]) -> bool:
    return req.get("category", "SFR") == "SFR" and not req.get("exceptions")


# --- first-time reader rules ----------------------------------------------------------------------
def summary_problems(lines: Sequence[str]) -> list[str]:
    if not lines:
        return ["missing"]
    if len(lines) > SUMMARY_MAX_LINES:
        return ["too_long"]
    return ["fragment"] if any(not _SENTENCE_END.search(line.strip()) for line in lines) else []


def brd_too_long(markdown: str) -> bool:
    return len(markdown) > BRD_MAX_CHARS


def missing_explanations(lines: Sequence[str]) -> list[str]:
    """Glossary terms whose first occurrence is not followed by a parenthesized explanation."""
    text = "\n".join(lines)
    hits = [(text.find(g["term"]), g["term"]) for g in GLOSSARY if g["term"] in text]
    return [term for pos, term in sorted(hits) if not text[pos + len(term):].startswith("(")]


def annotate_terms(lines: Sequence[str]) -> list[str]:
    """Add "(explanation)" after the first occurrence of each glossary term. Idempotent."""
    result = list(lines)
    for entry in GLOSSARY:
        term = entry["term"]
        for i, line in enumerate(result):
            pos = line.find(term)
            if pos < 0:
                continue
            if not line[pos + len(term):].startswith("("):
                result[i] = f"{line[:pos + len(term)]}({entry['explain']}){line[pos + len(term):]}"
            break
    return result


def client_jargon(text: str) -> list[str]:
    return [w for w in CLIENT_BANNED if w in text]


def quote_interpretation_problem(row: Sequence[str], texts: Mapping[str, str]) -> bool:
    """BRD problem row = [SRC id, quote, interpretation]: quote verbatim, interpretation separate."""
    src_id, quote, interpretation = row[0], row[1], row[2]
    return texts.get(src_id) != quote or not interpretation.strip() or interpretation.strip() == quote.strip()


def solution_words(text: str) -> list[str]:
    return [w for w in SOLUTION_WORDS if w in text]


# --- aggregation ----------------------------------------------------------------------------------
def warning(code: str, target: str, doc: str, message: str) -> dict[str, Any]:
    return {"id": f"{code}:{target}", "code": code, "severity": "info", "target": target, "doc": doc,
            "message": message}


def requirement_warnings(req: Mapping[str, Any]) -> list[dict[str, Any]]:
    rid, statement = req["id"], str(req.get("statement", ""))
    acceptance = " ".join(str(v) for v in (req.get("acceptance") or {}).values())
    out = []
    if singular_violation(statement):
        out.append(warning("quality.singular", rid, "prd", "한 요구사항에 서로 다른 동작이 둘 이상 있습니다"))
    words = ambiguous_words(f"{statement} {acceptance}")
    if words:
        out.append(warning("quality.ambiguous", rid, "prd", f"모호한 말: {', '.join(words)}"))
    if missing_acceptance(req):
        out.append(warning("quality.unverifiable", rid, "prd", "인수 조건(Given/When/Then)에 빈칸이 있습니다"))
    if missing_exceptions(req):
        out.append(warning("quality.no_exceptions", rid, "prd", "기능 요구사항인데 예외 칸이 비어 있습니다"))
    return out


def client_warnings(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for card in source.get("questions", []):
        text = " ".join([card.get("question", ""), card.get("why", ""), *card.get("options", [])])
        words = client_jargon(text)
        if words:
            out.append(warning("quality.client_jargon", card["id"], "client",
                               f"발주사 화면에 전문 용어: {', '.join(words)}"))
    return out


def document_warnings(doc_id: str, doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    problems = summary_problems(doc.get("summary", []))
    if problems:
        labels = {"missing": "없습니다", "too_long": "5줄을 넘습니다", "fragment": "완전한 문장이 아닌 줄이 있습니다"}
        out.append(warning("quality.summary", doc_id, doc_id, f"한눈에 보기가 {labels[problems[0]]}"))
    terms = missing_explanations(doc.get("summary", []))
    if terms:
        out.append(warning("quality.glossary", doc_id, doc_id, f"풀이 없는 용어: {', '.join(terms)}"))
    return [*out, *doc.get("rule_warnings", [])]


def quality_warnings(source: Mapping[str, Any], docs: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = [w for req in source.get("requirements", []) for w in requirement_warnings(req)]
    out.extend(client_warnings(source))
    for doc_id, doc in docs.items():
        out.extend(document_warnings(doc_id, doc))
    return out
