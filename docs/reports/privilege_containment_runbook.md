# 백엔드 임시 권한 격리 실행 계획

> 상태: 문서화 완료, 미적용  
> 작성일: 2026-08-24  
> 목적: `exec()` 제거 전까지 워크플로 실행 취약점이 호스트 관리자 권한 탈취로 확대되는 것을 제한한다.

## 1. 현재 관찰 결과

- 백엔드는 일반 사용자 `ubuntu`로 실행 중이다.
- `ubuntu`는 `sudo`, `docker`, `lxd` 그룹에 포함되어 있다. 이 그룹들은 호스트 관리자 권한 획득으로 이어질 수 있으므로 서비스 실행 계정으로 사용하면 안 된다.
- `backend/.env` 권한은 점검 시점에 `755`였다. 자격 증명 파일은 소유자만 읽거나, 전용 서비스 그룹만 읽도록 제한해야 한다.
- 워크플로 실행에는 외부 HTTP API, PostgreSQL, 파일 업로드, ChromaDB 및 일부 문서/브라우저 처리 기능이 필요하다. 따라서 네트워크와 모든 파일 접근을 일괄 차단할 수는 없다.

## 2. 방어 목표와 한계

| 위협 | 임시 격리 효과 |
| --- | --- |
| `sudo`, Docker, LXD를 통한 호스트 관리자 권한 획득 | 전용 무권한 계정으로 차단 |
| 시스템 파일 및 애플리케이션 소스 변조 | systemd 읽기 전용 파일 시스템 정책으로 제한 |
| 다른 로컬 사용자의 `.env` 열람 | 파일 권한 `0640` 또는 `0600`으로 제한 |
| 커널 모듈, 제어 그룹, 장치 조작 | systemd hardening 옵션으로 제한 |
| 애플리케이션 DB와 외부 API 키 접근 | 차단하지 못함. 정상 워크플로에 필요한 권한이므로 별도 분리가 필요 |
| 허용된 외부 네트워크를 이용한 정보 유출 | 차단하지 못함. 연동 노드별 egress 정책이 추가로 필요 |
| `exec()` 취약점 자체 | 제거하지 않음. 피해 범위만 축소 |

이 계획은 RCE의 근본 해결책이 아니다. 최종 목표는 `backend/graph.py`의 동적 코드 실행을 노드별 dispatcher로 교체하는 것이다.

## 3. 사전 준비

적용 전에 현재 프로세스, 권한 및 쓰기 경로를 기록한다.

```bash
cd /home/ubuntu/app
ps -eo user,group,pid,ppid,cmd | grep '[u]vicorn'
id ubuntu
stat -c '%a %U:%G %n' backend/.env backend/uploads backend/chroma_db backend/error_log
```

PostgreSQL 백업과 `backend/.env`의 별도 암호화 백업을 준비한다. 백업 파일은 저장소와 동일한 서버 디렉터리에 평문으로 두지 않는다.

## 4. 전용 서비스 계정

로그인 셸과 특권 그룹이 없는 시스템 계정을 만든다.

```bash
sudo useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin workflowapp
id workflowapp
```

출력에 `sudo`, `docker`, `lxd`, `adm` 등의 그룹이 없어야 한다. 소스 디렉터리는 계속 `ubuntu` 소유의 읽기 전용 대상으로 두고, 런타임 쓰기가 필요한 경로만 서비스 계정에 넘긴다.

```bash
sudo chown -R workflowapp:workflowapp /home/ubuntu/app/backend/uploads
sudo chown -R workflowapp:workflowapp /home/ubuntu/app/backend/chroma_db
sudo touch /home/ubuntu/app/backend/error_log
sudo chown workflowapp:workflowapp /home/ubuntu/app/backend/error_log
sudo chown root:workflowapp /home/ubuntu/app/backend/.env
sudo chmod 0640 /home/ubuntu/app/backend/.env
sudo chmod 0700 /home/ubuntu/app/backend/uploads
```

소스 파일과 가상환경은 `workflowapp`이 읽을 수 있어야 하지만 쓸 수 없어야 한다.

## 5. systemd 격리 초안

