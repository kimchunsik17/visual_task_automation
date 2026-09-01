#!/usr/bin/env bash
#
# rollback.sh — deploy.sh 가 남긴 태그로 되돌린다.
#
#   scripts/rollback.sh                 # 가장 최근 deploy-* 태그로
#   scripts/rollback.sh deploy-2026...  # 특정 태그로
#   scripts/rollback.sh --list          # 되돌릴 수 있는 지점 보기
#
# ⚠️ 마이그레이션은 **자동으로 내리지 않는다.**
#    코드만 되돌리면 스키마가 앞서 있는 상태가 되는데, 그건 대개 안전하다(새 컬럼을 안 쓸 뿐).
#    반대로 downgrade 는 데이터를 지울 수 있어 되돌릴 수 없다. 스키마까지 내려야 한다면
#    릴리스 노트에 적힌 대상 리비전을 확인하고 **손으로** 실행하라:
#        cd backend && venv/bin/python -m alembic downgrade <revision>

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
VENV_PY="${VENV_PY:-$BACKEND/venv/bin/python}"
SERVICE="${FASTAPI_SERVICE:-fastapi}"
BASE_URL="${SMOKE_BASE_URL:-http://127.0.0.1:8000}"

fail() { printf '\033[31m롤백 중단: %s\033[0m\n' "$*" >&2; exit 1; }

if [ "${1:-}" = "--list" ]; then
  git -C "$REPO_ROOT" tag --list 'deploy-*' --sort=-creatordate | head -20
  exit 0
fi

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  TARGET="$(git -C "$REPO_ROOT" tag --list 'deploy-*' --sort=-creatordate | head -1)"
  [ -n "$TARGET" ] || fail "deploy-* 태그가 없다. 되돌릴 지점을 직접 지정하라."
fi
git -C "$REPO_ROOT" rev-parse --verify "$TARGET^{commit}" >/dev/null 2>&1 || fail "그런 지점이 없다: $TARGET"

CURRENT="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
echo "현재 $CURRENT → $TARGET 으로 되돌린다."
echo "현재 스키마 리비전:"
(cd "$BACKEND" && "$VENV_PY" -m alembic current 2>/dev/null || echo "  (확인 실패)")
printf '계속하려면 yes 를 입력: '
read -r answer
[ "$answer" = "yes" ] || fail "취소됐다"

git -C "$REPO_ROOT" checkout --detach "$TARGET"

if [ -d "$REPO_ROOT/frontend" ]; then
  (cd "$REPO_ROOT/frontend" && npm ci && npm run build)
fi

sudo systemctl restart "$SERVICE"

for _ in $(seq 1 30); do
  curl -fsS -o /dev/null "$BASE_URL/api/health" 2>/dev/null && break
  sleep 1
done
curl -fsS -o /dev/null "$BASE_URL/api/health" || fail "되돌린 뒤에도 /api/health 가 응답하지 않는다 (journalctl -u $SERVICE -n 50)"

READY_CODE="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/api/ready")"
if [ "$READY_CODE" != "200" ]; then
  echo "⚠️  /api/ready 가 $READY_CODE 다. 스키마가 코드보다 앞서 있어 기동을 거부했을 수 있다"
  echo "    (AUTO_MIGRATE_ON_BOOT=0 인 경우). 릴리스 노트의 대상 리비전으로 downgrade 가 필요한지 판단하라."
  exit 1
fi

echo "롤백 완료: $TARGET (이전 HEAD 는 $CURRENT)"
