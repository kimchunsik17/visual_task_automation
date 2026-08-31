# `/statistics` 구조·버그·디자인 감사 및 개선 계획

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 상태 | 분석 및 제안안 v1.0 |
| 작성일 | 2026-08-27 |
| 대상 | `frontend/src/pages/StatisticsPage.jsx`, `GET /api/statistics`, 사용량 로그 생성 경로 |
| 목표 | 통계 수치의 신뢰성, 화면 상태 처리, 반응형 사용성과 유지보수 구조를 함께 개선 |
| 이번 범위 | 현황 분석과 구현 계획 문서화 |
| 제외 | 실제 DB 마이그레이션, API와 UI 코드 변경 |

## 1. 결론 요약

현재 `/statistics`는 토큰 잔액, 누적 사용량, 기능별 사용량, 기간별 추이와 프로젝트별 사용량을 한 화면에 보여준다. 기능의 뼈대는 갖추었지만, 지금 상태에서는 **디자인보다 데이터 의미와 기록 경로를 먼저 바로잡아야 한다.**

핵심 문제는 다음 네 가지다.

1. **비용을 부담한 사용자와 로그에 기록된 사용자가 다를 수 있다.**
   - 공유 App Runner와 Custom App은 프로젝트 소유자의 잔액을 차감하면서 실행한 사용자를 로그의 `user_id`로 기록한다.
   - 익명 실행이면 `user_id`가 `NULL`이므로 소유자의 통계에 해당 사용량이 나타나지 않는다.

2. **한 개의 `status` 필드가 실행 결과와 사용 유형을 동시에 표현한다.**
   - `success`, `error`는 실행 결과지만 `agent`, `app_builder`, `evaluation`은 사용 유형이다.
   - `app_agent`는 현재 집계 함수가 인식하지 않아 워크플로우 실행으로 분류된다.

3. **기간 필터와 화면의 수치 범위가 일치하지 않는다.**
   - 기간 선택은 추이 차트에만 적용된다.
   - 요약 카드, 기능별 비율과 프로젝트 사용량은 계속 전체 누적값이므로 화면 전체가 선택 기간 기준이라는 오해를 만든다.

4. **모바일 레이아웃이 실제로 깨진다.**
   - 390px 브라우저에서 통계 콘텐츠의 `scrollWidth`가 435px로 측정됐다.
   - `1fr 310px` 고정 2열 구조가 유지되어 추이 차트 제목과 범례가 한 글자 단위로 줄바꿈된다.

권장 순서는 **사용량 기록 계약 수정 → 집계 API 개선 → 화면 구조 분리 → 시각 디자인 정리**다. 데이터가 부정확한 상태에서 카드와 차트만 다듬으면 더 설득력 있게 잘못된 수치를 보여주게 된다.

## 2. 감사 범위와 방법

### 2.1 확인한 코드

- 화면과 상태 처리: `frontend/src/pages/StatisticsPage.jsx`
- 공통 페이지 레이아웃: `frontend/src/pages/MainPage.css`
- 테마와 전역 스타일: `frontend/src/index.css`
- 라우팅과 인증 경계: `frontend/src/App.jsx`, `frontend/src/AuthContext.jsx`, `frontend/src/RequireAuth.jsx`
- 통계 API: `backend/main.py:2449`
- 로그 모델: `backend/models.py:57`
- 워크플로우, 공개 앱, Webhook, Agent, App Builder, Evaluation의 로그 생성 경로

### 2.2 렌더링 확인

결정적인 화면 상태를 보기 위해 `/api/statistics` 응답을 고정된 샘플로 대체하고 다음 뷰포트에서 렌더링했다.

| 뷰포트 | 결과 |
| --- | --- |
| 1440×1000 | 전체 정보는 표시되지만 왼쪽 Main Sidebar와 Chat rail이 동시에 공간을 사용하고, 6개 KPI가 4+2의 불균형한 행으로 배치됨 |
| 390×844 | 콘텐츠 폭 435px, 가로 overflow 발생, 추이 차트와 도넛이 강제로 2열 유지되어 차트 판독 불가 |

