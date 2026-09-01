#!/usr/bin/env bash
#
# 03 — fastapi 유닛에 재기동 상한과 실패 알림을 건다.
#
# 왜: 감사 실측에서 4.2일간 재기동 6,645회가 관측됐다(`journalctl -u fastapi | grep -c
# 'Failed with result'`). 상한이 없으면 크래시 루프가 조용히 계속 돌고, 그동안 아무도
# 모른다. 임포트 시점 마이그레이션까지 붙어 있으면 매 사이클이 운영 스키마를 건드린다.
#
# ⚠️ **바인드 변경(--host 127.0.0.1)은 이 스크립트에 넣지 않았다.** 계획서가 "두 바인드
#    변경을 한 번에 하지 않는다" 고 못 박았고, 실패하면 사이트 전체가 502 다. 04 에서
#    따로, 사이트 왕복을 확인하면서 한다.
#
#   sudo scripts/server/03-systemd-hardening.sh --dry-run
#   sudo scripts/server/03-systemd-hardening.sh

set -euo pipefail

SERVICE="${FASTAPI_SERVICE:-fastapi}"
UNIT="$(systemctl show -p FragmentPath --value "$SERVICE" 2>/dev/null || true)"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

fail() { printf '\033[31m중단: %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[1m%s\033[0m\n' "$*"; }

[ -n "$UNIT" ] && [ -f "$UNIT" ] || fail "유닛 파일을 찾지 못했다: $SERVICE"
info "유닛: $UNIT"

DROPIN_DIR="/etc/systemd/system/${SERVICE}.service.d"
DROPIN="$DROPIN_DIR/10-restart-limits.conf"

# 드롭인으로 넣는다 — 원본 유닛을 건드리지 않아 되돌리기가 파일 하나 삭제로 끝난다.
read -r -d '' CONTENT <<'EOF' || true
# scripts/server/03-systemd-hardening.sh 가 만든 파일이다.
# 되돌리려면 이 파일을 지우고 `systemctl daemon-reload` 하면 된다.
[Unit]
# 5분 안에 5번 넘게 죽으면 재기동을 멈춘다. 멈추는 것이 조용히 도는 것보다 낫다 —
# 크래시 루프는 로그만 채우고 서비스는 어차피 안 된다.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
# venv/bin 만 있던 PATH 에 시스템 경로를 덧붙인다. 일부 노드가 외부 실행 파일을 부른다.
Environment="PATH=/usr/local/bin:/usr/bin:/bin:%h/app/backend/venv/bin"
RestartSec=3
EOF

info "넣을 드롭인 ($DROPIN):"
printf '%s\n' "$CONTENT" | sed 's/^/    /'

if [ "$DRY_RUN" = 1 ]; then
  info "[dry-run] 여기까지."
  echo ""
  info "참고 — 현재 값"
  systemctl show "$SERVICE" -p StartLimitIntervalSec -p StartLimitBurst -p Restart -p RestartSec -p Environment | sed 's/^/    /'
  exit 0
fi

mkdir -p "$DROPIN_DIR"
printf '%s\n' "$CONTENT" > "$DROPIN"
systemctl daemon-reload

info "적용 후 값"
systemctl show "$SERVICE" -p StartLimitIntervalSec -p StartLimitBurst -p Restart -p RestartSec | sed 's/^/    /'

info "재기동해서 정상인지 확인"
systemctl restart "$SERVICE"
for _ in $(seq 1 30); do
  curl -fsS -o /dev/null "${SMOKE_BASE_URL:-http://127.0.0.1:8000}/api/health" 2>/dev/null && break
  sleep 1
done
CODE="$(curl -sS -o /dev/null -w '%{http_code}' "${SMOKE_BASE_URL:-http://127.0.0.1:8000}/api/ready" || echo 000)"
echo "    /api/ready → $CODE"
[ "$CODE" = "200" ] || fail "재기동 후 ready 가 $CODE 다. journalctl -u $SERVICE -n 50 을 보라."

info "완료. 되돌리려면: sudo rm $DROPIN && sudo systemctl daemon-reload && sudo systemctl restart $SERVICE"
echo ""
echo "다음: 강제 실패 리허설을 한 번 해 두면 상한이 실제로 도는지 알 수 있다."
echo "  (일부러 죽는 상태를 만들고 5회 만에 'start request repeated too quickly' 가 나오는지 확인)"
