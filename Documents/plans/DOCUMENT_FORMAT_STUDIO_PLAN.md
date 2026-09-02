# 문서 포맷(Format Studio) 계획 — templateAnalyzer·fileModifier 대체

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 상태 | v1.2 — **Phase 0~3 구현 완료**(2026-08-31). 보류 항목만 남음 |
| 작성일 | 2026-08-31 |
| 대상 | Workflow Editor(포맷 스튜디오 창·formatNode), 실행 엔진, 문서 페이지, LLM 생성 |
| 목표 | 포맷(문서 골격 + 빈칸 선언)을 에디터 안에서 직접 만들거나 AI로 생성하거나 프리셋에서 골라, 표·이미지를 포함한 완성 문서·포스터·팜플렛을 워크플로우가 자동 생성하게 한다. 출력: hwpx·docx·pdf·xlsx(문서류) / pdf·png(디자인류) |
| 대체 대상 | `templateAnalyzerNode`(템플릿 분석) + `fileModifierNode`(자동 완성) 의 "새 문서" 용도 전부 |
| 관련 문서 | `../ADR.md` ADR-0005(정의 정본)·0016(NodeError)·0018(Artifact)·0025(파이프라인 채널), `KOREAN_SERVICE_NODE_EXPANSION_PLAN.md` §1(HWPX 엔진), `DATA_FLOW_SEPARATION_PLAN.md`(빈칸 채움의 기본 경로 — 정형 데이터는 바인딩, 비정형만 LLM. 착수 순서는 그 문서 §9) |
| 정본 파일(신설) | `document_formats/*.json`(프리셋 포맷), `node_definitions/formatNode.json` |

## 1. 결론

**포맷 = 변수 선언(fields) + 블록 골격(blocks)** 이라는 하나의 스펙(FormatSpec)을 정본으로 두고,
그 스펙을 세 가지 방법(직접 편집 · AI 생성 · 프리셋)으로 만들게 한 뒤, 새 노드 `formatNode` 가
실행 시 변수를 채워 .hwpx/.docx/.pdf 를 만든다.

핵심 결정 네 가지:

1. **FormatSpec 은 hwpxDocumentNode 의 DocumentSpec 을 확장한다 — 새 포맷 언어를 발명하지 않는다.**
   기존 hwpx 빌더(`backend/documents/hwpx/builder.py`)가 이미 heading·paragraph·table·image·
   page_break 5블록을 안전하게 렌더하고, 이미지 소스를 artifactId 로 격리(경로·URL 거부)하는
   설계까지 끝나 있다. 여기에 `fields`(빈칸 선언)와 `{{변수}}` 참조만 얹는다.
2. **formatNode 는 결정적(deterministic)이다 — LLM 을 부르지 않는다.** 빈칸 값은 직전 노드가
   JSON 으로 준다(fields 선언에서 파생한 JSON Schema 로 llmNode 의 Structured Output 을 강제하는
   기존 패턴 그대로). 렌더 비용이 없고 같은 입력이면 같은 문서가 나온다.
3. **프리셋 포맷은 저장소 루트 정본 JSON 이다** — `workflow_patterns.json`·`node_definitions/` 와
   같은 방식(ADR-0005). 사용자 포맷은 DB(포맷 라이브러리)에 저장한다.
4. **기존 두 노드는 삭제하지 않는다.** 카탈로그에서 용도를 "이미 갖고 있는 서식 **파일**의
   빈칸 채우기"로 좁히고, 새 문서·표·이미지·프리셋은 전부 formatNode 로 유도한다.
   기존 그래프·템플릿은 그대로 동작한다.

## 2. 왜 기존 방식으로는 안 되는가 (현황 진단)

templateAnalyzer → llmNode → fileModifier 파이프라인의 구조적 한계:

