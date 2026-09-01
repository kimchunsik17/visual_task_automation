#!/usr/bin/env bash
#
# 06 — requirements.lock.txt 를 만든다.
#
# 왜: requirements.txt 는 대부분 버전을 고정하지 않는다. 배포마다 의존성이 조용히 올라가고,
# 어제 되던 것이 오늘 안 되는 원인을 찾을 때 "무엇이 바뀌었는가" 를 답할 수 없다.
#
# **왜 서버에서 만드는가**: pip freeze 결과는 플랫폼에 따라 다르다. Windows 개발 머신에서
# 만들면 리눅스에 없는 패키지가 섞이고 해석 결과도 어긋난다. 운영과 같은 OS·파이썬에서
# 만들어야 lock 이 의미가 있다.
#
#   scripts/server/06-requirements-lock.sh          # 만들고 diff 만 보여준다
#   scripts/server/06-requirements-lock.sh --write  # backend/requirements.lock.txt 에 쓴다

set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/ubuntu/app}"
BACKEND="$APP_ROOT/backend"
VENV_PY="${VENV_PY:-$BACKEND/venv/bin/python}"
LOCK="$BACKEND/requirements.lock.txt"
WRITE=0
[ "${1:-}" = "--write" ] && WRITE=1

fail() { printf '\033[31m중단: %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[1m%s\033[0m\n' "$*"; }

[ -x "$VENV_PY" ] || fail "python 이 없다: $VENV_PY"

info "환경"
"$VENV_PY" -c "import sys, platform; print(f'    {platform.platform()}  python {sys.version.split()[0]}')"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

{
  echo "# 이 파일은 scripts/server/06-requirements-lock.sh 가 **운영 서버에서** 만든다."
  echo "# 개발 머신(Windows)에서 만들면 플랫폼이 달라 쓸 수 없다."
  echo "#"
  echo "# 배포는 이 파일로 설치한다:  pip install -r backend/requirements.lock.txt"
  echo "# 의존성을 바꿀 때는 requirements.txt 를 고치고 이 스크립트를 다시 돌려 갱신한다."
  echo "#"
  "$VENV_PY" -c "import sys, platform; print(f'# 생성: {platform.platform()} / python {sys.version.split()[0]}')"
  echo "# 생성일: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  "$VENV_PY" -m pip freeze --exclude-editable
} > "$TMP"

COUNT="$(grep -cE '^[A-Za-z0-9]' "$TMP" || true)"
info "고정된 패키지 $COUNT 개"

if [ -f "$LOCK" ]; then
  info "기존 lock 과의 차이"
  diff -u "$LOCK" "$TMP" | sed 's/^/    /' | head -40 || true
else
  info "기존 lock 이 없다 (새로 만든다)"
fi

if [ "$WRITE" = 0 ]; then
  echo ""
  info "쓰려면 --write 를 붙여라. 그 뒤 커밋해야 다음 배포가 쓴다."
  exit 0
fi

cp "$TMP" "$LOCK"
info "썼다: $LOCK"
echo ""
echo "다음:"
echo "  1) 깨끗한 환경에서 검증 —"
echo "     python -m venv /tmp/lockcheck && /tmp/lockcheck/bin/pip install -r $LOCK"
echo "     /tmp/lockcheck/bin/python -c 'import gspread, playwright; from hwpx.document import HwpxDocument'"
echo "  2) 커밋: git add backend/requirements.lock.txt && git commit"
