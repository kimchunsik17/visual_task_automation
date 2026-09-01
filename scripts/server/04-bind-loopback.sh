#!/usr/bin/env bash
#
# 04 — 백엔드를 루프백에만 바인드한다.
#
# 왜: 실측 `LISTEN 0.0.0.0:8000` — nginx 를 우회해 8000 으로 직접 붙을 수 있다는 뜻이다.
# nginx 가 하는 것(TLS, 헤더, 로깅, 경로 제한)이 전부 건너뛰어진다.
#
# ⚠️ **이 스크립트는 혼자 실행한다.** 계획서가 "두 바인드 변경을 한 번에 하지 않는다" 고
#    못 박았다. 실패하면 nginx → 백엔드 연결이 끊겨 **사이트 전체가 502** 다. mock_server
#    바인드는 코드에서 이미 루프백으로 바꿨고(mock_server/server.js) 배포로 나가므로
#    여기서 함께 만지지 않는다.
#
#   sudo scripts/server/04-bind-loopback.sh --dry-run
#   sudo scripts/server/04-bind-loopback.sh

set -euo pipefail

SERVICE="${FASTAPI_SERVICE:-fastapi}"
UNIT="$(systemctl show -p FragmentPath --value "$SERVICE" 2>/dev/null || true)"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

fail() { printf '\033[31m중단: %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[1m%s\033[0m\n' "$*"; }

[ -n "$UNIT" ] && [ -f "$UNIT" ] || fail "유닛 파일을 찾지 못했다: $SERVICE"

info "현재 ExecStart"
systemctl show "$SERVICE" -p ExecStart --value | sed 's/^/    /'
info "현재 LISTEN"
ss -ltnp 2>/dev/null | grep -E ':8000' | sed 's/^/    /' || echo "    (없음)"

CURRENT_EXEC="$(grep -E '^ExecStart=' "$UNIT" | head -1)"
[ -n "$CURRENT_EXEC" ] || fail "$UNIT 에 ExecStart 가 없다"

if printf '%s' "$CURRENT_EXEC" | grep -q -- '--host'; then
  if printf '%s' "$CURRENT_EXEC" | grep -q -- '--host 127.0.0.1'; then
    info "이미 127.0.0.1 이다 — 할 일 없음."
    exit 0
  fi
  NEW_EXEC="$(printf '%s' "$CURRENT_EXEC" | sed -E 's/--host [^ ]+/--host 127.0.0.1/')"
else
  NEW_EXEC="$(printf '%s' "$CURRENT_EXEC" | sed -E 's/(uvicorn [^ ]+)/\1 --host 127.0.0.1/')"
fi

echo ""
info "바꿀 내용"
echo "    - $CURRENT_EXEC"
echo "    + $NEW_EXEC"

if [ "$DRY_RUN" = 1 ]; then
  info "[dry-run] 여기까지."
  exit 0
fi

BACKUP="${UNIT}.bak-$(date +%Y%m%d-%H%M%S)"
cp -a "$UNIT" "$BACKUP"
info "백업: $BACKUP"

python3 - "$UNIT" "$CURRENT_EXEC" "$NEW_EXEC" <<'PY'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
if old not in text:
    sys.exit("ExecStart 를 찾지 못했다")
open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
PY

systemctl daemon-reload
systemctl restart "$SERVICE"

for _ in $(seq 1 30); do
  curl -fsS -o /dev/null "${SMOKE_BASE_URL:-http://127.0.0.1:8000}/api/health" 2>/dev/null && break
  sleep 1
done

info "확인 ①: 루프백으로만 듣는가"
ss -ltn 2>/dev/null | grep -E ':8000' | sed 's/^/    /' || echo "    (없음)"
if ss -ltn 2>/dev/null | grep -qE '0\.0\.0\.0:8000|\[::\]:8000'; then
  cp -a "$BACKUP" "$UNIT"; systemctl daemon-reload; systemctl restart "$SERVICE"
  fail "아직 0.0.0.0 이다 — 원복했다."
fi

info "확인 ②: nginx 를 통한 사이트가 살아 있는가 (여기가 502 면 즉시 원복해야 한다)"
SITE="$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: wa-pnu.duckdns.org' https://127.0.0.1/api/health --insecure || echo 000)"
echo "    https://.../api/health → $SITE"
if [ "$SITE" != "200" ]; then
  cp -a "$BACKUP" "$UNIT"; systemctl daemon-reload; systemctl restart "$SERVICE"
  fail "사이트가 $SITE 다 — 원복했다($BACKUP). nginx upstream 이 127.0.0.1:8000 인지 확인하라."
fi

info "완료. 되돌리려면: sudo cp -a $BACKUP $UNIT && sudo systemctl daemon-reload && sudo systemctl restart $SERVICE"
echo ""
echo "권장: ufw 로 22/80/443 만 열어 둔다 (8000 이 방화벽에서도 막히는지 확인)"
echo "  sudo ufw allow 22 && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable"
