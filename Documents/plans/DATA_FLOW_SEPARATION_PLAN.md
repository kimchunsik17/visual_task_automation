# 데이터 흐름 분리(필드 바인딩) 계획 — 실행 흐름과 데이터 흐름의 이원화

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 상태 | v1.5 — **Phase 0~3 완료 + 안정화 1차**(2026-08-31). ADR-0026 으로 기록. 남은 것: path 환각 실측, 문서 노드 선택 2/3→3/3 (둘 다 생성 반복 측정 필요) |
| 작성일 | 2026-08-31 |
| 대상 | 실행 엔진(graph.py 코드젠), 노드 정의 체계, Workflow Editor 캔버스, LLM 생성 |
| 목표 | 노드 "내부 필드"끼리 값을 직접 잇는 데이터 바인딩을 도입해, LLM 을 데이터 성형기로 쓰는 관행(환각·토큰 비용·비결정성)을 줄인다 |
| 핵심 결정 | **하이브리드**: 실행 엣지는 유지(순서·제어·기본 payload·후방 호환), 필드 단위 바인딩을 두 번째 계약으로 추가. 정본은 선이 아니라 `data.bindings` |
| 관련 문서 | `../ADR.md` ADR-0017(databaseNode parameters — 개념 선례)·0025(채널 분리 — 이 계획의 전 단계), `DOCUMENT_FORMAT_STUDIO_PLAN.md`(1급 소비자) |

## 1. 결론

현재 노드 간 값은 실행 엣지를 따라 흐르는 **문자열 하나**다. 하류 노드가 상류의 특정 값
(웹훅 payload 의 `order.name`, DB 조회의 첫 행)을 쓰려면 jsonParser 를 끼우거나 llmNode 에게
"이 형태로 다시 써줘"라고 시켜야 한다 — 후자가 환각·토큰 비용의 주범이다.

**필드 바인딩**을 도입한다: 노드의 입력 필드가 상류 노드 출력의 특정 경로를 직접 가리킨다.

```jsonc
// emailNode 의 data — toEmail 은 웹훅 payload 에서, subject 는 LLM 요약에서
{
  "toEmail":  "",                       // 값이 아니라 바인딩이 채운다
  "subject":  "",
  "bindings": {
    "toEmail": { "source": "n_webhook", "path": "customer.email" },
    "subject": { "source": "n_llm",     "path": "title" }
  }
}
```

- 실행 엣지는 그대로 — **실행 순서·분기·반복·기본 payload** 를 계속 담당한다. 바인딩이 없는
  기존 그래프는 한 글자도 안 바뀌고 동일하게 동작한다.
- 바인딩의 정본은 엣지가 아니라 **노드 data** 다. 캔버스에 선을 상시 그리지 않는다(§5).
- 이 계약의 원형은 이미 저장소에 있다: **databaseNode.parameters 의
  `{source: "직전 노드 출력", path: "JSON 경로"}`** (ADR-0017). 이것을 "직전 노드"에서
  "실행 경로상 임의 상류 노드"로, databaseNode 에서 전 노드로 일반화하는 것이다.

### 전면 포트 그래프(실행 엣지 폐지)를 하지 않는 이유

1. **순서 모호성** — 데이터 그래프만으로는 부수효과(발송 2건의 순서, 승인 게이트의 위치)가
   정의되지 않는다. Unreal Blueprint 가 데이터 핀과 별도로 exec 핀을 유지하는 이유와 같다.
2. **개편 폭발** — 실행 엔진은 문자열 릴레이 기반 코드 생성기다. 전면 전환은 생성기 50여 곳,
   LLM 생성 스키마, 공식 템플릿 242종, 정화·dry_run·평가의 동시 재작성이다.
3. **후방 호환** — 기존 그래프·템플릿·튜토리얼이 전부 유효해야 한다.

### LLM 의존이 실제로 줄어드는 지점

| 지금 | 바인딩 후 |
| --- | --- |
| 웹훅 payload → jsonParser(extract) ×N | 필드가 payload 경로를 직접 바인딩 |
| LLM 에게 "위 JSON 에서 email 만 골라 …" | LLM 호출 없음 (결정적) |
| formatNode 빈칸을 llmNode Structured Output 으로 | 정형 데이터는 바인딩, **비정형 해석만 LLM** |
| conditionNode 앞 jsonParser 사슬 | conditionNode 비교값 필드도 바인딩 대상 |

