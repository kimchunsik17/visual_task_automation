"""delivery_attachments.py — 발송 노드 공통 첨부 runtime (ADR-0018, 우선 백로그 20 FILE-SEND-1).

모든 발송 채널(Discord·SMTP·Gmail)이 **같은 검증·stream·정리 경로**를 쓰게 한다. 채널마다 파일
처리를 따로 두면 한쪽만 소유권을 확인하거나 한쪽만 descriptor 를 닫는 상태가 반드시 생긴다.

정책(`AttachmentPolicy`)은 한 곳에 선언하고 Node Definition·Inspector 사전 검증·런타임이 같은 값을
읽는다. provider 실제 한도보다 **작은 제품 기본값**을 둔다 — 우리 쪽에서 먼저 거절해야 사용자가
파일별 이유를 볼 수 있고, provider 의 413 은 어떤 파일이 문제인지 알려주지 않는다.

전부 통과하기 전에는 어떤 파일도 열지 않는다(all-or-nothing). §4.10 출시 게이트의 "다중 파일 중
하나가 만료·초과·미지원이면 발송 전에 전체 요청이 안전하게 중단된다" 가 이 규칙이다.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Sequence

import artifacts
from artifacts import ArtifactError, ResolvedArtifact
from node_errors import make_error

MB = 1024 * 1024


def _flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no"}


def delivery_v1_enabled() -> bool:
    """`ARTIFACT_DELIVERY_V1` — 공통 resolver 를 통한 첨부 전송 전체 스위치(기본 켜짐).

    끄면 발송 노드는 본문만 보낸다. 소유권을 확인하지 않는 예전 로컬 경로 fallback 은 어느 쪽에서도
    되살아나지 않는다(§4.10 되돌리기).
    """
    return _flag("ARTIFACT_DELIVERY_V1", True)


def connector_enabled(provider: str) -> bool:
    """connector 별 flag. 문제가 생기면 해당 채널의 첨부만 끄고 텍스트 발송은 유지한다."""
    return delivery_v1_enabled() and _flag(f"ARTIFACT_DELIVERY_{provider.upper()}", True)


def legacy_path_binding_enabled() -> bool:
    """`ARTIFACT_DELIVERY_LEGACY_PATHS` — 결과 문자열의 `uploads/...` 를 등록된 artifact 로 되돌리는
    한 릴리스짜리 이행 adapter(기본 켜짐). 등록·소유권이 확인되는 경우에만 변환한다."""
    return _flag("ARTIFACT_DELIVERY_LEGACY_PATHS", True)


# ── 정책 ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AttachmentPolicy:
    provider: str
    max_files: int
    max_bytes_per_file: int
    max_total_bytes: int
    timeout_seconds: float
    # 비어 있으면 "등록된 형식 전부 허용". 채널이 제한하는 경우에만 채운다.
    allowed_mime_prefixes: Sequence[str] = ()
    blocked_kinds: Sequence[str] = ()

    def allows_mime(self, mime_type: str) -> bool:
        if not self.allowed_mime_prefixes:
            return True
        lowered = (mime_type or "").lower()
        return any(lowered.startswith(prefix) for prefix in self.allowed_mime_prefixes)

    def to_public_dict(self) -> Dict[str, Any]:
        """Inspector 가 "provider 한도 대비 총량" 을 그릴 때 읽는 값."""
        return {
            "provider": self.provider,
            "maxFiles": self.max_files,
            "maxBytesPerFile": self.max_bytes_per_file,
            "maxTotalBytes": self.max_total_bytes,
            "timeoutSeconds": self.timeout_seconds,
            "allowedMimePrefixes": list(self.allowed_mime_prefixes),
        }


# provider 실제 한도(참고): Discord 봇/웹훅 기본 25MB·파일 10개, Gmail 25MB, SMTP 는 서버마다 다름.
# 아래는 그보다 작은 제품 기본값이다.
POLICIES: Dict[str, AttachmentPolicy] = {
    "discord": AttachmentPolicy(
        provider="discord", max_files=10,
        max_bytes_per_file=8 * MB, max_total_bytes=20 * MB, timeout_seconds=30.0,
    ),
    "smtp": AttachmentPolicy(
        provider="smtp", max_files=10,
        max_bytes_per_file=10 * MB, max_total_bytes=20 * MB, timeout_seconds=30.0,
    ),
    "gmail": AttachmentPolicy(
        provider="gmail", max_files=10,
        # Gmail 은 base64 로 감싼 raw message 전체가 한도에 들어간다(약 4/3 배). 원본 기준으로
        # 더 작게 잡아 인코딩 뒤에도 한도 안에 남게 한다.
        max_bytes_per_file=8 * MB, max_total_bytes=15 * MB, timeout_seconds=45.0,
    ),
}


def policy_for(provider: str) -> AttachmentPolicy:
    return POLICIES.get((provider or "").lower(), POLICIES["discord"])


def policies_public() -> Dict[str, Dict[str, Any]]:
    return {name: policy.to_public_dict() for name, policy in POLICIES.items()}


# ── 노드 설정 → artifact id 목록 ─────────────────────────────────────────
ATTACH_MODE_AUTO = "auto"
ATTACH_MODE_NONE = "none"
ATTACH_MODE_SELECT = "select"
ATTACH_MODES = (ATTACH_MODE_AUTO, ATTACH_MODE_NONE, ATTACH_MODE_SELECT)


def normalize_config(raw: Any) -> Dict[str, Any]:
    """노드의 `attachments` 설정을 `{mode, artifactIds}` 로 정규화한다.

    사용자·AI 생성기·예전 그래프가 넣는 모양이 제각각이라(문자열 하나, id 배열, dict) 여기서
    한 모양으로 모은다. 알 수 없는 값은 기본값(auto)으로 떨어진다 — 설정 하나 때문에 발송
    자체가 실패하지는 않게 한다.
    """
    if raw is None or raw == "":
        return {"mode": ATTACH_MODE_AUTO, "artifactIds": []}
    if isinstance(raw, str):
        text = raw.strip()
        if text in ATTACH_MODES:
            return {"mode": text, "artifactIds": []}
        return {"mode": ATTACH_MODE_SELECT, "artifactIds": [text]} if text else \
               {"mode": ATTACH_MODE_AUTO, "artifactIds": []}
    if isinstance(raw, (list, tuple)):
        ids = [str(item).strip() for item in raw if str(item or "").strip()]
        return {"mode": ATTACH_MODE_SELECT if ids else ATTACH_MODE_AUTO, "artifactIds": ids}
    if isinstance(raw, dict):
        mode = str(raw.get("mode") or "").strip().lower()
        ids = raw.get("artifactIds") or raw.get("artifact_ids") or []
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        ids = [str(item).strip() for item in ids if str(item or "").strip()]
        if mode not in ATTACH_MODES:
            mode = ATTACH_MODE_SELECT if ids else ATTACH_MODE_AUTO
        return {"mode": mode, "artifactIds": ids}
    return {"mode": ATTACH_MODE_AUTO, "artifactIds": []}


def collect_artifact_ids(
    config: Any,
    *,
    upstream_artifact_ids: Sequence[str] = (),
    upstream_text: str = "",
    db=None,
    owner_user_id: int = 0,
) -> List[str]:
    """이번 발송에 쓸 artifact id 목록.

      select — 사용자가 Inspector 에서 고른 것만.
      none   — 첨부하지 않는다(본문만).
      auto   — 선행 노드가 만든 artifact(`NodeResult.artifacts`)를 그대로 잇는다. 그것이 없고
               legacy adapter 가 켜져 있으면 결과 문자열의 `uploads/...` 를 **등록된 artifact 로
               역조회되는 경우에만** 변환한다(임의 로컬 경로는 열지 않는다).
    """
    normalized = normalize_config(config)
    mode = normalized["mode"]
    if mode == ATTACH_MODE_NONE:
        return []
    if mode == ATTACH_MODE_SELECT:
        return list(normalized["artifactIds"])

    ids = [str(item) for item in upstream_artifact_ids if str(item or "").strip()]
    if ids:
        return ids
    if not (db is not None and upstream_text and legacy_path_binding_enabled()):
        return []

    converted: List[str] = []
    for raw_path in artifacts.find_legacy_paths(upstream_text):
        ref = artifacts.lookup_by_stored_path(db, raw_path)
        # 소유자가 다르면 변환하지 않는다. 여기서 걸러도 resolve() 가 한 번 더 막지만, 애초에
        # 남의 파일 id 를 목록에 올리지 않는 편이 오류 메시지도 정확하다.
        if ref and ref.artifact_id and int(ref.owner_user_id or 0) == int(owner_user_id or 0):
            if ref.artifact_id not in converted:
                converted.append(ref.artifact_id)
    return converted


def unresolved_legacy_paths(db, text: str, *, owner_user_id: int = 0) -> List[str]:
    """결과 문자열에는 있지만 등록된 artifact 로 되돌릴 수 없는 경로들.

    편집기가 "파일을 다시 선택하세요"(needs_input) 를 띄울 근거다(FILE-SEND-4 ④).
    """
    missing: List[str] = []
    for raw_path in artifacts.find_legacy_paths(text):
        ref = artifacts.lookup_by_stored_path(db, raw_path) if db is not None else None
        if not ref or int(ref.owner_user_id or 0) != int(owner_user_id or 0):
            missing.append(raw_path)
    return missing


# ── 검증과 stream ────────────────────────────────────────────────────────
def _too_large(ref, index: int, limit: int, node_type, node_id) -> ArtifactError:
    return ArtifactError(make_error(
        "ARTIFACT_TOO_LARGE", effect_state="not_started",
        safe_details={"artifactId": ref.artifact_id, "attachmentIndex": index,
                      "sizeBytes": ref.size_bytes, "limitBytes": limit},
        node_type=node_type, node_id=node_id,
    ))


def validate_attachments(
    db,
    artifact_ids: Sequence[str],
    *,
    owner_user_id: int,
    project_id: Optional[int],
    policy: AttachmentPolicy,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
) -> List[ResolvedArtifact]:
    """전송 없이 **검증만** 한다. Inspector 의 "첨부 검증" 과 런타임이 같은 함수를 쓴다.

    하나라도 실패하면 예외로 끝난다 — 일부만 빠진 채로 발송하지 않기 위해서다.
    """
    ids = [str(item).strip() for item in artifact_ids if str(item or "").strip()]
    # 같은 파일을 두 번 첨부하지 않는다(auto + select 가 겹치는 경우).
    deduped: List[str] = []
    for item in ids:
        if item not in deduped:
            deduped.append(item)

    if len(deduped) > policy.max_files:
        raise ArtifactError(make_error(
            "ARTIFACT_TOO_LARGE", effect_state="not_started",
            user_message=f"첨부는 최대 {policy.max_files}개까지 보낼 수 있습니다. 지금은 {len(deduped)}개입니다.",
            safe_details={"attachmentIndex": policy.max_files, "limitBytes": policy.max_total_bytes},
            node_type=node_type, node_id=node_id,
        ))

    resolved: List[ResolvedArtifact] = []
    total_bytes = 0
    for index, artifact_id in enumerate(deduped):
        item = artifacts.resolve(
            db, artifact_id, owner_user_id=owner_user_id, project_id=project_id,
            index=index, node_type=node_type, node_id=node_id,
        )
        if item.ref.size_bytes > policy.max_bytes_per_file:
            raise _too_large(item.ref, index, policy.max_bytes_per_file, node_type, node_id)
        if not policy.allows_mime(item.ref.mime_type) or item.ref.kind in policy.blocked_kinds:
            raise ArtifactError(make_error(
                "ARTIFACT_UNSUPPORTED_TYPE", effect_state="not_started",
                safe_details={"artifactId": item.ref.artifact_id, "attachmentIndex": index,
                              "mimeType": item.ref.mime_type,
                              "allowedTypes": ", ".join(policy.allowed_mime_prefixes) or "all"},
                node_type=node_type, node_id=node_id,
            ))
        total_bytes += item.ref.size_bytes
        if total_bytes > policy.max_total_bytes:
            raise _too_large(item.ref, index, policy.max_total_bytes, node_type, node_id)
        resolved.append(item)
    return resolved


@contextlib.contextmanager
def open_attachments(resolved: Sequence[ResolvedArtifact]) -> Iterator[List[tuple]]:
    """열린 파일 handle 을 `(filename, handle, mime_type)` 로 넘기고, 어떤 경로로 끝나든 닫는다.

    성공·실패·취소·재시도 전부에서 descriptor 가 남지 않아야 한다(§4.10 출시 게이트). 그래서
    handle 을 만드는 곳과 닫는 곳을 한 함수 안에 둔다 — adapter 마다 try/finally 를 쓰면 언젠가
    한 곳이 빠진다.
    """
    handles: List[Any] = []
    try:
        entries = []
        for item in resolved:
            handle = item.open()
            handles.append(handle)
            entries.append((item.filename, handle, item.ref.mime_type))
        yield entries
    finally:
        for handle in handles:
            try:
                handle.close()
            except Exception:
                pass


@contextlib.contextmanager
def resolve_delivery_attachments(
    db,
    *,
    owner_user_id: int,
    project_id: Optional[int],
    artifact_ids: Sequence[str],
    policy: AttachmentPolicy,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
) -> Iterator[tuple]:
    """§4.10 FILE-SEND-1 의 진입점. `(resolved, opened)` 를 넘긴다.

    `resolved` 는 메타데이터(결과 보고용), `opened` 는 전송용 stream 이다. 검증이 하나라도
    실패하면 **파일을 열기 전에** 예외로 끝난다.
    """
    resolved = validate_attachments(
        db, artifact_ids, owner_user_id=owner_user_id, project_id=project_id,
        policy=policy, node_type=node_type, node_id=node_id,
    )
    with open_attachments(resolved) as opened:
        yield resolved, opened


def attachment_report(resolved: Sequence[ResolvedArtifact], *, status: str = "sent") -> List[Dict[str, Any]]:
    """`DeliveryResult.attachments` — 파일별 식별자·이름·크기·상태. 경로는 들어가지 않는다."""
    return [
        {
            "artifactId": item.ref.artifact_id,
            "filename": item.filename,
            "sizeBytes": item.ref.size_bytes,
            "mimeType": item.ref.mime_type,
            "status": status,
        }
        for item in resolved
    ]
