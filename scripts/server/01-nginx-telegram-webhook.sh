#!/usr/bin/env bash
#
# 01 — nginx 에 /telegram-webhook/ 프록시 규칙을 추가한다.
#
# 왜: 텔레그램 트리거가 통째로 죽어 있다. 백엔드에는 라우트가 있는데 nginx 에 location 이
# 없어서 요청이 백엔드까지 가지 못하고 SPA 셸로 떨어진다. 감사 실측 결과 location 8개
# (`/`, `/assets/`, `/api/`, `= /mockserver`, `/mockserver/`, `/mock/`, `/webhook/`, `/uploads/`)
# 중 telegram-webhook 이 없다.
#
# 어떻게: 이미 동작하는 `/webhook/` 블록을 그대로 복제해 경로만 바꾼다. 손으로 새 블록을
# 쓰면 proxy_set_header 한 줄을 빠뜨리기 쉽다.
#
#   sudo scripts/server/01-nginx-telegram-webhook.sh --dry-run   # 무엇을 넣을지만 출력
#   sudo scripts/server/01-nginx-telegram-webhook.sh

set -euo pipefail

CONF="${NGINX_CONF:-/etc/nginx/sites-enabled/app}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

fail() { printf '\033[31m중단: %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[1m%s\033[0m\n' "$*"; }

[ -f "$CONF" ] || fail "nginx 설정이 없다: $CONF (NGINX_CONF 로 지정할 수 있다)"

if grep -q 'location /telegram-webhook/' "$CONF"; then
  info "이미 있다 — 할 일 없음."
  exit 0
fi

# /webhook/ 블록을 통째로 떠서 경로만 바꾼다.
NEW_BLOCK="$(python3 - "$CONF" <<'PY'
import re, sys

text = open(sys.argv[1], encoding="utf-8").read()
start = text.find("location /webhook/")
if start == -1:
    sys.exit("SOURCE_BLOCK_NOT_FOUND")

# 중괄호 균형을 세어 블록 끝을 찾는다(정규식으로는 중첩을 못 센다).
brace = text.find("{", start)
if brace == -1:
    sys.exit("SOURCE_BLOCK_NOT_FOUND")
depth, i = 0, brace
while i < len(text):
    if text[i] == "{":
        depth += 1
    elif text[i] == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
else:
    sys.exit("SOURCE_BLOCK_NOT_FOUND")

block = text[start:i + 1]
print(block.replace("location /webhook/", "location /telegram-webhook/", 1))
PY
)" || fail "/webhook/ 블록을 찾지 못했다. $CONF 를 직접 확인하라."

info "추가할 블록:"
printf '%s\n' "$NEW_BLOCK" | sed 's/^/    /'

if [ "$DRY_RUN" = 1 ]; then
  info "[dry-run] 여기까지. 실제로 넣으려면 --dry-run 없이 실행하라."
  exit 0
fi

BACKUP="${CONF}.bak-$(date +%Y%m%d-%H%M%S)"
cp -a "$CONF" "$BACKUP"
info "백업: $BACKUP"

# /webhook/ 블록 바로 뒤에 넣는다 — 같은 성격끼리 붙여 두어야 다음 사람이 찾는다.
python3 - "$CONF" "$NEW_BLOCK" <<'PY'
import sys

path, new_block = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
start = text.find("location /webhook/")
brace = text.find("{", start)
depth, i = 0, brace
while i < len(text):
    if text[i] == "{":
        depth += 1
    elif text[i] == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
end = i + 1
open(path, "w", encoding="utf-8").write(text[:end] + "\n\n    " + new_block.strip() + text[end:])
PY

info "문법 검사 (nginx -t)"
if ! nginx -t; then
  cp -a "$BACKUP" "$CONF"
  fail "nginx -t 실패 — 원복했다($BACKUP → $CONF). 위 오류를 보라."
fi

info "reload"
systemctl reload nginx

info "확인: /telegram-webhook/ 이 백엔드까지 가는가 (nginx 405 가 아니라 백엔드 404/422 여야 한다)"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H 'Host: wa-pnu.duckdns.org' \
        https://127.0.0.1/telegram-webhook/999999 --insecure || echo 000)"
echo "    POST /telegram-webhook/999999 → $CODE"
case "$CODE" in
  404|422|401|403) info "백엔드까지 도달했다." ;;
  405) fail "아직 405 다 — nginx 가 처리하고 있다. 블록 위치를 확인하라." ;;
  *)   echo "    ⚠️  예상 밖의 코드다. journalctl -u fastapi -n 30 을 보라." ;;
esac

info "대조군: /webhook/ 이 그대로인지"
curl -sS -o /dev/null -w '    POST /webhook/nonexist → %{http_code}\n' \
     -X POST -H 'Host: wa-pnu.duckdns.org' https://127.0.0.1/webhook/nonexist --insecure || true

info "완료. 되돌리려면: sudo cp -a $BACKUP $CONF && sudo nginx -t && sudo systemctl reload nginx"
