# LLM 생성 품질 및 로컬 전환 개선 계획

## 1. 목적

이 문서는 자연어 요청으로 워크플로우를 생성하고 수정하는 기능의 정확도와 안정성을 높이고, 현재 외부 LLM API 중심 구조를 추후 메인 PC의 로컬 LLM으로 전환하기 위한 실행 계획을 정의한다.

목표는 특정 모델이 한 번에 완벽한 결과를 내도록 만드는 것이 아니다. 다음의 닫힌 품질 루프를 제품의 기본 동작으로 만드는 것이 목표다.

```text
요청 구조화 -> 관련 문맥 선택 -> 워크플로우 생성 -> 결정론적 검증
          -> 제한된 자동 수정 -> dry-run/평가 -> 결과 또는 명확한 실패 보고
```

## 2. 현재 상태

### 잘 갖춰진 기반

- `backend/meta_agent.py`에 `FlowGraph`, `FlowNode`, `FlowEdge` 구조화 출력이 정의되어 있다.
- 노드 카탈로그를 요청별로 줄여 전달하고, 실패하면 전체 카탈로그로 폴백한다.
- `validate_flow()`가 DAG, 필수 필드, 노드 및 엣지 연결, 분기, 병합 등 여러 구조 오류를 검사한다.
- `generate_safely()`가 생성 후 검증하고 오류 사유를 포함해 한 번 재생성한다.
- 에이전트 편집 도구는 변경 전 스냅샷과 검증 실패 시 롤백 방식을 사용한다.
- 프로젝트 문서를 ChromaDB에서 검색해 대화 문맥으로 주입한다.
- Langfuse 연동, 토큰 사용량, 실행 및 노드 로그가 일부 구현되어 있다.
- `backend/evaluator.py`에 골든 데이터 생성, 실행, LLM 판정, 자동 수정 흐름이 있다.

### 우선 해결할 문제

1. LLM 제공자 결합이 여러 파일에 분산되어 있다.
   - `backend/meta_agent.py`
   - `backend/graph.py`
   - `backend/evaluator.py`
   - `backend/main.py`의 대화 제목 생성
   - `backend/node_generators/core_nodes.py`
   - `backend/node_generators/agent_nodes.py`
   - `backend/node_generators/template_nodes.py`

2. `get_llm()`만 교체하면 된다는 주석과 달리, 실행용 코드 생성 경로에는 `ChatOpenAI`, `ChatGoogleGenerativeAI`, `ChatAnthropic`가 직접 들어간다.

3. `backend/evaluation.py`의 벤치마크는 5개 사례와 필수 노드 포함 여부만으로 품질을 판단한다. 또한 현재 비동기 `run_agent_turn()` 호출 및 반환값 계약과 맞지 않으므로 평가 기반선부터 신뢰할 수 있게 고쳐야 한다.

4. 생성 로그에 모델, 프롬프트 버전, 검증 오류, 수정 횟수, 최종 채택 여부가 일관된 형식으로 남지 않는다.

5. LLM 판정만으로 평가하면 생성 모델과 유사한 오류를 공유할 수 있다. 구조 및 실행 가능성은 코드 기반 평가가 먼저여야 한다.

6. 노드 카탈로그와 프롬프트가 큰 단일 문자열에 가까워 변경 영향과 버전 비교가 어렵다.

## 3. 목표 아키텍처

```text
Frontend
  -> Generation API
     -> TaskSpec normalizer
     -> Context selector
     -> Generation orchestrator
        -> ModelProvider
           -> Hosted API adapter
           -> Local LLM adapter
           -> Hybrid router
        -> FlowGraph schema
        -> Deterministic validator
        -> Repair loop
        -> Dry-run evaluator
     -> GenerationTrace store
```

### 제공자 추상화

앱의 나머지 코드는 OpenAI 또는 로컬 서버의 응답 객체를 직접 다루지 않는다. 공통 입력과 결과만 사용한다.

```python
class ModelProvider(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        ...

class GenerationRequest(BaseModel):
    task_type: str
    system_prompt: str
    user_prompt: str
    context: list[dict]
    output_schema: dict | None = None
    model_profile: str = "balanced"

class GenerationResult(BaseModel):
    text: str = ""
    structured_output: dict | None = None
    model: str
    provider: str
    latency_ms: int
    usage: dict = Field(default_factory=dict)
    finish_reason: str | None = None
```

