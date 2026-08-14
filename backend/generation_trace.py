from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from llm.providers import load_llm_settings
from llm.task_spec import TASK_SPEC_PROMPT_VERSION


GENERATION_TRACE_SCHEMA_VERSION = "generation-trace-v1"
MAX_TRACE_TEXT_LENGTH = 2_000
_UI_DATA_KEYS = {
    "onChange", "onDelete", "onExpandChange", "onClearAIHighlight",
    "isAIModified", "aiChanges",
}
_SENSITIVE_DATA_KEY = re.compile(
    r"api.?key|token|secret|password|authorization|credential|connection.?string|bot.?token|access.?token|refresh.?token",
    re.IGNORECASE,
)

_SECRET_PATTERNS = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(api[_ -]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
    (re.compile(
        r"(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9._%+-])",
        re.IGNORECASE,
    ), "[REDACTED_EMAIL]"),
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def redact_trace_text(value: Any, max_length: int = MAX_TRACE_TEXT_LENGTH) -> str:
    text = str(value or "")
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    if len(text) > max_length:
        text = text[:max_length] + "..."
    return text


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_trace_text(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_trace_text(value)


def sanitize_training_graph(graph_data: Optional[dict]) -> dict:
    graph = graph_data or {}

    def sanitize(value: Any, key: str = "") -> Any:
        if _SENSITIVE_DATA_KEY.search(key):
            return "[REDACTED_CREDENTIAL]"
        if isinstance(value, dict):
            return {
                str(child_key): sanitize(child_value, str(child_key))
                for child_key, child_value in value.items()
                if child_key not in _UI_DATA_KEYS
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if isinstance(value, str):
            return redact_trace_text(value, max_length=5_000)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return redact_trace_text(value, max_length=5_000)

    return sanitize({
        "title": graph.get("title", ""),
        "description": graph.get("description", ""),
        "nodes": graph.get("nodes") or [],
        "edges": graph.get("edges") or [],
    })


def summarize_graph(graph_data: Optional[dict]) -> dict:
    graph = graph_data or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_types: dict[str, int] = {}
    for node in nodes:
        node_type = str(node.get("type") or "unknown")
        node_types[node_type] = node_types.get(node_type, 0) + 1
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_types": node_types,
    }


def _trace_hash(value: Any) -> str:
    salt = os.getenv("GENERATION_TRACE_HASH_SALT") or os.getenv("JWT_SECRET") or "generation-trace"
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hmac.new(salt.encode("utf-8"), encoded, hashlib.sha256).hexdigest()


def graph_signature(graph_data: Optional[dict]) -> dict:
    graph = graph_data or {}
    nodes = []
    for node in graph.get("nodes") or []:
        data = {
            str(key): value for key, value in (node.get("data") or {}).items()
            if key not in _UI_DATA_KEYS
        }
        nodes.append({
            "id": str(node.get("id") or ""),
            "type": str(node.get("type") or "unknown"),
            "data_hash": _trace_hash(data),
        })
    edges = [{
        "source": str(edge.get("source") or ""),
        "target": str(edge.get("target") or ""),
        "source_handle": edge.get("sourceHandle"),
        "target_handle": edge.get("targetHandle"),
    } for edge in graph.get("edges") or []]
    return {
        "nodes": sorted(nodes, key=lambda item: (item["id"], item["type"])),
        "edges": sorted(edges, key=lambda item: (
            item["source"], item["target"], str(item["source_handle"]), str(item["target_handle"]),
        )),
    }


def graph_fingerprint(graph_data: Optional[dict]) -> str:
    return _trace_hash(graph_signature(graph_data))


def compare_graph_signatures(generated: dict, saved: dict) -> dict:
    generated_nodes = {node["id"]: node for node in generated.get("nodes") or []}
    saved_nodes = {node["id"]: node for node in saved.get("nodes") or []}
    generated_ids = set(generated_nodes)
    saved_ids = set(saved_nodes)
    added_nodes = sorted(saved_ids - generated_ids)
    removed_nodes = sorted(generated_ids - saved_ids)
    modified_nodes = sorted(
        node_id for node_id in generated_ids & saved_ids
        if generated_nodes[node_id] != saved_nodes[node_id]
    )

    def edge_key(edge: dict) -> tuple:
        return (
            edge.get("source"), edge.get("target"),
            edge.get("source_handle"), edge.get("target_handle"),
        )

    generated_edges = {edge_key(edge) for edge in generated.get("edges") or []}
    saved_edges = {edge_key(edge) for edge in saved.get("edges") or []}
    added_edges = len(saved_edges - generated_edges)
    removed_edges = len(generated_edges - saved_edges)
    changed_elements = (
        len(added_nodes) + len(removed_nodes) + len(modified_nodes) + added_edges + removed_edges
    )
    generated_elements = max(1, len(generated_nodes) + len(generated_edges))

    if not saved_nodes and generated_nodes:
        acceptance_status = "discarded"
    elif generated_nodes and saved_nodes and not (generated_ids & saved_ids):
        acceptance_status = "discarded"
    elif changed_elements == 0:
        acceptance_status = "accepted"
    else:
        acceptance_status = "partially_modified"

    return {
        "acceptance_status": acceptance_status,
        "changed_elements": changed_elements,
        "edit_ratio": round(changed_elements / generated_elements, 4),
        "added_node_count": len(added_nodes),
        "removed_node_count": len(removed_nodes),
        "modified_node_count": len(modified_nodes),
        "added_edge_count": added_edges,
        "removed_edge_count": removed_edges,
    }


def build_generation_trace(
    *,
    trace_id: str,
    thread_id: str,
    message: str,
    complexity_level: str,
    graph_data: Optional[dict],
    token_usage: Optional[dict] = None,
    task_spec: Optional[dict] = None,
    validation_issues: Optional[list] = None,
    repair_notes: Optional[list[str]] = None,
    outcome: str,
    status: str,
    latency_ms: int,
    error_message: Optional[str] = None,
    repair_prompt_version: Optional[str] = None,
    langfuse_trace_id: Optional[str] = None,
    dry_run_result: Optional[dict] = None,
    training_consent: bool = False,
) -> dict:
    settings = load_llm_settings()
    routing_mode = os.getenv("LLM_ROUTING_MODE", "provider").strip().lower()
    trace_provider = settings.provider if routing_mode == "provider" else routing_mode
    trace_model_name = settings.model_for(complexity_level)
    if routing_mode in {"local", "hybrid"}:
        aliases = {"low": "FAST", "medium": "BALANCED", "high": "QUALITY"}
        profile_key = aliases.get(complexity_level.strip().lower(), complexity_level.upper())
        local_model = os.getenv(f"LLM_LOCAL_MODEL_{profile_key}", "").strip() or trace_model_name
        trace_model_name = (
            local_model if routing_mode == "local" else f"{local_model} -> {trace_model_name}"
        )
    store_content = _env_bool("GENERATION_TRACE_STORE_CONTENT", False)
    message_bytes = message.encode("utf-8")
    safe_usage = {
        key: value for key, value in (token_usage or {}).items()
        if not str(key).startswith("_")
    }
    request_kind = task_spec.get("request_kind") if task_spec else None
    graph_summary = summarize_graph(graph_data)
    graph_summary["fingerprint"] = graph_fingerprint(graph_data)
    graph_summary["_signature"] = graph_signature(graph_data)
    if dry_run_result is not None:
        graph_summary["dry_run"] = _sanitize_value(dry_run_result)
    trace = {
        "schema_version": GENERATION_TRACE_SCHEMA_VERSION,
        "trace_id": trace_id,
        "thread_id": thread_id,
        "status": status,
        "outcome": outcome,
        "request_kind": request_kind,
        "provider": trace_provider,
        "model_profile": complexity_level,
        "model_name": trace_model_name,
        "task_spec_prompt_version": TASK_SPEC_PROMPT_VERSION,
        "repair_prompt_version": repair_prompt_version,
        "request_hash": hashlib.sha256(message_bytes).hexdigest(),
        "request_length": len(message),
        "request_preview": redact_trace_text(message) if store_content else None,
        "task_spec": _sanitize_value(task_spec) if store_content and task_spec else None,
        "graph_summary": graph_summary,
        "validation_issues": _sanitize_value(validation_issues or []),
        "repair_notes": _sanitize_value(repair_notes or []),
        "token_usage": _sanitize_value(safe_usage),
        "latency_ms": max(0, int(latency_ms)),
        "langfuse_trace_id": langfuse_trace_id,
        "error_message": redact_trace_text(error_message) if error_message else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if (
        training_consent
        and _env_bool("LLM_TRAINING_DATA_COLLECTION_ENABLED", False)
        and outcome == "graph"
    ):
        trace["_training_candidate"] = {
            "request_text": redact_trace_text(message, max_length=8_000),
            "task_spec": _sanitize_value(task_spec) if task_spec else None,
            "generated_graph": sanitize_training_graph(graph_data),
            "consent_policy_version": "training-consent-v1",
        }
    return trace


def persist_generation_trace(db, trace: dict, *, user_id: Optional[int], project_id: Optional[int]):
    from models import GenerationTrace, TrainingExample

    row = GenerationTrace(
        trace_id=trace["trace_id"],
        user_id=user_id,
        project_id=project_id,
        thread_id=trace.get("thread_id"),
        status=trace.get("status") or "completed",
        outcome=trace.get("outcome"),
        request_kind=trace.get("request_kind"),
        provider=trace.get("provider"),
        model_profile=trace.get("model_profile"),
        model_name=trace.get("model_name"),
        task_spec_prompt_version=trace.get("task_spec_prompt_version"),
        repair_prompt_version=trace.get("repair_prompt_version"),
        request_hash=trace["request_hash"],
        request_length=trace.get("request_length", 0),
        request_preview=trace.get("request_preview"),
        task_spec=trace.get("task_spec"),
        graph_summary=trace.get("graph_summary") or {},
        validation_issues=trace.get("validation_issues") or [],
        repair_notes=trace.get("repair_notes") or [],
        token_usage=trace.get("token_usage") or {},
        latency_ms=trace.get("latency_ms", 0),
        langfuse_trace_id=trace.get("langfuse_trace_id"),
        error_message=trace.get("error_message"),
    )
    db.add(row)
    candidate = trace.get("_training_candidate")
    if candidate and user_id is not None:
        db.add(TrainingExample(
            trace_id=trace["trace_id"],
            user_id=user_id,
            project_id=project_id,
            request_hash=trace["request_hash"],
            request_text=candidate["request_text"],
            task_spec=candidate.get("task_spec"),
            generated_graph=candidate["generated_graph"],
            validation_issues=trace.get("validation_issues") or [],
            provider=trace.get("provider"),
            model_name=trace.get("model_name"),
            prompt_versions={
                "task_spec": trace.get("task_spec_prompt_version"),
                "repair": trace.get("repair_prompt_version"),
                "schema": trace.get("schema_version"),
            },
            consent_policy_version=candidate["consent_policy_version"],
        ))
    db.commit()
    db.refresh(row)
    return row


def record_trace_adoption(
    db,
    *,
    trace_id: str,
    user_id: int,
    project_id: int,
    saved_graph_data: dict,
) -> Optional[dict]:
    from models import GenerationTrace, TrainingExample

    row = db.query(GenerationTrace).filter(
        GenerationTrace.trace_id == trace_id,
        GenerationTrace.user_id == user_id,
        GenerationTrace.outcome == "graph",
    ).first()
    if row is None:
        return None
    summary = dict(row.graph_summary or {})
    generated_signature = summary.get("_signature")
    if not isinstance(generated_signature, dict):
        return None
    saved_signature = graph_signature(saved_graph_data)
    metrics = compare_graph_signatures(generated_signature, saved_signature)
    summary.update({
        "saved_fingerprint": _trace_hash(saved_signature),
        "acceptance_status": metrics["acceptance_status"],
        "edit_metrics": metrics,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    })
    row.project_id = project_id
    row.graph_summary = summary
    training_example = db.query(TrainingExample).filter(
        TrainingExample.trace_id == trace_id,
        TrainingExample.user_id == user_id,
    ).first()
    if training_example is not None:
        training_example.project_id = project_id
        training_example.final_graph = sanitize_training_graph(saved_graph_data)
        training_example.acceptance_status = metrics["acceptance_status"]
        training_example.edit_metrics = metrics
    db.commit()
    return metrics


def trace_to_dict(row) -> dict:
    graph_summary = dict(row.graph_summary or {})
    graph_summary.pop("_signature", None)
    return {
        "trace_id": row.trace_id,
        "status": row.status,
        "outcome": row.outcome,
        "request_kind": row.request_kind,
        "provider": row.provider,
        "model_profile": row.model_profile,
        "model_name": row.model_name,
        "task_spec_prompt_version": row.task_spec_prompt_version,
        "repair_prompt_version": row.repair_prompt_version,
        "request_hash": row.request_hash,
        "request_length": row.request_length,
        "request_preview": row.request_preview,
        "task_spec": row.task_spec,
        "graph_summary": graph_summary,
        "acceptance_status": graph_summary.get("acceptance_status"),
        "edit_metrics": graph_summary.get("edit_metrics"),
        "validation_issues": row.validation_issues or [],
        "repair_notes": row.repair_notes or [],
        "token_usage": row.token_usage or {},
        "latency_ms": row.latency_ms,
        "langfuse_trace_id": row.langfuse_trace_id,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