브라우저 렌더링은 UI 구조를 확인하기 위한 샘플 응답 기반이다. 실제 운영 데이터의 합계 일치 여부와 대용량 성능은 별도의 스테이징 데이터 검증이 필요하다.

## 3. 현재 구조

### 3.1 프론트엔드 흐름

```text
StatisticsPage mount
  -> AuthContext의 user/token 확인
  -> GET /api/statistics?time_range=weekly
  -> stats 단일 객체 저장
  -> summary cards / area chart / donut / project bar chart 렌더링
```

현재 한 파일이 다음 책임을 모두 가진다.

- 요청과 loading 상태
- 기간 선택
- 토큰/비용 표시 변환
- 사용 유형 label과 color 정의
- 데이터 존재 여부 판정
- KPI, 추이, 도넛, 프로젝트 차트 렌더링
- 빈 상태와 비로그인 상태

페이지 전용 CSS는 없으며 대부분의 레이아웃과 시각 속성이 JSX inline style이다. 공통 화면용 `MainPage.css`를 가져오기 때문에 통계 화면만의 breakpoint와 상태 스타일을 안전하게 조정하기 어렵다.

### 3.2 백엔드 흐름

`GET /api/statistics`는 요청마다 대략 다음 작업을 수행한다.

1. 사용자의 전체 토큰 합계를 `SUM`으로 조회한다.
2. 선택 기간의 로그 전체를 `.all()`로 가져와 Python에서 bucket을 만든다.
3. 사용자의 전체 로그를 다시 `.all()`로 가져와 기능별 누적값을 계산한다.
4. 프로젝트별 합계를 조회한다.
5. 각 프로젝트 ID마다 프로젝트를 다시 조회한다.
6. 프로젝트 없는 실행을 별도 집계한다.

응답 구조는 다음과 같다.

```json
{
  "total_used": 0,
  "remaining": 0,
  "total_allocated": 0,
  "chart_data": [],
  "project_usage": [],
  "usage_by_type": {
    "execution": 0,
    "agent": 0,
    "app_builder": 0,
    "evaluation": 0
  }
}
```

### 3.3 현재 데이터 모델의 한계

`FlowExecutionLog`는 실행 감사 로그, 오류 로그와 토큰 사용량 원장을 동시에 담당한다.

```text
user_id
project_id
execution_time
payload / result
total_tokens / token_usage_details
status / error_message
```

여기에는 다음 구분이 없다.

- 실행한 사용자와 비용을 부담한 사용자
- 실행 결과와 사용 유형
- provider와 model
- input, output, cached, reasoning token의 정규화된 필드
- 실제 비용과 추정 비용
- 중복 기록을 막는 request/event ID
- 충전, 관리자 지급, 차감, 환불 같은 잔액 변동 원인

따라서 현재 로그만으로는 잔액과 사용량을 안정적으로 대조하거나 모델별 실제 비용을 계산하기 어렵다.

## 4. 확인된 버그와 위험

### 4.1 우선순위 표