제공자마다 다음 capability를 선언하고, 오케스트레이터가 지원하지 않는 기능을 요구하지 않도록 한다.

- 구조화 출력 지원 수준
- tool calling 지원 여부
- 최대 문맥 길이
- 스트리밍 지원 여부
- 이미지 입력 지원 여부
- 사용량 메타데이터 제공 여부

로컬 서버가 OpenAI 호환 API를 제공하더라도 내부 인터페이스를 별도로 둔다. 서버마다 Chat Completions, structured output, tool calling의 세부 동작이 다를 수 있기 때문이다.

### 생성 단계 분리

한 번의 거대한 프롬프트로 모든 판단과 생성을 처리하지 않는다.

1. `TaskSpec` 생성
   - 사용자 목표
   - 트리거
   - 필요한 입력과 출력
   - 외부 연동
   - 조건, 반복, 승인 요구
   - 명시된 제약과 추정한 항목

2. 관련 노드와 문맥 선택
   - 요청과 관련된 노드 정의만 제공
   - 최신 노드 스키마는 코드 또는 검색 문맥으로 제공
   - 파인튜닝 가중치에 자주 바뀌는 노드 지식을 넣지 않음

3. `FlowGraph` 생성
   - Pydantic 및 JSON Schema로 형식 강제
   - 위치는 현재처럼 코드가 계산

4. 정적 검증
   - 기존 `validate_flow()`를 단일 품질 게이트로 승격
   - 오류마다 안정된 코드와 사람이 읽는 설명을 함께 반환

5. 부분 수정
   - 전체 그래프 재생성보다 실패한 노드, 엣지, 필드만 수정
   - 최대 2~3회로 제한
   - 동일 오류 반복 시 즉시 중단

6. dry-run 및 의미 평가
   - 외부 쓰기 작업은 mock 또는 차단된 sandbox 사용
   - 구조 검사를 통과한 결과에만 의미 평가 수행

## 4. 품질 측정 기준

모델 교체, 프롬프트 수정, 파인튜닝은 동일한 비공개 평가 세트로 비교한다.

| 지표 | 정의 | 초기 목표 |
| --- | --- | --- |
| Schema pass rate | 첫 생성이 `FlowGraph` 스키마를 통과한 비율 | 98% 이상 |
| Structural pass rate | 첫 생성이 `validate_flow()`를 통과한 비율 | 90% 이상 |
| Repair success rate | 첫 검증 실패 후 제한된 수정으로 통과한 비율 | 80% 이상 |
| Intent coverage | 요청의 필수 트리거, 액션, 조건이 반영된 비율 | 평가 세트 기준 90% 이상 |
| Dry-run success rate | 외부 부작용 없이 실행 경로가 완료된 비율 | 85% 이상 |
| User acceptance rate | 큰 수정 없이 사용자가 채택한 비율 | 지속 측정 |
| Edit distance | 생성 후 사용자가 변경한 노드와 엣지 수 | 지속 감소 |
| Latency | 생성 전체 P50/P95 | 사용자 수 확정 후 설정 |
| Cost | 성공한 워크플로우 한 건당 외부 API 비용 | 지속 측정 |
| Local fallback rate | 로컬 생성 후 외부 API로 넘어간 비율 | 안정화 단계에서 지속 감소 |

평가 케이스는 최소 다음 축을 포함한다.

- 단순 선형 워크플로우
- 조건 분기와 병합
- 반복과 중단
- 외부 API 및 webhook
- 파일, PDF, 문서 생성
- 구조화 출력과 JSON 파싱
- 사용자 승인과 결제처럼 고위험 작업
- 모호한 요청과 잘못된 입력
- 기존 그래프의 부분 수정
- 로컬 모델이 긴 노드 카탈로그를 처리하는 상황

학습 데이터와 평가 데이터는 프로젝트 또는 시나리오 단위로 분리해 유사 그래프가 양쪽에 섞이지 않도록 한다.

## 5. 데이터 수집 설계

각 생성 시도에 `GenerationTrace`를 남긴다.

```text
trace_id
user_request
normalized_task_spec
retrieved_context_refs
provider / model / quantization
prompt_version / schema_version / catalog_version
initial_graph
validation_errors
repair_attempts
final_graph
dry_run_result
latency / usage / cost
user_accepted
user_edits
failure_category
```

수집 원칙:

