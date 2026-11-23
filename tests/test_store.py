from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.store import (
    BUNDLES,
    ProjectStore,
    export_fixture,
    load_fixture_file,
    source_from_fixture,
)


@pytest.fixture
def fixture_path(repo_root: Path) -> Path:
    return repo_root / "examples" / "flower-subscription" / "requirements_fixture.json"


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "test.sqlite3")


def test_fixture_round_trip_through_sqlite(store: ProjectStore, fixture_path: Path) -> None:
    original = json.loads(fixture_path.read_text(encoding="utf-8"))
    project = store.create("꽃님", "demo", source_from_fixture(load_fixture_file(fixture_path)))
    loaded = store.get(project["id"])
    assert loaded is not None
    assert export_fixture(loaded["source"]) == original


def test_export_strips_added_fields(fixture_path: Path) -> None:
    original = load_fixture_file(fixture_path)
    source = source_from_fixture(original)
    extended = copy.deepcopy(source)
    extended["requirements"][0] |= {"status": "가정", "source_refs": ["SRC-01"], "owner_agent": "pm"}
    extended["screens"][0] |= {"elements": ["버튼"], "requirement_refs": ["REQ-01"]}
    extended["tests"][0] |= {"steps": ["1"], "expected": "ok"}
    extended["evidence"].append({"id": "EV-01"})
    assert export_fixture(extended) == original


def test_source_from_fixture_does_not_mutate_input(fixture_path: Path) -> None:
    original = load_fixture_file(fixture_path)
    snapshot = copy.deepcopy(original)
    source = source_from_fixture(original)
    source["requirements"][0]["title"] = "바뀜"
    assert original == snapshot


def test_new_project_has_all_bundles_empty(store: ProjectStore) -> None:
    project = store.create("새 프로젝트", "real")
    assert project["mode"] == "real"
    for bundle in BUNDLES:
        assert project["source"][bundle] == []


def test_get_unknown_project_returns_none(store: ProjectStore) -> None:
    assert store.get("missing") is None


def test_invalid_mode_rejected(store: ProjectStore) -> None:
    with pytest.raises(ValueError, match="mode"):
        store.create("x", "turbo")


def test_store_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite3"
    project = ProjectStore(db).create("지속", "demo")
    assert ProjectStore(db).get(project["id"])["name"] == "지속"
