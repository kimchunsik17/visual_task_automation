# 한국형 서비스 노드 확장 계획

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 상태 | v1.7 — Phase 0~3 구현 완료. 남은 것은 승인키 실호출 대조와 보류 항목뿐 |
| 작성일 | 2026-08-30 |
| 대상 | Workflow Editor, API Center, Connector Runtime, 문서 처리·커뮤니티·소셜 노드 |
| 기준 | 공식 문서에서 현재 제공 범위를 확인할 수 있고, 범용 HTTP 노드보다 전용 인증·상태·오류·mock 경험을 개선하는 노드만 채택 |
| 관련 문서 | `../ROADMAP.md` §4(공식 연동 노드 공통 계약), `INCOMPLETE_NODE_STRUCTURE_REVIEW.md`(같은 폴더), `../ADR.md` ADR-0007·0008·0009·0016·0021 |
| 정본 파일 | `error_catalog.json`(오류 코드), `credential_providers.json`(자격증명), `node_definitions/*.json`(노드 계약) |

## 1. 결론

다음 한국형 노드 묶음은 아래 순서로 진행한다.

0. ~~**먼저, 지금 새고 있는 것부터 막는다**~~ — **완료**. 문서 노드의 템플릿 덮어쓰기, `webCrawlerNode`의 무검증 URL 요청(§8 Phase 0 이전)
1. ~~**HWPX 문서 생성 엔진 안정화 + `hwpxDocumentNode`**~~ — **완료**
2. ~~**네이버 검색/모니터링 + 네이버 카페 게시**~~ — **완료**
3. ~~**범용 수집 노드(`webCrawlerNode`) 정비**~~ — **완료**
4. **공공데이터포털 + 도로명주소** ← 남은 활성 범위

**2026-08-30 범위 축소.** X·Instagram 은 API 비용 때문에, 커뮤니티 전용 preset·네이버 커머스·NAVER WORKS·OpenDART·카카오 로컬·KOSIS 는 수요와 자격 요건 때문에 보류한다. 각각의 재개 조건은 §8 보류표에 있다.

중요한 범위 구분은 다음과 같다.

- HWPX 생성에는 서버용 한컴 오피스가 필수가 아니다. HWPX는 OWPML을 따르는 ZIP/XML 기반 개방형 포맷이므로 Linux에서 직접 만들 수 있다. 현재 저장소에도 `python-hwpx` 기반의 최소 생성 경로가 이미 있다.
- 현재 HWPX 구현은 제목과 `{{field}}` 문단을 만드는 수준이며, 치환 문자열이 여러 XML 텍스트 노드로 나뉘면 실패할 수 있다. 더 급한 것은 실패 자체가 아니라 **실패했을 때의 동작**이다. 키가 안 맞으면 지금은 사용자가 올린 서식을 빈 문서로 덮어써 버린다(§2 불일치 3). 따라서 새 기능의 핵심은 “처음 지원”이 아니라 **안전한 공용 엔진으로 확장하고 실제 한/글 호환성을 검증하는 것**이다.
- 네이버 카페는 OAuth 2.0 기반 가입·게시글 작성 API가 있지만, 특정 카페의 새 글 목록/댓글을 읽는 공식 API는 확인되지 않았다. 카페 읽기는 네이버 전체 카페글 검색 범위로 제한하고, 카페 전용 Trigger라고 과장하지 않는다.
- 네이버 블로그 글쓰기 Open API는 2020년 5월 6일 종료됐다. **블로그 검색·새 검색 결과 감지만 제공하고 자동 발행은 제공하지 않는다.**
- 디시인사이드는 이용약관에서 사전 서면 동의 없는 크롤링을 명시적으로 금지한다. **조건이 아니라 전제**이므로 호출량을 줄이는 것으로 충족되지 않는다. 전용 노드는 폐기하고(§6.5) 차단 목록만 유지한다.
- 아카라이브 규정 8번은 "**서버에 부하를 주는** 크롤링, 스크랩핑" 을 제한 사유로 든다. 금지 대상이 행위가 아니라 **부하**라서, 호출량 상한으로 규정 문언을 지킬 수 있다. 다만 운영사가 크롤링에 의한 서비스 장애 공지를 낸 적이 있으므로 기본값을 보수적으로 둔다.
- 에펨코리아는 2026-08-30 기준 공식 공개 API·RSS 개발 문서를 확인하지 못했다. 범위에서 빼고 아카라이브로 대체한다.
- 루리웹은 공식 RSS 안내와 게시판별 RSS 규칙을 제공하므로 기존 `rssTriggerNode`에 검증된 preset을 추가하는 방식으로 먼저 지원한다. 커뮤니티별 executor를 복제하지 않는다.
- X API는 과금·호출 제한이 계정과 endpoint에 따라 달라지므로 연결 시 가용 기능과 예산을 검사한다. 검색/감지는 읽기, 게시/답글/삭제는 쓰기로 분리한다.
- Instagram은 공식 API가 Business·Creator 등 Professional 계정만 지원한다. 개인 계정 수집·게시를 지원한다고 표시하지 않으며, 다중 고객 제공 전 App Review와 필요한 Advanced Access를 출시 gate로 둔다.
- **이 계획의 커뮤니티 정책은 기존 `webCrawlerNode`를 먼저 처리하지 않으면 성립하지 않는다.** 그 노드는 지금도 임의 URL을 robots·allowlist·사설 IP 검사 없이 긁고, URL이 비면 직전 노드 출력을 URL로 쓴다. 전용 Trigger를 카탈로그에서 감춰도 같은 수집이 가능하다(§2 불일치 11, §6.5).
- **여기서 만드는 것 중 실제로 처음인 것은 OAuth 인가 코드 callback이다.** 현재 저장소에는 refresh 갱신만 있고 authorize→callback 경로가 없다. 네이버·X·Instagram 세 묶음이 전부 여기에 묶여 있으므로 Phase 0의 실질 임계경로다(§2 불일치 10).
- 반대로 Trigger cursor 저장소, 오류 코드 정본, 커뮤니티 정화 규칙은 **이미 있다.** 새로 만들지 말고 확장한다(§2 이미 있는 기반, §7).

### 추천 출시 묶음

| 묶음 | 포함 | 판단 |
| --- | --- | --- |
| Korea Pack A | HWPX, 네이버 블로그/카페글 검색, 네이버 카페 글쓰기 | 먼저 출시. 한국 사용자에게 즉시 보이는 차별점이고 기존 Connector 기반을 재사용할 수 있음 |
| Korea Pack B | 네이버 커머스 주문·상품·문의 | 판매자 계정과 운영 승인 절차가 필요하므로 별도 beta |
| Korea Pack C | NAVER WORKS, OpenDART, 카카오 로컬 | 기업 업무·리서치 자동화 범위를 넓히는 고가치 묶음 |
| Korea Community Pack | 루리웹 공식 RSS preset, 공식 RSS/Atom 커뮤니티 감지 | 읽기 전용부터 출시. 디시인사이드·에펨코리아는 차단 목록 유지 |
| Social Pack | X 검색·게시, Instagram Professional 게시·댓글 Trigger | 공식 API만 사용하며 비용 budget, 권한 심사, 게시 승인 UX가 선행되어야 함 |
| Korea Data Pack | KOSIS, 공공데이터포털, 도로명주소 | 읽기 전용부터 시작. 서비스별로 다른 공공 API 스키마를 정규화해야 함 |
| 정비 | `webCrawlerNode` 구조화 추출·robots.txt·호출량 상한 | 사이트별 전용 노드를 대신한다(§6.5) |

## 2. 현재 저장소 기준선과 바로 고칠 불일치

### 이미 있는 기반

- `backend/connectors/`에 인증 주입, 오류 정규화, retry, rate limit, pagination, mock transport 계약이 있다.
- YouTube, RSS, Gmail, Google Drive, HTTP 노드가 Node Definition 기반 Connector의 기준 구현이다.
- API Center의 자격증명은 graph에 원문을 저장하지 않고 `{{API_CENTER:<provider>}}` reference로만 두고 실행 시점에 주입한다.
- mock 실행은 실제 네트워크를 호출하지 않고 `success`, `auth_failed`, `rate_limited`, `not_found`, `timeout`을 재현한다(`node_definitions/youtubeNode.json`의 `mock.scenarios`).
- **Trigger cursor 저장소가 이미 있다.** `backend/graph.py:265-286`의 `_load_node_cursor`/`_save_node_cursor`가 `models.NodeMemory`를 `session_id='__cursor__'`로 재사용하고 `(project_id, node_id)`로 키를 잡는다. YouTube·RSS·Gmail Trigger가 이미 쓰고 있다(`backend/node_generators/connector_nodes.py:51,140,178`).
- **오류 코드의 정본은 `error_catalog.json` 하나다**(ADR-0016). 지금 39개 code가 8개 category와 9개 resolution 위에 등록돼 있고, `frontend/src/generated/errorCatalog.json`과 `Documents/ERROR_CATALOG.md`는 `python backend/export_node_definitions.py`가 거기서 생성한다.
- **모든 노드 타입은 커뮤니티 공개용 정화 규칙을 가져야 한다**(ADR-0021). `backend/community_sanitize.py`는 규칙 없는 타입이 그래프에 있으면 `SanitizeRefused`로 공개 자체를 거부하고, `backend/test_community_qna.py:102`가 실행 가능한 모든 타입에 규칙이 있는지 검사한다. 이 계획의 신규 노드는 전부 이 규칙을 함께 내야 한다.
- Node Definition의 `sideEffect` 허용값은 `none | external-read | external-write` 세 개다(`backend/node_definition.py:150`). `connector` 블록은 외부 연동 노드만 갖는다(`node_definition.py:156`).
- `templateAnalyzerNode`와 `fileModifierNode`는 `.hwpx`를 지원하고 `.hwp`는 거부한다.
- `backend/template_generator.py`는 `HwpxDocument.new()`로 한컴 오피스 없이 최소 HWPX를 생성한다.
- **범용 `webCrawlerNode`가 이미 카탈로그에 있다.** 임의 URL을 `requests.get` + BeautifulSoup으로 긁어 5000자를 돌려주고, 큐레이션 템플릿 3개가 쓴다(`backend/node_generators/action_nodes.py:72-101`).

### 발견한 불일치

아래는 2026-08-30에 저장소를 직접 읽어 확인한 것이다. 3·4·9·10·11·12는 v1.1에 없던 항목이다.

**1·3·4·7·11은 2026-08-30에 해결했다**(§8 "Phase 0 이전"). **9·10도 같은 날 해결했다**(§8 Phase 0 — OAuth 인가 코드 callback). 나머지는 각 Phase에서 다룬다.

1. ~~`backend/requirements.txt:33`의 `python-hwpx`가 버전 고정 없이 선언돼 있다.~~ **(2026-08-30 해결 — `==3.4.1` 고정)**
2. HWPX 치환은 `section*.xml` 문자열에 단순 `replace()`를 수행한다(`backend/node_generators/template_nodes.py:265-268`). `{{customer_name}}`이 여러 `<hp:t>`로 분할되면 찾지 못한다.
3. **(2026-08-30 해결)** ~~(신규·데이터 손실) 템플릿 자동 재생성이 사용자가 올린 원본을 덮어쓴다.~~ `templateAnalyzerNode`(`template_nodes.py:105`)와 `fileModifierNode`(`template_nodes.py:251`)는 기존 `{{key}}`와 이번 데이터 키의 겹침이 절반 미만이면 `generate_hwpx_template(...)`을 부른다. 그런데 첫 인자가 출력 경로가 아니라 **템플릿 경로 자체**다. 사용자가 올린 계약서 서식이 빈칸만 있는 새 문서로 교체되고 되돌릴 수 없다.
4. **(2026-08-30 해결)** ~~(신규) 치환 후 재압축이 `mimetype` 규칙을 깬다.~~ `zipfile.ZipFile(output, 'w', ZIP_DEFLATED)`로 모든 entry를 `writestr` 한다(`template_nodes.py:269-271`). `HwpxDocument.new()`가 만든 원본은 `mimetype`이 첫 entry이면서 STORED(`compress_type=0`)인데, 재작성본은 deflate로 압축된다. OCF 계열 규칙을 엄격히 검사하는 reader에서 깨질 수 있다.
5. XML/package 입력 제한과 zip bomb, 외부 관계, 잘못된 entry path 방어가 HWPX 전용 경로에 명시되어 있지 않다.
6. 한/글에서 실제로 열리는지를 보장하는 golden fixture와 호환성 매트릭스가 없다.
7. **(2026-08-30 해결)** ~~큐레이션 템플릿 `계약서 템플릿 자동 채움`이 지원하지 않는 `contract_template.hwp`를 참조한다~~(`backend/seed_curated_templates.py:1128,1132`). 저장소에서 `.hwp` 파일을 실제로 가리키는 곳은 이 두 줄뿐이므로 교정 범위는 작다.
8. 기존 `templateAnalyzerNode`/`fileModifierNode`와 새 HWPX 생성 노드가 별도 구현을 가지면 포맷 버그가 두 군데로 분기된다.
9. **(신규) v1.1 §4.3이 쓴 `kind: oauth_client`는 존재하지 않는 값이다.** 허용값은 `api_key | token_pair | compound | oauth2 | service_account`이고(`backend/connectors/providers.py:60`), 실제 OAuth 앱 자격증명(`google_oauth_client`)은 `compound` + `secretFormat: "client_id:client_secret"`으로 표현한다. 토큰은 `token_pair` + `refresh.clientCredential`로 앱 자격증명과 연결한다. `depends_on`이라는 필드는 스키마에 없다.
10. **(2026-08-30 해결 — `connectors/oauth_flow.py`)** ~~(신규) 인가 코드 callback이 아직 없다.~~ `backend/connectors/oauth.py`는 refresh_token 갱신만 담당하고, `google_oauth`·`kakao_token` 모두 사용자가 토큰을 직접 붙여넣는 방식이다. 즉 §4.3이 말한 공통 OAuth callback은 "복제하지 않는다"가 아니라 **이 계획이 처음 만드는 것**이며, 네이버·X·Instagram 세 묶음의 공통 선행 조건이다.
11. **(2026-08-30 해결 — `url_guard`)** ~~(신규·정책 모순) `webCrawlerNode`가 §11 비목표를 이미 우회할 수 있다.~~ URL 검증이 placeholder 비교뿐이고 robots.txt·allowlist·사설 IP 차단이 없으며, `data.url`이 비면 **직전 노드 출력을 그대로 URL로 쓴다**(`action_nodes.py:84-91`). 그래서 (a) 디시인사이드·에펨코리아 전용 Trigger를 감춰도 사용자와 생성기가 같은 수집을 할 수 있고, (b) LLM이 만든 URL이 내부 주소를 가리키면 SSRF가 된다. 커뮤니티 gate를 논하기 전에 이 노드의 처리를 먼저 정해야 한다.
12. **(신규) `rssTriggerNode`의 cursor에 겹침 창이 없다.** `backend/connectors/services/rss.py:117`이 매 실행마다 cursor를 "현재 피드에 있는 id 전체"로 교체한다. 피드에서 밀려났다 다시 들어온 항목은 새 항목으로 재통지된다. §6.5가 약속한 dedupe는 이 파일을 고쳐야 성립한다.

## 3. HWPX: 한컴 오피스 없는 생성 전략

