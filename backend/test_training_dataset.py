import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import TrainingExample
from training.export_dataset import dataset_split, export_datasets
from training.train_qlora import load_config


def test_dataset_split_keeps_same_project_in_same_partition():
    assert dataset_split("project-1") == dataset_split("project-1")
    assert dataset_split("project-1") in {"train", "validation", "test"}


def test_export_only_includes_adopted_low_edit_examples(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    session.add_all([
        TrainingExample(
            trace_id="accepted", user_id=None, project_id=1, request_hash="a",
            request_text="요약해줘", generated_graph={"nodes": []}, final_graph={"nodes": []},
            acceptance_status="accepted", edit_metrics={"edit_ratio": 0},
        ),
        TrainingExample(
            trace_id="large-edit", user_id=None, project_id=2, request_hash="b",
            request_text="바꿔줘", generated_graph={"nodes": []}, final_graph={"nodes": [{"id": "n1"}]},
            acceptance_status="partially_modified", edit_metrics={"edit_ratio": 0.9},
        ),
    ])
    session.commit()
    session.close()

    manifest = export_datasets(tmp_path, session_factory=factory)

    assert sum(value for key, value in manifest["counts"].items() if key.startswith("generation_")) == 1
    assert manifest["counts"]["excluded_large_edit"] == 1


def test_qlora_config_requires_explicit_base_model(tmp_path, monkeypatch):
    monkeypatch.delenv("QLORA_BASE_MODEL", raising=False)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"base_model": ""}), encoding="utf-8")

    with pytest.raises(ValueError, match="QLORA_BASE_MODEL"):
        load_config(config_path)
