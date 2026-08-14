# 로컬 LLM 전환 및 QLoRA 실행 가이드

이 문서는 메인 PC의 RTX 5070 Ti 16GB와 시스템 RAM 32GB 환경에서 로컬 모델 비교, 데이터셋 생성, QLoRA 학습, 점진 배포를 같은 절차로 반복하기 위한 실행 가이드다.

## 1. 로컬 서버 연결

Ollama, llama.cpp 또는 다른 서버에서 OpenAI 호환 `/v1` endpoint를 실행한 뒤 `backend/.env`에 다음 값을 설정한다.

```dotenv
LLM_ROUTING_MODE=local
LLM_LOCAL_BASE_URL=http://127.0.0.1:11434/v1
LLM_LOCAL_API_KEY=
LLM_LOCAL_MODEL_FAST=<7B 또는 8B 모델 ID>
LLM_LOCAL_MODEL_BALANCED=<12B 또는 14B 모델 ID>
LLM_LOCAL_MODEL_QUALITY=<12B 또는 14B 모델 ID>
```

서버 재시작 후 어드민 패널의 `LLM Operations`에서 `Local ready`와 모델 노출 여부를 확인한다. API로는 `GET /api/admin/llm-health`를 사용한다.

## 2. 후보 모델 비교

먼저 비용이 작은 smoke 3건으로 연결과 구조화 출력을 확인한다.

```bash
cd backend
./venv/bin/python local_benchmark.py \
  --base-url http://127.0.0.1:11434/v1 \
  --models <7B_MODEL_ID> <14B_MODEL_ID> \
  --profile smoke
```

smoke를 통과한 후보만 전체 30개 평가로 비교한다.

```bash
./venv/bin/python local_benchmark.py \
  --base-url http://127.0.0.1:11434/v1 \
  --models <CANDIDATE_MODEL_ID> \
  --profile full \
  --output evaluation_results/local-model-full.json
```

비교 기준은 schema, structural, intent coverage, dry-run, P95 지연시간, GPU 메모리다. 결과 파일에는 모델별 평가 요약과 `nvidia-smi` 메모리 표본이 함께 저장된다.

## 3. 학습 데이터 수집

### API 없이 합성 데이터로 시작

현재 노드 계약을 바탕으로 500개 합성 데이터를 로컬에서 생성할 수 있다. 이 명령은 `.env`의 API 키나 외부 LLM을 사용하지 않는다.

```bash
cd backend
./venv/bin/python -m training.generate_synthetic
```

기본 출력은 `training/datasets/synthetic-v1/`이다. 생성 SFT 300개, validator 오류 repair 150개, 실제 생성 전에 질문해야 하는 clarification 50개가 도메인 단위로 train 80%, validation 10%, hidden test 10%에 분리된다. 생성 과정에서 최종 그래프 450개를 `FlowGraph`, `validate_flow()`, `dry_run_workflow()`로 전수 검사하고, 중복 ID·평가 프롬프트 누수·민감정보 패턴·split 누수를 함께 확인한다. 결과는 `manifest.json`과 `validation-report.json`에서 확인한다.

합성 데이터는 초기 출력 형식과 repair 행동을 학습하는 부트스트랩 용도다. 실제 사용자 요청의 표현과 선택 분포를 대체하지 않으므로, 아래의 동의·채택 데이터가 쌓이면 함께 사용하고 최종 품질 판단은 별도 hidden test로 한다.

### 동의·채택 데이터 수집

서버와 사용자 양쪽에서 동의한 요청만 후보로 저장된다.

```dotenv
LLM_TRAINING_DATA_COLLECTION_ENABLED=true
```

사용자는 설정의 `데이터` 탭에서 `품질 개선 데이터 제공`을 켠다. 자격증명, 토큰, 이메일과 UI 전용 필드는 저장 전에 제거된다. 생성 결과를 실제 프로젝트로 저장한 경우에만 최종 학습 정답이 생긴다.

데이터셋은 다음 명령으로 만든다.

```bash
cd backend
./venv/bin/python -m training.export_dataset
```

동일 프로젝트의 사례는 항상 같은 split으로 이동한다. 기본 분리는 train 80%, validation 10%, hidden test 10%이며, 수정 비율이 35%를 넘는 사례는 자동 제외한다.

## 4. QLoRA 학습

학습 전용 가상환경에 선택 의존성을 설치한다.

```bash
pip install -r training/requirements-qlora.txt
```

예제 설정을 복제한 뒤 `QLORA_BASE_MODEL`로 베이스 모델을 지정한다. 14B 설정은 16GB VRAM을 고려해 2K 문맥, rank 8, batch 1을 사용한다.

```bash
export QLORA_BASE_MODEL=<BASE_MODEL_ID>
python -m training.train_qlora --config training/qlora-14b.example.json --check
python -m training.train_qlora --config training/qlora-14b.example.json
```

합성 데이터 500개를 모두 섞어 첫 adapter를 학습할 때는 다음 설정을 사용한다.

```bash
export QLORA_BASE_MODEL=<BASE_MODEL_ID>
python -m training.train_qlora --config training/qlora-synthetic-7b.example.json --check
python -m training.train_qlora --config training/qlora-synthetic-7b.example.json
```

14B 후보는 파일명만 `qlora-synthetic-14b.example.json`으로 바꾼다. `generation-test.jsonl`, `repair-test.jsonl`, `clarification-test.jsonl`은 학습 입력에 넣지 않고 최종 비교에만 사용한다.

학습된 adapter를 로컬 서버에 연결하고 Phase 0과 동일한 hidden test를 다시 실행한다. 베이스 모델보다 구조 및 dry-run 성공률이 개선되고 주요 범주의 회귀가 없을 때만 배포 후보로 승격한다.

## 5. 점진 배포

초기에는 hosted provider를 fallback으로 유지한다.

```dotenv
LLM_ROUTING_MODE=hybrid
LLM_LOCAL_TRAFFIC_PERCENT=10
LLM_FALLBACK_PROVIDER=openai
LLM_HIGH_RISK_FORCE_HOSTED=true
```

10%에서 시작해 25%, 50%, 100% 순서로 올린다. 각 단계에서 어드민 패널의 fallback rate, generation success, dry-run pass, user acceptance, P95를 확인한다. 결제, 송금, 삭제, 외부 게시처럼 고위험 키워드가 포함된 요청은 기본적으로 hosted 경로를 사용한다.

외부 API 크레딧이 없으면 hybrid fallback도 실패하므로, 완전 오프라인 운용 시에는 `LLM_ROUTING_MODE=local`로 설정하고 실패를 사용자에게 명확히 반환한다.