LLM 의 역할이 "성형기"에서 "비정형 → 정형 해석기"로 좁아진다. 완전 제거가 아니라 **필요한
곳에만** 남기는 것이 목표다.

## 2. 이미 있는 기반 (새로 만들지 말 것)

| 기반 | 위치 | 이 계획에서의 역할 |
| --- | --- | --- |
| `{source, path}` 파라미터 계약 | databaseNode.parameters (ADR-0017) | BindingSpec 의 원형. 문법·검증 메시지 재사용 |
| `__node_results__` | graph.py 코드젠 (mergeNode 용) | 실행 시 바인딩 해석의 데이터 소스 |
| `__node_meta__` | ADR-0025 | 소스 노드가 오류였을 때의 바인딩 실패 판정 |
| inputs/outputs dataType 선언 | node_definitions 27종 전부 | 바인딩 타입 힌트(json 출력만 path 허용 등) |
| JSON 경로 추출기 | databaseNode 실행기 내 | 공용 헬퍼로 승격 |
| 필드 정의(kind·required) | NodeDefinitions/NodeRegistry | 바인딩 가능한 필드 목록·타입의 정본 |
| popout(분리 텍스트) UI | customNodes(NodeDetachedHandles 등) | **프론트 전용, 실행 계약 없음** — 이 체계로 흡수·정리 대상 |

## 3. BindingSpec v1 (계약)

```jsonc
"bindings": {
  "<fieldName>": {
    "source": "<nodeId>",       // 실행 경로상 상류 노드여야 한다 (검증기)
    "path":   "a.b[0].c",       // 비우면 출력 전체. 소스 출력이 JSON 아닐 때 path 지정 시 오류
    "required": true            // 기본 true — 해석 실패 시 노드가 needs_input 으로 멈춘다
  }
}
```

규칙:

1. **해석 시점**: 노드 실행 직전, 생성 코드가 `_resolve_bindings(node_id, data)` 를 호출해
   `__node_results__[source]` 에서 값을 꺼내 필드에 주입한다. 필드에 이미 고정값이 있으면
   바인딩이 우선한다(UI 가 동시 설정을 막는다).
2. **상류 보장**: 바인딩 소스는 반드시 그 노드로 오는 실행 경로의 상류에 있어야 한다 —
   검증기(validate_flow)가 정적으로 막고, 실행기는 미실행 소스를 만나면
   `BINDING_SOURCE_NOT_RUN` 오류(분기로 소스가 실행되지 않은 경우의 명시 실패).
3. **반복 경계**: v1 에서는 distributorNode/loopNode 반복 안의 노드가 반복 밖을 바인딩하는
   것은 허용, **반복 안 → 반복 밖** 바인딩은 금지(항목별 값이 모호). done 경로는 기존 누적
   규약을 따른다.
4. **소스 오류**: `__node_meta__[source].status == 'error'` 면 required 바인딩은 실패 처리 —
   ADR-0025 의 "오류가 데이터로 위장하지 않는다" 원칙을 바인딩에도 적용.
5. **바인딩된 필드는 실행 엣지 payload 와 무관** — 기본 payload(직전 출력 전체)는 지금처럼
   "본문" 성격의 대표 입력(프롬프트 본문, 발송 본문)에만 쓰인다.

오류 코드(error_catalog.json 등록): `BINDING_SOURCE_NOT_FOUND` · `BINDING_SOURCE_NOT_RUN` ·
`BINDING_PATH_MISSING` · `BINDING_SOURCE_NOT_JSON` · `BINDING_LOOP_BOUNDARY`.

## 4. 실행 엔진 변경 (범위가 작다)

1. 코드젠 프리앰블에 `_resolve_bindings(node_id, data_dict)` 헬퍼 추가 — `__node_results__` +
   JSON 경로 추출(코드펜스 벗기기 `_strip_json_fence` 재사용) + `__node_meta__` 오류 검사.
