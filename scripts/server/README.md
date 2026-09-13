# 서버 작업 묶음 (0·1단계 잔여)

로컬에서 할 수 있는 것은 전부 끝냈고, **서버에 붙어야만 되는 것**만 여기 모았다. 한 번의
세션에서 순서대로 실행하도록 만들었다.

> 이 디렉터리의 스크립트는 서버에서 실행하는 것이 전제다. 개발 머신(Windows)에서 돌리지 말 것.

## 브랜치 규약 (2026-09-11)

**서버는 `release` 브랜치를 추적한다.** main 에 머지되는 것과 서버에 반영되는 것을 분리하기 위한 것이다 —
시연 빌드를 그대로 둔 채 main 에 큰 스택(실행 엔진 v2 등)을 머지할 수 있어야 했다. 이 저장소에는 CI/CD 가
없으므로 서버는 사람이 `git pull` 하고 `scripts/deploy.sh` 를 돌릴 때만 바뀐다. `deploy.sh` 는 현재 브랜치가
`DEPLOY_BRANCH`(기본 `release`)가 아니면 첫 단계에서 멈춘다.

| 하려는 일 | 어디서 | 명령 |
| --- | --- | --- |
| main 을 서버에 내보낸다 | 로컬 | `git checkout release && git merge --ff-only origin/main && git push` (ff 가 안 되면 `git merge origin/main`) |
| 서버 반영 | 서버 | `cd /home/ubuntu/app && git pull && scripts/deploy.sh` |
| 핫픽스만 서버에 | 로컬 | main 에 머지한 뒤 `git checkout release && git cherry-pick <sha> && git push` |
| release 가 아닌 브랜치를 일부러 | 서버 | `DEPLOY_BRANCH=<branch> scripts/deploy.sh` |

`rollback.sh` 는 HEAD 를 detached 로 두므로, 되돌린 뒤 다시 배포하려면 `git checkout release && git pull` 부터.

## 시작 전에

```bash
cd /home/ubuntu/app
git fetch origin && git log --oneline -3 origin/release   # 내보낼 커밋이 release 에 있는지
git pull
```

**전제 하나**: PR #33 이 머지돼 있어야 한다. `scripts/deploy.sh`, `/api/health`, `/api/ready`
가 그 안에 있고, 아래 절차가 그것들을 쓴다.

**배포 명령이 바뀌었다**: 의존성 설치 대상이 `requirements_linux.txt` → `requirements.txt` 다.
그 파일은 폐기됐다(부분집합이라 python-hwpx·gspread·google-auth-oauthlib·playwright 4개가
빠져 있었고, 해당 노드들이 런타임에만 죽고 있었다).

```bash
cd /home/ubuntu/app/backend && venv/bin/pip install -r requirements.txt
```

## 순서

각 스크립트는 `--dry-run` 을 지원한다. **먼저 dry-run 으로 무엇이 바뀌는지 보고 실행하라.**
전부 실행 전 백업을 만들고, 실패하면 스스로 원복하거나 원복 명령을 알려준다.

| # | 스크립트 | 무엇을 | 위험 |
| --- | --- | --- | --- |
| 1 | `01-nginx-telegram-webhook.sh` | 텔레그램 프록시 규칙 추가 | 낮음 (`nginx -t` 실패 시 자동 원복) |
| 2 | `02-env-permissions.sh` | `.env` 를 0640 으로 | 낮음~중간 (서비스가 못 읽으면 ready 실패로 드러난다) |
| 3 | `03-systemd-hardening.sh` | 재기동 상한·PATH | 낮음 (드롭인이라 파일 삭제로 원복) |
| 4 | **`04-bind-loopback.sh`** | 8000 을 루프백에만 | **높음 — 실패하면 사이트 전체 502** |
| 5 | `05-log-rotation.sh` | logrotate + journald 상한 | 낮음 |
| 6 | `06-requirements-lock.sh` | lock 파일 생성 | 없음 (읽기만, `--write` 로 써야 반영) |
| 7 | `07-uploads-per-user-move.sh` | 기존 업로드 파일을 소유자 디렉토리로 이동 | 낮음 (dry-run 기본, `--apply` 로 실행. **마이그레이션 0023 이 적용된 배포 뒤에만**) |
| 8 | `08-run-worker-unit.sh` | 큐 워커 systemd 템플릿 유닛 `run-worker@` 생성·기동 | 낮음 (유닛 파일 하나, 되돌리기는 disable + rm). **ENGINE-2 코드(0024~0026)가 배포된 뒤에만** — 절차는 아래 "큐 모드 켜기" |

