# PICKLE LLM 게이트웨이 연동 (2026-09-05)

지원처가 GPT 키 대신 **PICKLE LLM 게이트웨이**(`https://llm.pcl.kr/v1`)로 지원하게 되면서 채팅/생성
호출을 이 경로로 옮겼다. 이 문서는 게이트웨이의 계약(지원처 안내문 요약)과 **우리 코드가 그 계약을
어떻게 지키는지**, 운영 중 무엇을 확인해야 하는지를 적는다.

## 1. 게이트웨이 계약 (지원처 안내문 요약)

| 항목 | 값 |
| --- | --- |
| base URL | `https://llm.pcl.kr/v1` (OpenAI 호환) |
| 경로 | `POST /v1/chat/completions` **만** 제공 (Responses API·임베딩·이미지 없음) |
| 인증 | `Authorization: Bearer <PICKLE_API_KEY>` |
| 모델 이름 | OpenRouter 모델 id 그대로 — vendor 접두가 붙는다 (`openai/gpt-5.6-luna`). 목록: https://openrouter.ai/models |
| 요청 필드 | 최상위 **17개만** 허용, 목록 밖이 있으면 **400**: `model, messages, stream, stream_options, max_tokens, max_completion_tokens, temperature, top_p, stop, presence_penalty, frequency_penalty, seed, user, response_format, tools, tool_choice, parallel_tool_calls` |
| 스트리밍 | `"stream": true`, 사용량 포함은 `"stream_options": {"include_usage": true}` |
| 도구 호출 | `tools`·`tool_choice` 동작 |
| 한도 | 키별 **금액 한도** 하나. 소진 시 `credit_exhausted` (429) |
| 승인 직후 | `credit_pending` (503) 이 잠시 나올 수 있다 — 재시도 |
| 모델 거절 | `model_not_allowed` → 키 상세의 「쓸 수 있는 유료 모델」 확인 |
| 사용량 | 키 상세 → 사용량 탭 (최근 호출은 늦게 반영될 수 있음) |
| 에러 코드 전체 | https://pickle.pusan.ac.kr/docs |
| 장애 문의 | 실패 응답의 **`X-Request-Id` 헤더** 값을 함께 전달 |

curl 예시(안내문 그대로):

```bash
curl https://llm.pcl.kr/v1/chat/completions \
  -H "Authorization: Bearer $PICKLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "openai/gpt-5.6-luna", "messages": [{"role": "user", "content": "안녕하세요"}]}'
```

## 2. 우리 설정 (`backend/.env`)

