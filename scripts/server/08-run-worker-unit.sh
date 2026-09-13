#!/usr/bin/env bash
#
# 08 — 큐 워커 systemd 템플릿 유닛 run-worker@.service 를 만들고 인스턴스를 켠다 (백로그 32 ENGINE-2 3단계, ADR-0029).
#
# 왜: EXECUTION_QUEUE=1 이면 스케줄·웹훅 실행이 큐에 들어가고, 누군가 잡아야 돈다. 인프로세스 워커
# (EXECUTION_WORKER_INPROCESS=1)는 검증용이고, 제대로 된 분리는 별도 프로세스다 — API 를 재기동해도 실행이
# 살아 있고, LLM 대기가 API 의 이벤트 루프를 점유하지 않는다. 템플릿 유닛이라 run-worker@2 로 하나 더 띄울
# 수 있다(SKIP LOCKED 가 중복을 막는다 — run_queue.claim).
#
# 무엇을 참조하나: fastapi 유닛의 User/Group 을 그대로 쓴다 — .env 를 같은 권한으로 읽어야 한다(02 가 0640 으로
# 좁혔다). .env 는 systemd EnvironmentFile 이 아니라 앱(database.py 의 load_dotenv)이 읽는다 — API 와 같은 방식.
#
#   sudo scripts/server/08-run-worker-unit.sh --dry-run
#   sudo scripts/server/08-run-worker-unit.sh              # run-worker@1
#   sudo INSTANCES=2 scripts/server/08-run-worker-unit.sh  # run-worker@1, run-worker@2
#
# 되돌리기: sudo systemctl disable --now 'run-worker@*'; sudo rm /etc/systemd/system/run-worker@.service; sudo systemctl daemon-reload
# 배포: scripts/deploy.sh 가 alembic 뒤 run-worker@* 를 재기동한다(유닛이 있을 때만).

set -euo pipefail

SERVICE="${FASTAPI_SERVICE:-fastapi}"
APP_ROOT="${APP_ROOT:-/home/ubuntu/app}"
INSTANCES="${INSTANCES:-1}"
STOP_TIMEOUT="${STOP_TIMEOUT:-900}"
UNIT_PATH="/etc/systemd/system/run-worker@.service"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

fail() { printf '\033[31m중단: %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[1m%s\033[0m\n' "$*"; }

BACKEND="$APP_ROOT/backend"
[ -x "$BACKEND/venv/bin/python" ] || fail "python 이 없다: $BACKEND/venv/bin/python (APP_ROOT 를 확인)"
[ -f "$BACKEND/run_worker.py" ] || fail "run_worker.py 가 없다 — ENGINE-2 가 든 코드가 먼저 배포돼 있어야 한다"
case "$INSTANCES" in ''|*[!0-9]*|0) fail "INSTANCES 는 1 이상의 정수여야 한다: $INSTANCES" ;; esac

# 실행 계정은 fastapi 유닛과 같게 — 같은 .env·같은 uploads 권한.
RUN_USER="$(systemctl show -p User --value "$SERVICE" 2>/dev/null || true)"
RUN_GROUP="$(systemctl show -p Group --value "$SERVICE" 2>/dev/null || true)"
[ -n "$RUN_USER" ] || RUN_USER="$(stat -c %U "$APP_ROOT")"
info "실행 계정: User=$RUN_USER${RUN_GROUP:+ Group=$RUN_GROUP} ($SERVICE 유닛과 같게)"