- API 키, 토큰, 개인정보, 업로드 문서 원문은 저장 전에 제거하거나 별도 보안 저장소로 분리한다.
- 최초 출력이 아니라 validator를 통과하고 사용자에게 채택된 최종 결과를 학습 정답으로 사용한다.
- 검증 실패 그래프와 최종 수정 그래프의 쌍은 repair 모델 학습 데이터로 보존한다.
- 프롬프트, 스키마, 노드 카탈로그 버전을 함께 저장해 회귀 원인을 추적한다.
- 사용자가 명시적으로 거부한 결과도 선호 학습 후보로 표시한다.

## 6. 로컬 LLM 전환 계획

### 대상 하드웨어

- GPU: NVIDIA RTX 5070 Ti, VRAM 16GB
- 시스템 RAM: DDR5 32GB 예상
- 권장 여유 구성: 가능하면 시스템 RAM 64GB

### 현실적인 모델 범위

- 주력 생성 모델: 12~14B급 instruction 또는 coder 모델의 4비트 양자화
- 요청 분류 및 필드 추출: 7~8B급 모델
- 20B 이상: 문맥과 KV cache 때문에 제한적으로만 검토
- 30B 이상: CPU 오프로딩으로 실행은 가능할 수 있으나 주력 서비스 경로로 사용하지 않음

실제 모델 이름은 전환 시점에 고정한다. 후보 모델을 평가 세트로 비교하고 구조화 출력 성공률, 수정 성공률, 지연시간, VRAM 사용량을 기준으로 선택한다.

### 단계적 전환

1. 개발 환경에서 로컬 서버를 OpenAI 호환 endpoint로 연결한다.
2. API 모델과 로컬 모델을 같은 평가 세트로 비교한다.
3. 로컬 모델이 초안을 만들고 validator 및 로컬 repair를 수행한다.
4. 반복 실패, 고위험 작업, 복잡한 요청만 외부 API로 폴백한다.
5. 품질 기준을 충족하면 로컬 모델을 기본 경로로 전환한다.
6. API는 비상 폴백 및 교사 데이터 생성 용도로 제한한다.

개발 및 단일 사용자 실험은 Ollama 또는 llama.cpp 계열로 시작할 수 있다. 동시 사용자와 처리량 요구가 확정되면 batching과 KV cache 관리가 강한 서버를 별도로 비교한다.

## 7. 파인튜닝 계획

### 시작 조건

다음 조건을 모두 충족한 후 실제 파인튜닝을 시작한다.

- 신뢰할 수 있는 평가 파이프라인이 있다.
- 베이스 로컬 모델의 점수가 기록되어 있다.
- 프롬프트와 RAG만 적용한 기준선이 있다.
- 검수되거나 채택된 생성 데이터가 충분히 쌓였다.
- 반복되는 실패 유형이 명확하다.

### 학습 범위

우선 QLoRA 기반 SFT를 사용한다.

- 7~8B: 기본 실험 및 빠른 반복
- 12~14B: 최종 주력 후보, 배치 1과 gradient accumulation부터 시작
- 4-bit NF4, gradient checkpointing, 2K~4K 문맥에서 기준선 측정
- LoRA rank는 8~16에서 시작해 평가 결과로 조정
- 전체 가중치 파인튜닝은 대상에서 제외

SFT가 해결할 대상:

- 사용자 표현을 `TaskSpec`으로 변환하는 방식
- 서비스 고유 노드 조합 패턴
- 안정적인 `FlowGraph` 형식
- validator 오류를 보고 부분 수정하는 방식

SFT로 해결하지 않을 대상:

- 자주 바뀌는 노드 목록과 API 문서
- 사용자별 데이터와 인증 정보
- 구조 검증 및 실행 안전 정책

선호 데이터가 충분해진 후에만 DPO 계열 학습을 검토한다. 파인튜닝 후에도 validator와 dry-run은 제거하지 않는다.

## 8. 단계별 실행 계획

### Phase 0. 기준선 복구

- `backend/evaluation.py`의 비동기 호출 및 반환값 계약 수정
- 5개 테스트를 최소 30개 대표 시나리오로 확장
- 노드 포함 여부 외에 엣지, 필수 데이터, 분기 핸들, 실행 가능성 평가 추가
- 현재 API 모델의 품질, 지연시간, 토큰 비용 기록

완료 조건: 같은 commit과 설정에서 평가를 반복 실행할 수 있고 결과가 저장된다.