| # | 한계 | 근거 |
| --- | --- | --- |
| 1 | **서식이 "파일"이라 편집·공유·미리보기가 안 된다.** 포맷을 고치려면 워드/한글에서 파일을 고쳐 다시 업로드해야 한다 | template_path 기반 설계 |
| 2 | **{{key}} 문자열 치환이 취약하다.** 치환 문자열이 여러 XML 텍스트 노드로 나뉘면 실패한다. 키가 안 맞으면 빈 문서가 조용히 저장된 사고 이력 | `KOREAN_SERVICE_NODE_EXPANSION_PLAN.md` §1, §2 불일치 3 |
| 3 | **analyzer 출력이 텍스트 blob 이라 메타/데이터가 섞인다.** "[채워야 할 빈칸 목록] + [실제 데이터]" 를 한 문자열로 — ADR-0025 가 지적한 채널 혼합의 대표 사례. 바로 뒤에 jsonParser 를 못 붙이는 함정 규칙이 카탈로그에 박혀 있다 | ADR-0025 맥락 2 |
| 4 | **표·이미지를 넣을 수 없다.** {{key}} 치환은 문단 텍스트만 다룬다. 반복 행(경력사항 N건) 표현 불가 | — |
| 5 | **파일이 없으면 즉석 생성으로 때운다.** template_generator 가 "빈칸 나열" 수준의 파일을 지어내는 응급 경로 — 포맷의 정본이 없다는 증거 | `template_generator.py` 머리말 |
| 6 | **프리셋이 없다.** 시말서·제안서 같은 흔한 요청마다 사용자가 서식 파일을 구해 와야 한다 | — |

이미 있는 기반(새로 만들지 말 것):

- **블록 렌더러**: hwpx 빌더(5블록, SpecError, 이미지 artifactId 격리, validate_editor_open_safety) — 그대로 재사용
- **docx·pdf 생성기**: python-docx(`template_generator.generate_docx_template` 계열), PyMuPDF 즉석 렌더 — 5블록 대응으로 확장
- **파일 유통**: Artifact(ADR-0018) — formatNode 산출물은 자동으로 이메일·디스코드·Gmail 첨부
- **정의 정본 체계**: node_definitions + export 번들 + 드리프트 테스트(ADR-0005)
- **오류 계약**: NodeError v1 + error_catalog.json(ADR-0016) — SpecError 를 코드로 등록
- **에디터 창 선례**: DeployModal·TemplateEditDialog — 포맷 스튜디오 모달의 뼈대
- **AI 생성 인프라**: Structured Output(llm.task_spec / meta_agent) — FormatSpec 생성에 그대로 사용
- **문서·패턴 정본**: nodeDocumentation.js, workflow_patterns.json(doc-fill 패턴 교체 대상)

## 3. FormatSpec v1 (정본 스키마) — layout 이원화

포맷은 두 계열(layout)로 나뉜다. **fields(빈칸 선언)와 채움 모델(§4.2-b)은 두 계열이 공유**하고,
골격의 표현과 렌더러만 다르다.

| layout | 골격 | 출력 | 렌더러 |
| --- | --- | --- | --- |
| `document` (문서류) | `blocks` — hwpx DocumentSpec 5블록 | hwpx · docx · pdf · **xlsx** | hwpx 빌더(재사용) · docx_builder(신규, python-docx) · xlsx_builder(신규, openpyxl — page_break 는 새 시트) · pdf 는 블록→HTML 후 Chromium 인쇄(아래 디자인류와 같은 렌더러 — PyMuPDF 흐름 렌더보다 표·이미지 품질이 좋고 렌더러가 하나로 통일된다) |
| `design` (디자인류: 포스터·팜플렛·카드뉴스) | `design` — html + css + theme(디자인 변수) | pdf · png | **poster_generator.render_html_to_file 재사용**(Playwright Chromium — posterGeneratorNode 가 이미 쓰는 경로, sanitize_poster_html 포함) |

디자인류 스키마:

```jsonc
{
  "layout": "design",
  "design": {
    "width": 794, "height": 1123,       // px. 팜플렛은 가로(1123×794) + 3단 CSS
    "html": "<header>{{title}}</header> … <img data-field=\"mainImage\">",
    "css":  "header { color: var(--fs-primary); } …",
    "theme": {                            // 스튜디오의 "디자인 변경"이 편집하는 변수들.
      "primaryColor": "#2563eb",          // 렌더 시 :root CSS 변수(--fs-*)로 주입되므로
      "backgroundColor": "#0f172a",       // css 를 몰라도 색·글꼴을 바꿀 수 있다
      "textColor": "#f8fafc",
      "fontFamily": "Pretendard"
    }
  }
}
```