2. **생성기 공통 진입점 한 곳**에서 호출 — 각 생성기가 `node.get('data')` 를 읽기 전에
   바인딩이 해석된 data 를 받도록, generate_block 레벨에서 노드별 `data_{node_id} =
   _resolve_bindings(...)` 를 주입한다. 생성기 50곳을 고치지 않는다 — 코드젠이 노드 data 를
   **컴파일 타임 리터럴로 굽는 현재 방식**을 바인딩 필드에 한해 런타임 조회로 바꾸는 것이
   이 계획에서 기술적으로 가장 조심스러운 지점이다(§7 리스크 1).
3. validate_flow 에 상류 보장·필드 존재·반복 경계 검사 추가. dry_run 에 바인딩 검사 단계 노출
   ("n3.toEmail ← n1.customer.email ✓").

## 5. 캔버스: 선 난잡함의 해법 — "기본은 무선, 선은 렌즈"

바인딩의 정본이 노드 data 이므로 **선을 그리지 않는 것이 기본**이다. 선은 필요할 때만
켜는 시각화(렌즈)다.

1. **필드 픽커(기본 입력 방식)** — 펼친 노드의 각 입력 필드 옆 ⚡ 버튼 → 팝오버에서
   상류 노드 선택 → 그 노드의 최근 실행 결과/출력 스키마에서 경로 선택(트리 뷰, 실행
   이력이 있으면 실제 값 미리보기). 확정 시 필드가 **소스 칩** `[웹훅 수신 → customer.email ×]`
   으로 바뀐다. 선은 생기지 않는다.
2. **데이터 레이어 토글** — 툴바 버튼(단축키 예: `D`). 켜면 모든 바인딩을 **얇은 점선 곡선**
   (필드 포트 위치에서 출발, 노드 색)으로 오버레이. 실행 엣지(굵은 실선)와 시각 언어를
   분리한다. 끄면 사라진다.
3. **선택·호버 로컬 렌즈** — 토글이 꺼져 있어도 노드를 선택하면 그 노드가 주고받는 바인딩만
   고스트 선으로 표시. "이 노드에 뭐가 들어오나"를 보는 가장 흔한 질문에 전체 토글 없이 답한다.
4. **접힌 노드에는 포트를 그리지 않는다** — 바인딩 개수 배지(`⇣2 ⇡3`)만. 펼쳐야 필드
   단위 포트·칩이 보인다. 노드 12개짜리 캔버스가 포트 수십 개로 뒤덮이는 것을 방지.
5. **변수 허브(named reroute)** — 같은 값을 5곳에 쓰면 무선이라도 칩 추적이 번거롭다.
   valueNode 를 확장한 "변수" 노드에 이름을 붙여 한 번 받고, 하류는 변수 노드를 바인딩한다.
   (Blueprint 의 named reroute 와 같은 역할. 신규 노드 타입이 아니라 valueNode 의 모드.)
6. **포트 드래그는 보조 입력** — 데이터 레이어가 켜진 상태에서 출력 포트 → 입력 필드로
   드래그하면 픽커와 같은 바인딩이 생긴다(선을 "긋는" 감각을 원하는 사용자용). 저장 결과는
   동일하게 data.bindings — 표현이 두 가지일 뿐 정본은 하나.
7. **popout 기능 흡수** — 분리 텍스트(popout)는 실행 계약이 없는 시각 효과였다. 데이터
   레이어 도입 시 "필드를 캔버스에 분리"는 변수 허브 + 바인딩으로 대체하고 popout 은 제거.

## 6. LLM 생성 통합 (AI 가 난이도를 보완하는 지점)

1. **스키마**: FlowNode.data 에 bindings 규약을 허용(자유 dict 라 스키마 변경 없음). 카탈로그에
   [데이터 바인딩] 절 신설 — 문법, "실행 경로 상류만", "지어낸 path 금지 — 소스 출력 형식이
   카탈로그에 명시된 노드(웹훅 payload·트리거 출력·databaseNode rows 등)만 path 를 쓰고,
   모르면 바인딩 대신 기존 방식".
