from __future__ import annotations

import copy
import json
import re
import sqlite3
import uuid
from app.naming import NAME_MAX
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Shared source bundles (PRD 2-6). requirements/screens/tests keep the fixture shape.
BUNDLES = (
    "sources", "evidence", "requirements", "screens", "tests", "questions",
    "decisions", "open_items", "confirmations", "versions", "events",
)
FIXTURE_BUNDLE_FIELDS = {
    "requirements": ("id", "title", "statement", "depends_on", "screens", "tests"),
    "screens": ("id", "title"),
    "tests": ("id", "title"),
}
MODES = ("demo", "real")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('demo', 'real')),
    created_at TEXT NOT NULL,
    source_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    run_lock TEXT
)
"""
# A company workspace (가입 회사): its projects, its shared material (systems list, notes). No login (PoC).
COMPANY_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    systems TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
)
"""
DEFAULT_COMPANY = "default"
DEFAULT_COMPANY_NAME = "기본 회사"
# Columns added after the first release; older data/*.sqlite3 files get them on startup.
MIGRATIONS = (
    ("revision", "ALTER TABLE projects ADD COLUMN revision INTEGER NOT NULL DEFAULT 0"),
    ("run_lock", "ALTER TABLE projects ADD COLUMN run_lock TEXT"),
    ("company_id", f"ALTER TABLE projects ADD COLUMN company_id TEXT NOT NULL DEFAULT '{DEFAULT_COMPANY}'"),
)
# Decisions that carry to the company's next projects: answers the client confirmed that still stand.
# build_or_buy / scope are calls about that one project; company decisions are already company material.
LOCAL_DECISION_KINDS = ("build_or_buy", "scope", "company", "placement")  # this project only
FEATURE_STATUSES = ("확정", "가정")  # requirements handed over to be built (app/company.py)
STALE_MESSAGE = "다른 요청이 먼저 반영됐어요, 화면을 새로 고쳐 주세요"


def display_name(row_name: str, source: Mapping[str, Any]) -> str:
    """D1: the name in the shared source (FDE lead's proposal or the client's own) wins over the row's placeholder."""
    name = (source.get("meta") or {}).get("name")
    value = name.get("value") if isinstance(name, Mapping) else name
    return str(value or row_name)