| ID | 우선순위 | 구분 | 문제 | 영향 |
| --- | --- | --- | --- | --- |
| STAT-001 | P0 | 데이터 | 공개 앱은 owner 잔액을 차감하지만 실행자 또는 `NULL`을 로그 사용자로 기록 | 소유자 사용량 누락, 실행자 사용량 과대 계상, 잔액과 누적값 불일치 |
| STAT-002 | P0 | 데이터 | `status`가 결과와 사용 유형을 동시에 표현 | 유형 오분류, 성공률 계산 불가, 신규 유형 추가 시 누락 |
| STAT-003 | P0 | 데이터 | `app_agent`가 허용 유형 집합에 없어 `execution`으로 집계 | App Builder/AI 생성 사용량 과소 계상 |
| STAT-004 | P0 | 데이터 | Webhook 로그는 남지만 프로젝트 소유자 잔액 차감이 보이지 않음 | 통계 사용량과 잔액 변화 불일치 |
| STAT-005 | P1 | 데이터 | 배포 API 실행 로그에 `project_id`를 저장하지 않음 | 프로젝트별 사용량이 `미지정 프로젝트`로 이동 |
| STAT-006 | P1 | 의미 | 기간 선택이 차트에만 적용되고 나머지는 누적값 | 사용자가 동일 기간 집계로 오해 |
| STAT-007 | P1 | 상태 | 성공 응답은 0값이어도 bucket 배열이 존재하여 빈 상태가 사실상 표시되지 않음 | 신규 사용자가 0만 있는 차트를 보게 됨 |
| STAT-008 | P1 | 상태 | API 실패를 console에만 기록하고 빈 상태와 구분하지 않음 | 장애가 `사용 기록 없음`으로 위장되고 재시도 불가 |
| STAT-009 | P1 | 반응형 | 차트 영역이 `1fr 310px` 고정 2열 | 390px에서 435px overflow 및 차트 판독 불가 |
| STAT-010 | P1 | 시간 | UTC의 naive datetime으로 일/월 경계를 계산 | KST 기준 사용량이 다른 날짜 bucket에 포함될 수 있음 |
| STAT-011 | P1 | 비용 | 모든 토큰을 `$2.5 / 1M`으로 환산 | 모델별 input/output 가격 차이를 무시한 부정확한 금액 표시 |
| STAT-012 | P1 | 성능 | 기간/전체 로그를 메모리에 올리고 프로젝트 N+1 조회 | 사용 기록이 늘수록 응답 시간과 메모리 사용 증가 |
| STAT-013 | P2 | 요청 | 기간 변경 요청을 취소하지 않음 | 빠르게 변경하면 이전 응답이 최신 선택을 덮을 수 있음 |
| STAT-014 | P2 | 표현 | KRW 값에 `₩` 또는 `KRW` 단위가 없음 | 숫자가 토큰인지 원화인지 모호함 |
| STAT-015 | P2 | 접근성 | select label, chart 대체 데이터, loading/error live region이 없음 | 키보드·스크린리더 사용성이 낮음 |
| STAT-016 | P2 | 품질 | 통계 API와 페이지 상태에 대한 전용 테스트가 없음 | 집계식과 반응형 회귀를 감지하기 어려움 |

### 4.2 데이터 귀속 오류

공개 App Runner는 `backend/main.py:978-989`에서 프로젝트 owner의 잔액을 차감하지만 `FlowExecutionLog.user_id`에는 현재 실행 사용자를 기록한다. Custom App도 `backend/main.py:1057-1068`에서 같은 방식이다.

통계 API는 `backend/main.py:2454`에서 `FlowExecutionLog.user_id == 현재 사용자`만 합산한다. 따라서 다음 식이 성립하지 않는다.

```text
현재 사용자의 잔액 감소량 == 현재 사용자의 통계 사용량
```

해결에는 단순히 `user_id`를 owner로 바꾸는 것보다 두 주체를 모두 보존하는 방식이 적합하다.

```text
actor_user_id: 실제 실행 요청자
billable_user_id: 잔액 또는 비용 부담자
```

통계 기본값은 `billable_user_id` 기준으로 집계하고, 운영 감사 화면에서는 actor를 별도로 조회해야 한다.

### 4.3 유형과 결과 상태의 충돌

현재 분류 함수는 `backend/main.py:2465-2468`에서 `agent`, `app_builder`, `evaluation`만 별도 유형으로 인정하고 나머지는 모두 `execution`으로 처리한다.

하지만 실제 `status` 값에는 다음 의미가 함께 들어간다.

```text
실행 결과: success, error, running
사용 유형: agent, app_builder, evaluation, app_agent
```

이 구조로는 `App Builder 생성이 실패했다`를 동시에 표현할 수 없다. 최소한 아래 필드를 분리해야 한다.