한컴 공식 설명에 따르면 HWPX는 국가 표준 KS X 6101의 OWPML을 따르는 XML 패키지이고, 내부 구조는 ZIP이다. 따라서 서버 런타임에 한컴 오피스를 설치하지 않고도 문서를 생성·편집할 수 있다. 공식 포맷 자료와 한컴 공개 OWPML 모델/DVC를 호환성 기준으로 삼는다.

### 3.1 채택 구조

```text
DocumentSpec(JSON)
  -> HwpxSemanticBuilder
       heading / paragraph / table / image / page break / style
  -> HwpxPackage
       canonical skeleton clone / manifest / relationships / binary data
  -> HwpxValidator
       package safety / structural rules / library safety / optional OWPML check
  -> Artifact(.hwpx + validation report)
```

템플릿 경로는 다음을 공유한다.

```text
Existing HWPX template
  -> SafePackageReader
  -> RunAwarePlaceholderIndex
  -> typed value insertion
  -> same HwpxValidator
  -> Artifact
```

### 3.2 새 노드 계약

노드 타입은 `hwpxDocumentNode` 하나로 시작한다.

| mode | 입력 | 출력 | Node Definition 분류 |
| --- | --- | --- | --- |
| `create` | `DocumentSpec` 또는 직전 노드 JSON | 새 `.hwpx` Artifact와 검증 보고서 | `sideEffect: none`, `capabilities: [filesystem]` |
| `fill_template` | HWPX Artifact, 값 JSON | 채워진 `.hwpx` Artifact와 미치환 필드 목록 | `sideEffect: none`, `capabilities: [filesystem]` |
| `inspect` | HWPX Artifact | 문서 메타데이터, 블록 요약, 플레이스홀더 | `none` |
| `validate` | HWPX Artifact | package/schema/safety 결과 | `none` |

`DocumentSpec` MVP는 다음만 지원한다.

```json
{
  "title": "회의 결과 보고",
  "metadata": {"author": "홍길동", "subject": "주간회의"},
  "page": {"size": "A4", "orientation": "portrait", "marginsMm": [20, 20, 18, 18]},
  "blocks": [
    {"type": "heading", "level": 1, "text": "회의 결과"},
    {"type": "paragraph", "text": "결정 사항입니다.", "style": "body"},
    {"type": "table", "columns": ["담당", "기한"], "rows": [["개발팀", "2026-09-10"]]},
    {"type": "image", "artifactId": "...", "widthMm": 80, "alt": "구성도"},
    {"type": "page_break"}
  ]
}
```

1차 버전에서 지원하지 않는 기능은 자유 배치 도형, 복잡한 수식, 차트, 매크로, 배포용 문서, 암호 문서다. 지원하지 않는 블록은 조용히 누락하지 않고 `HWPX_UNSUPPORTED_FEATURE`로 실패시킨다.

`hwpxDocumentNode`는 외부 서비스 연동이 아니므로 Node Definition에 `connector` 블록을 두지 않는다. 대신 `type`, `version`, `category`, `display`, `inputs`, `outputs`, `fields`, `capabilities`, `sideEffect`, `executor`, `mock`, `llm`을 채운다. `mock`은 네트워크가 없는 노드라도 입력 검증 실패와 미치환 placeholder 시나리오를 제공한다. `community_sanitize`의 정화 규칙도 같은 PR에 포함한다 — 정의의 `kind: "secret"`·`credential` 블록에서 자동 파생되므로 별도 표를 만들 필요는 없지만, 규칙 없이 합치면 `test_community_qna`가 깨진다.

### 3.3 구현 원칙

- 현재 `python-hwpx`는 생성 backend 중 하나로 사용하되 버전을 고정하고 라이선스·유지보수·API 안정성을 검토한다.
- 패키지 전체를 매번 새로 조립하기보다 한/글에서 검증된 최소 canonical skeleton을 저장소 asset으로 두고 필요한 XML과 관계만 수정한다.
- 템플릿 치환은 XML 문자열 치환을 중단한다. 한 문단의 텍스트 노드들을 논리 문자열로 합쳐 placeholder 범위를 찾은 뒤 원래 run/style 범위를 보존하며 다시 분배한다.
- XML escape는 serializer에 맡기고, 문자열을 수동으로 `&amp;` 변환한 뒤 다시 파싱하는 방식을 제거한다.
- **입력 템플릿은 어떤 경로에서도 덮어쓰지 않는다.** 결과는 항상 새 출력 Artifact에 쓴다(§2 불일치 3).
- **템플릿을 자동 재생성하지 않는다.** 키가 맞지 않으면 조용히 새 서식을 만드는 대신 `HWPX_UNRESOLVED_PLACEHOLDER`로 실패시키고 없는 키와 있는 키를 함께 알린다. 빈 서식이 필요하면 사용자가 `create` mode를 명시적으로 고른다.
- 패키지를 다시 묶을 때 `mimetype`을 첫 entry·STORED로 유지하고, 나머지 entry의 순서와 압축 방식을 원본에서 보존한다(§2 불일치 4).
- 이미지 입력은 Artifact ID만 받는다. 임의 서버 경로나 URL을 직접 열지 않는다.
- HWPX ZIP은 entry 수, 개별/전체 해제 크기, 압축 비율, 중복 이름, 절대경로와 `..`, symlink, 외부 relationship을 검사한다.
- DTD/외부 entity를 거부하고 XML 깊이와 노드 수를 제한한다.
- `mimetype`, manifest, content relationships와 section 참조 무결성을 검증한다.
- 결과에 `validation.status`, `warnings`, `unresolvedPlaceholders`, `compatibilityProfile`을 함께 반환한다.
- Linux에서의 생성과 한/글에서의 시각적 재레이아웃을 분리한다. 서버가 한/글 렌더링과 픽셀 동일성을 보장한다고 표현하지 않는다.

### 3.4 호환성 검증 계층

1. **단위 검증:** ZIP/package 규칙, XML well-formedness, 참조 대상 존재 여부
2. **라이브러리 검증:** `python-hwpx`의 editor-open safety 검사
3. **공식 모델 검증:** 한컴 공개 OWPML 모델 또는 DVC를 CI 보조 검사로 검토
4. **golden 검증:** 공문, 계약서, 표 중심 보고서, 이미지 포함 문서 등 대표 문서 10종의 추출 결과와 package diff
5. **실편집기 검증:** 릴리스 후보를 한/글 최신판과 지원할 최소판에서 열기·다른 이름으로 저장·재열기. 이 검증기는 별도 Windows QA runner 또는 수동 release gate일 수 있으며 Linux 운영 서버에는 한컴을 설치하지 않는다.

### 3.5 `.hwp` 처리 방침

- 바이너리 `.hwp` 생성·수정은 이번 노드 범위가 아니다.
- 사용자가 `.hwp`를 올리면 `.hwpx` 또는 `.docx`로 변환해 다시 올리도록 안내한다.
- 서버 변환이 꼭 필요해지면 공개 포맷 구현을 사용하는 격리 converter를 별도 연구하되, 변환 충실도·라이선스·악성 파일 방어를 통과하기 전에는 기본 경로에 넣지 않는다.
- UI에서 `.hwp`와 `.hwpx`를 모두 “한글 문서 지원”으로 묶어 표시하지 않는다.

### 3.6 HWPX 완료 조건

- Linux 이미지에 한컴 오피스/Windows COM이 전혀 없어도 생성된다.
- 제목, 문단, 표, 이미지, 페이지 나누기가 포함된 golden 문서 10종이 한/글에서 복구 경고 없이 열린다.
- 여러 텍스트 run으로 분할된 placeholder, 표 안 placeholder, 특수문자, 줄바꿈을 모두 채운다.
- 미치환 placeholder를 결과에 명시하고 기본 설정에서는 실패로 취급한다.
- 악성 ZIP/XML fixture를 모두 거부하고 서버 파일을 읽거나 외부 URL을 호출하지 않는다.
- 실행 전후로 입력 템플릿 파일이 byte 단위로 동일하다. 자동 재생성 경로가 제거됐음을 회귀 테스트로 고정한다.
- 재작성한 패키지에서 `mimetype`이 첫 entry이고 `compress_type == 0`이다.
- 기존 `templateAnalyzerNode`와 `fileModifierNode`도 같은 엔진을 호출하며 기존 정상 워크플로가 회귀하지 않는다.

## 4. 네이버 노드 설계

### 4.0 NAVER API HUB 이관 (2026-08-30 확인, v1.1 작성 시점과 달라진 부분)

**검색 API가 개발자센터에서 네이버 클라우드의 NAVER API HUB로 옮겨갔다.** v1.1은 개발자센터 기준으로 쓰였으므로 §4의 전제 일부가 낡았다.

| 항목 | 옛 개발자센터 | NAVER API HUB |
| --- | --- | --- |
| 등록 | developers.naver.com | 네이버 클라우드 플랫폼 콘솔 |
| 호스트 | `openapi.naver.com` | `naverapihub.apigw.ntruss.com` |
| 인증 헤더 | `X-Naver-Client-Id` / `X-Naver-Client-Secret` | `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY` |
| 경로 | `/v1/search/news.json` | `/search/v1/news` |

**일정.** HUB 출시 2026-06-25 → 개발자센터 신규 신청 마감 2026-07-31 → 레거시 방식 지원 종료 2027-06-30. **지금 새로 시작하는 사용자는 HUB만 쓸 수 있다.**

**우리 계획에 미치는 영향.**

- **블로그·카페글 검색은 살아남았다.** 둘 다 HUB로 이관돼 계속 제공된다 — §4.2의 `naverSearchNode` 두 mode 는 그대로 간다.
- **쇼핑·책·전문자료 검색은 2026-07-31에 완전히 종료됐다.** 대체 API가 없다. 우리는 쓰지 않았으므로 영향 없다.
- **자격증명이 바뀐다.** `naver_open_api`(client id/secret)를 `naver_api_hub`(NCP API Gateway key 쌍)로 교체했다. 헤더 이름과 호스트가 달라 connector 구현도 그 기준으로 쓴다.
- **네이버 로그인·카페 API는 HUB에 없다 — 그런데 원래 거기 있던 적이 없다.** HUB로 옮겨간 것은 검색 API 계열이고, 카페 가입·글쓰기는 처음부터 개발자센터의 **로그인 오픈API**였다. 즉 "ncloud 문서에 카페가 없다"는 것은 이관 실패가 아니라 **이관 대상이 아니었다**는 뜻이다(2026-08-30 확인).

#### 비용 — 콘솔 실제 요금표 (2026-08-30 사용자 확인)

| API | 구간 | 호출량 | 요금 | 비고 |
| --- | --- | ---: | ---: | --- |
| **검색 API**(블로그·카페글·지식iN 등) | 무료 | 0 ~ 775,000건 | 0원 | **일 최대 25,000건** |
| 검색어 트렌드 | 무료 | 0 ~ 30,000건 | 0원 | 기본 무료 |
| | 유료 | 30,001 ~ 50,000건 | 0원 | **한시적** 무료 |
| 쇼핑 인사이트 | 무료 | 0 ~ 30,000건 | 0원 | 기본 무료 |
| | 유료 | 30,001 ~ 50,000건 | 0원 | **한시적** 무료 |

**우리가 쓰는 검색 API 에는 유료 구간이 아예 없다.** 그리고 월 무료 한도 775,000 = 일 한도 25,000 × 31 이라, **일 한도에 먼저 걸려서 무료 구간을 넘어설 방법이 없다.** 즉 검색 API 는 돈이 아니라 **한도** 문제다.

한시적 무료 표시가 붙은 것은 검색어 트렌드와 쇼핑 인사이트의 초과 구간이고, 우리는 둘 다 쓰지 않는다. 쓰게 되면 그때 비용 계약을 다시 본다.

**그래서 Trigger 에 필요한 것은 비용 상한이 아니라 한도 공유 관리다.** 한도는 키 단위라 한 워크플로의 폭주가 같은 키를 쓰는 나머지를 굶긴다. 일 25,000건을 폴링 간격으로 환산하면:

| 폴링 간격 | 워크플로 1개당 하루 | 한 키로 감당 가능한 워크플로 |
| ---: | ---: | ---: |
| 1분 | 1,440회 | 17개 |
| 5분 | 288회 | 86개 |
| **10분** | **144회** | **173개** |
| 30분 | 48회 | 520개 |
| 60분 | 24회 | 1,041개 |

**기본 폴링 간격을 10분으로 둔다.** 개인 사용자가 워크플로를 173개까지 만들 일은 드물고, 그보다 짧게 두면 몇 개만 켜도 한도가 위태로워진다. 1분 간격은 17개에서 한도가 차므로 **선택지에서 뺀다** — 고를 수 있게 두면 "왜 오늘은 안 되지"를 사용자가 겪는다.

**남은 확인.** 겹침 창(중복 방지용 재조회)이 호출 수를 얼마나 늘리는지는 실제 응답을 봐야 안다. 무료 구간 자체가 넉넉하므로 출시를 막는 문제는 아니다.

**아직 확인하지 못한 것.** 검색 API의 개별 경로(`/search/v1/blog`·`/search/v1/cafearticle`)는 위의 패턴에서 유추한 것이고 공식 문서에서 직접 보지 못했다. 구현 직전에 HUB 문서·콘솔로 대조한다.

#### 카페 API 는 살아 있다 (2026-08-30 확인)

"HUB 에 카페가 없다"를 근거로 카페 게시를 접을 뻔했는데, 확인해 보니 **카페는 이관 대상이 아니었을 뿐 그대로 있다.**

| 확인한 것 | 결과 |
| --- | --- |
| HUB(ncloud) 제공 목록 | 카페 없음 — 다만 검색·트렌드·쇼핑인사이트만 옮겨간 것이라 예상된 결과 |
| 개발자센터 카페 API 문서 | **살아 있음.** 본문 30,252자 온전, 종료·이관 공지 **0건** |
| 이용 신청 링크 | `developers.naver.com/apps/#/register?api=cafe` 라우트 응답 |
| 카페 엔드포인트 응답 | `openapi.naver.com/v1/cafe/{clubid}/menu/{menuid}/articles` → **405** |

**405 가 결정적이다.** 인증 헤더 없이 GET 하면 이 게이트웨이는 대부분 400 을 준다 — 살아 있는 블로그 검색도, 이미 종료된 쇼핑·책 검색도, 아예 없는 경로도 전부 400 이라 생사를 구분하지 못한다. 그런데 **카페 경로만 405(Method Not Allowed)** 다. 라우터가 그 경로를 알고 있고 "GET 은 허용되지 않는다"고 답한 것이다(카페 글쓰기·가입은 POST 전용). 등록되지 않은 경로였다면 400 무리에 섞였을 것이다.

**즉 검색 API 의 개발자센터 신규 신청 마감(2026-07-31)은 검색 계열에 한정된 이야기로 보인다.** 카페는 별도 트랙이다.

**남은 확인 하나.** 실제 등록 화면에서 '카페'를 사용 API 로 고를 수 있는지는 로그인이 필요해 확인하지 못했다. 개발자 계정으로 위 등록 링크를 열어 카페가 목록에 뜨는지 보면 끝난다. 뜨면 §4.2 의 `naverCafeNode` 를 계획대로 진행한다.

**비용은 별개이고 아직 모른다.** 카페 API 는 HUB 가 아니라 개발자센터에 있어 위의 HUB 요금표가 적용되지 않는다. 역사적으로 무료였으나 현재 조건은 확인하지 못했다.

