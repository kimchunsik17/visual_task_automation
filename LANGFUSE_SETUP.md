# Langfuse 실행 및 설정 가이드

본 문서는 프로젝트 내 포함된 `docker-compose.langfuse.yml` 파일을 사용하여 로컬 환경에 Langfuse 서버를 띄우고, 백엔드와 연동하기 위한 준비 과정을 설명합니다.

## 1. 사전 준비

- Docker 및 Docker Compose가 설치되어 있어야 합니다.
- 포트 충돌 확인:
  - **3000 포트**: Langfuse 웹 UI 및 API 서버가 사용합니다.
  - **5432 포트**: Langfuse용 PostgreSQL DB가 사용합니다. (만약 로컬에 이미 PostgreSQL이 5432 포트로 실행 중이라면, `docker-compose.langfuse.yml` 파일에서 `ports: - "5432:5432"` 부분을 `"5433:5432"` 등으로 수정해야 할 수 있습니다.)

## 2. Langfuse 서버 실행

터미널을 열고 프로젝트 루트 디렉토리(업무자동화 비주얼화)에서 다음 명령어를 실행합니다.

```bash
# 백그라운드(데몬) 모드로 컨테이너 실행
docker-compose -f docker-compose.langfuse.yml up -d
```

명령어가 성공적으로 실행되면, 브라우저를 열고 **http://localhost:3000** 에 접속합니다.
초기 접속 시 회원가입 화면이 나타나며, 로컬 환경에서 사용할 관리자 계정을 생성해 주시면 됩니다.

## 3. 프로젝트(Project) 생성 및 API 키 발급

1. Langfuse 웹(http://localhost:3000)에 로그인합니다.
2. 새 프로젝트(예: `visual_task_automation`)를 생성합니다.
3. 프로젝트 설정(Settings) -> **API Keys** 메뉴로 이동하여 새로운 API 키를 생성합니다.
4. 발급된 **Public Key**, **Secret Key**, **Host URL** 값을 복사해 둡니다.

## 4. 백엔드 연동 설정 (.env)

복사한 API 키 정보들을 백엔드의 `.env` 파일(`backend/.env`)에 추가하여 애플리케이션과 연동합니다.

`backend/.env` 파일 맨 아래에 다음 내용을 추가하세요:

```env
# Langfuse 연동 키
LANGFUSE_PUBLIC_KEY="발급받은_PUBLIC_KEY"
LANGFUSE_SECRET_KEY="발급받은_SECRET_KEY"
LANGFUSE_HOST="http://localhost:3000"
```

## 5. 컨테이너 종료 방법

작업이 끝나거나 Langfuse 서버를 종료하고 싶을 때는 다음 명령어를 사용합니다.

```bash
docker-compose -f docker-compose.langfuse.yml down
```

> **참고**: 볼륨(`langfuse-db-data`)이 설정되어 있으므로, 컨테이너를 내렸다가 다시 올려도 DB에 저장된 데이터(계정 정보, 로그 데이터 등)는 유지됩니다. 저장된 데이터를 완전히 초기화하고 싶다면 `docker-compose -f docker-compose.langfuse.yml down -v` 옵션을 사용하세요.