### Phase 1. 제공자 추상화

- `backend/llm/providers/` 모듈 추가
- `ModelProvider`, `GenerationRequest`, `GenerationResult` 정의
- 생성, 실행, 평가, 제목 생성에 흩어진 직접 모델 호출을 adapter 뒤로 이동
- 환경변수로 provider, endpoint, model profile을 선택
- 제공자 capability 검사와 명확한 오류 메시지 추가

완료 조건: 비즈니스 로직 변경 없이 hosted provider와 mock provider를 교체할 수 있다.

### Phase 2. 생성 및 수정 품질 루프

- `TaskSpec` 구조화 단계 도입
- validator 오류 코드 표준화
- 전체 재생성 대신 부분 repair 적용
- 최대 시도 횟수, 동일 오류 중단, timeout 설정
- 외부 쓰기 차단 dry-run 구현

완료 조건: 모든 결과가 `통과`, `수정 후 통과`, `설명 가능한 실패` 중 하나로 끝난다.

### Phase 3. 관측성과 데이터 축적

- `GenerationTrace` 저장 구조 추가
- prompt, catalog, schema 버전 관리
- 사용자 채택 및 수정량 기록
- Langfuse trace와 내부 실행 로그를 `trace_id`로 연결
- 민감 정보 제거 정책 적용

완료 조건: 실패 한 건을 모델, 프롬프트, 검증 오류, 사용자 수정까지 역추적할 수 있다.

### Phase 4. RTX 5070 Ti 로컬 PoC

- 7~8B 및 12~14B 4비트 후보 비교
- 모델별 구조화 출력, VRAM, 지연시간, 긴 문맥 성능 측정
- `LocalProvider` 및 health check 구현
- 로컬 우선, API fallback 라우터 구현

완료 조건: 12~14B 후보가 합의한 품질 기준을 만족하거나 부족한 지표가 명확히 기록된다.

### Phase 5. QLoRA 파인튜닝

- 채택된 최종 그래프로 SFT 데이터셋 생성
- 실패 그래프와 수정 그래프로 repair 데이터셋 생성
- train, validation, hidden test 분리
- 베이스, prompt/RAG, fine-tuned 모델을 동일 조건으로 비교
- adapter와 데이터셋 버전 및 재현 설정 저장

완료 조건: 비공개 평가 세트에서 통계적으로 의미 있는 개선이 있고 주요 회귀가 없다.

### Phase 6. 점진적 운영 전환

- 내부 사용자 또는 일부 요청만 로컬 경로로 전송
- fallback rate, 오류율, P95 지연시간 모니터링
- 고위험 노드는 API 또는 사용자 승인 경로 유지
- 품질 기준 충족 시 로컬 기본 비율을 점진적으로 확대

완료 조건: 외부 API 장애 시에도 핵심 생성 기능이 동작하고, 품질 저하가 허용 범위 안에 있다.

## 9. 우선순위 백로그

### P0

- 평가 실행 계약 수정 및 기준선 확보
- 제공자 직접 호출 위치 목록화와 adapter 설계
- validator 오류 코드 도입
- 생성 trace 최소 스키마 정의

### P1

- `TaskSpec` 및 부분 repair loop
- 30개 이상 평가 사례와 회귀 테스트
- dry-run sandbox
- 사용자 채택 및 수정량 수집

### P2

- 로컬 7~8B, 12~14B 모델 비교
- hybrid routing
- QLoRA 데이터 정제 및 첫 학습
- 운영 대시보드와 fallback 정책

## 10. 주요 의사결정

- 프롬프트 개선보다 평가와 validator를 먼저 만든다.
- 특정 API SDK를 핵심 도메인 로직에서 직접 사용하지 않는다.
- 로컬 전환과 파인튜닝을 동시에 시작하지 않는다. 베이스 모델 기준선을 먼저 측정한다.
- 변하는 지식은 RAG로, 반복되는 행동 패턴은 파인튜닝으로 해결한다.
- LLM 판정은 결정론적 검증을 대체하지 않는다.
- 파인튜닝 후에도 구조 검증, dry-run, 실패 제한을 유지한다.
- 초기 운영은 로컬과 외부 API를 함께 쓰는 하이브리드 방식으로 전환 위험을 낮춘다.

## 11. 다음 작업