- 텍스트 필드는 `{{field}}` 로 html 안에서 치환(**HTML 이스케이프 필수** — 값에 태그가 들어와도
  마크업이 되지 않는다), 이미지 필드는 `<img data-field="이름">` 슬롯의 src 에 artifact 바이트를
  data URI 로 주입한다.
- 디자인류의 "디자인 전체 변경" 단계: ① theme 변수(색·글꼴 — 스튜디오 UI), ② css/html 직접
  편집(고급 탭), ③ AI 재생성(§4.4 AI 바 — posterGeneratorNode 의 디자이너 지시문 재사용).
- `rows` kind 필드는 v1 에서 문서류 전용(디자인류의 반복 요소는 보류).

### 3-b. 문서류 스키마 (기존)

```jsonc
{
  "version": 1,
  "id": "incident-report",            // 프리셋만. 사용자 포맷은 DB id
  "name": "시말서",
  "description": "업무 중 발생한 사건의 경위와 재발 방지 대책을 보고하는 문서",
  "output": { "default": "hwpx", "allowed": ["hwpx", "docx", "pdf"] },
  "fields": [                          // ── 빈칸 선언 (LLM Schema·에디터 UI·검증의 정본)
    { "name": "authorName",  "label": "작성자",   "kind": "text",  "required": true,
      "example": "김워크" },
    { "name": "incidentAt",  "label": "발생 일시", "kind": "text",  "required": true },
    { "name": "summary",     "label": "사건 개요", "kind": "multiline", "required": true },
    { "name": "timeline",    "label": "경위",     "kind": "rows",       // 표의 반복 행
      "columns": ["시각", "내용"] },
    { "name": "signature",   "label": "서명 이미지", "kind": "image", "required": false }
  ],
  "blocks": [                          // ── 골격 (hwpx DocumentSpec 확장)
    { "type": "heading", "level": 1, "text": "시 말 서" },
    { "type": "table", "columns": ["항목", "내용"],
      "rows": [["작성자", "{{authorName}}"], ["발생 일시", "{{incidentAt}}"]] },
    { "type": "heading", "level": 2, "text": "1. 사건 개요" },
    { "type": "paragraph", "text": "{{summary}}" },
    { "type": "heading", "level": 2, "text": "2. 경위" },
    { "type": "table", "fromField": "timeline" },      // rows-kind 필드 → 표 전개
    { "type": "image", "fromField": "signature", "width": 120 },  // 실행 시 artifactId 주입
    { "type": "page_break" }
  ]
}
```

규칙:

- **블록 타입은 hwpx 빌더의 5종 그대로.** 확장은 참조 문법 두 가지뿐 — 텍스트/셀 안 `{{field}}`,
  블록 단위 `fromField`(rows→table 전개, image→artifactId 주입). 렌더러가 못 그리는 것은 스펙에
  넣을 수 없다(SpecError, 조용히 빠지지 않음 — 기존 빌더 원칙 유지).
- **fields 가 세 곳의 단일 원본**: ① 실행 검증(required 누락 시 NodeResult.needs_input),
  ② 앞 llmNode 의 JSON Schema 자동 파생, ③ 스튜디오·노드 UI 의 빈칸 목록 표시.
- 이미지 값은 **artifactId 만** 받는다(기존 `resolve_source` 의 소유 검증 재사용). 실행 중 앞
  노드가 만든 이미지(imageGenerationNode·posterGeneratorNode)는 `__node_artifacts__` 에서 참조.
- `{{field}}` 치환은 파일 치환이 아니라 **스펙(JSON) 단계에서** 일어난다 — XML 노드 분할
  문제(§2-2)가 원천적으로 사라진다.

## 4. 구성 요소

### 4.1 백엔드