2. **디자인 패턴 갱신**: webhook-integration·db-report 패턴에 jsonParser 사슬 대신 바인딩
   사용을 명시. few-shot 에 바인딩 예시 1~2개 추가(빠름 모드는 보수적으로 — 확실한 트리거
   출력에만).
3. **대화형 편집 도구**: `bind_field(node_id, field, source_node_id, path)` 도구 추가 —
   "웹훅의 이메일을 수신자로 써줘" 류 요청을 정확한 바인딩으로.
4. **평가**: 평가 케이스에 "바인딩을 썼어야 할 자리에 llmNode/jsonParser 를 넣었는가" 감점
   항목 추가. 성공 지표: 대표 시나리오의 LLM 호출 수·토큰 사용량 감소(§8).

## 7. 리스크

| # | 리스크 | 방어 |
| --- | --- | --- |
| 1 | **코드젠이 data 를 컴파일 타임 리터럴로 굽는다** — 바인딩 필드는 런타임 값이어야 해서 생성기가 f-string 으로 박아버리면 안 된다 | **해결(Phase 0)**: 생성기가 값 자리에 `bound_expr(node, node_id, field)` 의 반환 표현식을 넣는다 — 바인딩이 있으면 `_resolve_binding(...)` 호출, 없으면 `repr` 리터럴(이스케이프 문제도 함께 사라진다). 50곳을 한 번에 고치는 대신 **BINDABLE_FIELDS 정본에 선언한 필드만** 전환하고, 목록에 있으나 배선되지 않은 필드는 테스트가 실제 컴파일 결과로 잡는다. 미지원 필드 바인딩은 검증에서 거부(조용한 무시 금지) |
| 2 | 분기로 소스가 실행되지 않음 | BINDING_SOURCE_NOT_RUN 명시 오류 + 검증기가 "조건 분기 갈래 간 바인딩" 경고 |
| 3 | 반복 문맥의 값 모호성 | v1 은 반복 안→밖 금지(§3-3). 반복 항목 바인딩(현재 항목의 path)은 후속 |
| 4 | LLM 이 path 를 지어냄 | 카탈로그 규칙(§6-1) + dry_run 바인딩 검사 + needs_input 강등 |
| 5 | UI 복잡도 증가로 초심자 이탈 | 바인딩은 전부 선택 사항 — 기존 "직전 출력" 방식이 항상 동작. 픽커는 ⚡ 하나로 숨김. 튜토리얼 심화 과정 추가 |
| 6 | popout 제거의 기존 사용자 | 저장된 그래프의 detached 상태는 열 때 일반 필드로 복원(값 보존). 마이그레이션 코드 1곳 |

## 8. 단계와 완료 기준