**4번은 혼자 실행한다.** 계획서가 "두 바인드 변경을 한 번에 하지 않는다" 고 못 박았다.
mock_server 바인드는 코드에서 이미 루프백으로 바꿨고 배포로 나가므로 여기서 함께 만지지 않는다.

```bash
cd /home/ubuntu/app
sudo scripts/server/01-nginx-telegram-webhook.sh --dry-run
sudo scripts/server/01-nginx-telegram-webhook.sh
# ... 하나씩, 각 단계 뒤에 /api/ready 가 200 인지 확인하고 다음으로
```

## 마지막 — AUTO_MIGRATE_ON_BOOT 전환

**순서를 뒤집으면 서비스가 선다.** 이건 위 1~6 이 끝나고, `scripts/deploy.sh` 로 배포를
**한 번 이상 성공시킨 뒤에** 한다.

지금은 앱이 임포트 시점에 마이그레이션을 적용한다. 그 말은 "재기동 = 운영 스키마 변경" 이고,
크래시 루프가 돌면 매 사이클이 그것을 실행한다(4.2일간 6,645회 재기동이 관측된 서버다).

`deploy.sh` 가 `alembic upgrade head` 를 먼저 완주시키는 레일이 자리잡으면, 앱은 스키마를
확인만 하게 바꾼다:

```bash
# backend/.env 에 추가
AUTO_MIGRATE_ON_BOOT=0
sudo systemctl restart fastapi
curl -s http://127.0.0.1:8000/api/ready     # {"status":"ready", ...} 여야 한다
```

이후로는 마이그레이션이 있는 배포에서 `deploy.sh` 를 거치지 않고 `systemctl restart` 만 하면
**기동을 거부한다**. 그것이 의도된 동작이다 — 운영자가 모르면 장애로 보이므로 미리 알아 둘 것.
`/api/ready` 가 그 상태를 `{"checks":{"schema":false}, "detail":{"schema":{...}}}` 로 구분해 준다.

## 큐 모드 켜기 (실행 엔진 v2 ENGINE-2, ADR-0029)

기본은 꺼져 있다(`EXECUTION_QUEUE=0`) — 배포만으로는 아무것도 바뀌지 않는다. 켜면 **스케줄·웹훅** 실행이 `workflow_runs` 큐에
들어가고(웹훅은 202 + run_id) 워커가 실행한다. 에디터·앱·봇·`/api/call` 은 인라인 그대로.

순서 — 각 단계 뒤 `/api/ready` 가 200 인지 본다.

| # | 어디서 | 무엇 | 확인 |
| --- | --- | --- | --- |
| 1 | 서버 | ENGINE-2 가 든 release 를 `scripts/deploy.sh` 로 배포(0024~0026 마이그레이션 포함) | `/api/ready` 200, `/api/features` 의 `execution_queue` false |
| 2 | 서버 | `sudo scripts/server/08-run-worker-unit.sh --dry-run` → `sudo scripts/server/08-run-worker-unit.sh` | `systemctl is-active run-worker@1`, `journalctl -u run-worker@1 -n 20` 에 "시작" |
| 3 | 서버 | `backend/.env` 에 `EXECUTION_QUEUE=1` 추가, `sudo systemctl restart fastapi` | `/api/ready` 의 `checks.queue` true(빈 큐), `/api/features` 의 `execution_queue` true |
| 4 | 브라우저·서버 | 스케줄 프로젝트 하나를 1분 뒤로 잡거나 웹훅을 한 번 쏜다 | 웹훅은 202 `{status: queued, run_id}`; `journalctl -u run-worker@1 -f` 에 claim → 실행; `GET /api/projects/{id}/workflow-runs/{run_id}` 가 succeeded |

