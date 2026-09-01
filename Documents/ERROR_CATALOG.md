# 공통 오류 catalog (NodeError v1)

이 문서는 `error_catalog.json` 에서 `python backend/export_node_definitions.py` 가 생성한다.
직접 고치지 마라 — 정본을 고치고 다시 생성한다(ADR-0016).

| code | category | owner | 기본 retry | effectState 기본 | 해결 동작 | 사용자 문구 |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="credential_missing"></a>`CREDENTIAL_MISSING` | credential | connectors | 아니오 | `not_started` | API 센터에서 연결 | 필요한 자격증명이 등록되어 있지 않습니다. API 센터에서 먼저 연결해주세요. |
| <a id="credential_invalid"></a>`CREDENTIAL_INVALID` | credential | connectors | 아니오 | `not_started` | API 센터에서 연결 | 인증에 실패했습니다. API 센터에 등록한 값이 만료됐거나 잘못됐습니다. |
| <a id="credential_forbidden"></a>`CREDENTIAL_FORBIDDEN` | credential | connectors | 아니오 | `not_started` | API 센터에서 연결 | 접근 권한이 없습니다. 필요한 권한(scope)이 있는지, 대상이 이 계정과 공유되어 있는지 확인해주세요. |
| <a id="credential_expired"></a>`CREDENTIAL_EXPIRED` | credential | connectors | 아니오 | `not_started` | API 센터에서 연결 | 자격증명이 만료됐습니다. API 센터에서 다시 연결해주세요. |
| <a id="validation_required"></a>`VALIDATION_REQUIRED` | validation | node-definition | 아니오 | `not_applicable` | 해당 입력으로 이동 | 필수 입력이 비어 있습니다. 노드 설정을 채워주세요. |
| <a id="validation_invalid_type"></a>`VALIDATION_INVALID_TYPE` | validation | node-definition | 아니오 | `not_applicable` | 해당 입력으로 이동 | 입력 값의 형식이 맞지 않습니다. |
| <a id="validation_out_of_range"></a>`VALIDATION_OUT_OF_RANGE` | validation | node-definition | 아니오 | `not_applicable` | 해당 입력으로 이동 | 입력 값이 허용 범위를 벗어났습니다. |
| <a id="artifact_not_found"></a>`ARTIFACT_NOT_FOUND` | artifact | artifacts | 아니오 | `not_started` | 파일 다시 선택 | 첨부할 파일을 찾지 못했습니다. 파일을 다시 선택해주세요. |
| <a id="artifact_forbidden"></a>`ARTIFACT_FORBIDDEN` | artifact | artifacts | 아니오 | `not_started` | 파일 다시 선택 | 이 파일에 접근할 권한이 없습니다. 현재 프로젝트에서 만든 파일만 첨부할 수 있습니다. |
| <a id="artifact_expired"></a>`ARTIFACT_EXPIRED` | artifact | artifacts | 아니오 | `not_started` | 파일 다시 선택 | 파일 보존 기간이 지났습니다. 파일을 다시 만들거나 업로드해주세요. |
| <a id="artifact_too_large"></a>`ARTIFACT_TOO_LARGE` | artifact | artifacts | 아니오 | `not_started` | 파일 다시 선택 | 파일이 허용 크기를 넘습니다. |
| <a id="artifact_unsupported_type"></a>`ARTIFACT_UNSUPPORTED_TYPE` | artifact | artifacts | 아니오 | `not_started` | 파일 다시 선택 | 이 채널이 지원하지 않는 파일 형식입니다. |
| <a id="database_driver_missing"></a>`DATABASE_DRIVER_MISSING` | database | database | 아니오 | `not_applicable` | 연결 정보 확인 | 이 데이터베이스 종류를 실행할 드라이버가 서버에 없습니다. 현재는 PostgreSQL 만 지원합니다. |
| <a id="database_connection_failed"></a>`DATABASE_CONNECTION_FAILED` | database | database | 예 | `not_applicable` | 연결 정보 확인 | 데이터베이스에 연결하지 못했습니다. 호스트·포트·네트워크와 접속 정보를 확인해주세요. |
| <a id="database_auth_failed"></a>`DATABASE_AUTH_FAILED` | database | database | 아니오 | `not_applicable` | 연결 정보 확인 | 데이터베이스 인증에 실패했습니다. API 센터의 Database 접속 정보(사용자·비밀번호)를 확인해주세요. |
| <a id="database_timeout"></a>`DATABASE_TIMEOUT` | database | database | 예 | `not_applicable` | 해당 입력으로 이동 | 쿼리가 제한 시간 안에 끝나지 않았습니다. 조회 범위를 줄이거나 제한 시간을 늘려주세요. |
| <a id="database_query_rejected"></a>`DATABASE_QUERY_REJECTED` | database | database | 아니오 | `not_applicable` | 해당 입력으로 이동 | 이 노드는 읽기 전용 조회(SELECT/WITH) 하나만 실행합니다. 쿼리를 확인해주세요. |
| <a id="database_query_failed"></a>`DATABASE_QUERY_FAILED` | database | database | 아니오 | `not_applicable` | 해당 입력으로 이동 | 데이터베이스가 쿼리를 실행하지 못했습니다. 테이블·컬럼 이름과 문법을 확인해주세요. |
| <a id="delivery_invalid_recipient"></a>`DELIVERY_INVALID_RECIPIENT` | delivery | delivery | 아니오 | `not_started` | 해당 입력으로 이동 | 수신 대상을 찾지 못했습니다. 채널 ID·웹훅·수신자 주소를 확인해주세요. |
| <a id="delivery_auth_failed"></a>`DELIVERY_AUTH_FAILED` | delivery | delivery | 아니오 | `not_started` | API 센터에서 연결 | 발송 채널 인증에 실패했습니다. 봇 토큰·웹훅·SMTP 계정 정보를 확인해주세요. |
| <a id="delivery_forbidden"></a>`DELIVERY_FORBIDDEN` | delivery | delivery | 아니오 | `not_started` | API 센터에서 연결 | 이 채널에 보낼 권한이 없습니다. 봇이 채널에 초대되어 있고 쓰기 권한이 있는지 확인해주세요. |
| <a id="delivery_rate_limited"></a>`DELIVERY_RATE_LIMITED` | delivery | delivery | 예 | `not_started` | 잠시 뒤 다시 시도 | 발송 채널의 호출 한도에 걸렸습니다. 잠시 뒤 다시 시도해주세요. |
| <a id="delivery_timeout"></a>`DELIVERY_TIMEOUT` | delivery | delivery | 아니오 | `unknown` | 발송 결과 확인 뒤 수동 재시도 | 전송 결과를 확인하지 못했습니다. 중복 발송을 막기 위해 자동으로 다시 보내지 않았습니다 — 채널에서 도착 여부를 확인해주세요. |
| <a id="delivery_provider_rejected"></a>`DELIVERY_PROVIDER_REJECTED` | delivery | delivery | 아니오 | `not_started` | 해당 입력으로 이동 | 발송 채널이 요청을 거절했습니다. 본문 길이·형식과 첨부 조건을 확인해주세요. |
| <a id="delivery_result_unknown"></a>`DELIVERY_RESULT_UNKNOWN` | delivery | delivery | 아니오 | `unknown` | 발송 결과 확인 뒤 수동 재시도 | 발송 채널에 일시적인 문제가 있어 전송 결과를 알 수 없습니다. 채널에서 도착 여부를 확인한 뒤 필요하면 다시 보내주세요. |
| <a id="connector_not_found"></a>`CONNECTOR_NOT_FOUND` | connector | connectors | 아니오 | `not_applicable` | 해당 입력으로 이동 | 연동 서비스에서 대상을 찾지 못했습니다. 입력한 ID나 주소를 확인해주세요. |
| <a id="connector_invalid_request"></a>`CONNECTOR_INVALID_REQUEST` | connector | connectors | 아니오 | `not_applicable` | 해당 입력으로 이동 | 연동 서비스가 요청을 거절했습니다. 노드에 입력한 값을 확인해주세요. |
| <a id="connector_rate_limited"></a>`CONNECTOR_RATE_LIMITED` | connector | connectors | 예 | `not_applicable` | 잠시 뒤 다시 시도 | 연동 서비스 호출 한도에 걸렸습니다. 잠시 뒤 다시 시도됩니다. |
| <a id="connector_quota_exceeded"></a>`CONNECTOR_QUOTA_EXCEEDED` | connector | connectors | 아니오 | `not_applicable` | 조치 없음 | 연동 서비스 사용 한도를 초과했습니다. 요금제나 할당량을 확인해주세요. |
| <a id="connector_timeout"></a>`CONNECTOR_TIMEOUT` | timeout | connectors | 예 | `not_applicable` | 다시 시도 | 연동 서비스 응답이 제한 시간 안에 오지 않았습니다. |
| <a id="connector_network_error"></a>`CONNECTOR_NETWORK_ERROR` | connector | connectors | 예 | `not_applicable` | 다시 시도 | 연동 서비스에 연결하지 못했습니다. 네트워크 상태를 확인해주세요. |
| <a id="connector_provider_error"></a>`CONNECTOR_PROVIDER_ERROR` | connector | connectors | 예 | `not_applicable` | 잠시 뒤 다시 시도 | 연동 서비스 쪽에 일시적인 문제가 있습니다. 잠시 뒤 다시 시도됩니다. |
| <a id="runtime_resource_exceeded"></a>`RUNTIME_RESOURCE_EXCEEDED` | runtime | runtime | 아니오 | `not_started` | 해당 입력으로 이동 | 코드가 허용된 실행 시간 또는 메모리를 넘어 중단했습니다. 처리량을 줄이거나 반복 범위를 좁혀주세요. |
| <a id="runtime_user_code_failed"></a>`RUNTIME_USER_CODE_FAILED` | runtime | runtime | 아니오 | `not_started` | 해당 입력으로 이동 | 코드 노드에서 오류가 났습니다. 들어온 데이터의 모양이 코드가 기대한 것과 다를 수 있습니다. |
| <a id="runtime_cancelled"></a>`RUNTIME_CANCELLED` | runtime | runtime | 아니오 | `unknown` | 조치 없음 | 실행이 취소됐습니다. |
| <a id="runtime_output_too_large"></a>`RUNTIME_OUTPUT_TOO_LARGE` | runtime | runtime | 아니오 | `applied` | 조치 없음 | 노드 출력이 허용 크기를 넘어 일부만 저장됐습니다. |
| <a id="runtime_serialization_failed"></a>`RUNTIME_SERIALIZATION_FAILED` | runtime | runtime | 아니오 | `applied` | 요청 ID 로 문의 | 노드 출력을 저장 가능한 형식으로 바꾸지 못했습니다. |
| <a id="runtime_node_disabled"></a>`RUNTIME_NODE_DISABLED` | runtime | runtime | 아니오 | `not_started` | 요청 ID 로 문의 | 이 노드는 현재 환경에서 꺼져 있습니다. 워크플로우에서 빼거나 관리자에게 문의해주세요. |
| <a id="internal_unknown"></a>`INTERNAL_UNKNOWN` | runtime | runtime | 아니오 | `unknown` | 요청 ID 로 문의 | 예상하지 못한 오류가 발생했습니다. 요청 ID 와 함께 문의해주세요. |
| <a id="legacy_node_error"></a>`LEGACY_NODE_ERROR` (이행용) | runtime | runtime | 아니오 | `unknown` | 조치 없음 | 노드가 오류 문구를 결과에 남겼습니다. |
| <a id="pointing_target_not_found"></a>`POINTING_TARGET_NOT_FOUND` | validation | pointing | 아니오 | `not_started` | 해당 입력으로 이동 | 지목한 대상을 찾을 수 없습니다. 삭제됐을 수 있으니 다시 선택해주세요. |
| <a id="pointing_target_stale"></a>`POINTING_TARGET_STALE` | validation | pointing | 아니오 | `not_started` | 해당 입력으로 이동 | 지목한 뒤 대상이 바뀌었습니다. 다시 첨부해주세요. |
| <a id="pointing_scope_violation"></a>`POINTING_SCOPE_VIOLATION` | validation | pointing | 아니오 | `not_applicable` | 발송 결과 확인 뒤 수동 재시도 | 지목하지 않은 항목이 함께 바뀌어 적용하지 않았습니다. 편집 범위를 넓히려면 범위를 다시 골라주세요. |
| <a id="pointing_context_too_large"></a>`POINTING_CONTEXT_TOO_LARGE` | validation | pointing | 아니오 | `not_started` | 해당 입력으로 이동 | 한 번에 다루기에 지목한 범위가 너무 넓습니다. 선택을 줄여주세요. |
| <a id="pointing_forbidden"></a>`POINTING_FORBIDDEN` | validation | pointing | 아니오 | `not_started` | 요청 ID 로 문의 | 이 대상을 수정할 권한이 없습니다. |
| <a id="pointing_invalid_context"></a>`POINTING_INVALID_CONTEXT` | validation | pointing | 아니오 | `not_started` | 해당 입력으로 이동 | 지목 정보를 읽지 못했습니다. 대상을 다시 선택해주세요. |
| <a id="format_not_found"></a>`FORMAT_NOT_FOUND` | validation | documents | 아니오 | `not_started` | 해당 입력으로 이동 | 선택한 문서 포맷을 찾을 수 없습니다. 노드에서 포맷을 다시 선택해주세요. |
| <a id="format_spec_invalid"></a>`FORMAT_SPEC_INVALID` | validation | documents | 아니오 | `not_started` | 해당 입력으로 이동 | 문서 포맷 정의가 잘못되어 렌더링할 수 없습니다. 포맷 스튜디오에서 포맷을 확인해주세요. |
| <a id="format_field_missing"></a>`FORMAT_FIELD_MISSING` | validation | documents | 아니오 | `not_started` | 해당 입력으로 이동 | 문서의 필수 빈칸이 채워지지 않았습니다. 앞 노드의 출력이나 값 설정을 확인해주세요. |
| <a id="format_output_unsupported"></a>`FORMAT_OUTPUT_UNSUPPORTED` | validation | documents | 아니오 | `not_started` | 해당 입력으로 이동 | 이 포맷이 지원하지 않는 출력 형식입니다. 출력 형식을 다시 선택해주세요. |
| <a id="format_image_forbidden"></a>`FORMAT_IMAGE_FORBIDDEN` | artifact | documents | 아니오 | `not_started` | 파일 다시 선택 | 이미지를 문서에 넣지 못했습니다. 업로드한 파일이거나 앞 노드가 만든 이미지만 넣을 수 있습니다. |
| <a id="binding_source_not_run"></a>`BINDING_SOURCE_NOT_RUN` | validation | runtime | 아니오 | `not_started` | 해당 입력으로 이동 | 연결한 값의 출처 노드가 이번 실행에서 실행되지 않았습니다. 분기 경로를 확인해주세요. |
| <a id="binding_path_missing"></a>`BINDING_PATH_MISSING` | validation | runtime | 아니오 | `not_started` | 해당 입력으로 이동 | 연결한 값이 출처 노드의 결과에 없습니다. 경로를 다시 선택해주세요. |
| <a id="binding_source_failed"></a>`BINDING_SOURCE_FAILED` | validation | runtime | 아니오 | `not_started` | 해당 입력으로 이동 | 연결한 값의 출처 노드가 오류로 끝나 값을 가져올 수 없습니다. |

