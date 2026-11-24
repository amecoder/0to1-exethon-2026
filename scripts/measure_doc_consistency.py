from __future__ import annotations
"""Do the hand-off documents agree with the shared source and with each other? Deterministic checks, no model.

    uv run python scripts/measure_doc_consistency.py SOURCE.json [--bundle-dir DIR] [--out result.json]

Without --bundle-dir the documents are rendered from SOURCE.json by the product's own code (no Liner call).

(a) scope: a requirement the client dropped when narrowing the screens (`dropped_requirements` of the scope
    decision) or a screen that was not kept is named in a document outside the 「이번 범위에서 뺀 것」 part
    without the mark 「(범위 밖)」; a wireframe still draws an element that leads to a dropped screen; a lane
    step on a dropped screen is not marked.
(b) open count: README.txt says 미결 N건, but more is open — items with status 미결·미확인, open items, BRD goals
    without a number, and requirements / screen elements whose text still says 미정·빈칸·확인 필요.
(c) integrations: 제안요약 says 연계 시스템 N개, but the requirements name more outside services (payment
    provider, push, address search, text message, sign-in provider …) than that.
(d) dangling: a document names an ID (REQ-·SCR-·TC-·DEC- …) that the source does not have.
"""

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DOCS = ("BRD.md", "PRD.md", "화면설계서.md", "테스트케이스.md", "AGENTS.md", "제안요약.md")
MARK = "(범위 밖)"
OUT_HEADINGS = ("범위에서 뺀", "범위 밖")
BLANK_WORDS = ("미정", "빈칸", "확인 필요", "확인이 필요", "결정 필요", "정해지지 않")
OPEN_STATUSES = ("미결", "미확인")
NEGATIONS = ("않", "없", "제외", "말고", "아니")
INTEGRATIONS: dict[str, tuple[str, ...]] = {
    "결제대행사(PG)": ("결제대행사", "PG사", "빌링키", "간편결제"),
    "앱 푸시 알림": ("푸시",),
    "문자·알림톡 발송": ("문자 발송", "문자로", "SMS", "알림톡"),
    "주소 검색": ("주소 검색", "우편번호"),
    "로그인·본인 확인 제공자": ("소셜 로그인", "카카오 로그인", "네이버 로그인", "구글 로그인", "애플 로그인", "간편 로그인", "본인인증"),
    "이메일 발송": ("이메일 발송", "메일 발송", "이메일로"),
    "지도·위치": ("지도", "위치 정보", "GPS"),
    "택배·배송 조회": ("택배사", "운송장", "배송 조회"),
}
COLLECTIONS = {"REQ": "requirements", "SCR": "screens", "TC": "tests", "DEC": "decisions", "SRC": "sources",
               "EV": "evidence", "FND": "findings", "Q": "questions", "ALT": "alternatives", "PS": "problem_statement",
               "CF": "confirmations", "SYS": "systems", "FB": "feedback", "CHG": "changes", "OPEN": "open_items"}
_ID_GROUP = re.compile(r"(?<![A-Za-z0-9/])([A-Z]{1,5})-(\d{1,4})((?:·\d{2,4}(?![\d-]))*)")
_CLAUSE = re.compile(r"[.,;]\s|\n")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def scope_cut(source: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    """(dropped requirement IDs, dropped screen IDs) of the latest scope decision; empty sets without one."""
    scope = next((d for d in reversed(source.get("decisions", [])) if d.get("kind") == "scope"), None)
    if not scope:
        return set(), set()
    kept = set(scope.get("screens_kept") or [])
    spec = (source.get("screen_spec") or [{}])[0]
    drawn = set((spec.get("id_map") or {}).values())
    return set(scope.get("dropped_requirements") or []), drawn - kept


def id_mentions(text: str) -> list[tuple[str, bool]]:
    """(ID, marked) for every ID in the text. 「REQ-12·14」 names REQ-12 and REQ-14; a mark after the group
    covers all of its members."""
    out = []
    for m in _ID_GROUP.finditer(text):
        marked = text[m.end():].startswith(MARK)
        width = len(m.group(2))
        numbers = [m.group(2), *[n for n in m.group(3).split("·") if n]]
        out += [(f"{m.group(1)}-{n.zfill(width) if len(n) < width else n}", marked) for n in numbers]
    return out


def lines_outside(markdown: str, headings: Sequence[str] = OUT_HEADINGS) -> list[tuple[str, str]]:
    """(section title, line) for every line that is not under a heading naming one of `headings`."""
    out, section, level_out = [], "", 0
    for line in markdown.splitlines():
        m = _HEADING.match(line)
        if m:
            level = len(line) - len(line.lstrip("#"))
            if level_out and level <= level_out:
                level_out = 0
            if any(h in m.group(1) for h in headings):
                level_out = level
            section = m.group(1)
        if not level_out and line.strip():
            out.append((section, line))
    return out


def _strings(node: Any) -> Iterable[str]:
    if isinstance(node, Mapping):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)
    elif isinstance(node, str):
        yield node