| Phase | 범위 | 완료 기준 |
| --- | --- | --- |
| **0. 계약·실행기** ✅ | (2026-08-31 완료) `node_bindings.py`(BindingSpec 파싱·정적 검증·**BINDABLE_FIELDS 정본**·bound_expr) · 코드젠 프리앰블 `_resolve_binding`(+`__node_bindings__` 주입) · 생성기 8노드 15필드 런타임 전환 · validate_flow·dry_run 검사 · 오류 코드 3종 · test_node_bindings.py 32케이스 | **달성**: 웹훅/valueNode payload 의 경로가 LLM·jsonParser 없이 필드로 들어간다(실행 검증: 바인딩만으로 문서 생성, LLM 0회). 전체 회귀 2515 통과 |
| **1. 에디터 무선 UI** ✅ | (2026-08-31 완료) `bindableFields.json` 번들 · `nodeBindings.js`(상류 BFS·실행 결과 경로 후보) · `FieldBindingPicker`(⚡ 픽커/소스 칩/접힘 배지) · `DefinitionField` 전 분기 + FormatNode 수동 배선 · EditorPage `bindingContext` 주입(실행 이력 → 경로 후보, `applyBinding` → data.bindings) | **달성**: Playwright 로 ⚡→경로 선택→칩→저장(`bindings.toEmail={source,path}`)→접힘 배지 ⇣1→해제→입력창 복귀 전 과정 확인. 검증 오류는 dry-run 문제 패널로 노출(validate_flow 경유) |
| **2. 데이터 레이어** ✅ | (2026-08-31 완료) `DataLayerOverlay`(ViewportPortal + 노드/칩 rect 측정 → 흐름 좌표 점선 곡선, 소스 노드 색) · `editorCommands` `view.dataLayer`(맨 키 `D` — mod+d 는 복제) · 선택 로컬 렌즈 · 필드 입력 포트 `bind:<필드>` + `onConnect` 가로채기(엣지 대신 data.bindings) · 변수 허브(valueNode `varName` + `value` 바인딩, 이름이 있으면 앞 결과를 이어 붙이지 않음) | **달성**: 바인딩 15개 그래프 Playwright — 평시 0선, node_fmt 선택 시 3선, `D` 후 15선, 포트 2개, 포트 드래그로 바인딩 생성(실행 엣지 10개 그대로), 끄면 0선. 오버레이는 z-index 음수로 노드·엣지 뒤 |
| **3. LLM·생태계** ✅ | (2026-08-31 완료) `node_bindings.render_binding_guide()`([데이터 바인딩] 블록, BINDABLE_FIELDS 파생) 을 4개 생성 프롬프트에 주입 · few-shot 바인딩 예시 2개(빠름·정밀) · `bind_field` 대화형 도구 · webhook-integration/db-report/format-fill 패턴 갱신 · 평가 케이스 33(FieldBinding) + `expected_bindings` 감점 · popout 제거 + `absorbDetachedText` 마이그레이션 · formatNode 안내 '바인딩 우선' · **필수 필드 검증이 바인딩을 인정**(`node_definition._check_rule`) · 결정적 수리가 실행 불가 바인딩 정리 | **달성**: 대표 시나리오 실제 생성 5회 모두 바인딩 사용(emailNode.toEmail). 이전(가이드 없음) llmNode 1개·값 성형 노드 1~2개·바인딩 0 → 이후 llmNode 0~1개·바인딩 1개 이상, 케이스 점수 35 → 60~90. 제거된 빈칸 채우기 LLM 1회의 실측 토큰 460(입력 374/출력 86) 이 그만큼 사라진다 |
| 보류 | 반복 항목 바인딩, 출력 스키마 선언 강화(dataType→구조 스키마), 타입 검사 강화, 바인딩 표현식(가공: upper/date 포맷 등 — **표현식 언어는 v1 금지**, pythonNode 로 충분) | Phase 3 안정화 후 |

## 9. 포맷 계획과의 관계

`DOCUMENT_FORMAT_STUDIO_PLAN.md` 의 formatNode 는 이 바인딩의 1급 소비자다 — fields 선언이
곧 바인딩 대상 목록이 된다. 정형 소스(웹훅·DB·트리거)는 바인딩으로, 비정형 소스(자기소개
원문)만 llmNode 로 채우는 것이 완성형이다. 포맷 Phase 1 의 "빈칸 채우기 LLM 자동 구성"은
"바인딩 우선, 남는 빈칸만 LLM" 으로 수정한다. 두 계획의 착수 순서: **이 계획 Phase 0 →
포맷 Phase 0~1 → 이 계획 Phase 1~2 와 포맷 Phase 2 병행** 을 권장(포맷이 바인딩 위에 앉도록).

## 10. 안정화 남은 작업 (2026-08-31 기준)

Phase 0~3 은 끝났고 1차 안정화(전체 평가 A/B · 문서·발견성 · 런타임 오류 화면 · 성능 · 정리)도
마쳤다(ADR-0026). **남은 둘은 모두 생성 LLM 반복 호출이 필요해서 중단했다** — 2026-08-31 시점에
API 크레딧이 소진됐다. 측정 도구는 `backend/binding_stabilization_eval.py` 에 남겨 뒀고,
`--self-test` 는 LLM 없이 언제든 돌려 스크립트가 살아 있는지 확인할 수 있다.

### 10.1 경로 환각 실측 — **아직 한 번도 재지 않았다**

가이드는 "출력 형식이 카탈로그에 문서화된 노드이거나 사용자가 키 이름을 말한 경우에만 path 를
쓰고, 아니면 빈 문자열(출력 전체)로 둬라"고 지시한다. 지켜지는지 확인한 적이 없다. 1차에서 관찰한
5회는 **요청이 키 이름을 알려준** 쉬운 조건이었다(case33 의 `managerEmail`).

