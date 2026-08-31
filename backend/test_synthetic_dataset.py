import hashlib
import json
from pathlib import Path

from training.generate_synthetic import generate_dataset


def test_synthetic_dataset_is_complete_and_valid(tmp_path: Path):
    manifest = generate_dataset(tmp_path)
    report = json.loads((tmp_path / "validation-report.json").read_text(encoding="utf-8"))

    assert manifest["counts"] == {
        "total": 500,
        "generation": 300,
        "repair": 150,
        "clarification": 50,
    }
    assert report["passed"] is True
    assert report["validated_final_graphs"] == 450
    assert report["successful_dry_runs"] == 450
    assert report["invalid_repair_sources"] == 150
    assert report["evaluation_prompt_overlap"] == 0
    assert report["counts"] == {
        "clarification_test": 5,
        "clarification_train": 40,
        "clarification_validation": 5,
        "generation_test": 30,
        "generation_train": 240,
        "generation_validation": 30,
        "repair_test": 15,
        "repair_train": 120,
        "repair_validation": 15,
    }

    for filename, entry in manifest["files"].items():
        content = (tmp_path / filename).read_bytes()
        assert len(content.splitlines()) == entry["count"]
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