```text
event_type: workflow_execution | workflow_generation | app_generation | evaluation
outcome: success | error | cancelled
trigger_type: editor | api | webhook | scheduler | bot | shared_app
```

### 4.4 빈 상태와 오류 상태

프론트의 `hasData`는 `total_used > 0` 또는 `chart_data.length > 0`이면 참이다. 백엔드는 weekly, monthly, yearly와 hourly 모두 값이 0인 bucket 배열을 생성하므로 정상 응답 뒤에는 빈 상태가 거의 도달 불가능하다.

반대로 요청이 실패하면 `stats`는 `null`로 남고 loading만 끝난다. 결과적으로 네트워크 오류, 500 오류와 실제 무사용 상태가 같은 화면으로 표시된다.

필요한 상태는 다음처럼 명시적으로 분리해야 한다.

```text
idle -> loading -> success(data | empty)
                 -> error(retry 가능)
```

`empty` 판정은 배열 길이가 아니라 선택 기간의 합계, 누적 합계 또는 서버가 제공하는 `has_usage`를 기준으로 해야 한다.

### 4.5 기간과 단위의 의미 불일치

상단 period select는 페이지 전체 필터처럼 보이지만 실제로는 `chart_data`에만 영향을 준다. 다음 항목은 모두 lifetime이다.

- 총 누적 사용량
- 기능별 네 개 카드
- 용도별 비율
- 프로젝트별 토큰 사용량

개선안은 두 가지 중 하나를 명시적으로 선택해야 한다.

1. **권장: 전체 화면을 선택 기간 기준으로 통일**
   - 요약: 선택 기간 사용량과 이전 기간 대비
   - 추이, 유형 비율, 프로젝트 순위: 모두 같은 기간
   - 잔여 balance만 현재 시점 값으로 별도 표기

2. **대안: lifetime과 period 섹션 분리**
   - 상단 `계정 잔액 및 전체 누적`
   - 하단 `선택 기간 분석`

첫 번째 안이 일반적인 분석 화면의 mental model과 더 잘 맞는다.

### 4.6 비용 표시의 정확성

현재 비용 모드는 총 토큰에 고정 평균 단가를 곱한다. 그러나 비용은 provider, model, input/output/cached token과 가격 적용 시점에 따라 달라진다. 로컬 LLM은 API 가격과 같은 방식으로 계산할 수도 없다.

단기에는 반드시 `추정 비용`으로 명명하고 계산 기준을 tooltip에 표시한다. 장기에는 사용 이벤트 저장 시 다음 값을 보존한다.

- provider와 model
- input/output/cached/reasoning token
- 적용한 가격표 version 또는 날짜
- 계산된 `cost_usd_micros`
- `cost_kind`: actual, estimated, local_infrastructure, unavailable

KRW는 저장 통화가 아니라 표시 통화로 다루고 조회 시점 환율과 환율 기준 시간을 함께 표시한다.

## 5. 디자인 감사

### 5.1 유지할 점

- 현재 제품과 맞는 Dark-first 작업 도구 성격
- Blue, Violet, Pink, Green으로 기능 유형을 구분하는 방식
- 요약 → 추이 → 프로젝트 순서의 기본 정보 흐름
- Recharts 기반의 반응형 차트 선택
- token과 cost 표시 설정을 존중하려는 구조

### 5.2 현재 문제

#### 정보 위계

- 서로 비슷한 강조도를 가진 카드가 6개라 중요한 수치를 빠르게 찾기 어렵다.
- 첫 두 카드는 전체 누적, 나머지 네 카드는 유형별 누적이지만 같은 단계에 놓여 있다.
- 모든 숫자가 각기 다른 강한 색이라 의미 색과 장식 색의 경계가 흐리다.
- 프로젝트 Bar chart는 긴 제목과 정확한 값 비교에 불리하다.

#### 레이아웃

