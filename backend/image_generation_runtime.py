"""OpenAI Responses API based image generation/editing runtime.

The workflow compiler deliberately emits a small call into this module instead of
embedding HTTP, base64 and filesystem handling in generated source.  Besides
keeping generated workflows auditable, this gives image generation the same
ownership/quota guarantees as normal uploads and preserves the response id needed
for a later human-feedback revision turn.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import requests

import upload_security


RESPONSES_URL = "https://api.openai.com/v1/responses"
ALLOWED_ACTIONS = {"auto", "generate", "edit"}
ALLOWED_QUALITIES = {"auto", "low", "medium", "high"}
ALLOWED_BACKGROUNDS = {"auto", "opaque", "transparent"}
ALLOWED_FORMATS = {"png", "jpeg", "webp"}
ALLOWED_SIZES = {
    "auto", "1024x1024", "1536x1024", "1024x1536",
    "2048x2048", "2048x1152",
}
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MAX_IMAGE_BYTES = 25 * 1024 * 1024


class ImageGenerationError(RuntimeError):
    """Stable, user-facing image generation failure."""

    def __init__(self, code: str, message: str, *, request_id: str = ""):
        self.code = code
        self.request_id = request_id
        suffix = f" (요청 ID: {request_id})" if request_id else ""
        super().__init__(f"[{code}] {message}{suffix}")


def _coerce_context(incoming: Any) -> dict[str, Any]:
    """Accept the future review-node contract without breaking plain text input."""
    if isinstance(incoming, dict):
        return incoming
    if not isinstance(incoming, str):
        return {}
    text = incoming.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return {}
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _effective_prompt(configured_prompt: str, incoming: Any, context: dict[str, Any]) -> str:
    feedback = str(context.get("feedback") or "").strip()
    contextual_prompt = str(context.get("prompt") or "").strip()
    base = str(configured_prompt or "").strip()

    if feedback:
        if base:
            return f"{base}\n\n다음 검수 피드백을 반영해 이미지를 수정해 주세요:\n{feedback}"
        return feedback
    if base:
        return base
    if contextual_prompt:
        return contextual_prompt
    return str(incoming or "").strip()


def _extract_api_error(response: Any) -> ImageGenerationError:
    request_id = str(response.headers.get("x-request-id") or "")
    try:
        payload = response.json()
    except Exception:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else {}
    error = error if isinstance(error, dict) else {}
    code = str(error.get("code") or error.get("type") or f"http_{response.status_code}")

    if code == "moderation_blocked":
        details = error.get("moderation_details") or {}
        stage = details.get("moderation_stage") if isinstance(details, dict) else None
        if stage == "output":
            message = "생성 결과가 안전성 검사에서 차단되었습니다. 프롬프트를 바꿔 다시 시도해 주세요."
        else:
            message = "프롬프트 또는 입력 이미지가 안전성 검사에서 차단되었습니다. 요청 내용을 수정해 주세요."
    elif response.status_code == 401:
        message = "OpenAI API 키가 유효하지 않습니다. API 센터 연결을 확인해 주세요."
    elif response.status_code == 429:
        message = "OpenAI 이미지 생성 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요."
    else:
        message = str(error.get("message") or f"OpenAI 이미지 요청에 실패했습니다 (HTTP {response.status_code}).")
    return ImageGenerationError(code, message, request_id=request_id)


def _post_response(
    api_key: str,
    payload: dict[str, Any],
    *,
    post: Callable[..., Any],
    timeout_seconds: int,
) -> tuple[dict[str, Any], str]:
    response = None
    for attempt in range(2):
        try:
            response = post(
                RESPONSES_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=(10, timeout_seconds),
            )
        except requests.Timeout as exc:
            raise ImageGenerationError("timeout", "이미지 생성 시간이 초과되었습니다. 다시 시도해 주세요.") from exc
        except requests.RequestException as exc:
            raise ImageGenerationError("network_error", "OpenAI 이미지 서비스에 연결하지 못했습니다.") from exc
        if response.status_code < 400:
            body = response.json()
            if not isinstance(body, dict):
                raise ImageGenerationError("invalid_response", "OpenAI가 올바르지 않은 응답을 반환했습니다.")
            return body, str(response.headers.get("x-request-id") or "")
        if response.status_code != 429 and response.status_code < 500:
            raise _extract_api_error(response)
        if attempt == 0:
            time.sleep(0.25)
    assert response is not None
    raise _extract_api_error(response)


def _decode_first_image(body: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    for item in body.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "image_generation_call":
            continue
        encoded = item.get("result")
        if not encoded:
            continue
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ImageGenerationError("invalid_image_data", "OpenAI 이미지 데이터가 손상되었습니다.") from exc
        return image_bytes, item
    raise ImageGenerationError("image_missing", "OpenAI 응답에 생성된 이미지가 없습니다.")


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    return value if value > 0 else default


def generate_or_edit_image(
    *,
    api_key: str,
    prompt: str,
    incoming: Any,
    action: str,
    model: str,
    size: str,
    quality: str,
    background: str,
    output_format: str,
    previous_response_id: str = "",
    db=None,
    owner_user_id: int = 0,
    project_id: Optional[int] = None,
    node_id: str = "",
    session_id: str = "",
    post: Callable[..., Any] = requests.post,
    upload_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Generate one immutable image version and register its ownership metadata."""
    key = str(api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key or key.startswith("{{API_CENTER:"):
        raise ImageGenerationError("credential_missing", "OpenAI API 키를 API 센터에 연결해 주세요.")
    if not db or not owner_user_id:
        raise ImageGenerationError("owner_required", "이미지를 안전하게 저장하려면 프로젝트를 먼저 저장해 주세요.")

    action = str(action or "auto")
    size = str(size or "auto")
    quality = str(quality or "auto")
    background = str(background or "auto")
    output_format = str(output_format or "png")
    if action not in ALLOWED_ACTIONS:
        raise ImageGenerationError("invalid_action", f"지원하지 않는 이미지 동작입니다: {action}")
    if size not in ALLOWED_SIZES or quality not in ALLOWED_QUALITIES:
        raise ImageGenerationError("invalid_output", "지원하지 않는 이미지 크기 또는 품질입니다.")
    if background not in ALLOWED_BACKGROUNDS or output_format not in ALLOWED_FORMATS:
        raise ImageGenerationError("invalid_output", "지원하지 않는 배경 또는 출력 형식입니다.")
    if background == "transparent" and output_format == "jpeg":
        raise ImageGenerationError("invalid_output", "투명 배경은 PNG 또는 WebP 형식에서만 사용할 수 있습니다.")

    context = _coerce_context(incoming)
    effective_prompt = _effective_prompt(prompt, incoming, context)
    if not effective_prompt:
        raise ImageGenerationError("prompt_missing", "이미지를 생성하거나 수정할 프롬프트가 필요합니다.")

    prior_response_id = str(
        previous_response_id
        or context.get("previous_response_id")
        or context.get("response_id")
        or ""
    ).strip()
    parent_artifact_id = str(context.get("parent_artifact_id") or context.get("artifact_id") or "").strip() or None
    parent = None
    import models
    if parent_artifact_id:
        parent = (
            db.query(models.ImageArtifact)
            .filter(
                models.ImageArtifact.owner_user_id == owner_user_id,
                models.ImageArtifact.artifact_id == parent_artifact_id,
            )
            .first()
        )
        if parent is None:
            raise ImageGenerationError("artifact_not_found", "수정할 이미지 버전을 찾을 수 없거나 접근 권한이 없습니다.")
        if prior_response_id and parent.response_id and prior_response_id != parent.response_id:
            raise ImageGenerationError("revision_context_mismatch", "이미지 버전과 이전 응답 ID가 서로 일치하지 않습니다.")
    elif prior_response_id:
        parent = (
            db.query(models.ImageArtifact)
            .filter(
                models.ImageArtifact.owner_user_id == owner_user_id,
                models.ImageArtifact.response_id == prior_response_id,
            )
            .order_by(models.ImageArtifact.id.desc())
            .first()
        )
        parent_artifact_id = parent.artifact_id if parent else None
    elif action == "edit":
        # A user can review the last version, change only the feedback prompt and rerun the
        # same node.  The dedicated review node will pass explicit ids, but this fallback
        # makes iterative editing useful before that UI is present.
        latest_query = db.query(models.ImageArtifact).filter(
            models.ImageArtifact.owner_user_id == owner_user_id,
            models.ImageArtifact.node_id == node_id,
        )
        if project_id is not None:
            latest_query = latest_query.filter(models.ImageArtifact.project_id == project_id)
        parent = latest_query.order_by(models.ImageArtifact.id.desc()).first()
        if parent and parent.response_id:
            prior_response_id = parent.response_id
            parent_artifact_id = parent.artifact_id
    if action == "edit" and not prior_response_id:
        raise ImageGenerationError("edit_context_missing", "수정 모드에는 이전 이미지 응답 ID가 필요합니다.")

    tool = {
        "type": "image_generation",
        "action": action,
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": output_format,
    }
    payload: dict[str, Any] = {
        "model": str(model or "gpt-5.6"),
        "input": effective_prompt,
        "tools": [tool],
    }
    if prior_response_id:
        payload["previous_response_id"] = prior_response_id

    body, request_id = _post_response(
        key,
        payload,
        post=post,
        timeout_seconds=_positive_int_env("IMAGE_GENERATION_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
    )
    image_bytes, image_call = _decode_first_image(body)
    max_bytes = _positive_int_env("MAX_GENERATED_IMAGE_BYTES", DEFAULT_MAX_IMAGE_BYTES)
    if not image_bytes or len(image_bytes) > max_bytes:
        raise ImageGenerationError("image_too_large", f"생성 이미지가 저장 한도({max_bytes // (1024 * 1024)}MB)를 초과했습니다.")

    # 물리 파일은 소유자 디렉토리(uploads/u<id>/) 밑에 쓴다. upload_root 인자는 테스트용
    # 루트 재지정이고, 그 밑의 소유자 하위 디렉토리 규칙은 owner_dir 가 정본이다.
    base = Path(upload_root) if upload_root else None
    root = upload_security.owner_dir(owner_user_id, root=base)
    root.mkdir(parents=True, exist_ok=True)
    extension = ".jpg" if output_format == "jpeg" else f".{output_format}"
    stored_path = root / f"{uuid.uuid4().hex}{extension}"
    upload_security.ensure_quota(db, owner_user_id, len(image_bytes))

    try:
        with stored_path.open("xb") as output:
            output.write(image_bytes)

        upload_security.record_upload(
            db,
            stored_path=stored_path,
            original_name=f"openai-image-{node_id or 'node'}{extension}",
            owner_user_id=owner_user_id,
            project_id=project_id,
            purpose="generated-image",
            content_type={"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}[output_format],
            size_bytes=len(image_bytes),
        )

        artifact = models.ImageArtifact(
            artifact_id=uuid.uuid4().hex,
            owner_user_id=owner_user_id,
            project_id=project_id,
            node_id=node_id or None,
            session_id=str(session_id or "") or None,
            stored_name=stored_path.name,
            parent_artifact_id=parent_artifact_id,
            response_id=str(body.get("id") or "") or None,
            request_id=request_id or None,
            revision_index=(parent.revision_index + 1) if parent else (1 if parent_artifact_id else 0),
            action=action,
            provider="openai",
            model=str(body.get("model") or model or "gpt-5.6"),
            prompt=effective_prompt,
            revised_prompt=str(image_call.get("revised_prompt") or "") or None,
            output_metadata={
                "size": size,
                "quality": quality,
                "background": background,
                "output_format": output_format,
                "usage": body.get("usage") or {},
            },
        )
        db.add(artifact)
        db.commit()
    except Exception:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise

    return {
        "file_path": f"uploads/{stored_path.name}",
        "artifact_id": artifact.artifact_id,
        "parent_artifact_id": parent_artifact_id,
        "response_id": artifact.response_id,
        "revision_index": artifact.revision_index,
        "revised_prompt": artifact.revised_prompt,
        "usage": body.get("usage") or {},
    }