### 4.1 API가 실제로 허용하는 범위

| 기능 | 공식 지원 | 구현 판단 |
| --- | --- | --- |
| 블로그 검색 | HUB로 이관, NCP key 쌍 방식 | 구현 |
| 카페글 검색 | HUB로 이관, 네이버 검색 결과 범위 | 구현 |
| 검색 결과 신규 감지 | 웹훅은 없으므로 polling으로 구성 가능 | 구현 |
| 카페 가입 | 네이버 로그인 OAuth 2.0 (개발자센터, HUB 이관 대상 아님) | 구현 — 등록 화면 확인 후 착수 |
| 카페 게시글 작성·이미지 첨부 | 네이버 로그인 OAuth 2.0 (엔드포인트 생존 확인) | 구현하되 승인 필수 |
| 특정 카페의 전체 새 글/댓글 읽기 | 공식 목록 API 확인 안 됨 | 제공하지 않음 |
| 블로그 자동 글쓰기 | 2020-05-06 종료 | 제공하지 않음 |
| 쇼핑·책·전문자료 검색 | 2026-07-31 완전 종료, 대체 없음 | 제공하지 않음 |

### 4.2 노드 구성

#### `naverSearchNode`

- modes: `blog`, `cafe_article`
- fields: `query`, `sort(sim|date)`, `display(1..100)`, `start(1..1000)`
- auth: `naver_open_api` client id/secret
- effect: `external-read`
- output: 공통 `SearchResult[]`로 정규화하되 `raw` 필드를 선택적으로 보존

#### `naverSearchTriggerNode`

- events: `new_blog_result`, `new_cafe_result`
- fields: `query`, `pollInterval`, `maxResults`, 선택적 include/exclude 도메인·작성자
- 첫 실행은 기준점만 저장하고 과거 결과를 알리지 않는다.
- cursor: `{publishedAt, canonicalLink, fingerprint}`. 날짜가 없거나 같을 때 링크+제목 hash로 중복을 제거한다.
- 검색 인덱스 지연과 순서 변경을 고려해 최근 N개 겹침 창을 다시 읽고 dedupe한다.
- 네이버 검색 API의 하루 호출 한도(25,000건)는 **키 단위로 공유**된다. 한 워크플로의 폭주가 같은 키를 쓰는 다른 워크플로를 굶기므로, 키별 일일 사용량을 세고 남은 양을 UI에 보여준다.
- **기본 폴링 간격은 10분이고 1분은 선택지에 두지 않는다**(§4.0 비용 — 1분이면 17개에서 한도가 찬다).
- 과금은 없다(검색 API에 유료 구간이 없다). 그래서 X API처럼 비용 상한을 둘 필요는 없고, **한도 소진을 미리 알리는 것**이면 충분하다 — 80%에서 경고, 100%에서 그날의 폴링 중단.

#### `naverCafeNode`

- modes: `join`, `write_article`
- fields:
  - join: `clubId`, `nickname`
  - write: `clubId`, `menuId`, `subject`, `content`, `images[]`, 공개/검색/댓글/스크랩 설정
- auth: `naver_user_oauth`
- effect: 두 mode 모두 `external-write`
- `write_article` 앞에는 기본적으로 `humanApprovalNode`를 삽입하고 preview에 카페·게시판·제목·공개 범위를 표시한다.
- timeout 시 재시도하지 않는다. 성공 응답의 `articleId`/`articleUrl`을 idempotency audit에 기록한다.
- 한국어 인코딩과 multipart 이미지 중복 파라미터를 공식 fixture로 고정한다.
- 공식 안내의 계정별 일일 처리 한도를 UI와 실행 오류에 반영한다.

### 4.3 네이버 자격증명

`credential_providers.json`의 실제 스키마에 맞춘다. `kind`는 `api_key | token_pair | compound | oauth2 | service_account` 중 하나이고, 앱 자격증명은 `compound` + `secretFormat`, 사용자 토큰은 `token_pair` + `refresh.clientCredential`로 표현한다(`google_oauth_client` ↔ `google_oauth`, `kakao` ↔ `kakao_token`과 같은 구조다).

```json
{
  "id": "naver_api_hub",
  "kind": "compound",
  "secretFormat": "key_id:key",
  "note": "NAVER API HUB(네이버 클라우드) 키 쌍. X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY 헤더로 실린다. 카페 게시에는 쓸 수 없다."
}
{
  "id": "naver_oauth_client",
  "kind": "compound",
  "secretFormat": "client_id:client_secret",
  "note": "사용자 토큰이 아니라 앱 자격증명이다. 네이버 사용자 토큰 갱신에만 쓰인다."
}
{
  "id": "naver_user_oauth",
  "kind": "token_pair",
  "scopes": [{"scope": "카페", "allows": "연결한 계정으로 카페에 가입하고 글을 씁니다."}],
  "refresh": {
    "tokenUrl": "https://nid.naver.com/oauth2.0/token",
    "clientCredential": {"provider": "naver_oauth_client", "format": "client_id:client_secret"},
    "marginMinutes": 30
  }
}
```

`backend/connectors/oauth.py`는 지금 refresh 갱신만 한다. authorize → callback → 토큰 저장 경로가 없어서 `google_oauth`·`kakao_token`은 사용자가 토큰을 직접 붙여넣는다. **이 계획은 그 공통 callback을 처음 만드는 것이고**, `state` 검증, redirect allowlist, 토큰 저장, revoke를 한 곳에 둔다. 네이버·X·Instagram이 모두 여기에 의존하므로 Phase 0에서 별도 vertical slice로 다룬다. 네이버 로그인은 요청 시 임의 scope를 늘리는 방식이 아니므로, Developer Center의 애플리케이션 API 권한에서 카페 기능만 활성화하고 연결 화면에 실제 허용 기능을 표시한다.

### 4.4 네이버 완료 조건

- 검색 페이지네이션, 429/일일 한도, HTML entity 제거와 원본 보존을 테스트한다.
- 키별 일일 사용량을 세고, 한도(25,000건)에 도달하면 그날의 폴링을 멈춘다. 한도 초과 호출 0건을 테스트로 고정한다(§4.0 비용).
- Trigger 재실행·순서 변경·동일 시각 결과에도 한 항목을 한 번만 방출한다.
- 카페 게시 preview와 승인 없이는 실제 POST가 나가지 않는다.
- 한글 제목/본문, 줄바꿈, 허용 HTML, 이미지 2개 첨부 fixture가 mock과 실제 beta에서 동일하게 직렬화된다.
- 생성기가 “네이버 블로그에 자동으로 써줘” 요청에 존재하지 않는 쓰기 mode를 만들지 않고, 검색/초안 생성/사용자 확인으로 대안을 안내한다.

## 6. 추가 한국형 서비스 후보

평가는 “국내 사용자 가치, 공식 API 명확성, 제품의 기존 노드보다 나아지는 정도, 운영 승인 난이도”를 함께 본다.

| 우선순위 | 노드 후보 | 첫 기능 | 인증 | 난이도 | 판단 |
| --- | --- | --- | --- | --- | --- |
| P1 | `naverCommerceTriggerNode` / `naverCommerceNode` | 변경 주문 수집, 상품·재고 조회, 문의 조회/답변 | Commerce OAuth 2.0 | L | 강력 추천. 스마트스토어 운영 자동화 핵심 |
| P1 | `naverWorksTriggerNode` / `naverWorksNode` | Bot callback, 메시지·파일 발송 | OAuth 2.0, service account | M~L | 강력 추천. 국내 기업 협업 흐름에 적합 |
| P1 | `openDartTriggerNode` / `openDartNode` | 새 공시, 회사·재무 조회 | API key | S~M | 추천. 읽기 전용이고 리서치 자동화 가치가 큼 |
| P1 | `rssTriggerNode` 한국 커뮤니티 preset | 루리웹 등 공식 RSS의 새 글·키워드 감지 | 없음 | S | 먼저 출시. 기존 executor를 재사용하고 공식 feed만 allowlist |
| P1 | `xTriggerNode` / `xNode` | 검색/멘션 감지, 게시·답글 | X OAuth 2.0/User context | M~L | 추천. 사용량 과금과 게시 승인·anti-spam gate 필수 |
| P1 | `instagramTriggerNode` / `instagramNode` | 댓글·멘션 감지, 이미지/Reels/Carousel 게시 | Meta/Instagram Login | L | 추천. Professional 계정과 App Review/Access gate 필수 |
| P2 | `kakaoLocalNode` | 주소↔좌표, 장소/카테고리 검색 | Kakao REST key | S | 추천. 기존 Kakao credential 일부 재사용 가능 |
| P2 | `kosisNode` | 통계표 검색·자료 조회 | API key | S~M | 추천. JSON/SDMX 정규화 필요 |
| P2 | `dataGoKrNode` | API 검색, 승인된 데이터셋 호출 | service key | M | 조건부 추천. 데이터셋별 스키마 차이를 다뤄야 함 |
| P3 | `jusoNode` | 도로명·지번·영문주소 검색 | approval key | S | 유용하지만 Kakao Local과 겹쳐 후순위 |

### 6.1 네이버 커머스

공식 커머스API는 상품, 주문, 문의, 정산, 판매자정보를 제공하며 OAuth 2.0과 API 그룹 권한을 사용한다. 첫 vertical slice는 범위를 줄인다.

- Trigger: `changed_orders`, `new_inquiry`
- Read: `list_products`, `get_product`, `list_orders`, `list_inquiries`
- Action: `change_inventory`, `acknowledge_order`, `answer_inquiry`
- 주문·문의 cursor는 KST timestamp와 provider ID를 함께 저장한다.
- 문의 답변, 주문 상태 변경은 쓰기로 분류하고 승인·감사 로그를 남긴다.
- 상품 등록 전체는 고시정보·인증·카테고리 속성 규칙이 크므로 MVP에서 제외한다.

### 6.2 NAVER WORKS

공식 API는 Bot, 캘린더, 메일, 드라이브, 게시판, 할 일을 제공한다. 모든 기능을 한 노드에 넣지 않는다.

- `naverWorksTriggerNode`: Bot message/postback callback
- `naverWorksNode`: `send_message`, `send_file`
- 후속 노드: `naverWorksCalendarNode`, `naverWorksMailNode`
- callback URL 검증, 이벤트 replay 방지, 첨부 Artifact 제한을 공통 Trigger 계약으로 검증한다.
- 조직·구성원 관리와 감사 API는 강한 권한이 필요하므로 초기 범위에서 제외한다.

### 6.3 OpenDART

- `openDartTriggerNode`: 기업/보고서 유형 필터를 둔 새 공시 polling
- `openDartNode`: `search_disclosures`, `get_company`, `get_financials`
- corp code 목록을 주기적으로 cache하고 종목코드/회사명 lookup을 제공한다.
- 첫 실행 baseline, `rcept_no` dedupe, 정정 공시를 별도 이벤트로 보존한다.
- 결과는 출처 URL, 접수번호, 보고서명, 법인/종목코드를 항상 포함한다.

### 6.4 카카오 로컬

- modes: `address_to_coord`, `coord_to_address`, `search_keyword`, `search_category`
- 기존 카카오 메시지용 사용자 token과 혼동하지 않고 REST API key provider를 재사용한다.
- 좌표계, 반경, 페이지네이션을 구조화하고 raw response를 선택적으로 보존한다.
- “장소 검색”만 먼저 만들고 경로 탐색·정적 지도는 사용량과 별도 API 조건을 확인한 뒤 추가한다.

### 6.5 한국 커뮤니티 연동

**2026-08-30 재정렬.** 처음에는 "사이트별 전용 노드 + 제휴 gate" 로 설계했는데, 실제로 두 사이트를 조사해 보니 **약관의 성격이 서로 달랐다.** 하나로 묶어 다루던 것을 갈랐다.

| 사이트 | 약관 | 판단 |
| --- | --- | --- |
| 디시인사이드 | 이용약관 제16조 — **사전 서면 동의 없는 크롤링 금지**. 조건이 아니라 전제다 | **폐기.** 개인 개발자가 서면 동의를 받을 창구가 마땅치 않다 |
| 아카라이브 | 규정 8번 — "**서버에 부하를 주는** 크롤링, 스크랩핑" 시 이용 제한 | 조건부다. 부하를 주지 않으면 규정 문언 안에 있다 |
| 에펨코리아 | 공식 개발 경로 확인 못 함 | 범위에서 뺀다(아카라이브로 대체) |
| 루리웹 | 공식 RSS 안내 있음 | 공식 경로. `rssTriggerNode` preset 으로 먼저 |

**둘의 차이가 설계를 가른다.** 디시인사이드는 "얼마나 적게 하느냐" 와 무관하게 동의가 없으면 안 되고, 아카라이브는 **양의 문제**다. 그래서 아카라이브는 전용 노드가 아니라 **호출량을 스스로 제한하는 범용 수집 노드**로 다룬다 — 사이트마다 전용 노드를 만들면 그 수만큼 약관을 따로 관리하게 된다.

**다만 아카라이브도 조심할 이유가 있다.** 운영사가 "DDOS 및 크롤링에 의한 서비스 장애" 공지를 낸 적이 있고, 공식 API·RSS 가 없어 HTML 을 읽어야 한다. 규정 문언 안에 있다는 것과 환영받는다는 것은 다르므로 **기본값을 아주 보수적으로** 둔다.

#### 채택: 범용 수집 노드를 제대로 만든다

사이트별 전용 노드 대신 기존 `webCrawlerNode` 를 쓸 만하게 고친다. 지금은 `requests.get` 후 텍스트 5,000자를 자르는 것이 전부다.

| 넣을 것 | 이유 |
| --- | --- |
| 구조화 추출(제목·본문·링크·발행일) | 통짜 텍스트는 하류 LLM 이 제목과 광고 문구를 구분하지 못한다 |
| `robots.txt` 준수 | 사이트가 "여기는 읽지 말라" 고 밝힌 곳을 존중한다. 약관과 별개로 기본 예의다 |
| **호스트별 호출량 상한** | 아카라이브 규정의 "서버에 부하" 를 우리가 먼저 막는다. 네이버 검색과 같은 방식(`rate_limit.py`)을 쓴다 |
| 요청 간 최소 간격 | 하루 총량이 적어도 한꺼번에 몰면 부하다 |
| 크기·시간 상한, SSRF 검사 | 이미 `url_guard` 에 있다 |

**차단 목록은 유지한다.** `url_guard.PARTNERSHIP_REQUIRED_HOSTS` 의 디시인사이드·에펨코리아는 그대로 둔다 — 기능을 폐기했다고 해서 우회 경로를 열어 둘 이유가 없다.

#### 구현 결과 (2026-08-30 완료)

| 파일 | 역할 |
| --- | --- |
| `backend/web_extract.py` (신규) | HTML → 제목·발행일·작성자·본문·링크. **네트워크에 나가지 않는 순수 함수**라 실제 페이지를 저장해 두고 회귀 테스트를 돌릴 수 있다 |
| `backend/url_guard.py` | `robots_policy()`(RFC 9309), 호스트별 최소 간격, `_spend_budget()` |
| `backend/rate_limit.py` | `crawl.fetch` = 50회/일. 주체가 사용자가 아니라 **호스트**라 사용자가 늘어도 상대 서버가 받는 총량은 늘지 않는다 |
| `backend/node_generators/action_nodes.py` | `output`(text/structured/links)·`maxChars`·`respectRobots` 를 생성 코드에 반영. `db=db` 를 넘겨야 상한이 실제로 센다 |
| `frontend/src/customNodes.jsx` | 위 세 가지 입력 UI |