| 항목 | 내용 |
| --- | --- |
| `backend/documents/format_spec.py` | FormatSpec 파싱·검증·치환(fields+blocks → 렌더용 DocumentSpec). 순수 함수, DB 모름 |
| `backend/documents/docx_builder.py` | 5블록 → .docx (python-docx). hwpx 빌더와 같은 SpecError 계약 |
| pdf 경로 | PyMuPDF 즉석 렌더 확장(5블록). fileModifier 의 pdf 경로 교훈: 서식-채우기가 아니라 즉석 렌더 |
| `formats` 테이블 | id·owner_user_id(→ workspace, ADR-0024 판정 재사용)·name·spec(JSON)·updated_at |
| API | `GET/POST/PUT/DELETE /api/formats`(라이브러리 CRUD) · `GET /api/formats/presets` · `POST /api/formats/generate`(AI 생성: 요청문 → FormatSpec, Structured Output) · `POST /api/formats/preview`(spec+예시값 → HTML 미리보기) |
| `formatNode` 실행기 | data.formatId(라이브러리/프리셋) 또는 data.inlineSpec → 직전 출력(JSON)으로 fields 채움 → 렌더 → artifact 저장. required 누락 시 needs_input |
| 오류 코드 | FORMAT_NOT_FOUND · FORMAT_SPEC_INVALID · FORMAT_FIELD_MISSING · FORMAT_IMAGE_FORBIDDEN 등을 error_catalog.json 에 등록 후 export |

### 4.2 프리셋 (저장소 정본)

`document_formats/*.json` — 1차 7종: 문서류 5종 **시말서 · 제안서 · 입사지원서 · 회의록 · 공문**
+ 디자인류 2종 **행사 포스터 · 3단 팜플렛**.
export_node_definitions.py 에 번들 추가(`frontend/src/generated/documentFormats.json`), 드리프트
테스트 동일 패턴. 프리셋도 렌더 스냅샷 테스트(각 포맷 × hwpx/docx/pdf 가 SpecError 없이 생성).

### 4.2-b 빈칸 채움 모델 (여러 변수의 "분배"는 없다)

포맷이 변수를 여럿 가질 때 상류가 값을 쪼개 "분배"하는 단계는 존재하지 않는다 —
**밀어주기(push)가 아니라 끌어오기(pull)** 다. formatNode 실행 시점에 **필드마다 독립적으로**
아래 순서로 해석한다:

| 순위 | 출처 | 성격 |
| --- | --- | --- |
| 1 | 바인딩 `bindings.<field> = {source, path}` | 명시 · 정형. 실행 경로상 **임의 상류**(직전 아님) 가능 — 웹훅과 llm 을 동시에 가리켜도 된다. 데이터 수집용 mergeNode 불필요 |
| 2 | 고정값 (스튜디오/노드 UI 에서 입력) | 명시 · 상수 (서명 이미지 artifactId 등) |
| 3 | 직전 출력 자동 매핑 (직전 노드 출력이 JSON 이면 `fields.name` 동명 키 매칭, 초과 키 무시) | 암시 · LLM 경로의 기본값 |
| 4 | 전부 실패 + required | **needs_input 으로 정지** — 조용히 빈 문서를 만들지 않는다(§2-2 사고의 반대) |

실행 로그에 필드별 출처를 남긴다: `authorName ← 바인딩(n1.user.name) · summary ← 직전 출력 ·
signature ← 고정값`.

**LLM 스키마 축소 규칙(토큰·환각 절감의 실체)**: "빈칸 채우기 LLM 자동 구성"이 만드는
llmNode 의 Structured Output 스키마는 전체 fields 가 아니라 **1·2순위로 못 채운 나머지 필드만**
담는다. 바인딩을 추가하면 그 필드는 스키마에서 자동으로 빠진다(fields 단일 원본). LLM 은
비정형 해석이 정말 필요한 필드만 만들고, 이름·날짜를 "옮겨 적는" 환각 기회가 사라진다.

### 4.3 formatNode (노드 계약)

- `node_definitions/formatNode.json` 신설(ADR-0005): fields — formatId(select, 라이브러리+프리셋),
  output(hwpx|docx|pdf), values(JSON, 선택 — 비우면 직전 노드 출력), output_path(선택)
- **meta_agent.NodeType 에 추가**(2026-08-30 누락 사고 재발 방지 테스트가 이미 대조함)
- 카탈로그 llm.description: "모르는 formatId 를 지어내지 말고 빈 값으로 두고 안내하라"(discord
  토큰 선례와 같은 규칙) + "앞 llmNode 에 fields 파생 스키마로 Structured Output 을 강제하라"