Phase 2의 구조 및 의미 repair를 안정화한 뒤 Phase 3의 `GenerationTrace` 저장으로 이동한다. 일상 개발에서는 Mock 회귀 테스트와 영향 사례 targeted 평가만 사용하고, 30개 전체 평가는 주요 마일스톤에서 명시적으로 실행한다.

## 12. 구현 진행 상황

### 2026-08-14: Phase 0 및 Phase 1

- [x] `run_agent_turn()`의 비동기 호출과 4개 반환값 계약 반영
- [x] 대표 시나리오 5개를 30개로 확장
- [x] 스키마, 필수 노드, 경로, 필수 데이터, 분기 핸들, validator, 생성 코드 컴파일 평가 추가
- [x] SSE 형식 수정 및 실행 결과 JSON 저장
- [x] hosted OpenAI, OpenAI-compatible local, Google, Anthropic, mock provider adapter 추가
- [x] 생성, 실행, 평가, 제목 생성의 직접 SDK 호출을 provider 모듈 뒤로 이동
- [x] 모델 profile과 provider capability 환경 설정 추가

첫 전체 기준선(`generation-baseline-v2`, run `20260814T082436Z-f428d63b`):

| 지표 | 결과 |
| --- | ---: |
| 전체 통과 | 6 / 30 |
| 평균 점수 | 48.2 |
| Schema pass rate | 100.0% |
| Structural pass rate | 33.3% |
| Compile pass rate | 40.0% |
| Intent coverage | 53.2% |
| 평균 지연시간 | 7.04초 |
| 총 토큰 | 424,839 |

런타임 예외는 없었으며, 18개 실패는 메타 에이전트가 필수 정보를 되묻고 그래프를 생성하지 않은 경우였다. 따라서 Phase 2의 첫 작업은 질문이 필요한 요청과 placeholder 및 합리적 기본값으로 즉시 생성할 요청을 구조적으로 구분하는 `TaskSpec` 도입이다.

### 2026-08-14: Phase 2 첫 구현

- [x] `TaskSpec` 구조화 단계와 `task-spec-v1` prompt 추가
- [x] 설정값, 자격증명, 실행 시 입력값은 placeholder/dynamic input으로 처리하는 clarification 정책 추가
- [x] 실제 routing 선택 및 위험 결정만 구조화된 확인 질문 허용
- [x] RAG 검색과 TaskSpec 정규화를 병렬 실행하고 사용량 및 지연시간 기록
- [x] 새 그래프의 최종 완전성 검증과 도달 불가능 노드/죽은 엣지의 결정론적 repair 추가
- [x] 상위 에이전트의 후속 편집이 그래프를 망가뜨릴 때 마지막 검증 통과 그래프로 복원
- [x] 생성 재시도 최대 3회 및 생성 도구 전체 75초 timeout 추가
- [x] 평가 요청의 일시적 429 rate limit 재시도 추가
- [x] 모호한 요청의 구조화된 clarification을 올바른 평가 결과로 분리

동일 30개 사례의 첫 `task-spec-v1` 비교 실행(run `20260814T083927Z-75553f55`) 결과:

| 지표 | Phase 0 기준선 | TaskSpec 첫 실행 |
| --- | ---: | ---: |
| 전체 통과 | 6 / 30 | 17 / 30 |
| 평균 점수 | 48.2 | 76.2 |
| Structural pass rate | 33.3% | 69.0% |
| Compile pass rate | 40.0% | 79.3% |
| Intent coverage | 53.2% | 76.8% |

이 실행에서는 3건이 API TPM rate limit으로 실패했다. 재시도 정책 추가 후 해당 유형을 포함한 실패 대표 사례 8건을 다시 실행한 결과 런타임 오류 없이 평균 85.0점, 구조화 출력 100%, 컴파일 100%를 기록했다. 남은 작업은 validator 오류 코드 표준화와 일반화 가능한 의미 repair 확장이다.

### 2026-08-14: Phase 2 repair 및 평가 비용 제어

- [x] validator 메시지를 안정적인 오류 코드와 구조화된 `ValidationIssue`로 변환
- [x] 전체 재생성 대신 제한된 `FlowRepairPlan` 부분 수정 적용
- [x] 동일 오류 반복 중단, 부분 수정 횟수 및 시간 제한 적용
- [x] webhook, API, JSON, 문서 서식, 반복, 분배, 조건 병합의 TaskSpec 의미 커버리지 검사 추가
- [x] 실행 입력, 연동 노드, 트리거, 문서 파이프라인의 결정론적 최소 repair 추가
- [x] bounded loop back-edge와 distributor done 경로를 실제 실행 계약에 맞게 검증
- [x] 상위 agent가 즉시 생성 결정을 놓친 경우 직접 생성 fallback 추가