- 6개 KPI가 데스크톱에서 4+2로 끝나 하단에 큰 빈 공간이 생긴다.
- 통계 화면에서도 Main Sidebar 옆의 Chat rail이 항상 남아 분석 공간을 줄인다.
- 도넛 패널은 310px, Pie 자체는 210px 고정이다.
- 프로젝트 Y axis는 150px 고정이라 긴 한국어 제목이 잘리거나 차트 영역을 압박한다.
- 모바일 전용 재배치 규칙이 없어 데스크톱 그리드가 축소된다.

#### 상태와 상호작용

- loading은 텍스트 한 줄뿐이고 이전 데이터 유지, skeleton, refresh 상태가 없다.
- 오류 메시지와 재시도 버튼이 없다.
- 마지막 갱신 시간과 timezone을 알 수 없다.
- period select에 연결된 label이 없고, 차트는 tooltip에 의존한다.
- 그래프의 실제 값을 표나 목록으로 확인할 수 없다.

#### 유지보수

- 거의 모든 스타일이 JSX에 있어 media query, theme와 focus state를 체계적으로 적용하기 어렵다.
- `StatisticsPage` 한 파일에 네 개 시각화와 API 상태가 결합되어 있다.
- 평가 아이콘만 emoji를 사용해 Lucide 아이콘 체계와 다르다.
- 카드 데이터의 `accent` 속성은 선언되지만 사용되지 않는다.

## 6. 목표 사용자 경험

통계 화면은 다음 질문에 빠르게 답해야 한다.

1. 선택 기간에 얼마나 사용했는가?
2. 이전 기간보다 늘었는가, 줄었는가?
3. 잔여 token/credit은 얼마인가?
4. 어떤 기능과 프로젝트가 사용량을 만들었는가?
5. 워크플로우가 정상적으로 실행됐는가?
6. 이상 증가나 반복 실패가 있는가?

현재 데이터로는 1~4를 정확하게 만드는 것이 1차 목표다. 5~6은 outcome, 실행 횟수와 latency 집계가 안정된 뒤 `실행 품질` 영역으로 추가한다.

## 7. 목표 화면 구조

### 7.1 데스크톱

```text
[사용 통계] [마지막 갱신 / timezone]       [Token | 비용] [기간 선택]

[기간 사용량 + 증감] [현재 잔여량] [실행 횟수] [성공률]

[기간별 사용 추이........................] [기능별 사용량....]

[프로젝트별 사용량 table........................................]

[실행 품질: 실패 유형 / 느린 실행 / 최근 오류]  <- 2차 범위
```

설계 원칙:

- KPI는 최대 4개만 첫 행에 둔다.
- 기능별 네 수치는 별도 breakdown으로 이동한다.
- 핵심 숫자는 기본 text color를 사용하고 accent는 icon, indicator와 chart series에 제한한다.
- 프로젝트 영역은 세로 Bar chart 대신 정렬 가능한 table과 행 내부 progress bar를 사용한다.
- 표에는 프로젝트명, 사용량, 점유율, 이전 기간 대비, 실행 수를 표시한다.
- Chat rail은 분석/관리 화면에서 숨기고 필요하면 헤더의 AI Assistant 버튼으로 drawer를 연다.

### 7.2 모바일

```text
[메뉴] 사용 통계
[기간 선택........] [Token/비용]

[기간 사용량] [잔여량]
[실행 횟수]   [성공률]

[추이 차트 - 한 열]
[기능별 사용량 - 한 열]
[프로젝트 순위 - compact list]
```

- 360~430px에서는 모든 분석 panel을 한 열로 배치한다.
- KPI만 안정적인 2열을 허용하고 긴 label은 두 줄까지 수용한다.
- Chart panel padding은 16px, 높이는 240~280px로 제한한다.
- Legend는 차트 아래 compact list로 빼고 줄바꿈 규칙을 통제한다.
- 프로젝트명은 2줄 ellipsis와 전체 제목 tooltip을 제공한다.
- 어떤 자식 요소도 viewport보다 큰 고정 폭을 갖지 않는다.

### 7.3 시각 규칙

기존 `Calm Technical Workspace` 방향을 따른다.