## safeDetails 허용 key

공개 payload 의 `safeDetails` 에는 아래 key 만 들어갈 수 있다. provider 원문, stack, SQL, credential, 경로는 어떤 key 로도 넣지 않는다.

- `CREDENTIAL_MISSING`: `provider`, `providerName`, `service`
- `CREDENTIAL_INVALID`: `provider`, `providerName`, `service`, `status`
- `CREDENTIAL_FORBIDDEN`: `provider`, `providerName`, `service`, `status`
- `CREDENTIAL_EXPIRED`: `provider`, `providerName`, `service`
- `VALIDATION_REQUIRED`: `field`, `label`
- `VALIDATION_INVALID_TYPE`: `field`, `label`, `expected`, `receivedType`
- `VALIDATION_OUT_OF_RANGE`: `field`, `label`, `min`, `max`, `allowed`
- `ARTIFACT_NOT_FOUND`: `artifactId`, `attachmentIndex`
- `ARTIFACT_FORBIDDEN`: `artifactId`, `attachmentIndex`
- `ARTIFACT_EXPIRED`: `artifactId`, `attachmentIndex`
- `ARTIFACT_TOO_LARGE`: `artifactId`, `attachmentIndex`, `sizeBytes`, `limitBytes`
- `ARTIFACT_UNSUPPORTED_TYPE`: `artifactId`, `attachmentIndex`, `mimeType`, `allowedTypes`
- `DATABASE_DRIVER_MISSING`: `dialect`, `supportedDialects`
- `DATABASE_CONNECTION_FAILED`: `dialect`, `phase`, `timeoutSeconds`
- `DATABASE_AUTH_FAILED`: `dialect`
- `DATABASE_TIMEOUT`: `dialect`, `timeoutSeconds`
- `DATABASE_QUERY_REJECTED`: `reason`, `allowedStatements`
- `DATABASE_QUERY_FAILED`: `dialect`
- `DELIVERY_INVALID_RECIPIENT`: `provider`, `status`
- `DELIVERY_AUTH_FAILED`: `provider`, `status`
- `DELIVERY_FORBIDDEN`: `provider`, `status`
- `DELIVERY_RATE_LIMITED`: `provider`, `status`, `retryAfterMs`
- `DELIVERY_TIMEOUT`: `provider`, `timeoutSeconds`
- `DELIVERY_PROVIDER_REJECTED`: `provider`, `status`, `reason`
- `DELIVERY_RESULT_UNKNOWN`: `provider`, `status`
- `CONNECTOR_NOT_FOUND`: `service`, `status`, `provider`
- `CONNECTOR_INVALID_REQUEST`: `service`, `status`, `provider`
- `CONNECTOR_RATE_LIMITED`: `service`, `status`, `provider`, `retryAfterMs`
- `CONNECTOR_QUOTA_EXCEEDED`: `service`, `status`, `provider`
- `CONNECTOR_TIMEOUT`: `service`, `provider`, `timeoutSeconds`
- `CONNECTOR_NETWORK_ERROR`: `service`, `provider`
- `CONNECTOR_PROVIDER_ERROR`: `service`, `status`, `provider`
- `RUNTIME_RESOURCE_EXCEEDED`: `limitKind`, `limit`, `nodeType`
- `RUNTIME_USER_CODE_FAILED`: `nodeType`, `errorType`, `line`
- `RUNTIME_CANCELLED`: `phase`
- `RUNTIME_OUTPUT_TOO_LARGE`: `sizeBytes`, `limitBytes`
- `RUNTIME_SERIALIZATION_FAILED`: `phase`
- `RUNTIME_NODE_DISABLED`: `nodeType`
- `INTERNAL_UNKNOWN`: `phase`
- `LEGACY_NODE_ERROR`: `legacyPattern`
- `POINTING_TARGET_NOT_FOUND`: `targets`, `scope`, `targetCount`
- `POINTING_TARGET_STALE`: `targets`, `scope`, `targetCount`
- `POINTING_SCOPE_VIOLATION`: `targets`, `scope`, `targetCount`
- `POINTING_CONTEXT_TOO_LARGE`: `targets`, `scope`, `targetCount`
- `POINTING_FORBIDDEN`: `targets`, `scope`, `targetCount`
- `POINTING_INVALID_CONTEXT`: `targets`, `scope`, `targetCount`
- `FORMAT_NOT_FOUND`: `formatId`
- `FORMAT_SPEC_INVALID`: `formatId`, `reason`
- `FORMAT_FIELD_MISSING`: `formatId`, `missingFields`
- `FORMAT_OUTPUT_UNSUPPORTED`: `formatId`, `output`
- `FORMAT_IMAGE_FORBIDDEN`: `formatId`, `artifactId`
- `BINDING_SOURCE_NOT_RUN`: `field`, `sourceNodeId`
- `BINDING_PATH_MISSING`: `field`, `sourceNodeId`, `path`
- `BINDING_SOURCE_FAILED`: `field`, `sourceNodeId`
