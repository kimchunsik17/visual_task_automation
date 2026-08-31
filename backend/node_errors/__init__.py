"""node_errors — 제품 공통 오류 계약 NodeError v1 과 중앙 catalog (ADR-0016).

    catalog     저장소 루트 error_catalog.json 로더·검증·번들 payload
    contract    NodeError / NodeResult / make_error / from_exception
    redaction   내부 기록·legacy 문구의 비밀 마스킹
    records     공개 payload 와 분리된 내부 ErrorRecord(requestId 로만 연결)
    adapters    ConnectorError → canonical code, legacy 문구 → LEGACY_NODE_ERROR
    database    Database Query 예외 분류
    delivery    Discord·SMTP 발송 실패 분류(effectState 판단)
    runtime     실행 로그에서 구조화 오류만 읽는 판정 함수들
    telemetry   code/category/effectState 집계

ADR-0007 의 ConnectorError 는 provider adapter 로 그대로 남고, 그 위에 이 계약이 얹힌다.
"""

from . import adapters, catalog, database, delivery, records, redaction, runtime  # noqa: F401
from .adapters import from_connector_error, legacy_error_from_text  # noqa: F401
from .catalog import CatalogError, UnknownErrorCode  # noqa: F401
from .contract import (  # noqa: F401
    ContractViolation,
    NodeError,
    NodeErrorException,
    NodeResult,
    from_exception,
    make_error,
)