정한 것들과 그 이유:

- **robots.txt 5xx 는 거부다.** RFC 9309 의 "알 수 없음" 이다. 허용으로 두면 사이트가 불안정할 때 우리가 가장 세게 때리게 된다.
- **429·503 에 재시도하지 않는다.** 부하를 줄이자는 장치가 재시도로 부하를 늘리면 앞뒤가 안 맞는다.
- **예산을 먼저 쓰고 나서 기다린다.** 순서가 반대면 어차피 거부할 요청을 위해 잠든다.
- **User-Agent 를 위장하지 않는다.** 상대가 우리를 식별하고 차단할 수 있어야 robots 를 지키는 것에 뜻이 있다.
- **Crawl-delay 가 30초를 넘으면 기다리지 않고 거부한다.** 그런 사이트는 자동 수집 대상이 아니다.

테스트 78건(`test_web_extract.py` 42, `test_url_guard_politeness.py` 36). 마지막 6건은 워크플로우를 실제로 컴파일해 실행한다 — `url_guard` 가 127.0.0.1 을 막으므로 로컬 서버를 띄울 수 없어 `requests.get` 을 갈아 끼운다.

읽기 결과는 아래 공통 `CommunityPost` 로 정규화하되, 원문 전체를 장기 보관하지 않는다.

```json
{
  "provider": "ruliweb",
  "communityId": "ruliweb",
  "boardId": "community/board/300143",
  "postId": "provider-stable-id",
  "title": "새 글 제목",
  "excerpt": "feed가 제공한 짧은 요약",
  "publishedAt": "2026-08-30T12:00:00Z",
  "canonicalUrl": "https://...",
  "tags": ["키워드"],
  "sourceMethod": "official_rss"
}
```

#### 공식 feed 경로 (먼저 출시)

- 기존 `rssTriggerNode` 에 `providerPreset: ruliweb` 과 게시판 URL 입력 UX 를 추가한다. 루리웹이 안내한 `.../board/{게시판번호}/rss` 규칙만 허용하고 URL 을 canonicalize 한다.
- **기존 노드 계약을 깨지 않는 방식으로 얹는다.** `rssTriggerNode` 는 지금 mode 가 `new_item` 하나이고 `outputSchemaByMode.new_item` 이 고정돼 있다. `new_item` 은 그대로 두고 `keyword_match` 를 추가한다.
- **cursor 를 먼저 고친다.** `rss.py:117` 은 cursor 를 매번 현재 피드 id 전체로 교체하므로 밀려났다 돌아온 항목이 재통지된다(§2 불일치 12). `naverSearchTriggerNode` 에서 쓴 겹침 창을 그대로 옮긴다.
- 첫 실행은 baseline 만 만들고 `guid` 가 없으면 canonical URL 과 게시 시각의 hash 로 dedupe 한다.
- 출력에는 제목, 요약, 게시 시각, 원문 URL 만 기본 보존한다. 작성자명은 workflow 가 명시적으로 요청할 때만 전달하고 원문 HTML·이미지를 재호스팅하지 않는다.
- 클리앙·뽐뿌·인벤 등 2차 후보는 구현 직전에 공식 API/RSS 와 이용 조건을 각각 재검증한다.

#### 폐기한 것 (2026-08-30)

- **`dcinsideTriggerNode`** — 서면 동의가 전제인데 받을 창구가 마땅치 않다. 차단 목록은 유지한다.
- **`fmKoreaTriggerNode`** — 공식 경로를 확인하지 못했고, 아카라이브로 대체한다.
- 두 사이트의 제휴 문의 자료 작성도 함께 뺀다.


### 6.6 X

- `xTriggerNode`: `new_matching_post`, `new_mention`을 우선 제공한다. 기본은 recent search/timeline polling과 `since_id` cursor이며, `filtered_stream` 또는 webhook은 연결 계정에서 실제 이용 가능성과 비용을 확인한 뒤 선택적으로 노출한다.
- `xNode`: `search_recent`, `get_post`, `create_post`, `reply`, `delete_post`를 제공한다. media upload, Like/Follow/DM 자동화는 MVP에서 제외한다.
- app-only Bearer token 읽기와 user-context 쓰기 자격증명을 구분한다. 연결 점검은 실제 scope, endpoint 접근 가능 여부, rate-limit header, 과금 budget을 반환한다.
- 게시·답글·삭제는 preview와 human approval을 요구하고 timeout 시 자동 재시도하지 않는다. `clientRequestId`와 반환된 Post ID로 idempotency를 보조한다.
- 검색/stream 결과는 `postId`, `authorId`, `text`, `createdAt`, `conversationId`, `editHistoryIds`, `canonicalUrl`로 정규화한다. 수정본과 삭제 통지를 반영하고 원문 보존 기간을 최소화한다.
- workspace별 월 비용 상한, 시간당 읽기/쓰기 상한, 규칙 수 상한을 두고 80%/100%에서 경고/중단한다. 대량 답글, 자동 Follow/Unfollow, engagement 조작 workflow는 생성기 hard negative로 막는다.

### 6.7 Instagram

- 대상은 Instagram Professional(Business/Creator) 계정이다. 개인 계정은 연결 UI에서 명확히 지원하지 않는다고 표시한다.
- `instagramTriggerNode`: webhook 기반 `new_comment`, `new_mention`부터 시작한다. 메시지는 별도 권한·응답 정책이 있으므로 후속 `instagramMessageTriggerNode`로 분리한다.
- `instagramNode`: `list_media`, `get_insights`, `publish_image`, `publish_reel`, `publish_carousel`, `reply_comment`를 제공한다. Story 게시 범위는 계정 유형과 최신 공식 제한을 다시 확인한 뒤 추가한다.
- 게시 과정은 `media container 생성 -> 제한된 status polling -> media_publish` 상태 머신으로 만들고, 각 단계의 container/media ID를 실행 상태에 저장한다.
- Meta가 게시 시 media URL을 가져갈 수 있도록 Artifact를 짧은 만료의 서명된 공개 URL로 staging한다. provider IP만으로 고정하지 말고 추측 불가능한 token, MIME/크기 검사, 다운로드 횟수 제한, 만료 후 즉시 폐기를 적용한다.
- 다중 고객 beta 전 App Review, 필요한 permission의 Advanced Access, Business verification을 완료한다. `instagram_business_basic`, `instagram_business_content_publish`, 댓글/insights 권한은 mode별 최소 scope로 나눈다.
- follower scraping, 개인 계정 접근, 자동 Like/Follow, 수신 이력이 없는 사용자에게 보내는 대량 DM은 제공하지 않는다. 게시와 공개 댓글 답변에는 preview·승인·감사 로그를 적용한다.

### 6.8 KOSIS·공공데이터·도로명주소

- `kosisNode`: 통계목록 검색과 통계자료 조회를 분리하고 JSON 결과를 long-form row로 정규화한다. 공식 제한인 분당 호출 수와 cell 수를 사전 계산해 너무 큰 요청을 거부한다.
- `dataGoKrNode`: 임의 URL 프록시가 아니라 승인된 `datasetId + operationId` registry만 호출한다. 데이터셋별 OpenAPI schema를 캐시하고 XML/JSON 응답을 공통 envelope로 만든다.
- `jusoNode`: 주소 검색 결과를 도로명, 지번, 우편번호, 영문주소의 고정 schema로 제공한다.
- 공공 데이터는 각 상세 페이지의 이용허락범위와 출처 표시 요구를 결과 metadata에 보존한다.

## 7. 공통 구현 아키텍처

모든 외부 서비스 노드는 ADR-0007/0008의 기준을 그대로 따른다.

```text
node_definitions/{service}Node.json
  -> UI / Inspector / validator / LLM catalog
     (backend/node_definition.py 가 검증, export_node_definitions.py 가 프론트로 내보냄)
credential_providers.json
  -> API Center / encrypted credential binding
     (kind: api_key | token_pair | compound | oauth2 | service_account)
error_catalog.json
  -> 새 오류 code 는 여기 먼저 등록하고 export 로 재생성
backend/connectors/services/{service}.py
  -> auth/signing / request / pagination / normalization
backend/node_generators/connector_nodes.py
  -> thin wrapper only
backend/community_sanitize.py
  -> 신규 타입의 정화 규칙(없으면 커뮤니티 공개가 거부되고 테스트가 깨진다)
mock fixture
  -> success / auth_failed / rate_limited / not_found / timeout / invalid input
telemetry + audit
  -> provider / mode / latency / normalized error / effect state
```

### Trigger 상태 모델

서비스마다 임의 JSON 파일을 만들지 않는다. 다만 **cursor store를 새로 만드는 것이 아니라 이미 있는 것을 확장한다.** 현재는 `models.NodeMemory`를 `session_id='__cursor__'`로 재사용해 `(project_id, node_id)`에 JSON 한 덩어리를 넣는다(`backend/graph.py:265-286`). 여기에는 workspace 격리, lease, cursor 버전, provider 구분이 없다.

```text
ConnectorCursor            현재 NodeMemory 대비
  workspace_id             신규 (ADR-0024 workspace 도입분과 맞춘다)
  project_id               있음
  node_id                  있음
  provider                 신규
  cursor_version           신규 (형식이 바뀔 때 안전하게 버린다)
  cursor_json              있음 (history 컬럼)
  lease_owner              신규
  lease_expires_at         신규
  updated_at               있음
```

- 새 표를 쓰든 `NodeMemory`에 컬럼을 더하든 Alembic 마이그레이션과 기존 cursor 이관이 필요하다(ADR-0006). YouTube·RSS·Gmail Trigger가 이미 옛 형식을 쓰고 있으므로, 이관 전에는 `cursor_version` 없는 값을 첫 실행이 아니라 **기존 baseline**으로 읽어야 한다. 잘못 읽으면 세 노드가 과거 항목을 한 번씩 다시 통지한다.
- cursor update와 event enqueue를 같은 transaction 또는 outbox로 묶는다.
- polling worker의 중복 실행을 lease로 막는다.
- provider event ID가 있으면 최우선 dedupe key로 사용한다.
- 첫 실행 `baseline_only`, 과거 N개부터 알림 `backfill`, 지정 시점 이후 `since`를 명시적으로 선택하게 한다.

### side effect와 승인

| Node Definition 분류 | 예 | 정책 |
| --- | --- | --- |
| `none` | HWPX inspect/validate | 바로 실행 |
| `external-read` | 네이버 검색, DART 조회, 공식 커뮤니티 feed, X 검색 | 제한된 retry와 cache 허용 |
| `none` + `filesystem` capability | HWPX create/fill | 경로·용량·artifact 권한 검증 |
| `external-write` | 카페/X/Instagram 게시, 공개 댓글 답변, 상품 가격 변경 | preview, 승인, audit, timeout 자동 재시도 금지 |

### 오류 코드 초안

`error_catalog.json`이 정본이다(ADR-0016). 아래 code를 쓰려면 먼저 그 파일에 `category`(현재 8종)와 `resolution`(현재 9종)을 붙여 등록하고 `python backend/export_node_definitions.py`로 `frontend/src/generated/errorCatalog.json`과 `Documents/ERROR_CATALOG.md`를 재생성한다. 코드 문자열을 실행 경로에 직접 쓰지 않는다. 아래 목록은 초안이며, 기존 39개 code 중 `CREDENTIAL_*`·`CONNECTOR_RATE_LIMITED`·`CONNECTOR_QUOTA_EXCEEDED`로 이미 표현되는 것은 새로 만들지 않고 재사용한다 — 새 code는 **사용자 조치나 제품 처리 방식이 실제로 다를 때만** 나눈다.

| 제안 code | category | resolution | 신규로 둘 이유 |
| --- | --- | --- | --- |
| `HWPX_INVALID_PACKAGE` | artifact | reselect_file | 파일을 다시 고르는 것 외에 방법이 없다. `ARTIFACT_UNSUPPORTED_TYPE`은 확장자 문제라 조치가 다르다 |
| `HWPX_UNRESOLVED_PLACEHOLDER` | validation | focus_field | 어떤 키가 안 채워졌는지 알려주고 그 필드로 이동시킨다 |
| `HWPX_UNSUPPORTED_FEATURE` | validation | focus_field | 지원하지 않는 블록을 지우거나 바꾸게 한다 |
| `HWP_BINARY_UNSUPPORTED` | artifact | reselect_file | `.hwpx`/`.docx`로 변환해 다시 올리라는 안내가 고유하다 |
| `NAVER_DAILY_QUOTA_EXCEEDED` | connector | wait_then_retry | 하루 한도라 재시도 시점이 `CONNECTOR_RATE_LIMITED`와 다르다(다음날) |
| `NAVER_BLOG_WRITE_UNAVAILABLE` | validation | none | 재시도로 풀리지 않는 폐지된 기능이다. 대안 안내가 본문이다 |
| `COMMUNITY_PARTNERSHIP_REQUIRED` | validation | none | 제휴 전 호출을 네트워크 이전에 끊는다 |
| `COMMUNITY_FEED_NOT_ALLOWLISTED` | validation | focus_field | 허용된 공식 feed URL로 고치게 한다 |
| `COMMUNITY_CONTENT_REMOVED` | connector | none | 원문 삭제·비공개 전환을 하류 노드가 구분해야 한다 |
| `X_API_BUDGET_EXCEEDED` | connector | none | 워크스페이스 비용 상한이라 대기로 풀리지 않는다 |
| `INSTAGRAM_PROFESSIONAL_ACCOUNT_REQUIRED` | credential | diagnose_connection | 계정 유형 전환이라는 고유 조치가 있다 |
| `INSTAGRAM_APP_REVIEW_REQUIRED` | credential | none | 사용자가 아니라 운영이 풀어야 한다 |
| `INSTAGRAM_MEDIA_STAGING_FAILED` | artifact | retry | container 생성 전 staging 단계 실패를 게시 실패와 구분한다 |
| `PUBLIC_DATA_LICENSE_REVIEW_REQUIRED` | validation | none | 이용허락범위 미확인 데이터셋 호출을 막는다 |

기존 code로 충분해 **새로 만들지 않는 것**: 카페 권한 부족·X scope 부족·Instagram 권한 부족은 `CREDENTIAL_FORBIDDEN`, 일반 rate limit은 `CONNECTOR_RATE_LIMITED`를 쓴다. v1.1 목록의 `NAVER_CAFE_PERMISSION_DENIED`, `COUPANG_SELLER_CREDENTIAL_REQUIRED`, `X_SCOPE_REQUIRED`는 그래서 뺐다.

오류의 상대 서비스 원문은 내부 진단 로그에만 두고 사용자에게는 수정 가능한 조치와 `requestId`를 보여준다.

## 8. 구현 단계와 예상 규모

아래 추정은 1명의 숙련된 풀스택 개발자 기준의 상대 규모이며 외부 서비스 심사·제휴 대기 시간은 제외한다.

### Phase 0 이전 — 지금 새고 있는 것 — **2026-08-30 완료**

이 계획을 승인하지 않아도 따로 고쳐야 하는 항목이었다. 어느 것도 새 노드에 의존하지 않는다.

