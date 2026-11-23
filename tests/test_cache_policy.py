from __future__ import annotations
"""After a deploy the page must load the new bundle: index.html is revalidated, hashed assets are kept."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_index_is_revalidated_and_hashed_assets_are_cached(tmp_path: Path, no_key_env: Path) -> None:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<script src=/assets/index-abc.js></script>", encoding="utf-8")
    (static / "assets" / "index-abc.js").write_text("1", encoding="utf-8")
    client = TestClient(create_app(Settings(db_path=tmp_path / "d.sqlite3", env_file=no_key_env, static_dir=static)))
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/index.html").headers["cache-control"] == "no-cache"
    assert "immutable" in client.get("/assets/index-abc.js").headers["cache-control"]
    assert "cache-control" not in client.get("/api/health").headers