첫 전체 `generation-repair-v1` 실행은 22/30 통과, 평균 90.4점, 의미 커버리지 90.2%를 기록했지만 총 465,190토큰을 사용했다. 이후 수정 과정에서 전체 평가 반복 비용이 지나치게 커지는 문제가 확인되어 다음 비용 정책을 코드로 강제했다.

| 평가 방식 | 기본 범위 | API 토큰 정책 |
| --- | ---: | --- |
| 로컬 회귀 | Mock 기반 전체 단위 테스트 | API 토큰 0 |
| smoke | 대표 사례 1, 6, 28 | 기본 평가 프로필 |
| targeted | 변경 영향 사례 | 한 번에 최대 5개 |
| full | 전체 30개 | `profile=full`을 명시한 경우만 허용 |

- 기본 평가 토큰 예산은 60,000이며 다음 사례의 예상 사용량을 더하면 초과할 때 자동 중단한다.
- 전체 평가도 기본 500,000토큰 상한을 갖는다.
- 같은 평가 버전, 소스 지문, provider, model, prompt의 통과 결과는 캐시하며 재사용 시 API 토큰을 집계하지 않는다.
- 실패 결과는 캐시하지 않아 수정 후 다시 평가할 수 있다.
- 평가 화면은 대표 3개만 기본 선택하며, 전체 평가는 별도 모드와 확인 절차를 요구한다.
- 전체 30개 실행은 릴리스 후보, 모델 변경, prompt/schema 버전 변경 같은 주요 마일스톤에서만 수행한다.

### 2026-08-14: Phase 3 GenerationTrace 최소 구현

- [x] 요청마다 UUID `trace_id`를 생성하고 API 응답에 포함
- [x] provider, model profile/name, TaskSpec/repair prompt 버전 기록
- [x] outcome, validator issue code, repair note, 토큰, 지연시간 기록
- [x] 최종 그래프는 노드 데이터 없이 노드 타입별 개수와 엣지 개수만 저장
- [x] 성공, 설명 가능한 실패, 예외, 사용자 취소를 같은 trace 스키마로 저장
- [x] Langfuse 호출 metadata에 내부 `generation_trace_id` 연결
- [x] 프로젝트 소유자용 `GET /api/projects/{project_id}/generation-traces` 조회 API 추가
- [x] `generation-trace-v1` 스키마와 로컬 DB 저장 테스트 추가

민감 정보 정책:

- 기본값 `GENERATION_TRACE_STORE_CONTENT=false`에서는 프롬프트 원문과 TaskSpec 내용을 저장하지 않는다.
- 대신 요청 SHA-256, 글자 수, 그래프 구조 요약을 저장한다.
- 원문 저장을 명시적으로 켜도 API key, bearer token, password, email을 마스킹하고 길이를 제한한다.
- 노드 `data`와 credential 값은 trace에 저장하지 않는다.

### 2026-08-14: Phase 3 채택 및 수정량 추적

- [x] 생성 그래프의 노드 데이터는 저장하지 않고 HMAC 지문과 내부 비교 서명만 저장
- [x] 위치와 UI 상태를 제외해 자동 정렬을 사용자 수정으로 잘못 집계하지 않도록 처리
- [x] 프로젝트 생성 및 저장 요청에 `generation_trace_id` 연결
- [x] 저장 그래프와 생성 그래프를 `accepted`, `partially_modified`, `discarded`로 분류
- [x] 추가, 삭제, 수정된 노드와 추가, 삭제된 엣지 수 및 수정 비율 기록
- [x] 일반 대화 trace가 생성 채택으로 집계되지 않도록 `graph` outcome만 연결
- [x] 조회 API에서는 비교용 내부 서명을 제거하고 채택 상태와 수정 지표만 반환

`GENERATION_TRACE_HASH_SALT`는 운영 환경에서 별도의 긴 난수로 설정한다. 지표가 없는 trace는 사용자가 아직 저장하지 않았거나 생성 결과가 아닌 경우이며, 이를 폐기로 추정하지 않는다. 이 데이터는 Phase 5에서 그대로 채택되었거나 적은 수정으로 채택된 결과를 우선 선별하는 품질 신호로 사용한다.

