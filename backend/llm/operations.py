from __future__ import annotations

from collections import Counter
from typing import Iterable


def summarize_generation_operations(traces: Iterable, *, training_example_count: int = 0) -> dict:
    rows = list(traces)
    outcomes = Counter(str(row.outcome or "unknown") for row in rows)
    providers = Counter(str(row.provider or "unknown") for row in rows)
    acceptance = Counter()
    issue_codes = Counter()
    latencies = []
    total_tokens = 0
    dry_run_applicable = 0
    dry_run_passed = 0

    for row in rows:
        summary = row.graph_summary or {}
        status = summary.get("acceptance_status")
        if row.outcome == "graph":
            acceptance[status or "unobserved"] += 1
        dry_run = summary.get("dry_run")
        if isinstance(dry_run, dict):
            dry_run_applicable += 1
            dry_run_passed += int(bool(dry_run.get("success")))
        for issue in row.validation_issues or []:
            if isinstance(issue, dict):
                issue_codes[str(issue.get("code") or "UNKNOWN")] += 1
        latencies.append(max(0, int(row.latency_ms or 0)))
        total_tokens += int((row.token_usage or {}).get("total_tokens", 0) or 0)

    ordered_latency = sorted(latencies)

    def percentile(fraction: float) -> int:
        if not ordered_latency:
            return 0
        index = min(len(ordered_latency) - 1, round((len(ordered_latency) - 1) * fraction))
        return ordered_latency[index]

    completed = sum(1 for row in rows if row.status == "completed")
    observed = sum(acceptance[key] for key in ("accepted", "partially_modified", "discarded"))
    adopted = acceptance["accepted"] + acceptance["partially_modified"]
    return {
        "trace_count": len(rows),
        "completed_count": completed,
        "error_count": len(rows) - completed,
        "success_rate": round(completed / max(1, len(rows)) * 100, 2),
        "outcomes": dict(outcomes),
        "providers": dict(providers),
        "acceptance": dict(acceptance),
        "acceptance_rate": round(adopted / max(1, observed) * 100, 2),
        "dry_run_pass_rate": round(dry_run_passed / max(1, dry_run_applicable) * 100, 2),
        "dry_run_sample_count": dry_run_applicable,
        "p50_latency_ms": percentile(0.5),
        "p95_latency_ms": percentile(0.95),
        "total_tokens": total_tokens,
        "validation_issue_codes": dict(issue_codes.most_common(10)),
        "training_example_count": training_example_count,
    }