- ~~**템플릿 덮어쓰기 제거**(§2 불일치 3)~~ — 완료. `templateAnalyzerNode`는 키 불일치 재생성 분기를 걷어냈고(`template_nodes.py`), `fileModifierNode`는 덮어쓰는 대신 **있는 빈칸과 채우려는 키를 함께 알리며 실패**한다. "파일이 없으면 즉석 생성"은 잃을 것이 없으므로 그대로 뒀다.
- ~~**`mimetype` STORED 보존**(§2 불일치 4)~~ — 완료. `namelist()` 대신 `infolist()`를 들고 다니며 각 entry의 `compress_type`·순서·속성을 원본에서 복사한다.
- ~~**`python-hwpx` 버전 고정**(§2 불일치 1)~~ — 완료. `python-hwpx==3.4.1`(설치본과 동일).
- ~~**큐레이션 템플릿의 `.hwp` 참조를 `.hwpx`로 교정**(§2 불일치 7)~~ — 완료(2곳).
- ~~**`webCrawlerNode` URL 안전 게이트**(§2 불일치 11, §6.5 선택지 A)~~ — 완료. 신규 `backend/url_guard.py`가 scheme → DNS 해석 → 해석된 IP → 리다이렉트 매 홉을 검사하고 본문 5MB 상한을 건다.

#### 구현 진행 상황 (2026-08-30)

**`backend/url_guard.py` (신규).** 호스트 **이름**이 아니라 **해석 결과**를 본다 — 이름만 보면 `http://[내부IP]`나 사설 IP를 가리키는 공개 도메인을 놓친다. `ipaddress.is_global`로 사설·루프백·링크로컬(169.254.169.254 포함)·멀티캐스트·예약 대역을 한 번에 거른다. 리다이렉트는 `requests`에 맡기지 않고 직접 따라가며 홉마다 재검사한다 — 자동으로 따라가면 최종 목적지가 검사를 안 거친다(공개 도메인 → 내부 주소로 302 하는 고전적 우회).

제휴 전 커뮤니티(`dcinside.com`, `fmkorea.com`)는 `PARTNERSHIP_REQUIRED_HOSTS`로 서브도메인까지 함께 막는다. §11 비목표가 문서에만 있지 않게 하는 장치다.

**남은 한계 하나.** 검사 시점과 접속 시점 사이 DNS rebinding은 이 방식으로 완전히 막지 못한다. A/AAAA 레코드를 전부 확인해(하나라도 사설이면 거부) 단순한 형태는 걸러내지만, 완전한 차단은 해석한 IP로 직접 접속하며 Host 헤더를 붙여야 한다. 현재 위협 모델에서는 과한 복잡도로 판단해 모듈 docstring에 명시만 했다.

**검증.** `backend/test_url_guard.py`(SSRF 벡터 15종 + 노드 실행 경로 3종), `backend/test_template_safety.py`(서식 보존·mimetype·값 채움 8종) 신규 27개 통과. 전체 924개 통과 — 기존 실패 2건(`test_llm_providers.py`)은 이 작업과 무관한 모델 기본값 불일치다.

**적용 범위 — 2026-08-30 결정.** 게이트는 `webCrawlerNode`에만 건다. `httpRequestNode`(`connectors/services/http_request.py`)는 URL 검증 없이 **그대로 두기로 했다** — 사설 IP를 막으면 사내망·자체 호스팅 연동이 깨지는데 "임의 HTTP 요청"이 그 노드의 존재 이유다. SSRF 노출이 남는다는 것을 알고 받아들인 결정이다(`ROADMAP.md` §7 열린 질문 9). `rssTriggerNode`는 scheme만 보는 상태 그대로다.

### Phase 0 — 계약·테스트 기반 — **2026-08-30 완료**

- ~~**공통 OAuth 인가 코드 callback 구현**(§2 불일치 10)~~ — **2026-08-30 완료**. 아래 구현 진행 상황 참고
- ~~Naver OAuth client/token provider를 `credential_providers.json`의 실제 `kind`로 등록(§4.3)~~ — **완료**. X·Instagram provider는 각 Phase 착수 때 등록한다
- ~~Trigger cursor 저장소 확장과 lease/idempotency helper 확정~~ — **2026-08-30 완료**. 아래 구현 진행 상황 참고
- ~~신규 노드의 `community_sanitize` 정화 규칙 등록 절차 확정(ADR-0021)~~ — **완료**
- ~~한국 서비스 공통 mock fixture 형식 확정~~ — **완료**. normalized output 규칙은 서비스별 출력이 실제로 나오는 Phase 2 에서 정한다
- ~~공식 문서 URL과 확인일을 connector metadata에 저장~~ — **완료**
- ~~커뮤니티 connector에 근거와 만료일을 의무화~~ — **완료**

완료 기준: credential이 graph/revision/log에 남지 않고, Trigger replay 테스트가 공통 helper로 통과하며, cursor 이관 후 기존 YouTube·RSS·Gmail Trigger가 과거 항목을 재통지하지 않는다.

#### 구현 진행 상황 (2026-08-30) — 새 연동 노드가 함께 내야 하는 것

Phase 0 의 나머지는 노드를 만드는 일이 아니라 **노드를 만들 때 무엇을 함께 내야 하는지 정하는** 일이다. 한국형 노드만 15종 가까이 들어올 예정이라 "이번엔 mock 을 빠뜨렸네"를 사람이 알아채는 방식으로는 버티지 못한다. 그래서 셋 다 **로드 시점에 거부되게** 만들었다.

**1. mock 계약** (`connectors/mock.py` 의 `required_scenarios`/`validate_mock`). 규칙은 지어내지 않고 이미 있는 7개 연동 정의에서 뽑았다.

| 시나리오 | 누가 | 왜 |
| --- | --- | --- |
| `success`·`timeout` | 모든 연동 | 네트워크를 타는 한 지연은 항상 가능하다 |
| `auth_failed`·`rate_limited` | **자격증명이 필요한** 연동만 | RSS 처럼 비로그인으로 읽는 연동에 "인증 실패"를 요구하면 재현 못 할 상황을 지어내게 된다 |

이름만 맞고 상황을 재현하지 않는 것도 잡는다 — `auth_failed` 인데 200 을 돌려주거나 `timeout` 인데 504 를 돌려주면 거부한다. 그런 mock 은 목업 탭에서 초록불을 켜면서 실제로 사용자를 막는 경로를 하나도 알려주지 않아 없느니만 못하다. 기존 7개 정의는 규칙을 이미 전부 만족했다(규칙을 데이터에서 뽑았으므로 당연하지만, 앞으로가 다르다).

**2. 출처 기록** (`ConnectorSpec.docsUrl`/`verifiedAt`). 외부 API 는 조용히 바뀐다. 기존 7개 연동에 `docsUrl` 을 채웠고, **모든 연동이 `docsUrl` 을 갖는지 테스트로 고정**했다. `verifiedAt` 은 **일부러 비워 뒀다** — 그 값의 뜻이 "사람이 그 문서를 마지막으로 직접 확인한 날"이라서, 확인하지 않고 오늘 날짜를 적으면 기록 자체가 거짓이 된다. 날짜는 `YYYY-MM-DD` 만 받는다(형식이 섞이면 만료 비교가 조용히 실패하는데, 하필 만료된 근거를 유효하다고 읽는 쪽으로 틀린다).

**3. 자동 처리 근거**(`TermsGate`)**와 그 의무화.** `basis` 는 `official_feed`/`official_api`/`written_partnership` 셋만 받는다 — "공개돼 있으니 괜찮다"는 근거가 아니다. 만료되면 `new_session()` 에서, 즉 **HTTP client 를 만들기 전에** 끊는다("실수로 한 번 나갔다"가 없게).

의무화는 자기 신고로 두지 않았다. **어느 호스트가 제휴 대상인지는 `url_guard.PARTNERSHIP_REQUIRED_HOSTS` 한 곳에서만 정하고** `ConnectorSpec` 이 그 판정을 그대로 쓴다 — `baseUrl` 이 그 호스트를 가리키면 `termsGate` 없이는 정의가 로드되지 않는다. 이렇게 묶지 않으면 "범용 크롤러에서는 막는데 전용 connector 로는 그냥 나간다"가 되어 §11 비목표가 반쪽이 된다.

오류 code 는 `ConnectorError` 에 `terms_blocked` 를 더하고 catalog 에서는 기존 `CONNECTOR_INVALID_REQUEST` 로 매핑했다. 전용 code(`COMMUNITY_PARTNERSHIP_REQUIRED`)는 **커뮤니티 connector 가 실제로 나올 때** 등록한다 — 지금 만들면 사용자 조치가 다르지 않은 code 를 늘리는 셈이고, 그건 `error_catalog.json` 자신의 규칙에 어긋난다.

**정화 규칙은 이미 자동이었다.** `community_sanitize.rule_for()` 가 정의의 `kind == "secret"`·`credential`·`attachments` 필드에서 규칙을 파생하므로, 새 연동 노드는 정화 표를 따로 쓸 필요가 없다. 확인만 하고 그 사실을 테스트로 고정했다(`httpRequestNode` 로 검증 — YouTube 는 자격증명을 필드가 아니라 `connector.credentials` 로 선언해서 파생 대상이 아니다).

**검증.** `test_connector_contract_phase0.py` 46개. 전체 1022개 통과 — 기존 실패 2건은 이 작업과 무관하다. 새 규칙이 기존 7개 연동을 하나도 깨지 않는 것도 테스트로 고정했다(회귀 0).

**미룬 것 하나.** "normalized output 규칙"은 정하지 않았다. 지금 정하면 실제 서비스 응답을 하나도 안 본 채로 공통 출력 형태를 지어내게 된다 — 네이버 검색·커뮤니티 글이 각각 나온 뒤 Phase 2 에서 세 개를 놓고 정하는 편이 낫다.

#### 구현 진행 상황 (2026-08-30) — OAuth 인가 코드 callback

**`backend/connectors/oauth_flow.py` (신규).** 기존 `oauth.py` 가 "만료된 토큰을 어떻게 새로 고치나"였다면 이건 "애초에 어떻게 받나"다. 서비스마다 다른 부분(동의 URL, 토큰 URL, scope 를 싣는 방식, PKCE 여부, refresh_token 을 받기 위한 추가 파라미터)은 전부 `credential_providers.json` 의 새 `authorize` 선언으로 옮겼고 절차는 한 곳에만 둔다.

지키는 것 다섯 가지 — 각각 테스트로 고정했다.

| 지키는 것 | 왜 | 어긴 경우 |
| --- | --- | --- |
| state 는 **서버가** 만들고 저장한다 | 클라이언트가 만든 값을 믿으면 CSRF 로 남의 계정에 공격자 토큰을 붙인다 | `STATE_UNKNOWN` |
| state 는 **한 번만** 쓴다 | 인가 코드 재생 공격 | `STATE_ALREADY_USED` — 토큰 endpoint 를 아예 부르지 않는다 |
| redirect_uri 는 **요청이 정하지 않는다** | 받는 순간 공격자 서버로 코드를 보낼 수 있다 | `REDIRECT_NOT_ALLOWED` |
| `return_to` 는 **상대 경로만** | 아니면 이 엔드포인트가 열린 리다이렉터가 된다 | `BAD_RETURN_TO` (`//evil.com` 같은 스킴 상대 URL 포함) |
| PKCE 는 **선언으로** 켠다 | 지원하지 않는 provider 에 보내면 오류를 낸다 | `usesPkce: false` 면 안 보낸다 |

**저장 위치를 바꾸지 않은 것이 설계의 핵심이다.** 토큰은 수동 붙여넣기와 똑같이 `user_api_keys` 에 들어간다. 그래서 `oauth.ensure_fresh_token` 과 `{{API_CENTER:...}}` 치환 경로를 **한 줄도 고치지 않았다** — 동의로 받은 토큰이 기존 자동 갱신을 그대로 탄다(테스트로 고정).

**HTTP 표면 3개** (`main.py`). 시작·해제는 다른 API 키와 같이 sudo 토큰이 필요하고, **콜백만 공개**다 — provider 가 브라우저를 보낼 때 Authorization 헤더가 없기 때문이다. 그래서 "누구의 토큰인가"는 세션이 아니라 state 가 정한다.

```
POST   /api/oauth/{provider}/start      sudo   동의 URL + 콘솔에 등록할 콜백 주소
GET    /api/oauth/{provider}/callback   공개    교환 후 303 으로 우리 화면 복귀
DELETE /api/oauth/{provider}            sudo   해제(상대 통보 실패해도 로컬은 지운다)
```

콜백은 **어떤 실패에서도 사이트 밖으로 보내지 않는다.** 동의 거부·state 실패 모두 `/api-center?oauth_error=...` 로 303 한다.

**설정.** `OAUTH_REDIRECT_BASE_URL` 에 쉼표로 여러 origin 을 둘 수 있고(운영 + 로컬), 첫 번째가 기본값이다. 사용자가 콜백 주소를 추측하지 않도록 `/api/credential-providers` 응답의 동의형 provider 에 `callback_url` 을 함께 실었다.

**화면 연결 (2026-08-30 추가).** Phase 0 에서 엔드포인트만 만들고 **버튼을 붙이지 않아** 사용자가 동의 절차를 시작할 방법이 없었다. 실제로 네이버 앱을 등록한 사용자가 막혀서 드러났다. `ApiCenterPage` 의 동의형 provider 카드에 다음을 넣었다.

- **연결하기** 버튼 — `/api/oauth/{id}/start` 를 sudo 토큰으로 부르고 받은 동의 URL 로 이동한다. `return_to` 는 그 provider 카드로 되돌아오게 준다.
- **콘솔에 등록할 Callback URL** 을 카드에 그대로 보여준다. 추측하면 `redirect_uri_mismatch` 만 보게 된다.
- 돌아왔을 때 `?connected=` / `?oauth_error=` 를 읽어 결과를 알린다(동의 취소는 따로 문구를 준다).
- 수동 토큰 입력란은 남기되 "정상 경로는 위 연결하기" 라고 낮춘다.

**교훈.** "엔드포인트를 만들었다"와 "사용자가 쓸 수 있다"는 다르다. Phase 0 완료 조건에 화면 경로가 없었던 것이 원인이고, 앞으로 연결이 필요한 provider 를 추가할 때는 카드까지가 한 벌이다.

**등록한 provider 3개**(§4.3 설계대로). `naver_open_api`(compound, 검색 전용), `naver_oauth_client`(compound, 앱 자격증명), `naver_user_oauth`(token_pair + refresh + authorize). 네이버는 인가 요청에 scope 를 싣지 않고(개발자센터 설정을 따른다) 토큰 교환에는 state 를 요구해서, 그 둘을 각각 `scopes: []` 와 `sendStateOnTokenExchange` 선언으로 표현했다. `google_oauth` 에도 `authorize` 를 얹어 기존 provider 로 흐름을 검증했다(수동 붙여넣기 경로는 그대로 둔다).

**마이그레이션 0016** `oauth_states`. 왕복 1회분(state·PKCE verifier·redirect_uri·return_to·만료·소비 시각)을 담고, 쓰거나 만료된 행은 `purge_expired()` 가 치운다.

**검증.** `test_oauth_flow.py` 29개(흐름·state·PKCE·저장·해제), `test_oauth_endpoints.py` 30개 검사(HTTP 경계, 임시 DB 하위 프로세스). 전체 954개 통과 — 기존 실패 2건은 이 작업과 무관한 `test_llm_providers.py` 의 모델 기본값 불일치다. 운영 서버 재시작 후 실제 응답도 확인했다(비로그인 start → 401, 콜백 거부 → 303 `/api-center?oauth_error=denied`).

