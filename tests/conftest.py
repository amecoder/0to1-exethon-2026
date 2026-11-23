from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def no_key_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Env without LINER_* vars and an .env path that does not exist."""
    monkeypatch.delenv("LINER_API_KEY", raising=False)
    monkeypatch.delenv("LINER_MODEL", raising=False)
    return tmp_path / ".env"


@pytest.fixture
def key_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An .env file containing a fake key and model (never a real key)."""
    monkeypatch.delenv("LINER_API_KEY", raising=False)
    monkeypatch.delenv("LINER_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LINER_API_KEY=test-key-123\nLINER_MODEL=test-model\n", encoding="utf-8")
    return env_file


@pytest.fixture(autouse=True)
def company_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The company workspace is off unless EXETHON_COMPANY=on (the contest build runs 실제·시연 only);
    tests exercise it on. tests/test_company_switch.py checks the default."""
    monkeypatch.setenv("EXETHON_COMPANY", "on")