- 팔레트 카테고리: 고급 → **문서** 신설 검토(formatNode·hwpxDocumentNode·templateAnalyzer·
  fileModifier 4종 — 카테고리 신설은 문서 페이지·팔레트에 자동 반영됨)
- 노드 UI: 포맷 선택 → 빈칸 목록 미리보기(필드별 출처 칩: 바인딩/고정/LLM/미해결) →
  "포맷 스튜디오에서 편집" 버튼 → "빈칸 채우기 LLM 자동 구성" 버튼(§4.2-b 의 축소 스키마를
  가진 llmNode 를 앞에 삽입 — 기존 '노드 사이 삽입' 재사용)

### 4.4 포맷 스튜디오 (에디터 내 별도 창)

DeployModal 계열의 풀스크린 모달. 세 열 구성:

```
┌─────────────────────────────────────────────────────────┐
│ [AI에게 포맷 요청: "시말서 양식 만들어줘"        ] [생성] │  ← AI 바
├──────────┬───────────────────────────┬──────────────────┤
│ 블록 팔레트│  블록 편집기               │  미리보기(HTML)   │
│ 제목      │  ▤ 제목1 "시 말 서"        │  예시값으로 렌더   │
│ 문단      │  ▤ 표 2×2 [항목|내용]      │  (fields.example) │
│ 표        │  ▤ 문단 {{summary}}       │                  │
│ 이미지    │  (드래그 정렬·인라인 편집)  │                  │
│ 쪽 나눔   ├───────────────────────────┤                  │
│──────────│  빈칸(fields) 목록·편집     │                  │
│ 프리셋 5종│  authorName·summary·…     │                  │
└──────────┴───────────────────────────┴──────────────────┘
│ [프리셋에서 시작] [저장(내 라이브러리)] [이 노드에 적용]   │
└─────────────────────────────────────────────────────────┘
```

- 미리보기는 FormatSpec→HTML 프론트 렌더러(신규, 블록 의미 그대로) — **한/글 픽셀 일치가 아니라
  구조 확인용**임을 명시. 서버 미리보기 API 는 후속(보류)
- 이미지 블록: 업로드 → 기존 artifact 업로드 경로 재사용 → artifactId 저장
- AI 생성: `POST /api/formats/generate` — FormatSpec JSON Schema 로 Structured Output 강제,
  생성 결과는 편집기에 초안으로 로드(바로 저장 아님)
- 표 편집: 열 추가/삭제·셀 인라인 편집·`fromField` 반복 행 지정
- 진입점 두 곳: formatNode 의 "편집" 버튼, 에디터 도구 메뉴(분석 및 품질 옆 "문서 포맷")

### 4.5 LLM 생성·문서·튜토리얼 연동

- **디자인 패턴**: workflow_patterns.json 의 `doc-fill` 을 `format-fill` 로 교체 —
  `startNode → promptNode → llmNode(fields 파생 스키마) → formatNode → (발송)`. 기존 doc-fill 은
  "업로드한 서식 파일 채우기" 한정으로 문구 수정
- **NODE_CATALOG**: formatNode 항목 추가, templateAnalyzer/fileModifier 항목을 "기존 서식 파일
  전용"으로 좁힘(원문 문구 수정이므로 스냅샷 갱신 필요 — test_node_definitions 의 문구 불변
  테스트와 충돌하지 않게 항목 추가 + 두 노드는 사용 조건 문장만 추가하는 방식 검토)
- **문서 페이지**: nodeDocumentation.js 에 formatNode 추가, 두 구노드 문서에 "새 문서는 문서
  포맷 노드 사용" 안내. 프리셋 포맷도 문서 페이지에 미리보기 노출(후속)
- **튜토리얼**: 기본 트랙 '서식 자동 완성'(doc-fill) 과정을 formatNode 기반으로 교체(Phase 3)

## 5. 단계 (Phase)