게이트웨이는 OpenRouter 모델 id 를 쓰는 OpenAI 호환 API 라 **기존 `openrouter` provider 를 그대로
탄다** — base URL 과 키만 바꾼다. 새 provider 를 만들지 않았다.

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_BASE_URL=https://llm.pcl.kr/v1
PICKLE_API_KEY=<발급 키>            # OPENROUTER_API_KEY 나 LLM_API_KEY 로 줘도 된다(그쪽이 우선)
OPENAI_API_KEY=<OpenAI 키>          # ⚠️ 임베딩·이미지 생성은 여전히 여기로 간다(§4)
```

- 키 우선순위: `LLM_API_KEY` → `OPENROUTER_API_KEY` → `PICKLE_API_KEY` (`llm/providers/config.py`).
- 모델 이름은 우리가 쓰던 이름 그대로 두면 된다 — provider 가 `gpt-5.6-luna → openai/gpt-5.6-luna`
  처럼 vendor 접두를 붙인다(`openrouter_model_id`). 이미 `/` 가 있으면 그대로 보낸다.
- 기본 모델(`LLM_MODEL_*` 미설정 시 `gpt-5.4-mini` / `gpt-5.6-terra` / `gpt-5.6-sol`)과 워크플로우
  노드의 `gpt-4o-mini` 는 각각 `openai/...` 로 나간다. **키에 허용된 모델인지**는 키 상세에서 확인해야
  한다 — `model_not_allowed` 가 나면 그 모델이 목록에 없다는 뜻이다(§5).
- 되돌리기: `LLM_PROVIDER=openai` 로 두고 `OPENROUTER_BASE_URL` 을 비우면 OpenAI 직결로 돌아간다.

## 3. 코드가 지키는 것 — 엄격 모드

`OPENROUTER_BASE_URL` 이 `openrouter.ai` 가 아니면 provider 가 자동으로 **엄격 모드**로 동작한다
(`llm/providers/adapters.py` `is_strict_gateway`). `OPENROUTER_STRICT_FIELDS=1|0` 으로 강제할 수 있다.

| 계약 | 우리 클라이언트(langchain_openai `ChatOpenAI`)가 보내는 것 | 조치 |
| --- | --- | --- |
| 허용 17개 필드 | 기본 요청: `model, messages, stream`. 구조화 출력: `+ response_format`. 스트리밍: `+ stream_options` | 모두 허용 안 |
| ⚠️ `reasoning_effort` | gpt-5/o1/o3 계열에 `reasoning_effort: none` 을 붙여 왔다 → **목록 밖 → 400** | 엄격 모드에서 **보내지 않는다** (모델 기본 reasoning 으로 동작. 공식 OpenRouter 에서는 종전대로 보낸다) |
| chat/completions 만 | langchain 은 `*-pro`·`codex` 모델을 Responses API(`/v1/responses`)로 자동 전환한다 → 404 | 엄격 모드에서 `use_responses_api=False` 고정 |
| `ls_structured_output_format` | 구조화 출력 시 내부 kwargs 에 보이지만 LangSmith 추적용 — langchain_core 가 **전송 전에 제거**한다 | 조치 없음(테스트로 확인) |
| 모델 id | vendor 접두 필요 | `openrouter_model_id` 가 붙인다 |

재발 방지: `backend/test_openrouter.py` — 게이트웨이 주소·`PICKLE_API_KEY` 인식, 여러 모델의 실제
페이로드가 허용 집합(`GATEWAY_ALLOWED_FIELDS`) 안인지, Responses API 로 새지 않는지, 공식 OpenRouter
동작은 그대로인지.

## 4. 게이트웨이로 가지 **않는** 것

게이트웨이는 chat/completions 만 제공한다. 아래는 `LLM_PROVIDER` 와 무관하게 **OpenAI 로 직접** 간다
— `OPENAI_API_KEY` 를 함께 두어야 동작한다.

- **이미지 생성 노드**(`image_generation_runtime`, OpenAI Images/Responses) — 시연 포스터 워크플로우가 쓴다.
- **임베딩**(RAG 컨텍스트 `rag_utils`, 노드 검색 `node_knowledge`).
- Gemini(`GEMINI_API_KEY`)·Anthropic(`ANTHROPIC_API_KEY`) 모델을 직접 지정한 경우는 각자 키로 간다.

## 5. 운영 중 확인할 것 · 에러 대응

| 증상 | 뜻 | 조치 |
| --- | --- | --- |
| `400` + 필드 관련 메시지 | 허용 목록 밖 필드를 보냈다 | 엄격 모드가 꺼졌는지 확인(`OPENROUTER_STRICT_FIELDS`, base URL). 새 필드가 필요하면 지원처에 요청 |
| `model_not_allowed` | 키에 허용되지 않은 모델 | 키 상세 「쓸 수 있는 유료 모델」 확인 후 `LLM_MODEL_*` 또는 노드 모델 변경 |
| `credit_exhausted` (429) | 금액 한도 소진 | 지원처에 한도 증액 요청. 그동안 `LLM_PROVIDER=openai` 로 임시 전환 가능 |
| `credit_pending` (503) | 승인 금액 적용 중 | 잠시 후 재시도 |
| `401` | 키 오류 | `PICKLE_API_KEY` 값·`Bearer` 전송 확인 |
| 특정 요청 실패 문의 | — | 응답 헤더 `X-Request-Id` 를 적어 지원처에 전달 |

빠른 연결 확인(키를 넣은 뒤):

```bash
cd backend && ./venv/Scripts/python -c "
from llm.providers import create_runtime_chat_model
m = create_runtime_chat_model(model='gpt-5.6-luna')
print(m.invoke('안녕하세요, 한 줄로 답해 주세요').content)"
```

## 6-1. 이미지 생성 — 게이트웨이 실측과 지원 요청서 (2026-09-05)

발급 키로 실측한 결과 게이트웨이는 이미지 생성 경로를 열어 두지 않았다:

| 시도 | 결과 |
| --- | --- |
| `POST /v1/images/generations` | 404 `unknown_endpoint` — "지원 범위는 GET /v1/models, POST /v1/chat/completions" |
| `POST /v1/responses` + `image_generation` 도구 (우리 이미지 노드 방식) | 404 `unknown_endpoint` |
| `POST /v1/chat/completions` + `modalities` | 400 `unsupported_parameter` (req_id 046133a5-80e7-4d1a-a83f-4dd6e57f7d93) |

OpenRouter 는 현재 이미지 생성을 **전용 엔드포인트 `POST /api/v1/images`** 로 제공한다(chat/completions
의 `modalities` 방식은 현행 문서에서 사라졌다). 게이트웨이가 이 경로를 그대로 중계해 주면 우리 쪽은
이미지 노드의 호출 경로만 바꾸면 된다. 아래는 지원처에 보낼 요청서 초안이다.

### 지원 요청서 (초안)

> **제목**: PICKLE 게이트웨이 이미지 생성 경로 개방 요청 (OpenRouter `POST /v1/images` 중계)
>
> 안녕하세요. `llm.pcl.kr` 게이트웨이로 채팅 API 는 정상 사용 중입니다(감사합니다). 저희 서비스의
> 포스터 생성 기능이 **이미지 생성**을 쓰는데, 현재 게이트웨이가 아래처럼 거절해 개방을 요청드립니다.
>
> **1. 현재 상태(실측, 2026-09-05)**
> - `POST /v1/images/generations` → 404 `unknown_endpoint`
> - `POST /v1/responses` (image_generation 도구) → 404 `unknown_endpoint`
> - `POST /v1/chat/completions` + `modalities: ["image","text"]` → 400 `unsupported_parameter`
>   (X-Request-Id: `046133a5-80e7-4d1a-a83f-4dd6e57f7d93`)
>
> **2. 요청 사항 — OpenRouter 이미지 API 중계**
> OpenRouter 는 이미지 생성을 전용 엔드포인트로 제공합니다:
> `POST https://openrouter.ai/api/v1/images` (문서: https://openrouter.ai/docs/features/multimodal/image-generation)
> 게이트웨이에서 **`POST /v1/images` 를 같은 계약으로 중계**해 주시길 요청합니다.
>
> (a) 허용이 필요한 요청 필드 — 최상위 10개:
> `model, prompt, resolution ("512"|"1K"|"2K"|"4K"), aspect_ratio ("1:1"|"3:4"|"4:3"|"9:16"|"16:9" 등), quality ("auto"|"low"|"medium"|"high"), output_format ("png"|"jpeg"|"webp"), background ("auto"|"transparent"|"opaque"), n (1~10), stream (bool), input_references (이미지 수정용: [{"type":"image_url","image_url":{"url":"<https 또는 data URL>"}}])`
> 저희가 실제로 보내는 것은 `model, prompt, aspect_ratio, quality, output_format, background, n=1` 이고,
> 수정 기능에만 `input_references` 를 씁니다. `stream` 은 쓰지 않습니다.
>
> (b) 응답은 OpenRouter 원형 그대로 통과되면 됩니다:
> `{"created": ..., "data": [{"b64_json": "<base64>", "media_type": "image/png"}], "usage": {"prompt_tokens", "completion_tokens", "total_tokens", "cost"}}`
> — `data[].b64_json` 은 이미지 한 장에 1~3MB 정도라 **응답 크기 제한과 타임아웃(생성에 10~60초)** 을
> 그에 맞게 잡아 주시면 감사합니다.
>
> (c) 저희 키에 **이미지 출력 모델 1종 이상** 허용을 요청합니다. 후보(OpenRouter 문서 예시):
> `openai/gpt-image-2` (품질 우선) 또는 `google/gemini-2.5-flash-image` (비용 우선). 둘 중 하나만
> 허용되어도 충분하며, 어느 쪽이 가능한지 알려주시면 그 모델로 맞추겠습니다.
>
> (d) 과금: OpenRouter 는 이미지 생성을 건당 정산하고(`usage.cost`, USD) 실패 건은 청구하지 않는다고
> 안내합니다. 게이트웨이의 금액 한도에 이 비용이 어떻게 반영되는지(사용량 탭 표기 포함) 알려주시면
> 시연 예산을 잡는 데 도움이 됩니다. 예상 사용량은 시연 기간(3일) 동안 이미지 100장 이내입니다.
>
> **3. 확인용 호출** (개방 후 저희가 이 요청으로 검증하겠습니다)
> ```bash
> curl https://llm.pcl.kr/v1/images \
>   -H "Authorization: Bearer $PICKLE_API_KEY" -H "Content-Type: application/json" \
>   -d '{"model": "google/gemini-2.5-flash-image", "prompt": "abstract gradient poster background, no text",
>        "aspect_ratio": "3:4", "quality": "low", "output_format": "png", "n": 1}'
> ```
> 기대 응답: HTTP 200, `data[0].b64_json` 에 PNG base64, `usage.cost` 에 비용.
>
> **4. 대안(위가 어려울 경우)**
> 이미지 전용 경로 개방이 어렵다면, `POST /v1/chat/completions` 의 허용 파라미터에 `modalities` 를
> 추가하고 이미지 출력 모델을 허용해 주셔도 저희가 맞출 수 있습니다(응답의
> `choices[0].message.images[].image_url.url` 을 읽습니다). 다만 OpenRouter 현행 문서는 전용 경로를
> 안내하므로 2번이 우선입니다.
>
> 필요한 정보가 더 있으면 말씀해 주세요. 감사합니다.