지어낸 경로는 실행 시 `BINDING_PATH_MISSING` 으로 그 자리에서 멈춘다 — 이 기능의 가장 아픈
실패 방식이고, 사용자에게는 "AI 가 만들어 준 워크플로우가 실행되지 않는다"로 보인다.

```
./venv/bin/python binding_stabilization_eval.py --path-hallucination --times 3
```

- 탐침 프롬프트 3종(키 미언급) + 대조군 1종(키 언급)이 스크립트에 들어 있다.
- 판정은 `classify_binding_paths()` — 근거는 둘뿐이다: 소스가 `PATH_DOCUMENTED_SOURCES` 이거나,
  경로 토큰이 요청 문장에 등장하거나. 그 외 path 는 지어낸 것으로 센다.
- **게이트: 환각 경로 0건.** 1건이라도 나오면 `render_binding_guide()` 의 해당 문구를 강화하고
  다시 잰다(문구만 고치면 되므로 재측정 비용이 전부다).
- 비용: 케이스당 생성 1회 × 4프롬프트 × 3회 ≈ 12회 생성.

### 10.2 문서 노드 선택을 2/3 → 3/3 으로

case31(시말서→한글→메일)과 case32(팜플렛→디스코드)가 3회 중 2회만 통과한다. 1차에서 두 원인을
잡았지만 완전히 안정되지는 않았다.

| 조치 | 결과 |
| --- | --- |
| `apply_selection_augmentation` — 구형 문서 노드가 선별되면 formatNode 를 결정론적으로 끼워 넣는다 | case31 1/3 → 2/3, case33 3/3 |
| `unrequested_review_step` — 요청에 없는 승인·검토 단계는 되묻지 않는다(생성 원칙 1) | case32 1/3 → 2/3 |

남은 실패의 모습:

- case31 의 실패 1회는 formatNode 가 카탈로그에 **있는데도** hwpxDocumentNode 를 고른다.
  → 설명 경계는 이미 넣었다("프리셋이 있는 정형 문서면 formatNode"). 다음 후보는 few-shot
  예시18(시말서)이 formatNode 를 쓰는데도 밀린다는 점 — 예시와 카탈로그가 같은 방향인데 선택이
  갈리므로, **선별 결과에서 hwpxDocumentNode 를 아예 빼는** 더 강한 조치를 검토할 수 있다
  (프리셋에 해당하는 문서 종류 어휘가 요청에 있으면).
- case32 의 실패 1회는 posterGeneratorNode 를 고른다. 포스터·팜플렛은 formatNode 프리셋
  (`event-poster`, `tri-fold-pamphlet`)이 있으므로 같은 부류의 경계 문제다.

```
./venv/bin/python binding_stabilization_eval.py --selection 31,32 --times 3   # 선별만(싸다)
./venv/bin/python binding_stabilization_eval.py --repeat 31,32,33 --times 3   # 생성까지
```

- **선별을 먼저 본다** — 케이스당 LLM 1회라 생성보다 훨씬 싸고, 1차에서 원인이 실제로 여기였다.
  선별에 formatNode 가 들어오는데도 생성이 다른 노드를 고른다면 그때부터 설명·few-shot 문제다.
- **게이트: 3/3.** 조치를 하나 넣을 때마다 `--repeat ... --times 3` 으로 확인한다.

### 10.3 측정 원칙 (1차에서 얻은 것)

- **1회 결과로 판단하지 않는다.** 1차 A/B 에서 case1·8 이 회귀로 보였지만 3회 반복에서 모두
  만점이었다 — 잡음이었다. 반대로 case32 는 반복에서도 재현됐고 실제 결함이었다.
- **원인을 프롬프트에서 찾기 전에 선별을 본다.** 노드가 트리밍된 카탈로그에 없으면 그 노드의
  설명은 프롬프트에 아예 들어가지 않는다 — 설명을 고쳐도 아무 일도 일어나지 않는다.
- 전체 A/B 는 조치를 여러 개 넣은 뒤 한 번만 돌린다(각 33케이스 ≈ 11분, 입력 토큰 약 75만 × 2).
