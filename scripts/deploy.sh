#!/usr/bin/env bash
#
# deploy.sh — 서버 배포 절차를 코드로 옮긴 것.
#
# 왜 필요한가: 이 저장소의 배포 사고는 "반영이 안 됐는데 화면이 200 으로 떠서 몰랐다" 는
# 모양이었다. 절차가 사람 기억에만 있으면 단계 하나를 건너뛰어도 아무도 모르고, 실패가
# `GET → 200 text/html` 로 위장된다. 각 단계를 실패 시 즉시 중단시키고, 마지막에 프로브로
# 확인한다.
#
# 사용법:
#   scripts/deploy.sh                # 배포
#   scripts/deploy.sh --dry-run      # 무엇을 할지만 출력(서버 상태를 바꾸지 않는다)
#   scripts/deploy.sh --skip-frontend
#
# 되돌리기: scripts/rollback.sh (배포 직전 태그로 돌아간다)

set -euo pipefail

DRY_RUN=0
SKIP_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --skip-frontend) SKIP_FRONTEND=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "알 수 없는 인자: $arg" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
VENV_PY="${VENV_PY:-$BACKEND/venv/bin/python}"
SERVICE="${FASTAPI_SERVICE:-fastapi}"
BASE_URL="${SMOKE_BASE_URL:-http://127.0.0.1:8000}"

step()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
run()   { if [ "$DRY_RUN" = 1 ]; then echo "   [dry-run] $*"; else eval "$@"; fi; }
fail()  { printf '\033[31m배포 중단: %s\033[0m\n' "$*" >&2; exit 1; }

[ -x "$VENV_PY" ] || [ "$DRY_RUN" = 1 ] || fail "python 이 없다: $VENV_PY (VENV_PY 로 지정할 수 있다)"

# ── 0) 되돌릴 지점을 먼저 만든다 ────────────────────────────────────────────
# 배포가 깨진 뒤에 "직전이 무엇이었나" 를 찾는 것은 늦다.
step "배포 직전 태그"
TAG="deploy-$(date +%Y%m%d-%H%M%S)"
run "git -C '$REPO_ROOT' tag -f '$TAG'"
echo "   되돌리려면: scripts/rollback.sh $TAG"

# ── 1) 생성물이 정본과 어긋나지 않는가 ──────────────────────────────────────
# 정의를 고쳐 놓고 파생물을 안 만들면 프론트는 옛 정의로 그리는데 백엔드는 새 정의로 실행한다.
step "생성물 동기화 확인 (export_node_definitions.py --check)"
if [ "$DRY_RUN" = 0 ]; then
  if ! (cd "$BACKEND" && "$VENV_PY" export_node_definitions.py --check); then
    fail "생성물이 정본과 다르다. \`python backend/export_node_definitions.py\` 를 돌리고 커밋하라."
  fi
else
  echo "   [dry-run] cd $BACKEND && $VENV_PY export_node_definitions.py --check"
fi

# ── 2) 프론트 빌드 ──────────────────────────────────────────────────────────
if [ "$SKIP_FRONTEND" = 0 ]; then
  step "프론트엔드 빌드"
  run "cd '$FRONTEND' && npm ci"
  run "cd '$FRONTEND' && npm run build"
else
  step "프론트엔드 빌드 건너뜀 (--skip-frontend)"
fi

# ── 3) 스키마 ───────────────────────────────────────────────────────────────
# 앱이 아니라 **여기서** 올린다. 임포트 시점 마이그레이션은 "재기동 = 스키마 변경" 이 되어,
# 크래시 루프가 매 사이클 운영 스키마를 건드린다(main.py 의 AUTO_MIGRATE_ON_BOOT 주석 참고).
step "DB 마이그레이션 (alembic upgrade head)"
run "cd '$BACKEND' && '$VENV_PY' -m alembic upgrade head"

# ── 4) 재기동 ───────────────────────────────────────────────────────────────
step "서비스 재기동 ($SERVICE)"
run "sudo systemctl restart '$SERVICE'"

# ── 5) 스모크 ───────────────────────────────────────────────────────────────
# 프로브가 없으면 여기서 확인할 수 있는 것이 index.html 뿐이고, 그러면 반영 실패를 못 잡는다.
step "스모크"
if [ "$DRY_RUN" = 1 ]; then
  echo "   [dry-run] $BASE_URL/api/health · /api/ready · 없는 라우트 404 확인"
else
  for _ in $(seq 1 30); do
    curl -fsS -o /dev/null "$BASE_URL/api/health" 2>/dev/null && break
    sleep 1
  done
  curl -fsS -o /dev/null "$BASE_URL/api/health" || fail "/api/health 가 응답하지 않는다 (journalctl -u $SERVICE -n 50)"
  echo "   health   ok"

  READY_BODY="$(curl -sS -w '\n%{http_code}' "$BASE_URL/api/ready")"
  READY_CODE="$(printf '%s' "$READY_BODY" | tail -n1)"
  [ "$READY_CODE" = "200" ] || fail "/api/ready 가 $READY_CODE 다: $(printf '%s' "$READY_BODY" | head -n1)"
  echo "   ready    ok"

  # 없는 API 경로가 SPA 셸(200 text/html)로 위장하지 않는지 — 이 저장소의 실제 재발 이력이다.
  MISS="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/api/__deploy_smoke_no_such_route__")"
  [ "$MISS" = "404" ] || fail "없는 API 경로가 $MISS 를 돌려준다 (200 이면 배포 반영이 안 된 것이다)"
  echo "   404 규약 ok"
fi

step "배포 완료 (태그 $TAG)"
echo "   되돌리려면: scripts/rollback.sh $TAG"
