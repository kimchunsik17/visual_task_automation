from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from database import SessionLocal
from models import TrainingExample


DATASET_VERSION = "workflow-sft-v1"
GENERATION_SYSTEM_PROMPT = (
    "사용자 요청과 TaskSpec을 바탕으로 유효한 워크플로우 FlowGraph JSON만 반환한다. "
    "자격증명과 실행 시 입력은 안전한 placeholder로 둔다."
)
REPAIR_SYSTEM_PROMPT = (
    "생성 그래프와 검증 오류를 확인하고 필요한 노드, 엣지, 필드만 수정한 전체 FlowGraph JSON을 반환한다."
)


def dataset_split(group_key: str, seed: str = "workflow-sft-v1") -> str:
    bucket = int(hashlib.sha256(f"{seed}:{group_key}".encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "validation"
    return "test"


def _generation_record(row: TrainingExample) -> dict:
    user_payload = {"request": row.request_text, "task_spec": row.task_spec}
    return {
        "id": row.trace_id,
        "messages": [
            {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            {"role": "assistant", "content": json.dumps(row.final_graph, ensure_ascii=False)},
        ],
        "metadata": {
            "dataset_version": DATASET_VERSION,
            "kind": "generation",
            "acceptance_status": row.acceptance_status,
            "provider": row.provider,
            "model": row.model_name,
            "prompt_versions": row.prompt_versions,
        },
    }


def _repair_record(row: TrainingExample) -> dict:
    user_payload = {
        "request": row.request_text,
        "generated_graph": row.generated_graph,
        "validation_issues": row.validation_issues,
    }
    return {
        "id": row.trace_id,
        "messages": [
            {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            {"role": "assistant", "content": json.dumps(row.final_graph, ensure_ascii=False)},
        ],
        "metadata": {
            "dataset_version": DATASET_VERSION,
            "kind": "repair",
            "edit_metrics": row.edit_metrics,
            "provider": row.provider,
            "model": row.model_name,
        },
    }


def export_datasets(
    output_dir: Path,
    *,
    max_edit_ratio: float = 0.35,
    seed: str = DATASET_VERSION,
    session_factory=SessionLocal,
) -> dict:
    db = session_factory()
    try:
        rows = db.query(TrainingExample).filter(
            TrainingExample.acceptance_status.in_(("accepted", "partially_modified")),
        ).all()
    finally:
        db.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        (kind, split): output_dir / f"{kind}-{split}.jsonl"
        for kind in ("generation", "repair") for split in ("train", "validation", "test")
    }
    handles = {key: path.open("w", encoding="utf-8") for key, path in files.items()}
    counts: Counter[str] = Counter()
    try:
        for row in rows:
            if not isinstance(row.final_graph, dict):
                counts["excluded_missing_final_graph"] += 1
                continue
            edit_ratio = float((row.edit_metrics or {}).get("edit_ratio", 0) or 0)
            if row.acceptance_status == "partially_modified" and edit_ratio > max_edit_ratio:
                counts["excluded_large_edit"] += 1
                continue
            split = dataset_split(str(row.project_id or row.request_hash), seed)
            handles[("generation", split)].write(
                json.dumps(_generation_record(row), ensure_ascii=False) + "\n"
            )
            counts[f"generation_{split}"] += 1
            if row.generated_graph != row.final_graph:
                handles[("repair", split)].write(
                    json.dumps(_repair_record(row), ensure_ascii=False) + "\n"
                )
                counts[f"repair_{split}"] += 1
    finally:
        for handle in handles.values():
            handle.close()

    manifest = {
        "dataset_version": DATASET_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "max_edit_ratio": max_edit_ratio,
        "split_policy": "project-grouped deterministic 80/10/10",
        "consent_policy_version": "training-consent-v1",
        "counts": dict(counts),
        "files": {f"{kind}_{split}": str(path) for (kind, split), path in files.items()},
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="동의·채택된 workflow SFT/repair 데이터셋 내보내기")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "datasets" / DATASET_VERSION)
    parser.add_argument("--max-edit-ratio", type=float, default=0.35)
    parser.add_argument("--seed", default=DATASET_VERSION)
    args = parser.parse_args()
    print(json.dumps(export_datasets(
        args.output_dir, max_edit_ratio=args.max_edit_ratio, seed=args.seed,
    ), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
