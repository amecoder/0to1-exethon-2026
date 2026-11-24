#!/usr/bin/env bash
# Install 0to1 and save the Liner key in .env (macOS, Linux).
# Usage: ./install.sh                     asks for the key (hidden input; empty = demo mode only)
#        LINER_API_KEY=<key> ./install.sh  no prompt
# Uses uv when present (uv.lock, fetches Python 3.12+ itself), otherwise python3 -m venv + pip.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '[0to1] %s\n' "$*"; }
die() { printf '[0to1] 오류: %s\n' "$*" >&2; exit 1; }

python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; }

install_deps() {
  if [ -x .venv/bin/uvicorn ]; then
    say "이미 설치돼 있어 설치는 건너뜁니다 (.venv)"
    return
  fi
  if command -v uv >/dev/null 2>&1; then
    say "uv 로 설치합니다 (uv.lock 과 같은 버전)"
    uv sync --frozen
    return
  fi
  local py="" c
  for c in python3.13 python3.12 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && python_ok "$c"; then py="$c"; break; fi
  done
  [ -n "$py" ] || die "Python 3.12 이상이 필요합니다. Python 을 설치하거나 uv(https://docs.astral.sh/uv/)를 설치한 뒤 다시 실행하세요"
  say "$py 의 venv 와 pip 로 설치합니다 (requirements.txt)"
  "$py" -m venv --clear .venv \
    || die "가상환경을 만들지 못했습니다. Ubuntu·Debian 이면 'sudo apt install python3-venv' 뒤 다시 실행하세요"
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
}

write_env() {
  if [ -f .env ]; then
    say ".env 가 이미 있어 그대로 둡니다 (키를 바꾸려면 .env 를 고치세요)"
    return
  fi
  local key="${LINER_API_KEY:-}"
  if [ -z "$key" ] && [ -t 0 ]; then
    printf '[0to1] Liner API 키를 붙여 넣고 Enter 를 누르세요 (화면에 보이지 않음, 비우면 시연 모드만): '
    IFS= read -rs key || key=""
    printf '\n'
  fi
  key="$(printf '%s' "$key" | tr -d '[:space:]')"
  if [ -z "$key" ]; then
    say "키 없이 설치했습니다. 시연 모드만 쓸 수 있고, 키가 생기면 ./install.sh 를 다시 실행하세요"
    return
  fi
  # 600 permissions: only this account can read the key. .gitignore already keeps .env out of git.
  (
    umask 077
    cat > .env <<EOF
# install.sh 가 만든 파일 — git 에 올리지 마세요 (.gitignore 에 있음)
LINER_API_KEY=${key}
LINER_MODEL=liner-claude-router
LINER_DECISION_MODEL=typesafe/jev-1.13
LINER_RERANK_MODEL=cohere/rerank-5-fast
LINER_STT_MODEL=openai/gpt-transcribe
LINER_IMAGE_MODEL=qwen/qwen-image-2.1-turbo
LINER_FILE_MODEL=google/gemini-3.8-flash
EOF
  )
  say "키와 권장 모델을 .env 에 저장했습니다"
}

install_deps
write_env
say "설치 끝. 실행: ./run.sh"
