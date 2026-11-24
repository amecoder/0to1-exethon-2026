#!/usr/bin/env bash
# Start 0to1 (macOS, Linux). The first run installs it and asks for the Liner key (./install.sh).
# Usage: ./run.sh                    http://127.0.0.1:8000
#        PORT=8001 ./run.sh          another port
#        HOST=0.0.0.0 ./run.sh       open to other machines on the network
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '[0to1] %s\n' "$*"; }

[ -x .venv/bin/uvicorn ] || ./install.sh

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
if .venv/bin/python -c 'import sys; from app.config import read_env; sys.exit(0 if read_env("LINER_API_KEY") else 1)'; then
  say "Liner 키 있음 — 실제 모드와 시연 모드를 쓸 수 있습니다"
else
  say "Liner 키 없음 — 시연 모드만 쓸 수 있습니다 (키 넣기: ./install.sh)"
fi
say "브라우저에서 http://127.0.0.1:${PORT} 을 여세요 (끄기: Ctrl+C)"
exec .venv/bin/uvicorn app.main:create_app --factory --host "$HOST" --port "$PORT"
