#!/usr/bin/env bash
#
# 05 — 로그 회전과 journald 상한을 건다.
#
# 왜: 예전 예외 처리기가 `error_log.txt` 에 무한 append 했고(지금은 logging 으로 옮겼다),
# journald 에도 상한이 없다. 감사 시점 8일치 journal 이 103,462줄이었다. 디스크가 차면
# DB 도 서비스도 함께 멈춘다.
#
#   sudo scripts/server/05-log-rotation.sh --dry-run
#   sudo scripts/server/05-log-rotation.sh

set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/ubuntu/app}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

info() { printf '\033[1m%s\033[0m\n' "$*"; }

LOGROTATE_CONF="/etc/logrotate.d/workflow-app"
read -r -d '' LOGROTATE_BODY <<EOF || true
# scripts/server/05-log-rotation.sh 가 만든 파일이다.
$APP_ROOT/backend/*.log $APP_ROOT/backend/error_log.txt {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF

JOURNALD_DROPIN="/etc/systemd/journald.conf.d/99-workflow-app.conf"
read -r -d '' JOURNALD_BODY <<'EOF' || true
# scripts/server/05-log-rotation.sh 가 만든 파일이다.
[Journal]
SystemMaxUse=500M
MaxRetentionSec=30day
EOF

info "logrotate ($LOGROTATE_CONF)"
printf '%s\n' "$LOGROTATE_BODY" | sed 's/^/    /'
info "journald ($JOURNALD_DROPIN)"
printf '%s\n' "$JOURNALD_BODY" | sed 's/^/    /'

info "현재 journal 사용량"
journalctl --disk-usage 2>/dev/null | sed 's/^/    /' || echo "    (확인 실패)"

if [ "$DRY_RUN" = 1 ]; then
  info "[dry-run] 여기까지."
  exit 0
fi

printf '%s\n' "$LOGROTATE_BODY" > "$LOGROTATE_CONF"
chmod 0644 "$LOGROTATE_CONF"

info "logrotate 문법 검사 (-d 는 실제로 돌리지 않는다)"
logrotate -d "$LOGROTATE_CONF" 2>&1 | tail -20 | sed 's/^/    /'

mkdir -p "$(dirname "$JOURNALD_DROPIN")"
printf '%s\n' "$JOURNALD_BODY" > "$JOURNALD_DROPIN"
chmod 0644 "$JOURNALD_DROPIN"
systemctl restart systemd-journald

info "적용 후 journal 사용량"
journalctl --disk-usage 2>/dev/null | sed 's/^/    /' || true

info "완료. 되돌리려면:"
echo "    sudo rm $LOGROTATE_CONF $JOURNALD_DROPIN && sudo systemctl restart systemd-journald"