**아직 실제 네이버 계정으로는 검증하지 않았다.** 개발자센터 앱 등록과 콜백 URL 등록이 사용자 계정에 묶인 작업이라 대신 할 수 없다. 토큰 endpoint 를 가짜로 둔 왕복까지만 확인했고, `authorizeUrl`·`tokenUrl` 은 구현 직전 공식 문서로 다시 대조해야 한다(§12).

#### 구현 진행 상황 (2026-08-30) — Trigger cursor 저장소

**`backend/connectors/cursor.py` (신규)와 마이그레이션 0017 `connector_cursors`.** 예전에는 이 로직이 `graph.py` 안에서 **문자열로 조립돼 생성 코드에 박혀 있었고**(그래서 테스트할 방법이 없었다) 저장은 `NodeMemory` 를 `session_id='__cursor__'` 로 빌려 썼다. 대화 기억용 표에 세션이 아닌 상태를 끼워 넣은 것이라 workspace 격리·provider 구분·형식 버전·lease 를 둘 자리가 없었다. 지금은 모듈이 정본이고 `graph.py` 는 얇은 wrapper 만 낸다.

**이 작업의 위험은 표를 만드는 게 아니라 값을 잃는 것이었다.** 트리거는 빈 cursor 를 "첫 실행"으로 읽고 아무것도 알리지 않는다(`rss.poll_new_items` 의 `first_run = not cursor`). 뒤집으면 **있는 cursor 를 못 읽고 `{}` 로 강등하는 순간 지난 글이 전부 새 글로 쏟아진다.** 그래서 세 겹으로 막았다.

| 겹 | 내용 |
| --- | --- |
| 마이그레이션 | 표 생성과 **같은 트랜잭션에서** `node_memory` 의 `__cursor__` 행을 복사한다. 프로젝트가 지워진 cursor 는 조인으로 빠지고, 대화 기억은 옮기지 않는다 |
| 이행기 읽기 | 새 표에 행이 없으면 옛 자리를 한 번 더 본다. 마이그레이션 뒤에 남은 행이 있어도 재통지가 안 난다 |
| 실패를 삼키지 않음 | 깨진 JSON·모르는 `cursor_version` 은 `{}` 로 강등하지 않고 `CursorUnreadable` 로 올린다 — 조용히 과거를 통지하느니 시끄럽게 실패하는 편이 낫다 |

**lease.** 같은 노드를 두 워커가 동시에 폴링하면 둘 다 통지한다. `acquire_lease`/`release_lease`/`purge_stale_leases` 로 먼저 잡은 쪽만 진행하게 했다. 같은 주인의 재획득은 갱신이고(한 실행 안에서 스스로를 막지 않는다), 프로세스가 죽어 release 를 못 불러도 만료로 풀린다. **아직 트리거 실행 경로에 연결하지는 않았다** — 지금 배포는 `--workers 1` 이라 중복 폴링이 나지 않고, 연결 지점은 스케줄러 구조와 함께 정하는 편이 낫다.

**옛 값은 지우지 않는다.** 되돌릴 때 필요하고 이행기 읽기의 근거도 된다. 크기도 작다.

**검증.** `test_connector_cursor.py` 22개 — 왕복·workspace/provider 기록·프로젝트 격리·이행기 읽기·읽기 실패·lease 6종, 그리고 **실제 `alembic upgrade` 를 돌려 값이 옮겨지는지** 확인하는 마이그레이션 테스트 2개. 그 밖에 RSS 트리거를 두 번 돌려 재통지가 없는 것과, 옛 자리에만 cursor 가 있을 때도 새 글 하나만 통지하는 것을 통합으로 확인했다. 전체 976개 통과.

**운영 반영.** 마이그레이션 0017 적용 완료(`alembic head: 0017_connector_cursors`). 옮길 cursor 는 0건이었다 — 아직 트리거를 돌린 프로젝트가 없어서 이번 배포는 재통지 위험 자체가 없었다.

**남은 것.** 계획 §7 이 함께 적은 "cursor update 와 event enqueue 를 같은 transaction 또는 outbox 로 묶는다"와 첫 실행 모드 선택(`baseline_only`/`backfill`/`since`)은 아직이다. 둘 다 트리거를 실제로 늘릴 때(Phase 2 이후) 필요해지는 것이라 그때 다룬다.

### Phase 1 — HWPX, 2~3인주 — **진행 중**

- ~~공용 `backend/documents/hwpx/` package 도입~~ — **2026-08-30 완료**
- ~~안전한 reader/writer, run-aware placeholder engine~~ — **완료**
- ~~기존 analyzer/modifier를 공용 엔진으로 이관~~ — **완료**
- ~~`DocumentSpec`과 paragraph/table/image builder~~ — **2026-08-30 완료**
- ~~`hwpxDocumentNode` 정의·UI·executor·Artifact 출력~~ — **완료**(`fill_template` 모드는 기존 `fileModifierNode` 가 이미 그 일을 해서 넣지 않았다 — 아래 참고)
- ~~golden 10종~~ — **2026-08-30 완료**. 실제 한/글 release gate 는 사용자 확인 대기

완료 기준: §3.6 전 항목 통과.

#### 구현 진행 상황 (2026-08-30) — 공용 엔진과 이관

**`backend/documents/hwpx/` (신규).** 예전에는 HWPX 처리가 **생성 코드 문자열 안에** 있었다(`node_generators/template_nodes.py`). 두 노드가 같은 일을 조금씩 다르게 했고, 포맷 버그를 고치면 두 군데를 고쳐야 했으며, 무엇보다 **테스트할 방법이 없었다.**

| 모듈 | 하는 일 |
| --- | --- |
| `safety` | 열기 전에 검사 — 압축 폭탄·경로 탈출·symlink·중복 entry·XML 폭탄·mimetype |
| `xmlio` | section XML 파싱과 **원래 모양대로** 직렬화 |
| `placeholders` | 여러 run 으로 쪼개진 `{{자리표시자}}` 를 찾아 채운다 |
| `package` | 원본 entry 순서·압축 방식을 보존해 다시 묶는다 |

**핵심은 run-aware 치환이다.** 사용자가 한/글에서 `{{name}}` 의 일부만 굵게 하면 그 한 낱말이 여러 `<hp:t>` 로 갈라진다. 문자열에는 `{{name}}` 이 **없으므로** 예전 구현은 조용히 안 채운 채 결과를 냈다. 라이브러리의 `replace_text_in_runs` 도 run 하나씩 보므로 같은 한계다 — **실제로 확인했다**(쪼개진 경우 0건 치환). 그래서 문단 단위로 `<hp:t>` 들을 이어 붙여 논리 문자열을 만들고 거기서 찾은 뒤, 걸친 조각들에 나눠 쓴다. 표 안 문단도 같은 경로로 처리된다(표는 셀 안에 문단을 품는다).

`<hp:tab/>` 같은 제어 요소는 `<hp:t>` 의 형제로 들어가므로 논리 문자열에 **경계 문자**를 넣어 자리표시자가 그걸 가로질러 매칭되지 않게 했다. 그러지 않으면 탭 하나가 값 한가운데 남는다.

**두 가지를 알아내 고쳤다.**

1. `ElementTree` 는 **실제로 쓰인 접두사만** 다시 쓴다. HWPX 루트는 namespace 를 14개 선언하는데 본문이 두세 개만 쓰므로, 그대로 두면 나머지 12개가 사라져 파일이 크게 달라진다. 한/글이 그걸 어떻게 받아들일지 확인된 바 없어 **원본 선언을 되돌리게** 했다.
2. **건드리지 않은 entry 는 재직렬화하지 않는다.** 전부 다시 쓰면 `<tag/>` → `<tag />` 같은 형식 차이가 문서 전체에 퍼진다. 편집한 section 만 다시 쓰고 나머지는 원본 바이트를 그대로 옮긴다.

**이관.** `templateAnalyzerNode` 는 이제 `template_keys()` 로 읽고, `fileModifierNode` 는 `fill_template()` 으로 채운다. Phase 0 이전에 손으로 고쳤던 것(덮어쓰기 금지·mimetype STORED)이 엔진 안으로 흡수됐다. 실패 메시지도 나아졌다 — 예전의 "겹침 비율이 절반 미만" 추정 대신 **못 채운 빈칸을 이름으로** 짚는다. hwpx 사전 점검은 뗐다: `extract_template_keys` 가 run 분할을 모르는 옛 방식이라 쪼개진 서식을 "키가 안 맞는다"고 잘못 막았다.

**검증.** `test_hwpx_engine.py` 43개 — run 분할 2·3조각, 표 안 자리표시자, XML 특수문자 5종, 줄바꿈, 미치환 보고, 입력 서식 byte 동일, entry 순서·압축 보존, 악성 패키지 9종(경로 탈출·symlink·압축 폭탄·XXE·중복 entry). 노드 실행 경로로도 통합 확인했다. 전체 1065개 통과.

라이브러리가 쪼개진 자리표시자를 못 채운다는 사실도 테스트로 고정했다 — 라이브러리가 나중에 고쳐지면 그 테스트가 알려주고, 그때 이 엔진의 일부를 덜어낼 수 있다.

#### §3.6 완료 조건 현황

| 조건 | 상태 |
| --- | --- |
| 한컴 오피스 없이 생성 | 충족(그 전부터) |
| 여러 run 분할·표 안·특수문자·줄바꿈 채움 | **충족** — 43개 테스트 |
| 미치환 자리표시자 명시와 실패 처리 | **충족** |
| 악성 ZIP/XML 거부, 서버 파일·외부 URL 접근 없음 | **충족** |
| 입력 서식 byte 동일 | **충족** |
| `mimetype` 첫 entry·STORED | **충족** |
| analyzer/modifier 가 같은 엔진 호출 | **충족** — 회귀 0 |
| golden 10종이 한/글에서 복구 경고 없이 열림 | **충족** — 2026-08-30 사용자 확인. 표 페이지네이션 1건은 고쳐서 재확인 대기 |

**한/글 실검증은 남았다.** 이 서버에는 한/글이 없고 설치하지도 않는다(§11 비목표). golden 문서를 만들어 Windows QA 또는 사용자 확인으로 여는 것이 남은 release gate다. 특히 **줄바꿈**은 확인이 필요하다 — 라이브러리가 `\n` 을 `<hp:t>` 안에 문자 그대로 쓰길래 그 동작을 따랐는데, OWPML 은 `<hp:lineBreak/>` 를 쓰는 자리다. 한/글에서 어떻게 보이는지 보고 정해야 한다.

#### 구현 진행 상황 (2026-08-30) — `DocumentSpec` 과 `hwpxDocumentNode`

**`documents/hwpx/builder.py`.** `DocumentSpec`(JSON) → 새 HWPX. heading·paragraph·table·image·page_break 다섯 가지를 만든다.

**스펙을 먼저 검사하고 만든다.** 지원하지 않는 블록(도형·수식·차트·매크로)이 오면 `HWPX_UNSUPPORTED_FEATURE` 로 **실패하고 파일을 아예 만들지 않는다** — 절반쯤 만들어진 문서를 내보내면 사용자는 열어 보고서야 알게 된다. 어느 블록에서 멈췄는지(`blocks[2]`)도 알려준다.

**이미지는 `artifactId` 로만 받는다**(§3.3). 경로나 URL 을 받으면 서버 파일을 문서에 실어 보낼 수 있다. 실제 해석은 호출자가 넘긴 `image_loader` 가 하고, 빌더는 DB 도 네트워크도 모른다. 런타임 쪽 loader 는 소유자까지 확인한다.

**heading 은 문자 서식(굵게 + 크기)으로 표현했다.** 한/글의 제목 스타일 id 는 문서마다 달라 신뢰할 수 없었다. 시각적 확인은 한/글 release gate 로 넘긴다.

**`hwpxDocumentNode`.** `create`·`inspect`·`validate` 세 모드. 실제 동작은 `documents/hwpx_runtime.py` 에 있는 평범한 파이썬이고 생성 코드(`node_generators/document_nodes.py`)는 그걸 한 번 부르는 것이 전부다 — `template_nodes.py` 가 zipfile·XML 조작을 문자열로 조립해 두는 바람에 테스트가 불가능했던 것을 반복하지 않는다.

| 판단 | 내용 |
| --- | --- |
| `fill_template` 모드를 넣지 않았다 | 기존 `fileModifierNode` 가 이미 그 일을 하고, 이제 같은 엔진을 쓴다. 같은 일을 하는 노드를 둘로 늘리면 생성기가 어느 쪽을 고를지 헷갈린다 |
| LLM 출력의 코드펜스를 벗겨 낸다 | ` ```json … ``` ` 으로 감싸 오는 것이 일상이다. 못 읽으면 "JSON 을 내도록 해주세요"로 실패한다 |
| 파일은 `uploads/` 안에만 쓴다 | `output_path` 에 `/etc/cron.d/evil.hwpx` 를 넣어도 `uploads/evil.hwpx` 가 된다 |
| `validate` 는 거부 사유를 결과로 준다 | 검사가 목적이라 "열 수 없다"도 정상 출력이다. 예외로 올리면 워크플로가 멈춘다 |

**새 노드 하나를 추가하며 함께 고친 곳**(다음 한국형 노드도 같은 목록을 따른다): `node_definitions/hwpxDocumentNode.json`, `node_generators/document_nodes.py`(+ `__init__` 등록), `meta_agent.py` 카탈로그 항목과 개수(44→45), `node_knowledge.py` 별칭, `test_node_definitions.py` 의 타입 목록, `frontend/src/editorNodeCatalog.js` 팔레트, 그리고 `export_node_definitions.py` 재생성. 정화 규칙은 정의에서 자동 파생돼 손댈 것이 없었다(Phase 0 에서 확인한 대로).

**검증.** `test_hwpx_document_node.py` 43개(만들기·미지원 블록 5종·스펙 검증 7종·이미지 Artifact 전용·LLM 출력 파싱·경로 정규화·세 모드). 워크플로우 실행으로도 세 모드를 확인했다. 전체 1110개 통과.

#### 구현 진행 상황 (2026-08-30) — golden 10종

**`backend/testdata/golden_hwpx.py`.** 문서 파일이 아니라 **스펙과 생성 스크립트**를 저장소에 둔다. 문서를 한 번 만들어 넣어 두면 엔진을 고쳤을 때 그 문서가 여전히 옳은지 알 방법이 없다 — 매번 만들어 내면 다시 열어 보기만 하면 되고, 추출 결과가 달라지면 테스트가 바로 알려준다.

앞의 넷은 §3.4 가 이름을 댄 실제 문서 종류이고, 나머지 여섯은 **엔진에서 깨지기 쉬운 자리**를 하나씩 맡는다.

| 문서 | 무엇을 확인하나 |
| --- | --- |
| 01-공문 | 제목·본문·서명란. 여백 20mm |
| 02-계약서 | 조항 번호 + 금액 표 |
| 03-표중심보고서 | 40행 표가 쪽을 넘어갈 때 |
| 04-이미지포함 | 그림이 보이는지, 폭 80mm 가 지켜지는지 |
| 05-쪽나누기 | 정확히 3쪽인지 |
| 06-서식_빈칸 | `{{빈칸}}` 이 그대로 보이는지 |
| 07-서식_채움 | 06 을 채운 결과 — 표 안 빈칸 포함 |
| 08-특수문자 | `& < > "` 가 `&amp;` 로 보이지 않는지 |
| 09-줄바꿈 | **가장 불확실.** 문단 안 줄바꿈이 실제로 줄을 바꾸는지 |
| 10-긴문서 | 120블록. 열리는 시간과 쪽 번호 |

