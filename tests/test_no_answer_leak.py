from __future__ import annotations

from pathlib import Path

# Files that hold the human owner's answers and the scoring key. The app must never read them,
# otherwise defect-detection scores (M1) become meaningless (PRD 1-7).
FORBIDDEN = ("owner_answers", "seeded_defects", "eval/golden", "examples/")
SCANNED_DIRS = ("app", "agents", "teams", "frontend/src", "scripts", "demo")
SCANNED_FILES = ("frontend/index.html", "frontend/vite.config.ts")
SCANNED_SUFFIXES = {".py", ".json", ".ts", ".tsx", ".js", ".html", ".css"}
# FR-24 measurement scripts are the only files allowed to open the scoring key (never the owner's answers).
SCORING_SCRIPTS = {
    "scripts/measure_m1.py": {"seeded_defects", "eval/golden", "examples/"},
    "scripts/measure_m2.py": {"eval/golden", "examples/"},
    "scripts/measure_decisions.py": {"eval/golden", "examples/"},
    "scripts/measure_intent.py": {"eval/golden"},
    "scripts/measure_policy.py": {"eval/golden"},
    "scripts/measure_hygiene.py": {"eval/golden", "examples/"},
    # 「예제 메모 채우기」: serves request_memo.md only (checked below) — never the answers or the key.
    "app/routes_catalog.py": {"examples/"},
}


def scanned_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in SCANNED_DIRS:
        base = root / rel
        assert base.is_dir(), f"scan target missing: {rel}"
        files.extend(p for p in base.rglob("*") if p.is_file() and p.suffix in SCANNED_SUFFIXES)
    files.extend(root / rel for rel in SCANNED_FILES)
    return files


def test_scan_covers_app_and_definitions(repo_root: Path) -> None:
    names = {p.name for p in scanned_files(repo_root)}
    assert {"main.py", "liner.py", "researcher.json", "default.json", "App.tsx", "index.html",
            "record_demo.py", "flower-run.json", "decisions.py", "flow_chart.py", "credits.py", "audio.py",
            "liner_sse.py", "measure_decisions.py"} <= names


def test_no_source_references_answer_files(repo_root: Path) -> None:
    offenders = [
        f"{path.relative_to(repo_root)}: {word}"
        for path in scanned_files(repo_root)
        for word in FORBIDDEN
        if word not in SCORING_SCRIPTS.get(str(path.relative_to(repo_root)), set())
        and word in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []


def test_scoring_scripts_exist_and_m2_never_opens_the_defect_key(repo_root: Path) -> None:
    for rel in SCORING_SCRIPTS:
        assert (repo_root / rel).is_file(), rel
    assert "seeded_defects" not in (repo_root / "scripts" / "measure_m2.py").read_text(encoding="utf-8")
    assert "seeded_defects" not in (repo_root / "scripts" / "measure_decisions.py").read_text(encoding="utf-8")


def test_app_and_frontend_never_import_the_scoring_scripts(repo_root: Path) -> None:
    offenders = [str(p.relative_to(repo_root)) for p in scanned_files(repo_root)
                 if str(p.relative_to(repo_root)) not in SCORING_SCRIPTS
                 and any(name in p.read_text(encoding="utf-8", errors="ignore")
                         for name in ("measure_m", "measure_decisions", "measure_intent", "measure_policy", "measure_hygiene", "complaint_cases",
                                      "client_intent_cases"))]
    assert offenders == []


def test_example_endpoint_reads_only_the_request_memo(repo_root: Path) -> None:
    text = (repo_root / "app" / "routes_catalog.py").read_text(encoding="utf-8")
    assert 'EXAMPLE_MEMO = "request_memo.md"' in text
    for other in ("owner_answers", "requirements_fixture", "seeded_defects", "glob(", "iterdir(", "rglob("):
        assert other not in text, other