| Phase | 범위 | 완료 기준 |
| --- | --- | --- |
| **0. 스펙·렌더러** | FormatSpec v1(layout 이원화) 확정, format_spec.py(검증·치환·축소 스키마), docx_builder·xlsx_builder·pdf(블록→HTML→Chromium)·design(poster 렌더러 재사용), 프리셋 7종 JSON, 렌더 스모크 테스트 | 문서류 5종 × 4출력 + 디자인류 2종 × 2출력이 오류 없이 생성되고 hwpx validate 통과 |
| **1. formatNode + 라이브러리** | formats 테이블·CRUD API, formatNode(정의·실행기·NodeType·카탈로그·오류 코드·dry_run mock), 노드 UI(선택+빈칸 표시+LLM 자동 구성), 문서 페이지 | 에디터에서 프리셋 선택 → 실행 → 문서 artifact 가 이메일 자동 첨부까지. 전체 회귀 통과 |
| **2. 포맷 스튜디오** | 모달 창(블록 편집·표·이미지 업로드·fields 편집·HTML 미리보기), AI 생성 API+바, 내 라이브러리 저장/불러오기 | 스튜디오에서 만든 포맷으로 1의 흐름이 그대로 동작. Playwright 시나리오 통과 |
| **3. 대체 완성** | format-fill 패턴 교체, 카탈로그·생성 규칙 유도 수정, 두 구노드 문서·카탈로그 문구 축소, 튜토리얼 과정 교체, 공식 템플릿 중 doc-fill 계열 점검 | AI 생성이 "시말서 만들어줘"에 formatNode 골격을 내놓는다(평가 케이스 추가) |
| **4. 파일→포맷 역변환** (2026-09-02 구현) | 서식 파일 업로드→FormatSpec 역변환 — `documents/format_import.py`(.hwpx/.docx 문단·표·쪽나눔·{{자리표시자}} 결정적 추출, 한글 표시자는 ASCII 개명+라벨 보존), `POST /api/formats/import`(파싱만 하고 버림, 상한 15MB), AI 빈칸 제안(`format_studio.refine_imported_spec` — 초안 근거 Structured Output, 실패 시 초안 폴백을 응답에 명시), 스튜디오 "파일에서 가져오기" 시작점 | 실제 hwpx/docx 왕복 + 렌더 복귀 + API 통합 테스트 8건(test_format_import.py) 통과 |
| **5. 포맷 탭 + 디자인 캔버스** (2026-09-02 구현) | ① `/formats` 페이지 — 내 포맷 라이브러리 관리(편집·복제·삭제, 스튜디오에 없던 삭제 UI 해소) + 프리셋 21종 브라우즈, 1차 내비게이션 "제작 > 포맷" 등록(브라우저 새 탭 = 별도 창 작업). ② 디자인 캔버스 편집기(`FormatCanvasEditor`) — 요소(text/image/box)의 드래그 이동·모서리 크기 조절·글자 크기/굵게/정렬/색(테마 키) 편집. 정본은 `design.elements`(validate 가 여분 키를 보존), 변경 때마다 `formatCanvas.serializeElements` 가 html/css 를 재직렬화하므로 렌더러 무수정·캔버스=산출물 보장. 디자인 프리셋 4종을 elements 기반으로 이관(`frontend/scripts/convert_design_presets.mjs`), AI 생성·수기 코드 포맷은 기존 테마/코드 편집기로 폴백("코드 편집으로 전환"은 배치 해제 경고 후) | 프리셋 4종 PNG 실렌더 확인 + design.elements 보존 테스트 |
| 보류 | 포맷 커뮤니티 공유(정화 규칙 필요), 서버 사이드 정밀 미리보기, 반복 섹션(표 밖 블록 반복), 역변환의 hwpx 제목 감지(charPr 역추적 — 지금은 문단으로 오고 AI 다듬기가 승격), 문서류 블록 스타일(정렬·글자 크기 — 4개 렌더러 동시 구현 필요, "워드 수준" 요구의 문서류 몫), 코드 기반 디자인→elements 역변환 | 재개 조건: Phase 3 안정화 + 수요 확인 |

## 6. 리스크와 방어