### 개방되면 우리가 바꿀 것

- `image_generation_runtime`: OpenAI Responses API(`api.openai.com/v1/responses`) 대신 게이트웨이
  `POST {OPENROUTER_BASE_URL}/images` 를 부르는 경로 추가 — 기존 필드(size→aspect_ratio, quality,
  background, output_format) 매핑, `data[0].b64_json` 을 지금과 같은 artifact 로 저장, 수정(edit)은
  `input_references` 에 이전 이미지를 실어 보낸다. `previous_response_id` 기반 이어가기는 이 경로에
  없으므로 참조 이미지 방식으로 대체한다. 예상 작업량: 반나절 + 테스트.
- 선택 규칙: `PICKLE_API_KEY`(게이트웨이)가 있으면 게이트웨이 경로, 없으면 지금처럼 `OPENAI_API_KEY`
  직결 — 두 경로 모두 유지해 OpenAI 크레딧으로도 계속 동작한다.

## 6. 아직 안 한 것

- 게이트웨이 에러 코드(`credit_exhausted` 등)를 실행 로그의 NodeError 코드로 매핑하지 않았다 —
  현재는 원문 메시지가 노드 오류 문구로 그대로 보인다. 필요해지면 `error_catalog.json` 에
  `LLM_*` 코드를 등록하고 `node_errors/adapters.py` 에서 분류한다.
- ~~시연 콘텐츠의 `gpt-4o-mini` 가 키 허용 목록에 있는지 확인~~ → **2026-09-05 실측 확인**: 발급 키로 `gpt-4o-mini`·`gpt-5.4-mini`·`gpt-5.6-terra`·`gpt-5.6-sol`·`gpt-5.6-luna` 모두 200, 구조화 출력(response_format)과 usage 메타데이터도 정상.