다음 구현 단위는 dry-run sandbox다. 컴파일 성공만으로 잡히지 않는 노드 실행 오류를 외부 부작용 없이 검출하고, 실패 노드와 오류 코드를 GenerationTrace 및 평가 결과에 연결한다.

### 2026-08-14: Phase 2 dry-run sandbox

- [x] validator와 생성 Python의 AST 및 bytecode 컴파일을 함께 검사
- [x] 시작 노드부터 도달 가능한 모든 실행 경로와 등록되지 않은 노드 검사
- [x] 네트워크, 메시지 발송, 데이터 저장, 파일 쓰기, 사용자 Python 실행 차단
- [x] 차단된 부작용과 고위험 노드를 실패가 아닌 별도 실행 단계로 기록
- [x] GenerationTrace에 `dry-run-v1` 결과 연결
- [x] 평가 결과와 요약에 `dry_run_passed`, `dry_run_pass_rate` 추가
- [x] 인증 사용자용 `POST /api/dry-run` 추가

### 2026-08-14: Phase 4 로컬 PoC 실행 기반

- [x] OpenAI-compatible 로컬 `/models` health check 및 모델 노출 확인
- [x] 로컬 전용 모델 profile과 endpoint 설정 분리
- [x] tool calling 및 structured output 래핑 이후에도 동작하는 local-first fallback 라우터
- [x] 요청 문자열 해시 기반의 안정적인 로컬 트래픽 비율 적용
- [x] 고위험 요청 hosted 강제 정책과 fallback 지표 수집
- [x] 동일 평가 세트로 여러 로컬 모델을 비교하는 `local_benchmark.py` 추가
- [ ] RTX 5070 Ti에서 실제 7~8B 및 12~14B 후보 실행과 결과 기록

실제 GPU 벤치마크는 메인 PC의 로컬 endpoint와 모델 파일이 필요하다. 코드 구현 완료와 모델 품질 기준 충족을 구분하며, 실행 전까지 Phase 4의 하드웨어 완료 조건은 미충족으로 둔다.

### 2026-08-14: Phase 5 QLoRA 파이프라인

- [x] 서버 수집 switch와 사용자별 명시적 동의의 이중 gate
- [x] 자격증명, 토큰, 이메일, UI 상태를 제거한 학습 후보 저장
- [x] 실제 저장 그래프와 채택·수정량을 학습 후보에 연결
- [x] 큰 수정 사례 제외 및 프로젝트 단위 train/validation/hidden test 분리
- [x] 생성 SFT와 부분 repair JSONL 데이터셋 exporter
- [x] 4-bit NF4, gradient checkpointing, batch 1 기반 7B/14B QLoRA 설정
- [x] adapter, prompt, schema, dataset 버전 재현 metadata 저장
- [x] 외부 API 없이 재현 가능한 `synthetic-v1` 500개 생성기 추가
- [x] 생성 300개와 repair 150개 최종 그래프의 validator 및 dry-run 전수 통과
- [x] clarification 50개, 도메인 그룹 split, 평가 문장 누수·중복·민감정보 검사
- [x] 합성 데이터 혼합 학습용 7B/14B QLoRA 설정과 생성 회귀 테스트
- [ ] 충분한 동의·채택 데이터 확보 후 실제 학습 및 hidden test 비교

### 2026-08-14: Phase 6 점진적 운영 전환 기반

- [x] `provider`, `local`, `hybrid` 라우팅 모드
- [x] 환경변수 기반 0~100% 로컬 rollout
- [x] 로컬 실패 시 hosted fallback과 이중 실패 전파
- [x] 고위험 요청 hosted 우선 정책
- [x] fallback rate, 성공률, P50/P95 지연시간 runtime 집계
- [x] trace 기반 채택률, dry-run 성공률, 오류 코드, 학습 후보 수 집계
- [x] 어드민 LLM 운영 대시보드와 health endpoint
- [ ] 실제 메인 PC 로컬 서버에서 10% → 25% → 50% → 100% 운영 검증

메인 PC 실행 절차와 명령은 `Documents/LOCAL_LLM_RUNBOOK.md`에 정리했다. 현재 서버에서 외부 API를 호출하는 전체 평가는 실행하지 않으며, Mock 회귀 테스트로 코드 계약을 검증한다.
