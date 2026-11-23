from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent

KEY_MISSING_MESSAGE = (
    "LINER_API_KEY 가 설정되지 않았습니다. 저장소 루트에 .env 파일을 만들고 "
    "'LINER_API_KEY=<발급받은 키>' 한 줄을 넣고 다시 시도하세요(서버는 켜 둔 채로 됩니다). "
    "키는 https://platform.liner.com 에서 발급합니다."
)


class LinerKeyMissingError(RuntimeError):
    """Raised when LINER_API_KEY is absent from both the process env and .env."""


def read_env(name: str, env_file: Path | None = None) -> str | None:
    """Read a setting at use time: process env first, then the .env file. Empty counts as absent."""
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    path = env_file if env_file is not None else REPO_ROOT / ".env"
    if not path.is_file():
        return None
    return (dotenv_values(path).get(name) or "").strip() or None


def require_api_key(env_file: Path | None = None) -> str:
    key = read_env("LINER_API_KEY", env_file)
    if not key:
        raise LinerKeyMissingError(KEY_MISSING_MESSAGE)
    return key


@dataclass(frozen=True)
class Settings:
    db_path: Path = REPO_ROOT / "data" / "exethon.sqlite3"
    env_file: Path = REPO_ROOT / ".env"
    definitions_root: Path = REPO_ROOT
    static_dir: Path = REPO_ROOT / "app" / "static"
    demo_file: Path = REPO_ROOT / "demo" / "flower-run.json"
    # Only request_memo.md is read from here (the 「예제 메모 채우기」 button). Never the answer sheets.
    examples_root: Path = REPO_ROOT / "examples" / "flower-subscription"