| 요소 | 제안 |
| --- | --- |
| Page title | 24/32, 모바일 20/28 |
| KPI 숫자 | 24/32, tabular numerals |
| Panel title | 16/24 |
| 기본 본문 | 14/21 |
| Panel radius | 8px |
| Panel padding | 20~24px, 모바일 16px |
| Grid gap | 16px |
| 강조 | Blue primary, 유형 색은 작은 marker와 series에만 사용 |
| Depth | 얇은 border 중심, shadow 최소화 |

도넛은 전체 비중 파악에는 쓸 수 있지만 정확한 비교가 목적이면 horizontal bars가 더 적합하다. 모바일은 도넛보다 유형별 bar list를 기본으로 사용하고, 데스크톱에서도 legend와 수치가 중복되지 않게 한다.

## 8. 목표 데이터 구조

### 8.1 권장 원장 분리

`FlowExecutionLog` 하나를 계속 확장하기보다 실행 관측과 금액/토큰 원장을 분리한다.

#### UsageEvent

```text
id
request_id                 # idempotency 및 중복 추적
actor_user_id              # 실행자
billable_user_id           # 비용 부담자
project_id / app_id
event_type                 # workflow_execution, workflow_generation 등
trigger_type               # editor, api, webhook, scheduler, bot, shared_app
outcome                    # success, error, cancelled
provider / model
input_tokens / output_tokens / cached_tokens / reasoning_tokens
total_tokens
cost_usd_micros
cost_kind                  # actual, estimated, local, unavailable
occurred_at                # timezone-aware UTC
metadata                   # 제한된 비정규 정보
```

#### CreditLedger

```text
id
user_id
request_id
transaction_type           # grant, debit, refund, admin_adjustment
amount
balance_after
created_at
metadata
```

`User.token_balance`는 빠른 조회용 snapshot으로 유지할 수 있지만, 변경은 CreditLedger 기록과 같은 transaction 안에서 원자적으로 처리한다.

### 8.2 점진적 전환안

대규모 마이그레이션이 부담되면 다음 순서로 진행한다.

1. `FlowExecutionLog`에 `actor_user_id`, `billable_user_id`, `event_type`, `outcome`, `trigger_type`, `request_id`를 추가한다.
2. 모든 로그 작성 경로를 공통 `record_usage()` service로 통합한다.
3. 기존 `user_id`, `status`는 호환을 위해 유지하되 신규 집계에서는 사용하지 않는다.
4. 과거 로그를 best-effort로 backfill하고 `metadata.source = legacy`를 표시한다.
5. 잔액 대사와 중복 방지가 안정되면 별도 UsageEvent/CreditLedger로 분리한다.

기존 데이터는 actor와 billable owner를 완전히 복원할 수 없는 경우가 있으므로 backfill 값에 `inferred` 여부를 남겨야 한다.

## 9. 목표 API

기존 API를 즉시 깨지 말고 `/api/statistics/v2`를 추가해 병행 검증한다.

### 9.1 요청

```text
GET /api/statistics/v2
  ?preset=7d
  &timezone=Asia/Seoul
  &project_id=optional
  &event_type=optional
```

- `preset`: 24h, 7d, 30d, 12m, custom
- custom은 `from`, `to`를 요구한다.
- 허용하지 않은 값은 weekly로 조용히 처리하지 않고 422를 반환한다.
- timezone은 IANA identifier로 검증한다.

### 9.2 응답 예시

```json
{
  "period": {
    "from": "2026-08-21T00:00:00+09:00",
    "to": "2026-08-28T00:00:00+09:00",
    "timezone": "Asia/Seoul",
    "granularity": "day"
  },
  "summary": {
    "period_tokens": 42800,
    "previous_period_tokens": 39100,
    "change_rate": 0.0946,
    "remaining_tokens": 71260,
    "execution_count": 84,
    "success_rate": 0.964
  },
  "series": [],
  "breakdown_by_event_type": [],
  "top_projects": [],
  "cost": {
    "usd_micros": 183200,
    "kind": "estimated",
    "pricing_version": "2026-08-01"
  },
  "meta": {
    "generated_at": "2026-08-27T09:30:00Z",
    "has_usage": true
  }
}
```