def check_scope(source: Mapping[str, Any], files: Mapping[str, str]) -> list[dict[str, str]]:
    reqs, screens = scope_cut(source)
    dropped = reqs | screens
    out = []
    for name in DOCS:
        for section, line in lines_outside(files.get(name, "")):
            for found in sorted({i for i, marked in id_mentions(line) if i in dropped and not marked}):
                out.append({"check": "a", "where": f"{name} · {section}", "what": found, "line": line.strip()[:120]})
    for screen in source.get("screens", []):
        svg = files.get(f"wireframes/{screen['id']}.svg", "")
        for e in screen.get("elements", []):
            if any(i in screens for i, _ in id_mentions(str(e.get("action", "")))) and str(e.get("name", "")) in svg:
                out.append({"check": "a", "where": f"wireframes/{screen['id']}.svg", "what": f"#{e.get('no')} {e.get('name')}",
                            "line": str(e.get("action", ""))[:120]})
    lanes = files.get("user_flow_lanes.html", "")
    for step in ((source.get("screen_spec") or [{}])[0].get("swimlane") or {}).get("steps", []):
        if step.get("screen_ref") in screens and lanes:
            group = re.search(rf'<g data-step="{re.escape(str(step["id"]))}".*?</g>', lanes, re.S)
            if group and "범위 밖" not in group.group(0):
                out.append({"check": "a", "where": "user_flow_lanes.html", "what": str(step["screen_ref"]),
                            "line": str(step.get("label", ""))})
    for found in sorted({i for i, marked in id_mentions(files.get("user_flow.html", "")) if i in dropped and not marked}):
        out.append({"check": "a", "where": "user_flow.html", "what": found, "line": ""})
    return out


def has_blank(node: Any) -> bool:
    return any(word in text for text in _strings(node) for word in BLANK_WORDS)


def open_points(source: Mapping[str, Any]) -> dict[str, list[str]]:
    """What is still open, by kind — the number README.txt should not undercount."""
    dropped, _ = scope_cut(source)
    reqs = [r for r in source.get("requirements", []) if r["id"] not in dropped]
    status = [f"{i['id']}" for kind in ("requirements", "screens", "tests") for i in source.get(kind, [])
              if i.get("status") in OPEN_STATUSES and i["id"] not in dropped]
    goals = [g.get("goal", "") for b in source.get("brd", []) for g in b.get("goals", []) if g.get("status") == "미결"]
    blanks = [r["id"] for r in reqs if r.get("status") not in OPEN_STATUSES
              and has_blank({k: r.get(k) for k in ("title", "statement", "acceptance", "exceptions")})]
    blanks += [f"{s['id']}#{e.get('no')}" for s in source.get("screens", []) for e in s.get("elements", [])
               if has_blank({k: e.get(k) for k in ("name", "description", "action", "input_rule")})]
    return {"status": status, "open_items": [o.get("id", "") for o in source.get("open_items", [])],
            "goals": goals, "blanks": blanks}


def check_open_count(source: Mapping[str, Any], files: Mapping[str, str]) -> list[dict[str, str]]:
    points = open_points(source)
    found = sum(len(v) for v in points.values())
    stated = re.search(r"미결 (\d+)(?:건|곳)", files.get("README.txt", ""))
    said = int(stated.group(1)) if stated else 0
    if said >= found:
        return []
    detail = " · ".join(f"{k} {len(v)}" for k, v in points.items())
    return [{"check": "b", "where": "README.txt", "what": f"미결 {said}건이라고 적었지만 {found}곳이 열려 있다",
             "line": detail}]


