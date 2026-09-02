from __future__ import annotations

import base64
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from graph import compile_workflow
from image_generation_runtime import ImageGenerationError, generate_or_edit_image
from node_registry import node_registry
import node_generators  # noqa: F401 - registers generators


class FakeResponse:
    def __init__(self, status_code, payload, request_id="req_test"):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"x-request-id": request_id}

    def json(self):
        return self._payload


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _success(response_id="resp_1", revised_prompt="modern abstract IT illustration"):
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nimage-bytes").decode("ascii")
    return FakeResponse(
        200,
        {
            "id": response_id,
            "model": "gpt-5.6",
            "output": [
                {
                    "type": "image_generation_call",
                    "result": encoded,
                    "revised_prompt": revised_prompt,
                }
            ],
            "usage": {"input_tokens": 12, "output_tokens": 34, "total_tokens": 46},
        },
    )


def test_node_generator_is_registered():
    assert node_registry.has_node("imageGenerationNode")


def test_image_node_compiles_as_terminal_artifact_action():
    source = compile_workflow(
        [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "p1", "type": "promptNode", "data": {"userPrompt": "abstract IT illustration"}},
            {
                "id": "i1",
                "type": "imageGenerationNode",
                "data": {
                    "action": "generate", "model": "gpt-5.6", "size": "1024x1024",
                    "quality": "low", "background": "opaque", "outputFormat": "png",
                },
            },
        ],
        [{"source": "n1", "target": "p1"}, {"source": "p1", "target": "i1"}],
        project_id=1,
    )
    assert not source.startswith("Error")
    assert "generate_or_edit_image" in source


def test_generate_registers_owned_file_and_artifact(db, tmp_path):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return _success()

    result = generate_or_edit_image(
        api_key="sk-test",
        prompt="simple modern IT illustration",
        incoming="",
        action="generate",
        model="gpt-5.6",
        size="1024x1024",
        quality="low",
        background="opaque",
        output_format="png",
        db=db,
        owner_user_id=7,
        project_id=11,
        node_id="img1",
        session_id="editor",
        post=post,
        upload_root=tmp_path,
    )

    assert result["file_path"].startswith("uploads/")
    assert result["response_id"] == "resp_1"
    assert result["revision_index"] == 0
    # 공개 문자열은 uploads/<이름> 그대로, 물리 파일은 소유자 디렉토리(u7/) 밑이다.
    assert (tmp_path / "u7" / result["file_path"].split("/", 1)[1]).is_file()
    assert db.query(models.UploadedFile).filter_by(owner_user_id=7).count() == 1
    artifact = db.query(models.ImageArtifact).one()
    assert artifact.artifact_id == result["artifact_id"]
    assert artifact.stored_name.endswith(".png")
    assert artifact.output_metadata["usage"]["total_tokens"] == 46
    assert calls[0][1]["json"]["tools"][0]["action"] == "generate"


def test_feedback_context_continues_previous_response_and_versions_artifact(db, tmp_path):
    response_ids = iter(["resp_first", "resp_second"])
    payloads = []

    def post(_url, **kwargs):
        payloads.append(kwargs["json"])
        return _success(next(response_ids))

    first = generate_or_edit_image(
        api_key="sk-test", prompt="base scene", incoming="", action="generate",
        model="gpt-5.6", size="auto", quality="low", background="auto", output_format="webp",
        db=db, owner_user_id=3, project_id=5, node_id="img", post=post, upload_root=tmp_path,
    )
    feedback = json.dumps({
        "feedback": "보라색을 줄이고 여백을 늘려줘",
        "previous_response_id": first["response_id"],
        "artifact_id": first["artifact_id"],
    }, ensure_ascii=False)
    second = generate_or_edit_image(
        api_key="sk-test", prompt="base scene", incoming=feedback, action="edit",
        model="gpt-5.6", size="auto", quality="medium", background="auto", output_format="webp",
        db=db, owner_user_id=3, project_id=5, node_id="img", post=post, upload_root=tmp_path,
    )

    assert payloads[1]["previous_response_id"] == "resp_first"
    assert "보라색을 줄이고" in payloads[1]["input"]
    assert second["parent_artifact_id"] == first["artifact_id"]
    assert second["revision_index"] == 1
    assert db.query(models.ImageArtifact).count() == 2


def test_edit_rerun_uses_latest_version_of_same_node(db, tmp_path):
    payloads = []

    def post(_url, **kwargs):
        payloads.append(kwargs["json"])
        return _success(f"resp_{len(payloads)}")

    first = generate_or_edit_image(
        api_key="sk-test", prompt="first version", incoming="", action="generate",
        model="gpt-5.6", size="auto", quality="low", background="auto", output_format="png",
        db=db, owner_user_id=9, project_id=4, node_id="img", post=post, upload_root=tmp_path,
    )
    second = generate_or_edit_image(
        api_key="sk-test", prompt="make the spacing wider", incoming="", action="edit",
        model="gpt-5.6", size="auto", quality="low", background="auto", output_format="png",
        db=db, owner_user_id=9, project_id=4, node_id="img", post=post, upload_root=tmp_path,
    )

    assert payloads[1]["previous_response_id"] == first["response_id"]
    assert second["parent_artifact_id"] == first["artifact_id"]
    assert second["revision_index"] == 1


def test_edit_requires_previous_context(db, tmp_path):
    with pytest.raises(ImageGenerationError, match="edit_context_missing"):
        generate_or_edit_image(
            api_key="sk-test", prompt="edit it", incoming="", action="edit",
            model="gpt-5.6", size="auto", quality="auto", background="auto", output_format="png",
            db=db, owner_user_id=1, post=lambda *_args, **_kwargs: _success(), upload_root=tmp_path,
        )


def test_moderation_error_is_not_retried(db, tmp_path):
    calls = 0

    def post(_url, **_kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse(
            400,
            {"error": {"type": "image_generation_user_error", "code": "moderation_blocked", "moderation_details": {"moderation_stage": "input"}}},
        )

    with pytest.raises(ImageGenerationError, match="moderation_blocked"):
        generate_or_edit_image(
            api_key="sk-test", prompt="blocked", incoming="", action="generate",
            model="gpt-5.6", size="auto", quality="auto", background="auto", output_format="png",
            db=db, owner_user_id=1, post=post, upload_root=tmp_path,
        )
    assert calls == 1
