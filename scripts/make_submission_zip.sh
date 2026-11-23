#!/usr/bin/env bash
# Build the contest submission zip from what git tracks at HEAD only (.env, .claude/, data/ are never inside),
# then check the zip with gitleaks. Usage: scripts/make_submission_zip.sh  → dist/0to1-<commit>.zip
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "커밋하지 않은 변경이 있어요. 커밋한 뒤 다시 실행하세요 (zip 은 HEAD 기준)." >&2
  exit 1
fi
rev="$(git rev-parse --short HEAD)"
out="dist/0to1-${rev}.zip"
mkdir -p dist
git archive --format=zip --prefix=0to1/ -o "$out" HEAD
# Python's zipfile, not macOS unzip: unzip garbles the Korean file names under docs/.
names() { python3 -c 'import sys, zipfile; print("\n".join(zipfile.ZipFile(sys.argv[1]).namelist()))' "$1"; }
if names "$out" | grep -Eq '(^|/)\.env$|(^|/)\.claude/'; then
  echo "zip 에 .env 또는 .claude/ 가 들어 있어요. 제출하지 마세요: $out" >&2
  exit 1
fi
check="$(mktemp -d)"
trap 'rm -rf "$check"' EXIT
python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$out" "$check"
cp .gitleaksignore "$check/0to1/" 2>/dev/null || true
if command -v gitleaks >/dev/null; then
  (cd "$check/0to1" && gitleaks dir --no-banner --redact . >/dev/null) || { echo "gitleaks 가 비밀값을 찾았어요: $out" >&2; exit 1; }
  echo "gitleaks: 비밀값 없음"
else
  echo "gitleaks 가 없어 비밀값 검사는 건너뛰었어요 (brew install gitleaks)" >&2
fi
echo "만들었어요: $out ($(du -h "$out" | cut -f1), 파일 $(names "$out" | grep -vc '/$')개)"