### 9.3 집계 구현

- Python `.all()` 반복 대신 DB의 `GROUP BY`, `CASE`, date bucket을 사용한다.
- 프로젝트는 join 한 번으로 제목과 합계를 가져온다.
- 기본 목록은 상위 N개와 `기타`로 제한하고 상세 목록은 pagination한다.
- `(billable_user_id, occurred_at)`, `(billable_user_id, event_type, occurred_at)`, `(project_id, occurred_at)` 복합 index를 검토한다.
- API response schema를 Pydantic으로 고정해 nullable과 숫자 타입을 명확히 한다.
- query count와 실행 계획은 대용량 fixture로 확인한 뒤 cache 도입 여부를 결정한다.

## 10. 프론트엔드 구조 개선

권장 파일 구조:

```text
frontend/src/pages/statistics/
  StatisticsPage.jsx
  StatisticsPage.css
  useStatistics.js
  statisticsFormatters.js
  StatisticsToolbar.jsx
  StatisticsSummary.jsx
  UsageTrendChart.jsx
  UsageBreakdown.jsx
  ProjectUsageTable.jsx
  StatisticsState.jsx
```

역할:

- `useStatistics`: 요청, 취소, retry, stale response 방지, filter state
- `statisticsFormatters`: token, cost, currency, percentage, date label
- `StatisticsState`: skeleton, empty, error 상태
- 각 시각화: server response를 표시하는 presentational component
- `StatisticsPage.css`: 공통 token을 사용하는 desktop/mobile grid

TanStack Query 같은 신규 의존성은 이 페이지 하나만을 위해 바로 추가하지 않는다. 현재 axios 패턴에서 `AbortController`와 request ID로 먼저 해결하고, 여러 데이터 화면이 같은 caching 요구를 가질 때 공통 query layer를 도입한다.

## 11. 구현 단계

### Phase 0. 의미 계약 확정

- `token`, `credit`, `cost`의 제품 용어 정의
- actor와 billable owner 정책 확정
- 공유 앱, API, Webhook, Bot, Scheduler의 비용 부담자 표 작성
- 선택 기간이 적용되는 화면 범위 확정
- 로컬 LLM 사용량과 비용 표시 정책 확정

완료 조건: 동일 요청에 대해 누가 실행했고 누구에게 어떤 단위가 차감되는지 문서로 설명 가능.

### Phase 1. 기록 정확성 복구

- `event_type`과 `outcome` 분리
- `actor_user_id`, `billable_user_id`, `request_id` 추가
- 공통 `record_usage()`와 원자적 잔액 차감 함수 작성
- App Runner, Custom App, 배포 API, Webhook, Scheduler, Bot, Agent, App Builder, Evaluation 경로 전환
- `app_agent` 매핑과 배포 API의 누락된 `project_id` 수정
- Webhook 잔액 정책에 따라 차감 또는 non-billable 명시

완료 조건: 테스트 fixture에서 모든 event의 사용량 합계와 billable user의 debit 합계가 일치.

### Phase 2. 집계 API v2

- timezone-aware 기간 계산
- SQL aggregation과 project join
- 현재/이전 기간 summary
- 명시적인 empty/error metadata
- response schema와 backend test 추가
- v1/v2 결과 차이를 로깅해 migration 오차 확인

완료 조건: 기간별 series, 유형 breakdown과 project 합계가 동일한 period total로 대사됨.

### Phase 3. 화면 상태와 구조 개편

- page 전용 CSS와 component 분리
- loading, empty, error, retry 구현
- period/filter 상태를 URL query에 반영
- 요청 취소와 최신 응답 보장
- KPI 4개와 breakdown 재구성
- 프로젝트 chart를 table/list로 교체

완료 조건: 새로고침과 공유 URL에서 같은 filter가 복원되고, API 오류가 빈 상태로 표시되지 않음.