| 리스크 | 방어 |
| --- | --- |
| LLM 이 formatId 를 지어냄 | 카탈로그 규칙(빈 값 + 안내) + 실행기 FORMAT_NOT_FOUND(needs_input) — discord 토큰 선례 |
| 미리보기(HTML)와 실제 문서(hwpx) 차이 | 스튜디오에 "구조 미리보기" 라벨 명시. 픽셀 일치를 약속하지 않음 |
| fields 와 blocks 의 참조 불일치({{오타}}) | format_spec.py 검증: 선언 안 된 변수 참조·미사용 필수 필드를 저장 시점에 거부. 프리셋은 CI 테스트 |
| 구노드 사용자 혼란 | 두 노드 UI 에 배너("새 문서는 문서 포맷으로") + 문서 상호 링크. 제거·경고는 하지 않음 |
| 카탈로그 문구 불변 테스트와 충돌 | 기존 항목은 문장 추가만(스냅샷 갱신 절차 준수), 신규 항목은 자유 |
| 표 안 이미지·병합 셀 등 hwpx 빌더 미지원 요청 | v1 범위 밖 — 스튜디오 UI 에서 아예 만들 수 없게 한다(렌더러가 못 그리는 것은 스펙에 못 넣는다) |

## 7. 산출물 체크리스트 (구현 시 갱신)

- [x] Phase 0 (2026-08-31): format_spec.py(검증·치환·축소 스키마) · format_renderer.py ·
      docx_builder.py · xlsx_builder.py · pdf(블록→HTML→Chromium) · design(poster 렌더러 재사용) ·
      document_formats/ 7종(문서 5 + 디자인 2) · export 번들(documentFormats.json) ·
      test_format_spec.py 31케이스(hwpx validate·Chromium 스모크·번들 드리프트 포함)
- [x] Phase 1 (2026-08-31): FORMAT_* 오류 5종(error_catalog) · node_definitions/formatNode.json ·
      NODE_CATALOG(51종)·NodeType 등록 · documents/format_runtime.py(프리셋→라이브러리 로드·소유 격리·
      needs_input) · 코드 생성기(artifact 등록·NodeError 변환) · document_formats DB 표(마이그레이션
      0021)·CRUD API(/api/formats, 저장 시 스펙 검증) · 팔레트 '문서' 카테고리 신설(구 문서 3종 이동) ·
      FormatNode 캔버스 UI(프리셋+내 포맷 선택·빈칸 칩·허용 출력 필터·**LLM 축소 스키마 복사** —
      자동 삽입 버튼은 Phase 2 로) · 문서 페이지 · test_format_node.py 9케이스(end-to-end 포함)
- [x] Phase 2 (2026-08-31): FormatStudio 모달(3열: 프리셋/블록 팔레트 · fields+blocks/theme 편집기 ·
      구조 미리보기) · AI 생성(`POST /api/formats/generate` — Structured Output 스키마 강제 +
      validate_format_spec 관문, format_studio.py) · 디자인 테마 편집(색 4·글꼴·크기, HTML/CSS 고급
      탭) · 표 인라인 편집(열/행 추가·fromField 연결) · 이미지 업로드(/api/upload 재사용, artifactId) ·
      내 라이브러리 저장/업데이트/"이 노드에 적용" · **빈칸 채우기 LLM 자동 삽입**(Phase 1 이월분 —
      축소 스키마 llmNode 를 앞에 삽입·재배선) · 진입점 2곳(노드 버튼·에디터 도구 메뉴) ·
      라이브러리 변경 이벤트로 노드 목록 동기화 · 미리보기: 문서=블록 렌더, 디자인=sandbox iframe
- [x] Phase 3 (2026-08-31): 디자인 패턴 `format-fill` 신설 + `doc-fill`→"서식 파일 채우기"로 축소 ·
      구노드 2종 카탈로그에 formatNode 유도 문장(스냅샷 갱신, diff 검증) · posterGeneratorNode 에
      선택 기준 추가("양식으로 반복 생성이면 formatNode") · few-shot 예시 추가(빠름·정밀 양쪽) ·
      평가 케이스 31·32 신설(구노드 forbidden) · 튜토리얼 '문서로 발행' 과정 신설(데이터 트랙 4번째,
      FormatFillLab — 빈칸 출처를 정형/LLM 으로 구분해 보여줌) · 공식 템플릿 242종 점검(구노드 사용 0건,
      마이그레이션 불필요). **완료 기준 달성**: 실제 생성이 "시말서→한글→메일"에 formatNode(incident-report,
      hwpx), "3단 팜플렛 양식"에 formatNode(tri-fold-pamphlet, pdf)를 내놓는다