**스냅샷으로 회귀를 잡는다.** `testdata/golden_hwpx_snapshot.json` 에 추출 텍스트와 패키지 구조(entry 이름·압축 방식)를 박아 두고 `test_golden_hwpx.py` 44개가 맞춰 본다(§3.4 'golden 검증'의 "추출 결과와 package diff"). 스냅샷을 갱신하려면 `--update` 를 주는데, **갱신했으면 한/글에서 다시 열어 봐야** 이 장치가 의미를 갖는다 — 그 사실을 스크립트 docstring 과 테스트 docstring 양쪽에 적었다.

**받는 곳.** `uploads/golden/` 에 두었고 `/uploads/golden/<파일>` 로 내려받는다. 열 문서와 확인 체크리스트를 묶은 `한글호환성확인.zip`(84KB)도 같이 있다.

**여기서 확인한 것과 못 한 것.** 자동으로 확인한 것은 값이 유실되지 않았는지, 이중 이스케이프가 없는지, 패키지 규칙이 지켜지는지, 우리 엔진과 표준 구현이 다시 열 수 있는지다. 한/글이 실제로 어떻게 그리는지는 사람이 봐야 했다.

#### 한/글 release gate 결과 (2026-08-30, 사용자 확인)

**통과.** 10종이 복구 경고 없이 열렸고 전반적으로 정상이었다. 우려했던 **09-줄바꿈은 문제가 없었다** — 라이브러리를 따라 `\n` 을 `<hp:t>` 에 문자 그대로 쓰는 방식이 한/글에서 그대로 줄을 바꾼다. `<hp:lineBreak/>` 로 바꿀 필요가 없다.

**한 가지가 걸렸고 고쳤다 — 03-표중심보고서의 40행 표가 20행쯤에서 잘려 보였다.**

원인은 우리 쪽이 아니라 라이브러리의 기본값이었다. `add_table` 이 표에 `<hp:pos treatAsChar="1">` 을 박아 넣는데, 이는 표를 **글자 하나처럼** 다루겠다는 뜻이라 한/글에서 그 표는 쪽을 넘어 나뉘지 못한다. 첫 쪽에 들어가는 만큼만 보이고 나머지는 잘린 것처럼 보인다.

**데이터는 온전했다** — XML 에는 41행(`rowCnt="41"`)이 다 들어 있었고 표시만 잘렸다. 그래서 손실이 아니라 표현 문제였다.

고친 것은 `builder._make_table_flow()` 두 줄이다.

| 속성 | 전 | 후 | 뜻 |
| --- | --- | --- | --- |
| `pos.treatAsChar` | `1` | `0` | 글자가 아니라 문단에 얹힌 블록 → 쪽을 넘어 이어진다 |
| `tbl.repeatHeader` | `0` | `1` | 둘째 쪽부터도 머리글 행이 보인다 |

`pageBreak="CELL"`(셀 경계에서 나눈다)은 라이브러리가 이미 붙이고 있어서 그대로 뒀다. 네 가지를 테스트로 고정했다(`test_hwpx_document_node.py` — treatAsChar·pageBreak·repeatHeader·행 수).

**이 수정 자체는 한/글에서 아직 확인하지 못했다.** golden 03 을 다시 만들어 뒀으니 다음에 한/글을 여실 때 한 번 더 봐 주시면 된다. 확인 전까지는 "표시 문제를 고쳤다고 믿는 상태"다.

### Phase 2 — 네이버 Search/Cafe — **2026-08-30 완료**

- ~~OAuth callback/refresh/revoke와 API Center 연결 UI~~ — 완료
- ~~`naverSearchNode`, `naverSearchTriggerNode`, `naverCafeNode`~~ — 완료
- ~~검색 cursor/dedupe, 일일 quota budget~~ — 완료
- ~~카페 게시 preview, 한글 인코딩~~ — 완료. **이미지 multipart 첨부는 남겼다**(아래)
- 생성 평가와 hard negative: 블로그 자동 발행 금지 — 카탈로그 문구로 넣었고 평가 사례는 남음

완료 기준: §4.4 전 항목과 실제 beta 계정 smoke test 통과.

#### 구현 진행 상황 (2026-08-30) — Trigger 와 Cafe

**`naverSearchTriggerNode`.** 첫 실행은 기준점만 잡고, 이후 새 결과만 알린다. 실제 API 로 두 번 돌려 확인했다(1회차 0건, 2회차 0건, 사용량 2건 집계).

| 정한 것 | 이유 |
| --- | --- |
| 폴링 기본 10분, **1분은 선택지에 없음** | 1분이면 워크플로 17개에서 하루 한도가 찬다(§4.0). 고를 수 있게 두면 "왜 오늘은 안 되지"를 사용자가 겪는다 |
| 겹침 창 300개 | 검색 인덱스는 순서가 흔들리고 항목이 밀려났다 돌아온다. 마지막 응답만 기억하면 그때마다 새 글로 알린다 — `rssTriggerNode` 가 겪은 문제(§2 불일치 12) |
| 폴링은 항상 `sort=date` | 정확도순으로 폴링하면 새 글이 상위에 못 올라와 영영 놓친다 |
| 모르는 cursor 형식은 **실패** | 첫 실행으로 강등하면 조용히 과거를 다시 알린다 |

**하루 한도를 우리가 먼저 센다.** `rate_limit.py`(ADR-0020 의 Postgres 고정 윈도우 카운터)에 `naver.search: (25000, 86400)` 규칙을 더해 **호출 전에** 센다. 80% 를 넘으면 로그로 알리고 100% 면 나가지 않는다. 한도는 키 단위라 사용자별로 센다.

**`naverCafeNode`.** 여기서 가장 조심한 것은 **실수로 게시되는 것**이다.

- **기본값이 미리보기다.** `confirm` 을 켜지 않으면 생성 코드에 게시 호출 자체가 없다(테스트로 고정). 어느 카페의 어느 게시판에 어떤 제목으로 올라가는지 먼저 보여준다.
- 계획은 "앞에 `humanApprovalNode` 를 삽입한다"였는데, 생성기에는 **"요청에 승인 절차를 언급하지 않았으면 임의로 넣지 않는다"** 는 원칙이 이미 있다(`meta_agent.py`). 그 원칙과 싸우는 대신 **노드 자체를 기본 안전**하게 만들었다.
- **재시도하지 않는다.** `maxAttempts: 1` + `idempotent=False`. timeout 뒤 재시도는 같은 글을 두 번 올린다 — 한 번 실패하는 것보다 나쁘다.

**한글 인코딩 함정.** 공식 예제가 URL 인코딩을 **두 번** 한다.

```java
// 해당 string은 UTF-8로 encode 후 MS949로 재 encode를 수행한 값
String subject = URLEncoder.encode(URLEncoder.encode("카페 가입 인사", "UTF-8"), "MS949");
```

1차 결과가 이미 ASCII 라 2차의 charset 은 무의미하고 `%` 가 `%25` 로 한 번 더 감싸질 뿐이다. 그래서 이미 인코딩된 문자열을 **raw body 로** 보낸다 — `data={...}` dict 로 넘기면 HTTP 라이브러리가 **세 번째** 인코딩을 해서 제목이 깨진다. 세 가지 모두 테스트로 고정했다.

**검증.** `test_naver_search.py` 50개, `test_naver_cafe.py` 33개. 전체 1,319개 통과.

#### Phase 2 에서 남긴 것

| 남긴 것 | 이유 |
| --- | --- |
| 카페 **이미지 첨부**(multipart) | 텍스트 게시가 먼저 실제로 쓰이는지 보고 붙인다. 공식 예제는 있으니 착수는 어렵지 않다 |
| 카페 실제 게시 검증 | 되돌릴 수 없는 외부 쓰기라 사용자 카페에 시험 글을 올리지 않았다. **`confirm` 을 켠 첫 실행은 사용자가 해야 한다** |
| `clubId`·`menuId` 를 고르는 UI | 카페 API 에 "내 카페 목록" 이 없어 사용자가 숫자를 찾아 넣어야 한다. 안내 문구로 위치를 알려주는 선에서 멈췄다 |
| 생성 평가 사례 | 블로그 자동 발행 금지는 카탈로그 문구에 넣었지만 hard-negative 평가 사례는 아직이다 |

**구조적 한계 하나를 확인했다.** 우리가 호출 전에 거르며 쓴 사유("제목이 너무 길다")는 `ConnectorError.detail` 에만 남고 사용자에게는 code 별 템플릿 문구가 간다(ADR-0016). 한국형 노드만의 문제가 아니라 connector 전반의 것이라 여기서 바꾸지 않았다.

#### 구현 진행 상황 (2026-08-30) — `naverSearchNode`

**실제 키로 먼저 확인하고 만들었다.** §4.0 에 "유추한 것이고 공식 문서에서 직접 보지 못했다"고 적어 둔 경로를 사용자 키로 호출해 확정했다.

| 확인한 것 | 결과 |
| --- | --- |
| `GET /search/v1/blog` | 200 |
| `GET /search/v1/cafearticle` | 200 |
| 헤더 `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY` | 동작 |
| 성공 응답 | `lastBuildDate·total·start·display·items[]` |
| 블로그 item | `title·link·description·bloggername·bloggerlink·postdate` |
| 카페글 item | `title·link·description·cafename·cafeurl` — **작성일이 없다** |

**오류가 두 가지 형태로 온다.** 게이트웨이가 막으면 401 `{"error": {...}}`, 검색 쪽이 거절하면 400 `{"errorMessage": ..., "errorCode": "SE01"}` 이다. 한 쪽만 보고 만들면 다른 쪽에서 사용자에게 빈 메시지가 간다. 둘 다 mock 시나리오로 고정했다.

**설계에서 정한 것 셋.**

1. **호출 전에 거른다.** 범위 밖 `display`, 빈 검색어, 모르는 mode, 형식이 틀린 키는 나가기 전에 막는다. HUB 가 400 으로 알려주기는 하지만 그건 **일 25,000건 한도를 축내며 배우는 것**이다.
2. **`<b>` 강조를 걷어낸다.** 네이버는 검색어에 태그를 씌워 준다. 그대로 하류로 넘기면 LLM 프롬프트와 문서에 태그가 섞인다. 걷어낸 값을 주고 `titleRaw`·`raw` 로 원문도 남긴다.
3. **없는 것을 지어내지 않는다.** 카페글에는 작성일이 없어서 `publishedAt` 을 빈 문자열로 둔다. 블로그의 `postdate` 를 흉내 내 채우면 하류가 잘못된 정렬을 하게 된다.

**테스트가 버그를 하나 잡았다.** `display or 10` 이 `0` 을 "미지정"으로 오인해 10 으로 바꿨다 — `-5` 는 1 로 깎으면서 `0` 만 10 이 되는 일관성 없는 동작이었다. 값이 **없을 때만** 기본값을 쓰도록 고쳤다.

**검증.** `test_naver_search.py` 37개(HUB 계약·사전 검증·정규화·오류 두 형태·mock 일치·정의 정합). 실제 워크플로우로 블로그 검색 1건을 돌려 결과를 확인했다. 전체 1,200개 통과.

**`verifiedAt: 2026-08-30` 은 진짜다** — 이 날 실제로 호출해 응답을 봤다. Phase 0 에서 "확인하지 않고 오늘 날짜를 적으면 기록이 거짓이 된다"고 비워 뒀던 그 필드다.

### Phase 3 — 국내 공공 데이터 — **2026-08-30 구현 완료**

- ~~`jusoNode` 도로명주소~~ — 완료. 테스트 61건
- ~~`dataGoKrNode` 공공데이터포털~~ — 완료. 테스트 58건
- ~~이용허락범위·출처 표시를 결과 metadata 에 보존~~ — 완료(`attribution`·`license`·`docsUrl`)

**남은 것은 승인키로 하는 실호출 대조 하나뿐이다.** 두 노드 다 규격을 문서 기준으로 만들고
mock 으로 검증했다. `jusoNode` 는 juso.go.kr 이 403 을 줘서 **공식 규격 문서를 직접 읽지도
못했다**(2차 출처) — `verifiedAt` 을 비워 두었으니 대조 뒤에 채운다.

#### `dataGoKrNode` 가 임의 URL 프록시가 아닌 이유

`DATASETS` registry 에 등록한 것만 호출한다. 등록 항목은 공식 문서 주소와 **대조한 날**을 갖는다.

- `httpRequestNode` 가 이미 임의 요청을 한다. 같은 것을 하나 더 만들 이유가 없다.
- 공공 데이터는 데이터셋마다 이용허락범위가 다르다. 임의 URL 을 허용하면 그 조건을 결과에
  붙일 방법이 없다.

**같은 포털인데 API 마다 다른 것들** — 이것이 registry 가 필요한 실제 이유다.

| 데이터셋 | JSON 요청 파라미터 |
| --- | --- |
| 과기정통부 보도자료 | `returnType=json` |
| 기상청 단기예보 | `dataType=JSON` |

이름을 틀리면 오류가 아니라 **XML 이 돌아온다.** 파서가 조용히 빈 결과를 내므로 XML·JSON 을
둘 다 읽게 했다.

### 함께 처리하는 잔여 결함

Phase 와 무관하게 이미 발견된 것이라 범위 축소와 별개로 고친다.

- `rss.py` cursor 에 겹침 창과 `seen_ids` 상한(§2 불일치 12) — 밀려났다 돌아온 항목이 재통지된다

### 보류 — 재개 조건이 있는 것들

**미루는 이유를 적어 둔다.** "언젠가" 로만 남기면 왜 멈췄는지 잊고 같은 조사를 다시 하게 된다.

| 보류 | 원래 내용 | 재개 조건 |
| --- | --- | --- |
| **X·Instagram Social Pack** (구 Phase 5) | X recent search/mention, 게시·답글, Instagram Login·webhook·media container | **API 비용**(2026-08-30 사용자 결정). X 는 유료 등급, Instagram 은 Business 인증·App Review 가 선행이다. 비용을 감수할 근거가 생길 때 |
| **한국 커뮤니티 읽기** (구 Phase 4) | 루리웹 공식 RSS preset, `CommunityPost` 정규화, 클리앙·뽐뿌·인벤 조사 | 범용 `webCrawlerNode` 정비가 끝나(§6.5) 급하지 않다. 전용 preset 요청이 실제로 관측될 때 |
| **국내 업무/리서치** (구 Phase 6) | 네이버 커머스, NAVER WORKS, OpenDART, 카카오 로컬 | 사업자·법인 자격이 필요하거나 수요가 확인되지 않았다 |
| **KOSIS** (구 Phase 7 일부) | 통계목록·통계자료 조회 | 공공데이터포털 adapter 가 자리를 잡은 뒤. 스키마 정규화 방식을 두 번 만들지 않는다 |
| 디시인사이드·에펨코리아 | 전용 Trigger | **폐기.** 차단 목록만 유지한다(§6.5) |
| 쿠팡 판매자 | 상품·주문 | **폐기**(2026-08-30) |

## 9. 테스트와 출시 게이트

### 모든 노드의 필수 테스트