### Phase 4. 반응형·접근성·시각 정리

- 360~430px 단일 열
- chart legend와 긴 project title 대응
- select label, focus ring, `aria-live`, chart 대체 table 추가
- Light/Dark theme와 숫자 단위 통일
- Chat rail의 관리 화면 노출 정책 정리
- Playwright visual regression 추가

완료 조건: 360, 390, 768, 1024, 1440px에서 가로 overflow와 UI overlap이 없음.

### Phase 5. 운영 통계 확장

- 실행 수, 성공률, p50/p95 latency
- 실패 trigger/node/model breakdown
- 비정상 사용량 증가 감지
- CSV export와 프로젝트 상세 drill-down
- 팀 기능 도입 시 workspace 기준 집계

이 단계는 토큰 집계의 정확성을 확보한 뒤 진행한다.

## 12. 테스트 계획

### 12.1 백엔드

- 각 preset의 시작/종료 경계와 bucket 수
- `Asia/Seoul` 자정과 UTC 날짜가 다른 event
- invalid preset/timezone의 422 응답
- 0건, 1건, 대량 event
- actor와 billable user가 다른 공유 앱 실행
- 익명 공유 앱 실행
- success/error와 event_type의 독립 집계
- App Builder, Agent, Evaluation, App Agent 분류
- Webhook, API, Scheduler, Telegram, Discord의 project 귀속
- 같은 `request_id` 재시도 시 중복 차감 방지
- 충전, debit, refund 후 balance 대사
- 프로젝트 삭제 후 `삭제된 프로젝트` 집계
- query count와 대량 데이터 실행 계획

### 12.2 프론트엔드

- loading, empty, success, 401, 403, 500, timeout 상태
- retry 성공과 이전 오류 제거
- 기간을 빠르게 연속 변경할 때 최신 응답만 표시
- token, USD, KRW 표시와 단위
- 긴 한국어 프로젝트명과 큰 숫자
- 유형이 0개, 1개, 4개 이상인 breakdown
- 360×800, 390×844, 768×1024, 1440×900 렌더링
- Light/Dark theme
- keyboard focus, select label, screen reader summary
- chart 아래 대체 table의 값 일치

## 13. 완료 기준

다음 조건을 모두 만족할 때 `/statistics` 1차 개선을 완료로 본다.

- 한 요청의 token 사용량과 billable user 잔액 차감이 같은 transaction과 `request_id`로 추적된다.
- 기간 summary, series, 유형별 합계와 프로젝트별 합계의 범위가 문서화되고 서로 대사된다.
- 비용이 실제값인지 추정값인지 UI와 API가 명시한다.
- 데이터가 없을 때만 empty state가 표시된다.
- API 오류에는 원인 요약과 retry가 표시된다.
- 선택 기간과 timezone이 화면에 보이고 모든 period 분석에 동일하게 적용된다.
- 390px에서 `scrollWidth <= clientWidth`이고 차트 제목과 legend가 정상적으로 읽힌다.
- 프로젝트 제목이 길어도 축소되거나 다른 UI를 가리지 않는다.
- 통계 endpoint와 주요 UI 상태에 자동화 테스트가 존재한다.
- 기존 v1과 v2의 차이를 확인한 뒤 v1을 제거한다.

## 14. 권장 첫 구현 묶음

첫 작업은 화면 색상 변경보다 아래 묶음으로 시작하는 것이 좋다.

1. 사용량 event 분류표와 billable owner 정책 작성
2. `record_usage()` 공통 함수와 최소 schema migration
3. P0 기록 경로 수정 및 대사 test
4. `/api/statistics/v2`의 7일 조회 구현
5. 프론트의 error/empty 분리와 모바일 1열 수정
6. 결과가 안정되면 KPI와 프로젝트 영역 redesign

이 순서는 가장 위험한 수치 오류를 먼저 막으면서도, 1차 릴리스에서 사용자가 바로 체감할 모바일과 오류 상태 개선까지 포함한다.