def integrations(source: Mapping[str, Any]) -> dict[str, list[str]]:
    """{outside service: [requirement / screen IDs]} from clauses that do not negate it."""
    dropped, _ = scope_cut(source)
    out: dict[str, list[str]] = {}
    items = [(r["id"], r) for r in source.get("requirements", []) if r["id"] not in dropped]
    items += [(s["id"], s.get("elements", [])) for s in source.get("screens", [])]
    for item_id, node in items:
        clauses = [c for text in _strings(node) for c in _CLAUSE.split(text)]
        for name, words in INTEGRATIONS.items():
            if any(w in c and not any(n in c for n in NEGATIONS) for c in clauses for w in words):
                out.setdefault(name, []).append(item_id)
    return out


def check_integrations(source: Mapping[str, Any], files: Mapping[str, str]) -> list[dict[str, str]]:
    listed = {f.get("system_ref") for s in source.get("scope", []) for f in s.get("systems", [])}
    named = integrations(source)
    stated = re.search(r"연계 시스템 (\d+)개", files.get("제안요약.md", ""))
    said = int(stated.group(1)) if stated else 0
    if said >= len(listed) + len(named):
        return []
    return [{"check": "c", "where": "제안요약.md", "what": f"연계 시스템 {said}개라고 적었지만 {len(listed) + len(named)}개다",
             "line": " · ".join(f"{k}({', '.join(v)})" for k, v in named.items())}]


def known_ids(source: Mapping[str, Any]) -> set[str]:
    ids = {str(i.get("id")) for kind in COLLECTIONS.values() for i in source.get(kind, []) if isinstance(i, Mapping)}
    ids |= {str(o.get("id")) for p in source.get("test_plan", []) for o in p.get("ops_checks", [])}
    return ids


def check_dangling(source: Mapping[str, Any], files: Mapping[str, str]) -> list[dict[str, str]]:
    known = known_ids(source)
    _, dropped_screens = scope_cut(source)
    prefixes = {*COLLECTIONS, "OPS"}
    out = []
    for name in DOCS:
        section = ""
        for line in files.get(name, "").splitlines():
            m = _HEADING.match(line)
            section = m.group(1) if m else section
            for found in sorted({i for i, _ in id_mentions(line)}):
                if found.split("-")[0] in prefixes and found not in known and found not in dropped_screens:
                    out.append({"check": "d", "where": f"{name} · {section}", "what": found, "line": line.strip()[:120]})
    return out


def read_bundle(folder: Path) -> dict[str, str]:
    return {str(p.relative_to(folder)): p.read_text(encoding="utf-8") for p in folder.rglob("*")
            if p.is_file() and p.suffix in (".md", ".txt", ".svg", ".html") and p.name != "prototype.html"}


def measure(source: Mapping[str, Any], files: Mapping[str, str] | None = None) -> dict[str, Any]:
    if files is None:
        from app.export import bundle_files

        files = {k: v for k, v in bundle_files(source).items() if isinstance(v, str)}
    checks = {"a": check_scope, "b": check_open_count, "c": check_integrations, "d": check_dangling}
    found = {key: check(source, files) for key, check in checks.items()}
    return {"counts": {key: len(v) for key, v in found.items()}, "total": sum(len(v) for v in found.values()),
            "violations": found}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="넘겨주는 문서가 공유 원본과, 또 서로 맞는지 규칙으로 센다")
    parser.add_argument("source", type=Path, help="source.json (공유 원본)")
    parser.add_argument("--bundle-dir", type=Path, help="이미 풀어 둔 묶음 폴더(없으면 지금 코드로 다시 만든다)")
    parser.add_argument("--out", type=Path, help="결과 JSON 을 쓸 파일")
    args = parser.parse_args(argv)
    source = json.loads(args.source.read_text(encoding="utf-8"))
    result = measure(source, read_bundle(args.bundle_dir) if args.bundle_dir else None)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    labels = {"a": "범위에서 뺀 것이 남음", "b": "미결 수가 적게 적힘", "c": "연계 수가 적게 적힘", "d": "없는 ID 를 가리킴"}
    for key, items in result["violations"].items():
        print(f"({key}) {labels[key]}: {len(items)}건")
        for v in items[:60]:
            print(f"    {v['where']} — {v['what']} | {v['line']}")
    print(f"합계 {result['total']}건")
    return 1 if result["total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
