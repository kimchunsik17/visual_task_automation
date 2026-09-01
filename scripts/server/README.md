# 서버 작업 묶음 (0·1단계 잔여)

로컬에서 할 수 있는 것은 전부 끝냈고, **서버에 붙어야만 되는 것**만 여기 모았다. 한 번의
세션에서 순서대로 실행하도록 만들었다.

> 이 디렉터리의 스크립트는 서버에서 실행하는 것이 전제다. 개발 머신(Windows)에서 돌리지 말 것.

## 시작 전에

```bash
cd /home/ubuntu/app
git fetch origin && git log --oneline -3 origin/main   # PR #33 이 머지됐는지
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