`/etc/systemd/system/workflow-backend.service`에 다음 단위를 배치한다. 실제 적용 전 스테이징 환경에서 문서 생성, RAG, 봇 및 외부 연동을 확인한다.

```ini
[Unit]
Description=Workflow Automation Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=workflowapp
Group=workflowapp
WorkingDirectory=/home/ubuntu/app/backend
EnvironmentFile=/home/ubuntu/app/backend/.env
ExecStart=/home/ubuntu/app/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=3
UMask=0077

NoNewPrivileges=true
CapabilityBoundingSet=
AmbientCapabilities=
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectClock=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictRealtime=true
SystemCallArchitectures=native

ReadWritePaths=/home/ubuntu/app/backend/uploads
ReadWritePaths=/home/ubuntu/app/backend/chroma_db
ReadWritePaths=/home/ubuntu/app/backend/error_log

[Install]
WantedBy=multi-user.target
```

`RestrictNamespaces=true`는 격리를 강화하지만 Playwright/Chromium 기반 문서 생성과 충돌할 수 있어 기본 초안에서는 제외했다. 해당 기능을 별도 프로세스로 분리한 뒤 활성화하는 것이 안전하다. 외부 연동 때문에 `PrivateNetwork=true`도 현재는 사용할 수 없다.

## 6. 적용 순서

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now workflow-backend.service
sudo systemctl status workflow-backend.service --no-pager
```

기존 수동 실행 `uvicorn` 프로세스는 systemd 서비스를 시작하기 전에 종료하여 포트 충돌을 방지한다. Nginx는 외부에서 백엔드 포트로 직접 접근하지 못하도록 `127.0.0.1:8000`으로만 프록시해야 한다.

## 7. 검증 체크리스트

- `systemctl show workflow-backend.service -p User -p Group -p NoNewPrivileges` 결과가 계획과 일치한다.
- `systemd-analyze security workflow-backend.service` 결과를 적용 전후로 저장한다.
- `workflowapp` 계정에서 `sudo -n true`가 실패한다.
- `workflowapp` 계정에서 `/etc`, 애플리케이션 소스 및 `.env`를 수정할 수 없다.
- 로그인, API 센터, 워크플로 저장/실행, RAG 업로드가 정상 작동한다.
- HWPX/DOCX/PDF 및 Playwright 기반 생성 기능이 정상 작동한다.
- Discord, Telegram, Kakao 및 예약 실행이 서버 재시작 후 정상 복구된다.
- 위험 확장자 업로드가 `415`, 인증 없는 컨텍스트 업로드가 `401`을 반환한다.
- 서비스 로그에 API 키, OAuth 토큰 또는 요청 본문이 기록되지 않는다.

권한 검증 예시는 다음과 같다.

```bash
sudo -u workflowapp sudo -n true
sudo -u workflowapp test ! -w /etc
sudo -u workflowapp test ! -w /home/ubuntu/app/backend/main.py
sudo -u workflowapp test -w /home/ubuntu/app/backend/uploads
curl -fsS http://127.0.0.1:8000/docs >/dev/null
```

## 8. 장애 시 되돌리기

```bash
sudo systemctl disable --now workflow-backend.service
sudo chown -R ubuntu:ubuntu /home/ubuntu/app/backend/uploads
sudo chown -R ubuntu:ubuntu /home/ubuntu/app/backend/chroma_db
sudo chown ubuntu:ubuntu /home/ubuntu/app/backend/error_log
sudo chown ubuntu:ubuntu /home/ubuntu/app/backend/.env
sudo chmod 0600 /home/ubuntu/app/backend/.env
```

이후 기존 실행 방식으로 백엔드를 기동한다. 롤백하더라도 `.env`를 다시 `755`로 되돌리면 안 된다.

## 9. 후속 작업

1. 운영 환경에서 `pythonNode`를 완전히 비활성화하는 feature flag를 추가한다.
2. 외부 연동 노드의 목적지 도메인 allowlist와 메타데이터 IP 차단을 적용한다.
3. PostgreSQL 역할을 런타임용과 마이그레이션용으로 분리한다.
4. 문서/브라우저 생성 노드를 별도 샌드박스 프로세스로 분리한다.
5. 노드별 dispatcher 전환을 완료하고 `exec()`를 제거한다.