**리허설 — 세 가지를 꼭 해 본다.** 출시 게이트("재시작이 실행 중 run 을 잃지 않는지", ROADMAP §3.1)가 이것으로 닫힌다.

1. **정상 재기동**: 긴 run(LLM 노드 여럿)이 running 인 동안 `sudo systemctl restart run-worker@1`. 기대: SIGTERM 을 받은 워커가 그 run 을
   **마치고** 종료·재기동한다(최대 TimeoutStopSec 900초 — `systemctl restart` 가 그동안 기다린다). 타임라인에서 그 run 은 succeeded,
   `journalctl` 에 "현재 run 을 마치고 종료".
2. **강제 종료**: 같은 상황에서 `sudo systemctl kill -s SIGKILL run-worker@1`. 기대: 유닛이 3초 뒤 다시 뜨고, 죽은 run 은
   `RUN_WORKER_STALE_SECONDS`(120) 뒤 **failed 로 확정**된다(error_summary "워커 heartbeat 끊김"). 재실행되지 않는다 — 부작용 노드를
   지났는지 모르기 때문(ADR-0029 결정 5). 그동안 `/api/ready` 는 `checks.queue` true(새 워커가 heartbeat 를 찍는다).
3. **워커를 내려 본다**: `sudo systemctl stop run-worker@1` 뒤 스케줄 하나 발화 → `RUN_QUEUE_STALL_SECONDS`(300) 지나면 `/api/ready` 가
   503 `checks.queue=false`, `detail.queue.stalled=true`. `start` 하면 queued 가 실행되고 200 으로 돌아온다. 이것이 "워커가 없다" 를
   프로브가 잡는 모양이다.

**되돌리기**: `.env` 에서 `EXECUTION_QUEUE=0`, `sudo systemctl restart fastapi` — 그 순간부터 스케줄·웹훅은 인라인. 남은 queued 는 워커가
비운다. 워커도 내리려면 `sudo systemctl disable --now 'run-worker@*'`, 그 뒤 `sudo rm /etc/systemd/system/run-worker@.service &&
sudo systemctl daemon-reload`.

**두 인스턴스가 될 때**: 같은 스케줄 슬롯(분)은 `idempotency_key` 로 run 하나만 들어가므로 APScheduler 를 양쪽에서 돌려도 중복 실행은
없다. 리더 선출은 필요 없다. 워커는 `INSTANCES=2` 로 하나 더 띄우면 되고 SKIP LOCKED 가 중복 claim 을 막는다.

## 전체 확인

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/ready
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/__no_such_route__   # 404
ss -ltn | grep 8000                                                                    # 127.0.0.1 만
curl -sS -o /dev/null -w '%{http_code}\n' -X POST -H 'Host: wa-pnu.duckdns.org' \
     https://127.0.0.1/telegram-webhook/999999 --insecure                              # 405 가 아니어야
```

브라우저로 사이트를 한 번 왕복하는 것으로 마무리한다 — 위 curl 은 전부 통과하는데 화면만
깨지는 경우가 이 저장소의 재발 이력이다.

## 여기 없는 것

- **전용 서비스 계정 이전** — 더 큰 별건이다. `docs/reports/privilege_containment_runbook.md`.
  그쪽을 먼저 적용했다면 `.env` 소유자가 이미 `root:workflowapp` 일 수 있는데, 02 는 소유자를
  건드리지 않으므로 충돌하지 않는다.
- **OpenAI 키 교체** — 이미 끝났다.
- **프론트엔드 항목**(`main.jsx` DEV 가드, ErrorBoundary) — 브라우저 확인이 필요해 로컬에 남겼다.