def _topic_key(topic: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", topic.lower())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope(mode: str, company_id: str | None) -> tuple[str, tuple[str, ...]]:
    if company_id is None:
        return "mode = ?", (mode,)
    return "mode = ? AND company_id = ?", (mode, company_id)


class StaleRevisionError(RuntimeError):
    """The project changed since it was read; this save would overwrite another request's work."""


def empty_source(first_stage: str | None = None) -> dict[str, Any]:
    """A new project's shared source. `first_stage`: the input stage of its flow (default flow: the workspace's S1)."""
    meta: dict[str, Any] = {"pipeline": {"stage": first_stage}} if first_stage else {}
    return {"meta": meta, **{bundle: [] for bundle in BUNDLES}}


def load_fixture_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_from_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    """Build a shared source from a fixture. Non-bundle keys (version, purpose, ...) go to meta."""
    data = copy.deepcopy(fixture)
    meta = {k: v for k, v in data.items() if k not in FIXTURE_BUNDLE_FIELDS}
    bundles = {k: data.get(k, []) for k in FIXTURE_BUNDLE_FIELDS}
    return {**empty_source(), "meta": meta, **bundles}


def export_fixture(source: dict[str, Any]) -> dict[str, Any]:
    """Export meta + requirements/screens/tests with only the fixture fields (added fields dropped)."""
    exported = copy.deepcopy(source.get("meta", {}))
    for bundle, fields in FIXTURE_BUNDLE_FIELDS.items():
        exported[bundle] = [{f: copy.deepcopy(item[f]) for f in fields} for item in source.get(bundle, [])]
    return exported


class ProjectStore:
    """SQLite document store: one row per project, the shared source kept as a JSON document."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)
            conn.execute(COMPANY_SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)")}
            for column, statement in MIGRATIONS:
                if column not in columns:
                    conn.execute(statement)
            conn.execute("INSERT OR IGNORE INTO companies (id, name, created_at) VALUES (?, ?, ?)",
                         (DEFAULT_COMPANY, DEFAULT_COMPANY_NAME, _now()))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open, commit on success (rollback on error), and always close the connection."""
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create(self, name: str, mode: str, source: dict[str, Any] | None = None,
               company_id: str = DEFAULT_COMPANY) -> dict[str, Any]:
        if mode not in MODES:
            raise ValueError(f"mode 는 {MODES} 중 하나여야 합니다: {mode!r}")
        if self.get_company(company_id) is None:
            raise KeyError(f"회사가 없습니다: {company_id}")
        project = {
            "id": uuid.uuid4().hex,
            "name": name,
            "mode": mode,
            "created_at": _now(),
            "source": source if source is not None else empty_source(),
            "company_id": company_id,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, mode, created_at, source_json, company_id) VALUES (?, ?, ?, ?, ?, ?)",
                (project["id"], name, mode, project["created_at"],
                 json.dumps(project["source"], ensure_ascii=False), company_id),
            )
        return project

    def get(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": display_name(row["name"], json.loads(row["source_json"])),
            "mode": row["mode"],
            "created_at": row["created_at"],
            "source": json.loads(row["source_json"]),
            "revision": row["revision"],
            "company_id": row["company_id"],
        }

    def ids(self) -> list[str]:
        with self._connect() as conn:
            return [row["id"] for row in conn.execute("SELECT id FROM projects ORDER BY created_at")]

    def count(self, mode: str = "real", company_id: str | None = None) -> int:
        where, args = _scope(mode, company_id)
        with self._connect() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM projects WHERE {where}", args).fetchone()[0])

    def summaries(self, mode: str = "real", limit: int = 20, company_id: str | None = None) -> list[dict[str, Any]]:
        """Newest first: id, name, mode, created_at and the pipeline stage/status (None before S1 input).
        `company_id`: only that company's projects (None = every company)."""
        where, args = _scope(mode, company_id)
        query = ("SELECT id, COALESCE(json_extract(source_json, '$.meta.name.value'), name) AS name, mode, created_at, "
                 "json_extract(source_json, '$.meta.pipeline.stage') AS stage, "
                 "json_extract(source_json, '$.meta.pipeline.status') AS status FROM projects "
                 f"WHERE {where} ORDER BY created_at DESC LIMIT ?")
        with self._connect() as conn:
            rows = conn.execute(query, (*args, limit)).fetchall()
        return [{"id": r["id"], "name": r["name"], "mode": r["mode"], "created_at": r["created_at"],
                 "stage": r["stage"], "status": r["status"], "completed": r["status"] == "completed"} for r in rows]

    def save_source(self, project_id: str, source: dict[str, Any], revision: int) -> int:
        """Save only if nobody saved since `revision` was read. Returns the new revision."""
        with self._connect() as conn:
            updated = conn.execute(
                "UPDATE projects SET source_json = ?, revision = revision + 1 WHERE id = ? AND revision = ?",
                (json.dumps(source, ensure_ascii=False), project_id, revision),
            ).rowcount
            exists = updated == 1 or conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not exists:
            raise KeyError(f"프로젝트가 없습니다: {project_id}")
        if updated != 1:
            raise StaleRevisionError(STALE_MESSAGE)
        return revision + 1

    def saver(self, project_id: str, revision: int) -> Callable[[dict[str, Any]], None]:
        """on_change callback for one Workspace: each save must follow the previous one of the same writer."""
        current = [revision]

        def save(source: dict[str, Any]) -> None:
            current[0] = self.save_source(project_id, source, current[0])

        return save

    # --- companies ------------------------------------------------------------------------------
    def create_company(self, name: str) -> dict[str, Any]:
        company = {"id": uuid.uuid4().hex, "name": name, "created_at": _now(), "systems": "", "notes": ""}
        with self._connect() as conn:
            conn.execute("INSERT INTO companies (id, name, created_at) VALUES (?, ?, ?)",
                         (company["id"], name, company["created_at"]))
        return company

    def get_company(self, company_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        return dict(row) if row is not None else None

    def companies(self) -> list[dict[str, Any]]:
        """Oldest first (the default company leads), each with how many real projects it holds."""
        query = ("SELECT c.id, c.name, c.created_at, (SELECT COUNT(*) FROM projects p WHERE p.company_id = c.id "
                 "AND p.mode = 'real') AS projects FROM companies c ORDER BY c.created_at, c.rowid")
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query)]

    def update_company(self, company_id: str, systems: str, notes: str) -> dict[str, Any]:
        with self._connect() as conn:
            updated = conn.execute("UPDATE companies SET systems = ?, notes = ? WHERE id = ?",
                                   (systems, notes, company_id)).rowcount
        if updated != 1:
            raise KeyError(f"회사가 없습니다: {company_id}")
        return self.get_company(company_id) or {}

    def past_decisions(self, company_id: str, exclude_project: str | None = None) -> list[dict[str, Any]]:
        """Answers the client confirmed in the company's other projects whose latest CP2 record is approved (an
        answer only counts once the requirements were agreed, D3 11-20), oldest project first. The same question
        (compared on letters and digits only) keeps the newest project's answer."""
        with self._connect() as conn:
            rows = conn.execute("SELECT id, name, source_json FROM projects WHERE company_id = ? AND mode = 'real' "
                                "ORDER BY created_at", (company_id,)).fetchall()
        past: list[dict[str, Any]] = []
        for row in rows:
            source = json.loads(row["source_json"])
            cp2 = [c for c in source.get("confirmations", []) if c.get("cp") == "CP2"]
            if row["id"] == exclude_project or not cp2 or cp2[-1].get("approved") is not True:
                continue
            for d in source.get("decisions", []):
                if (d.get("status") == "확정" and d.get("answered_by") == "client" and not d.get("superseded_by")
                        and d.get("kind") not in LOCAL_DECISION_KINDS and str(d.get("chosen", "")).strip()):
                    past.append({"project": display_name(row["name"], source), "project_id": row["id"], "decision_id": d.get("id", ""),
                                 "topic": str(d.get("topic", "")), "chosen": str(d["chosen"])})
        newest = {_topic_key(d["topic"]): n for n, d in enumerate(past) if _topic_key(d["topic"])}
        return [d for n, d in enumerate(past) if not _topic_key(d["topic"]) or newest[_topic_key(d["topic"])] == n]

    def services(self, company_id: str, exclude_project: str | None = None) -> list[dict[str, Any]]:
        """The company's projects confirmed at CP4 (latest CP4 record approved), oldest first, with their
        features: requirements settled (확정) or filled with a default (가정), and the screens that show them."""
        with self._connect() as conn:
            rows = conn.execute("SELECT id, name, source_json FROM projects WHERE company_id = ? AND mode = 'real' "
                                "ORDER BY created_at", (company_id,)).fetchall()
        out = []
        for row in rows:
            source = json.loads(row["source_json"])
            cp4 = [c for c in source.get("confirmations", []) if c.get("cp") == "CP4"]
            if row["id"] == exclude_project or not cp4 or cp4[-1].get("approved") is not True:
                continue
            features = [{"id": r.get("id", ""), "title": str(r.get("title", "")), "statement": str(r.get("statement", "")),
                         "screens": list(r.get("screens") or [])}
                        for r in source.get("requirements", []) if r.get("status") in FEATURE_STATUSES]
            if features:
                base, n = display_name(row["name"], source), 2
                name, taken = base, {o["name"] for o in out}
                while name in taken:  # the same name twice in one company: 「이름 (2)」, kept within the name limit
                    suffix = f" ({n})"
                    name = f"{base[:NAME_MAX - len(suffix)].rstrip()}{suffix}"
                    n += 1
                out.append({"project_id": row["id"], "name": name, "features": features})
        return out

    # --- run lock: one writer per project until its background work ends ---------------------------
    def acquire_run(self, project_id: str) -> str | None:
        """Take the project's run lock atomically. Returns the holder token, or None if someone holds it."""
        token = uuid.uuid4().hex
        with self._connect() as conn:
            taken = conn.execute("UPDATE projects SET run_lock = ? WHERE id = ? AND run_lock IS NULL",
                                 (token, project_id)).rowcount
        return token if taken == 1 else None

    def release_run(self, project_id: str, token: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE projects SET run_lock = NULL WHERE id = ? AND run_lock = ?", (project_id, token))

    def release_all_runs(self) -> None:
        """Startup: no background work survives a restart, so every lock is stale."""
        with self._connect() as conn:
            conn.execute("UPDATE projects SET run_lock = NULL WHERE run_lock IS NOT NULL")