ENV_FILE="$BACKEND/.env"
if [ -f "$ENV_FILE" ]; then
  if ! sudo -u "$RUN_USER" test -r "$ENV_FILE" 2>/dev/null; then
    fail "$RUN_USER 가 $ENV_FILE 을 읽을 수 없다 — 워커가 DATABASE_URL 을 못 본다. 02-env-permissions 의 그룹 설정을 확인."
  fi
  if ! grep -qE '^EXECUTION_QUEUE=(1|true|on|yes)\s*$' "$ENV_FILE"; then
    echo "  ⚠️  .env 에 EXECUTION_QUEUE=1 이 없다 — 워커는 뜨지만 큐에 아무것도 들어오지 않는다(켜는 절차는 README '큐 모드 켜기')."
  fi
  if grep -qE '^EXECUTION_WORKER_INPROCESS=(1|true|on|yes)\s*$' "$ENV_FILE"; then
    echo "  ⚠️  EXECUTION_WORKER_INPROCESS=1 이다 — 별도 워커를 쓰면 0 으로 돌려도 된다(둘 다 있어도 중복 실행은 없다)."
  fi
fi

GROUP_LINE=""
[ -n "$RUN_GROUP" ] && GROUP_LINE="Group=$RUN_GROUP"

read -r -d '' CONTENT <<EOF || true
# scripts/server/08-run-worker-unit.sh 가 만든 파일이다 (백로그 32 ENGINE-2, ADR-0029).
# 되돌리려면: systemctl disable --now 'run-worker@*' && rm $UNIT_PATH && systemctl daemon-reload
[Unit]
Description=workflow_runs 큐 워커 %i (run_worker.py)
After=network-online.target
Wants=network-online.target
# 5분에 5번 넘게 죽으면 멈춘다 — fastapi 유닛(03)과 같은 상한. 크래시 루프는 로그만 채운다.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=$RUN_USER
$GROUP_LINE
WorkingDirectory=$BACKEND
Environment="PATH=/usr/local/bin:/usr/bin:/bin:$BACKEND/venv/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$BACKEND/venv/bin/python run_worker.py --worker-id %H-w%i
Restart=always
RestartSec=3
# run_worker.py 는 SIGTERM 에 현재 run 을 마치고 종료한다 — 그 시간을 준다. 넘기면 SIGKILL 이고, 그 run 은
# heartbeat 끊김(RUN_WORKER_STALE_SECONDS)으로 failed 확정된다(재실행하지 않는다 — ADR-0029 결정 5).
KillSignal=SIGTERM
TimeoutStopSec=$STOP_TIMEOUT

[Install]
WantedBy=multi-user.target
EOF

INSTANCE_UNITS=""
for i in $(seq 1 "$INSTANCES"); do INSTANCE_UNITS="$INSTANCE_UNITS run-worker@$i"; done

info "넣을 유닛 ($UNIT_PATH):"
printf '%s\n' "$CONTENT" | sed '/^$/d' | sed 's/^/    /'

if [ "$DRY_RUN" = 1 ]; then
  info "[dry-run] 여기까지. 실행하면: 유닛 쓰기 → daemon-reload → systemctl enable --now$INSTANCE_UNITS → is-active 확인"
  exit 0
fi

if [ -f "$UNIT_PATH" ]; then
  BACKUP="${UNIT_PATH}.bak-$(date +%Y%m%d-%H%M%S)"
  cp -a "$UNIT_PATH" "$BACKUP"
  info "백업: $BACKUP"
fi
printf '%s\n' "$CONTENT" | sed '/^$/d' > "$UNIT_PATH"
systemctl daemon-reload
# shellcheck disable=SC2086
systemctl enable --now $INSTANCE_UNITS
sleep 2
for unit in $INSTANCE_UNITS; do
  systemctl is-active --quiet "$unit" || fail "$unit 이 뜨지 않았다: journalctl -u $unit -n 50"
  echo "    $unit active"
done

info "최근 로그"
journalctl -u 'run-worker@*' -n 5 --no-pager 2>/dev/null | sed 's/^/    /' || true

info "완료. 다음을 확인한다:"
echo "    curl -s http://127.0.0.1:8000/api/ready      # checks.queue 가 true (큐가 켜져 있을 때) · detail.queue.depth 가 줄어드는지"
echo "    journalctl -u run-worker@1 -f               # claim → 실행 → 과금 로그"
echo "되돌리려면: systemctl disable --now 'run-worker@*' && rm $UNIT_PATH && systemctl daemon-reload"