- Node Definition schema, mode별 required field, UI 조건부 필드
- credential 연결/누락/만료/갱신/권한 부족
- 성공, 400, 401/403, 404, 429, timeout, 5xx
- 읽기 retry와 쓰기 non-retry
- pagination 최대 페이지/항목과 cursor 종료
- mock 실행 중 실제 네트워크 0건
- Authorization, secret, 개인정보 redaction
- dry-run과 human approval
- 생성기가 expected node를 선택하고 금지 mode를 만들지 않는지
- webhook 서명/CRC, replay, 순서 역전, 중복 delivery
- 공식 feed allowlist와 SSRF 방어, 삭제·수정·비공개 전환 반영
- `webCrawlerNode`를 포함한 모든 URL 입력 노드에서 사설·링크로컬·메타데이터 주소와 redirect 우회 차단
- 문서 노드가 입력 템플릿을 수정하지 않음(실행 전후 해시 동일)
- 신규 노드 타입에 `community_sanitize` 규칙이 있고 공개 시 비밀이 남지 않음
- 새 오류 code가 `error_catalog.json`에 등록돼 있고 export 결과가 최신임
- X 비용 budget과 Instagram media staging 만료·권한 격리

### beta 출시 조건

1. 공식 문서의 제공 범위와 실제 test credential 응답이 일치한다.
2. mock fixture와 실제 응답의 contract test가 같은 normalized schema를 만든다.
3. P95 latency, success rate, 429 비율, cursor lag을 dashboard에서 볼 수 있다.
4. 외부 쓰기는 실행 전 대상·내용·공개 범위를 사용자가 확인할 수 있다.
5. 약관이 불명확한 기능은 feature flag가 아니라 카탈로그 자체에서 숨긴다.
6. 서비스 API 변경 공지를 분기별로 재검토하고 connector metadata의 확인일을 갱신한다.
7. 커뮤니티는 공식 feed/API 근거 또는 유효한 서면 제휴가 있어야 하며, 제휴 범위를 벗어난 board/mode 요청을 runtime에서도 거부한다.
8. X/Instagram 쓰기는 실제 scope와 계정 유형을 사전 진단하고 비용·게시량 상한과 anti-spam 평가를 통과한다.

### 초기 성공 지표

| 지표 | 목표 |
| --- | ---: |
| HWPX golden 열기 성공 | 10/10, 복구 경고 0 |
| HWPX placeholder 채움 | 지원 fixture 100% |
| 문서 노드의 입력 템플릿 변조 | 0건 |
| 사설·내부 주소로 나간 크롤/feed 요청 | 0건 |
| 검색/상품/커뮤니티 Trigger 중복 이벤트 | replay 테스트 0건 |
| mock 외부 네트워크 | 0건 |
| credential/개인정보 로그 노출 | 0건 |
| 신규 노드 expected Recall@10 | 95% 이상 |
| 외부 쓰기 승인 우회 | 0건 |
| 제휴 전 DC/FM connector 외부 요청 | 0건 |
| X workspace 비용 상한 초과 호출 | 0건 |
| Instagram 만료 staging URL 재접근 | 0건 |
| normalized error 분류율 | 95% 이상 |

## 10. 구체적 작업 목록

### 공통

- [x] 인가 코드 callback — `backend/connectors/oauth_flow.py`(신규), 마이그레이션 0016, `test_oauth_flow.py`·`test_oauth_endpoints.py`
- [x] `credential_providers.json`: Naver Open API/OAuth 3종 추가 + `google_oauth` 에 `authorize` 선언
- [ ] `credential_providers.json`: X app/user context, Instagram Login, Naver Commerce, NAVER WORKS, OpenDART provider 추가(각 Phase 착수 때)
- [x] `backend/connectors/cursor.py`: 저장소·형식 버전·lease — `test_connector_cursor.py`
- [ ] `backend/connectors/cursor.py`: baseline/backfill/since 모드와 overlap window(트리거를 늘릴 때)
- [x] `NodeMemory` 기반 기존 cursor의 Alembic 이관(0017)과 이행기 읽기 — 마이그레이션 테스트로 고정
- [ ] `error_catalog.json`에 §7 표의 신규 code 등록 후 `python backend/export_node_definitions.py` 재생성 — 각 노드가 실제로 그 code 를 낼 때 등록한다(지금은 `terms_blocked`만 기존 code 로 매핑)
- [x] 정화 규칙은 정의에서 자동 파생됨을 확인하고 테스트로 고정 — 새 연동 노드는 따로 쓸 필요 없다
- [x] Connector metadata에 `docsUrl`·`verifiedAt`·`termsGate` 추가 — 기존 7개 연동에 `docsUrl` 채움
- [ ] 기존 7개 연동의 `verifiedAt` 채우기(공식 문서를 실제로 열어 대조한 날)
- [x] mock 시나리오 계약(`connectors/mock.py`)과 로드 시점 강제 — 서비스별 fixture 는 각 노드와 함께
- [ ] API Center에 만료·IP allowlist·scope 상태 표시

### HWPX

- [x] **(선행)** `template_nodes.py`의 자동 재생성이 입력 템플릿을 덮어쓰지 않게 수정 + 회귀 테스트 — `test_template_safety.py`
- [x] **(선행)** 재압축 시 `mimetype` STORED·첫 entry 보존
- [x] **(선행)** `backend/requirements.txt`의 `python-hwpx` 버전 고정 — `==3.4.1`
- [x] **(선행)** `seed_curated_templates.py:1128,1132`의 `.hwp` → `.hwpx` 교정 — 서식 파일 자체는 없어도 노드가 즉석 생성한다
- [x] `backend/documents/hwpx/` 공용 엔진 — safety·xmlio·placeholders·package, `test_hwpx_engine.py` 43개
- [x] `node_definitions/hwpxDocumentNode.json` (connector 블록 없음, `sideEffect: none`)
- [x] `backend/node_generators/document_nodes.py` 얇은 wrapper
- [x] analyzer/modifier의 문자열 치환 제거 — 공용 엔진으로 이관
- [x] 악성 package fixture 9종
- [x] golden fixture 10종 — `testdata/golden_hwpx.py` + 스냅샷 회귀 테스트 44개
- [x] 한/글 실검증(사용자, 2026-08-30) — 통과. 줄바꿈은 문제 없었고, 표 페이지네이션 1건을 고쳤다
- [ ] 고친 표 페이지네이션을 한/글에서 재확인(golden 03)

### 네이버

- [ ] `backend/connectors/services/naver_search.py`
- [ ] `backend/connectors/services/naver_cafe.py`
- [ ] `naverSearchNode`, `naverSearchTriggerNode`, `naverCafeNode` 정의
- [ ] OAuth callback과 revoke
- [ ] 검색 budget/cursor와 카페 승인 UX
- [ ] 블로그 쓰기 hard-negative 평가

### 한국 커뮤니티

- [x] **(선행)** `webCrawlerNode` URL 안전 게이트 — `backend/url_guard.py`, `test_url_guard.py`
- [x] **(2026-08-30 결정)** `httpRequestNode`·`rssTriggerNode`에는 게이트를 걸지 않는다 — 자체 호스팅 연동을 깨지 않기 위해. 남는 노출은 받아들였다(`ROADMAP.md` §7 열린 질문 9)
- [ ] `rss.py` cursor에 겹침 창과 `seen_ids` 상한 추가
- [ ] `rssTriggerNode`에 루리웹 공식 RSS preset과 게시판 URL canonicalizer 추가(기존 `new_item` 계약 유지)
- [ ] `CommunityPost` normalized schema, cursor/dedupe, 원문 최소 보존 정책 추가
- [ ] 공식 feed allowlist와 redirect/DNS/IP 재검증을 포함한 SSRF 테스트 추가
- [x] **(2026-08-30 완료)** `webCrawlerNode` 정비: 구조화 추출, robots.txt 준수, 호스트별 일일 호출 상한, 요청 간 최소 간격
- [ ] 클리앙·뽐뿌·인벤 공식 API/RSS 조사표 작성
- [ ] 제휴 근거가 없을 때 HTTP client가 호출되기 전에 `COMMUNITY_PARTNERSHIP_REQUIRED`로 실패하는 테스트 추가

### 보류 (X·Instagram) — 2026-08-30

API 비용 때문에 멈췄다. 원래 항목은 문서 이력에 남아 있고, 재개 조건은 §8 보류표에 있다.

### 공공데이터포털·도로명주소

- [ ] `backend/connectors/services/juso.py` — 도로명·지번·우편번호·영문주소 고정 schema
- [ ] `jusoNode` 정의와 mock 6종
- [ ] `backend/connectors/services/data_go_kr.py` — `datasetId + operationId` registry, XML/JSON 공통 envelope
- [ ] `dataGoKrNode` 정의와 승인 데이터셋 registry
- [ ] 이용허락범위·출처 표시를 결과 metadata 에 보존하는 테스트

## 11. 명시적 비목표

- 한컴 오피스나 Windows COM을 Linux 운영 서버에 설치
- 바이너리 `.hwp`를 완전 편집 가능한 형식으로 광고
- 네이버 블로그 자동 발행
- 비공개 카페 데이터 수집 또는 카페 로그인 세션 스크래핑
- 디시인사이드의 사전 서면 동의 없는 크롤링
- 에펨코리아의 공개 개발 경로·제휴 없는 HTML 수집
- 어떤 사이트든 `robots.txt` 가 막은 경로 수집, 그리고 호출량 상한을 끈 대량 수집
- 커뮤니티 로그인 cookie, 비공개 endpoint, CAPTCHA 우회 또는 IP rotation
- 범용 `webCrawlerNode`로 위 제한을 우회하는 커뮤니티 수집 — 전용 노드를 감추는 것만으로는 이 비목표가 성립하지 않으므로 `url_guard` 게이트로 강제한다

  > **`httpRequestNode`에는 강제 수단이 없다**(2026-08-30 결정, `ROADMAP.md` §7 열린 질문 9).
  > 그 노드는 URL 검증을 거치지 않으므로 차단 목록도 적용되지 않는다. 이 비목표는 그 경로에
  > 대해서는 **정책이지 강제가 아니다** — 문서에만 있는 약속을 강제라고 적지 않는다.
- 사용자가 올린 서식 파일을 실행 중에 자동으로 교체하거나 덮어쓰기
- 사용자 브라우저 쿠키 또는 커뮤니티·포털 비밀번호 저장
- 외부 게시·상품 수정의 무승인 대량 실행
- X의 대량 자동 답글·Follow/Unfollow·Like 조작
- Instagram 개인 계정 접근, follower 수집, unsolicited bulk DM
- 커뮤니티·소셜 원문을 모델 학습 corpus로 영구 축적
- 공공데이터 이용허락범위를 무시한 재배포

## 12. 공식 근거

확인일은 2026-08-30이다. 구현 직전에 각 링크와 변경 공지를 다시 확인한다.

이 v1.2 검토가 실제로 대조한 것은 **저장소 코드뿐**이다(§2의 12개 항목은 파일·줄 번호까지 확인했다). 아래 외부 링크의 현재 제공 범위와 약관은 이번 검토에서 다시 열어 보지 않았으므로, v1.1 작성 시점의 조사 결과를 그대로 둔다. 각 Phase 착수 전에 해당 서비스 링크를 재확인하는 것이 여전히 필요하다.

### HWPX

- [한컴: HWP/OWPML 형식](https://online.hancom.com/support/downloadCenter/hwpOwpml)
- [한컴테크: HWPX 포맷 구조](https://tech.hancom.com/hwpxformat/)
- [한컴 공개 OWPML 모델](https://github.com/hancom-io/hwpx-owpml-model)
- [한컴 공개 HWPX Document Validation Checker](https://github.com/hancom-io/dvc)

### 네이버

**2026-08-30 확인: 검색 API는 아래 개발자센터 문서가 아니라 NAVER API HUB 기준으로 구현한다**(§4.0).

- [NAVER API HUB 제품 소개](https://www.ncloud.com/product/applicationService/naverApiHub)
- [NAVER API HUB 개요 문서](https://api.ncloud-docs.com/docs/naver-api-hub-overview)
- [NAVER API HUB 사용 가이드](https://guide.ncloud-docs.com/docs/apihub-use)

아래 개발자센터 링크는 **레거시 방식(2027-06-30 지원 종료)** 의 근거이고, 로그인·카페 API 는 아직 이쪽에만 있다.

- [네이버 블로그 검색 API](https://developers.naver.com/docs/serviceapi/search/blog/blog.md)
- [네이버 카페글 검색 API](https://developers.naver.com/docs/serviceapi/search/cafearticle/cafearticle.md)
- [네이버 카페 가입·글쓰기 API](https://developers.naver.com/docs/login/cafe-api/cafe-api.md)
- [네이버 로그인 OAuth API](https://developers.naver.com/docs/login/api/api.md)
- [네이버 블로그 글쓰기 Open API 종료 공지](https://developers.naver.com/notice/article/7527)
- [네이버 커머스API 소개](https://apicenter.commerce.naver.com/docs/introduction)
- [네이버 커머스API 최신 목차](https://apicenter.commerce.naver.com/docs/commerce-api/current)
- [네이버 커머스API 제약 사항](https://apicenter.commerce.naver.com/docs/restriction)

### 추가 서비스

- [NAVER WORKS API](https://developers.worksmobile.com/kr/docs/api)
- [NAVER WORKS Bot API](https://developers.worksmobile.com/kr/docs/bot-api)
- [NAVER WORKS Calendar API](https://developers.worksmobile.com/kr/docs/calendar)
- [OpenDART 공시검색 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)
- [카카오 REST API 레퍼런스](https://developers.kakao.com/docs/ko/rest-api/reference)
- [KOSIS 공유서비스 소개](https://kosis.kr/openapi/introduce/introduce_01List.do)
- [공공데이터포털](https://www.data.go.kr/)
- [도로명주소 API 체험·신청](https://m1.juso.go.kr/addrlink/openApi/apiExprn.do)

### 커뮤니티

- [디시인사이드 이용약관 제16조: 크롤링 및 인공지능 학습](https://nstatic.dcinside.com/dc/m/policy/policy.html)
- [에펨코리아 공식 사이트](https://www.fmkorea.com/)
- [아카라이브 전체 규정 — 8번 기타 제한 사항](https://arca.live/b/notice/13076564)
- [아카라이브: DDOS 및 크롤링에 의한 서비스 장애 및 대응 안내](https://arca.live/b/notice/59148622)
- [루리웹 공식 RSS 안내](https://bbs.ruliweb.com/etcs/board/10/read/31)

에펨코리아 링크는 공개 개발 문서의 근거가 아니라 조사 대상의 공식 사이트다. 2026-08-30 조사에서 공식 공개 API/RSS 문서를 확인하지 못했다.

아카라이브 규정 문구는 2026-08-30 에 검색 결과로 확인했고 **규정 페이지 원문을 직접 읽지는 못했다**(자동 요청에 HTTP 403). 구현 전에 사람이 브라우저로 8번 항목을 직접 확인한다.

### X·Instagram

- [X API 개요](https://docs.x.com/x-api/overview)
- [X Post 생성·삭제 API](https://docs.x.com/x-api/posts/manage-tweets/introduction)
- [X Filtered Stream](https://docs.x.com/x-api/posts/filtered-stream/introduction)
- [X API 사용량 과금](https://docs.x.com/x-api/getting-started/pricing)
- [X API rate limit](https://docs.x.com/x-api/fundamentals/rate-limits)
- [Meta 공식 Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
