#!/usr/bin/env bash
#
# 02 — 자격증명 파일 권한을 좁힌다.
#
# 왜: 감사 실측에서 `backend/.env` 가 `-rwxr-xr-x`(755) 였다. 이 서버의 다른 로컬 사용자가
# 그대로 읽을 수 있다는 뜻이고, 그 안에는 운영 DB 접속 문자열·JWT_SECRET·API 키가 있다.
# JWT_SECRET 은 credential_crypto 의 자격증명 복호화 키 후보이기도 하다.
#
# 이 스크립트는 **권한만** 바꾼다. 전용 서비스 계정으로 옮기는 더 큰 작업은 별건이다 —
# docs/reports/privilege_containment_runbook.md 를 보라. 그쪽을 먼저 적용했다면 소유자가
# 이미 root:workflowapp 일 수 있는데, 이 스크립트는 소유자를 건드리지 않으므로 충돌하지 않는다.
#
#   sudo scripts/server/02-env-permissions.sh --dry-run
#   sudo scripts/server/02-env-permissions.sh

set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/ubuntu/app}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

info() { printf '\033[1m%s\033[0m\n' "$*"; }

TARGETS=(
  "$APP_ROOT/backend/.env"
  "$APP_ROOT/frontend/.env"
)

info "현재 상태"
for f in "${TARGETS[@]}"; do
  [ -e "$f" ] && stat -c '    %a %U:%G %n' "$f" || echo "    (없음) $f"
done

if [ "$DRY_RUN" = 1 ]; then
  info "[dry-run] 위 파일들을 0640 으로 바꾼다. 소유자·그룹은 건드리지 않는다."
  exit 0
fi

for f in "${TARGETS[@]}"; do
  [ -e "$f" ] || continue
  chmod 0640 "$f"
done

info "적용 후"
for f in "${TARGETS[@]}"; do
  [ -e "$f" ] && stat -c '    %a %U:%G %n' "$f"
done

info "확인: 서비스가 아직 .env 를 읽는가"
echo "    (0640 이면 소유자와 그룹만 읽는다. 서비스 실행 계정이 둘 중 하나여야 한다)"
systemctl restart "${FASTAPI_SERVICE:-fastapi}"
sleep 5
CODE="$(curl -sS -o /dev/null -w '%{http_code}' "${SMOKE_BASE_URL:-http://127.0.0.1:8000}/api/ready" || echo 000)"
echo "    /api/ready → $CODE"
if [ "$CODE" != "200" ]; then
  echo ""
  echo "  ⚠️  서비스가 .env 를 못 읽는 것일 수 있다. 실행 계정을 확인하고, 필요하면"
  echo "      chgrp <서비스그룹> $APP_ROOT/backend/.env 로 그룹을 맞춰라."
  echo "      급하면 되돌리기: sudo chmod 0644 $APP_ROOT/backend/.env && sudo systemctl restart fastapi"
  exit 1
fi

info "완료."
