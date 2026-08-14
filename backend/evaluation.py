from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, Optional

from graph import compile_workflow
from dry_run import dry_run_workflow
from flow_validation import validation_issues
from llm.providers import load_llm_settings
from llm.task_spec import TASK_SPEC_PROMPT_VERSION
from meta_agent import FLOW_REPAIR_PROMPT_VERSION, FlowGraph, run_agent_turn, validate_flow


EVALUATION_VERSION = "generation-repair-v2"
RESULTS_DIR = Path(os.getenv("EVALUATION_RESULTS_DIR", Path(__file__).parent / "evaluation_results"))
CACHE_DIR = Path(os.getenv("EVALUATION_CACHE_DIR", RESULTS_DIR / "cache"))
DEFAULT_SMOKE_CASE_IDS = (1, 6, 28)
EVALUATION_SOURCE_FILES = (
    Path(__file__),
    Path(__file__).parent / "meta_agent.py",
    Path(__file__).parent / "flow_validation.py",
    Path(__file__).parent / "llm" / "task_spec.py",
    Path(__file__).parent / "llm" / "providers" / "__init__.py",
)


def _case(
    case_id: int,
    category: str,
    prompt: str,
    expected_nodes: list[str],
    expected_paths: Optional[list[tuple[str, str]]] = None,
    required_data: Optional[dict[str, list[str]]] = None,
    expected_handles: Optional[list[tuple[str, str]]] = None,
    expected_outcome: str = "graph",
) -> dict:
    return {
        "id": case_id,
        "category": category,
        "prompt": prompt,
        "expected_nodes": expected_nodes,
        "expected_paths": [list(path) for path in (expected_paths or [])],
        "required_data": required_data or {},
        "expected_handles": [list(item) for item in (expected_handles or [])],
        "expected_outcome": expected_outcome,
    }


# 시나리오 축을 분리해 모델/프롬프트 변경 후 같은 입력으로 회귀를 비교한다.
TEST_CASES = [
    _case(1, "Linear", "입력받은 글을 세 문장으로 요약해서 결과 화면에 텍스트로 출력해줘.",
          ["startNode", "dynamicInputNode", "promptNode", "llmNode", "outputNode"],
          [("dynamicInputNode", "llmNode"), ("llmNode", "outputNode")],
          {"dynamicInputNode": ["inputLabel"], "promptNode": ["userPrompt"], "llmNode": ["model", "systemPrompt"]}),
    _case(2, "Schedule", "매일 아침 9시에 서울 날씨 API를 조회해서 슬랙으로 보내줘.",
          ["scheduleNode", "httpRequestNode", "slackNode"],
          [("scheduleNode", "httpRequestNode"), ("httpRequestNode", "slackNode")],
          {"scheduleNode": ["cronExpression"], "httpRequestNode": ["method", "url"]}),
    _case(3, "Webhook", "쇼핑몰 새 주문 webhook이 들어오면 카카오톡과 디스코드로 알려줘.",
          ["webhookNode", "kakaoNode", "discordNode"],
          [("webhookNode", "kakaoNode"), ("webhookNode", "discordNode")]),
    _case(4, "Condition", "리뷰 점수가 3점 미만이면 디스코드 경고, 아니면 감사 이메일을 보내줘.",
          ["conditionNode", "discordNode", "emailNode"],
          [("conditionNode", "discordNode"), ("conditionNode", "emailNode")],
          {"conditionNode": ["rules"]}, [("conditionNode", "else")]),
    _case(5, "Approval", "결제 요청을 보여주고 승인하면 결제 API를 호출하고 거절하면 거절 메일을 보내줘.",
          ["humanApprovalNode", "httpRequestNode", "emailNode"],
          [("humanApprovalNode", "httpRequestNode"), ("humanApprovalNode", "emailNode")],
          {"humanApprovalNode": ["message"]},
          [("humanApprovalNode", "approved"), ("humanApprovalNode", "rejected")]),
    _case(6, "Loop", "사용자 문장을 최대 3번 반복해서 다듬고 최종 결과를 출력해줘.",
          ["loopNode", "promptNode", "llmNode", "outputNode"],
          [("loopNode", "llmNode"), ("loopNode", "outputNode")],
          {"loopNode": ["maxIterations"]}, [("loopNode", "loop_start"), ("loopNode", "done")]),
    _case(7, "Distribution", "입력된 상품 목록 각각의 설명을 생성하고 결과를 합쳐줘.",
          ["distributorNode", "llmNode", "mergeNode", "outputNode"],
          [("distributorNode", "llmNode"), ("llmNode", "mergeNode")]),
    _case(8, "HTTP", "외부 REST API에 JSON을 POST하고 응답을 출력해줘.",
          ["httpRequestNode", "outputNode"], [("httpRequestNode", "outputNode")],
          {"httpRequestNode": ["method", "url"]}),
    _case(9, "JSON", "입력 문자열을 JSON으로 파싱하고 customer.email 값만 추출해줘.",
          ["jsonParserNode", "outputNode"], [("jsonParserNode", "outputNode")],
          {"jsonParserNode": ["mode", "extractKey"]}),
    _case(10, "Crawler", "해커뉴스를 크롤링해서 주요 글을 요약해줘.",
          ["webCrawlerNode", "promptNode", "llmNode", "outputNode"],
          [("webCrawlerNode", "llmNode"), ("llmNode", "outputNode")],
          {"webCrawlerNode": ["url"]}),
    _case(11, "Email", "입력된 회의 내용을 정리해서 담당자에게 이메일로 보내줘.",
          ["dynamicInputNode", "llmNode", "emailNode"],
          [("dynamicInputNode", "llmNode"), ("llmNode", "emailNode")],
          {"emailNode": ["toEmail", "subject"]}),
    _case(12, "Messenger", "입력 메시지를 짧게 요약해 텔레그램으로 보내줘.",
          ["dynamicInputNode", "llmNode", "telegramNode"], [("llmNode", "telegramNode")]),
    _case(13, "Calendar", "요청 내용을 바탕으로 구글 캘린더 일정을 생성해줘.",
          ["dynamicInputNode", "googleCalendarNode"],
          [("dynamicInputNode", "googleCalendarNode")], {"googleCalendarNode": ["mode"]}),
    _case(14, "Sheets", "webhook으로 받은 설문 응답을 구글 시트에 한 행씩 추가해줘.",
          ["webhookNode", "googleSheetsNode"], [("webhookNode", "googleSheetsNode")],
          {"googleSheetsNode": ["mode"]}),
    _case(15, "Notion", "회의록을 요약한 뒤 Notion 데이터베이스에 새 페이지로 저장해줘.",
          ["llmNode", "notionNode"], [("llmNode", "notionNode")], {"notionNode": ["mode"]}),
    _case(16, "Database", "읽기 전용 SQL로 오늘 가입한 사용자 수를 조회해서 출력해줘.",
          ["databaseNode", "outputNode"], [("databaseNode", "outputNode")]),
    _case(17, "Python", "CSV 텍스트를 파이썬으로 전처리해서 중복 행을 제거하고 출력해줘.",
          ["dynamicInputNode", "pythonNode", "outputNode"],
          [("dynamicInputNode", "pythonNode"), ("pythonNode", "outputNode")]),
    _case(18, "Tokenize", "업로드한 PDF에서 텍스트를 추출해 요약해줘.",
          ["tokenizerNode", "llmNode", "outputNode"],
          [("tokenizerNode", "llmNode")], {"tokenizerNode": ["method"]}),
    _case(19, "Document", "지원자 정보를 자기소개서 Word 서식에 채워 새 파일로 저장해줘.",
          ["templateAnalyzerNode", "llmNode", "fileModifierNode"],
          [("templateAnalyzerNode", "llmNode"), ("llmNode", "fileModifierNode")]),
    _case(20, "Poster", "행사 정보를 받아 900x1200 PNG 홍보 포스터로 저장해줘.",
          ["dynamicInputNode", "llmNode", "posterGeneratorNode"],
          [("llmNode", "posterGeneratorNode")],
          {"posterGeneratorNode": ["outputFormat", "width", "height"]}),
    _case(21, "Delay", "webhook을 받으면 10분 기다렸다가 확인 이메일을 보내줘.",
          ["webhookNode", "delayNode", "emailNode"],
          [("webhookNode", "delayNode"), ("delayNode", "emailNode")], {"delayNode": ["seconds"]}),
    _case(22, "Payment", "토스 결제 링크를 생성해서 카카오톡으로 발송해줘.",
          ["paymentLinkNode", "kakaoNode"], [("paymentLinkNode", "kakaoNode")]),
    _case(23, "MultiAgent", "번역, 요약, 감성 분석 전문가 중 알맞은 에이전트가 입력을 처리하게 해줘.",
          ["multiAgentNode", "llmNode", "outputNode"], [("multiAgentNode", "outputNode")]),
    _case(24, "Trigger", "텔레그램 메시지가 오면 내용을 요약해서 답장해줘.",
          ["telegramTriggerNode", "llmNode", "telegramNode"],
          [("telegramTriggerNode", "llmNode"), ("llmNode", "telegramNode")]),
    _case(25, "Trigger", "디스코드 메시지가 오면 질문에 답하고 같은 채널에 전송해줘.",
          ["discordTriggerNode", "llmNode", "discordNode"],
          [("discordTriggerNode", "llmNode"), ("llmNode", "discordNode")]),
    _case(26, "Risk", "환불 요청을 분류하고 10만원 이상이면 사람 승인을 거쳐 처리해줘.",
          ["conditionNode", "humanApprovalNode", "mergeNode"],
          [("conditionNode", "humanApprovalNode")], {"conditionNode": ["rules"]},
          [("conditionNode", "else")]),
    _case(27, "Monitoring", "30분마다 서비스 상태 API를 확인해 장애면 슬랙으로 알려줘.",
          ["scheduleNode", "httpRequestNode", "conditionNode", "slackNode"],
          [("scheduleNode", "httpRequestNode"), ("conditionNode", "slackNode")],
          {"scheduleNode": ["cronExpression"], "conditionNode": ["rules"]}),
    _case(28, "Ambiguous", "고객 문의 처리 자동화 만들어줘.",
          [], expected_outcome="clarification"),
    _case(29, "InvalidInput", "입력이 비어 있으면 안내하고, 있으면 요약해서 출력해줘.",
          ["dynamicInputNode", "conditionNode", "llmNode", "mergeNode", "outputNode"],
          [("conditionNode", "llmNode")], {"conditionNode": ["rules"]},
          [("conditionNode", "else")]),
    _case(30, "StructuredOutput", "지원자 소개를 name, skills, summary 필드의 JSON으로 변환해줘.",
          ["dynamicInputNode", "llmNode", "jsonParserNode", "outputNode"],
          [("llmNode", "jsonParserNode"), ("jsonParserNode", "outputNode")],
          {"llmNode": ["model", "systemPrompt"], "jsonParserNode": ["mode"]}),
]


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _smoke_case_ids() -> list[int]:
    raw = os.getenv("EVALUATION_SMOKE_CASE_IDS", "")
    if not raw.strip():
        return list(DEFAULT_SMOKE_CASE_IDS)
    valid_ids = {case["id"] for case in TEST_CASES}
    parsed = []
    for value in raw.split(","):
        try:
            case_id = int(value.strip())
        except ValueError:
            continue
        if case_id in valid_ids and case_id not in parsed:
            parsed.append(case_id)
    return parsed or list(DEFAULT_SMOKE_CASE_IDS)


def get_test_cases() -> list[dict]:
    return TEST_CASES


def get_evaluation_catalog() -> dict:
    return {
        "cases": TEST_CASES,
        "default_profile": os.getenv("EVALUATION_DEFAULT_PROFILE", "smoke"),
        "smoke_case_ids": _smoke_case_ids(),
        "targeted_max_cases": _env_int("EVALUATION_TARGETED_MAX_CASES", 5),
        "default_max_total_tokens": _env_int("EVALUATION_MAX_TOTAL_TOKENS", 60_000),
        "full_max_total_tokens": _env_int("EVALUATION_FULL_MAX_TOTAL_TOKENS", 500_000),
        "cache_enabled": _env_bool("EVALUATION_CACHE_ENABLED", True),
    }


def _has_path(nodes: list[dict], edges: list[dict], source_type: str, target_type: str) -> bool:
    node_types = {node.get("id"): node.get("type") for node in nodes}
    forward: dict[str, list[str]] = {}
    for edge in edges:
        if edge.get("targetHandle") in {"tools", "template"}:
            continue
        forward.setdefault(edge.get("source"), []).append(edge.get("target"))
    starts = [node_id for node_id, node_type in node_types.items() if node_type == source_type]
    for start in starts:
        seen = set()
        stack = list(forward.get(start, []))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            if node_types.get(current) == target_type:
                return True
            stack.extend(forward.get(current, []))
    return False


def _coverage(found: int, expected: int) -> float:
    return 1.0 if expected == 0 else found / expected


def score_generated_graph(test: dict, graph_data: Dict[str, Any]) -> dict:
    """Score deterministic graph properties without a judge model."""
    try:
        graph = FlowGraph(
            title=graph_data.get("title", ""), description=graph_data.get("description", ""),
            nodes=graph_data.get("nodes", []), edges=graph_data.get("edges", []),
        )
    except Exception as exc:
        return {
            "score": 0, "passed": False, "schema_passed": False,
            "structural_passed": False, "compile_passed": False, "dry_run_passed": False,
            "generated_nodes": [], "missing_nodes": test["expected_nodes"],
            "missing_paths": test.get("expected_paths", []),
            "missing_data": test.get("required_data", {}),
            "missing_handles": test.get("expected_handles", []),
            "validation_errors": [f"FlowGraph schema 오류: {exc}"], "intent_coverage": 0.0,
            "validation_issues": [],
        }

    dumped = graph.model_dump()
    nodes, edges = dumped["nodes"], dumped["edges"]
    generated_types = [node.get("type") for node in nodes]
    missing_nodes = [node_type for node_type in test["expected_nodes"] if node_type not in generated_types]
    missing_paths = [path for path in test.get("expected_paths", []) if not _has_path(nodes, edges, path[0], path[1])]

    missing_data = {}
    for node_type, fields in test.get("required_data", {}).items():
        candidates = [node.get("data") or {} for node in nodes if node.get("type") == node_type]
        absent = [field for field in fields if not any(data.get(field) not in (None, "", []) for data in candidates)]
        if absent:
            missing_data[node_type] = absent

    missing_handles = []
    nodes_by_id = {node.get("id"): node for node in nodes}
    for source_type, handle in test.get("expected_handles", []):
        found = any(
            nodes_by_id.get(edge.get("source"), {}).get("type") == source_type
            and edge.get("sourceHandle") == handle for edge in edges
        )
        if not found:
            missing_handles.append([source_type, handle])

    structural_passed, validation_errors = validate_flow(graph)
    structured_issues = [issue.model_dump() for issue in validation_issues(validation_errors)]
    compile_passed = False
    try:
        source = compile_workflow(nodes, edges)
        if source.startswith("Error"):
            raise ValueError(source)
        compile(source, "<generated-workflow>", "exec")
        compile_passed = True
    except Exception as exc:
        validation_errors = [*validation_errors, f"생성 코드 컴파일 오류: {exc}"]

    dry_run = dry_run_workflow(dumped)
    dry_run_passed = dry_run.success

    node_coverage = _coverage(len(test["expected_nodes"]) - len(missing_nodes), len(test["expected_nodes"]))
    path_coverage = _coverage(len(test.get("expected_paths", [])) - len(missing_paths), len(test.get("expected_paths", [])))
    data_expected = sum(len(fields) for fields in test.get("required_data", {}).values())
    data_missing = sum(len(fields) for fields in missing_data.values())
    data_coverage = _coverage(data_expected - data_missing, data_expected)
    handle_expected = len(test.get("expected_handles", []))
    handle_coverage = _coverage(handle_expected - len(missing_handles), handle_expected)
    intent_coverage = (node_coverage + path_coverage + data_coverage + handle_coverage) / 4
    score = round(
        10 + 30 * node_coverage + 20 * path_coverage + 10 * data_coverage + 10 * handle_coverage
        + (10 if structural_passed else 0) + (5 if compile_passed else 0) + (5 if dry_run_passed else 0)
    )
    passed = (
        not any((missing_nodes, missing_paths, missing_data, missing_handles))
        and structural_passed and compile_passed and dry_run_passed
    )
    return {
        "score": score, "passed": passed, "schema_passed": True,
        "structural_passed": structural_passed, "compile_passed": compile_passed,
        "dry_run_passed": dry_run_passed, "dry_run": dry_run.model_dump(),
        "generated_nodes": generated_types, "missing_nodes": missing_nodes,
        "missing_paths": missing_paths, "missing_data": missing_data,
        "missing_handles": missing_handles, "validation_errors": validation_errors,
        "validation_issues": structured_issues,
        "intent_coverage": round(intent_coverage, 4),
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent,
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _save_results(run_id: str, payload: dict) -> str:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{run_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _source_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in EVALUATION_SOURCE_FILES:
        digest.update(str(path.relative_to(Path(__file__).parent)).encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"missing")
    return digest.hexdigest()


def _cache_path(test: dict, settings, source_fingerprint: str) -> Path:
    payload = {
        "version": EVALUATION_VERSION,
        "source": source_fingerprint,
        "case_id": test["id"],
        "prompt": test["prompt"],
        "provider": settings.provider,
        "models": settings.models,
    }
    key = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return CACHE_DIR / f"{key}.json"


def _read_cached_result(path: Path) -> Optional[dict]:
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        result = cached.get("result")
        if not isinstance(result, dict) or not result.get("passed"):
            return None
        original_usage = result.get("token_usage") or {}
        result = dict(result)
        result["cached"] = True
        result["cached_token_usage"] = original_usage
        result["token_usage"] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        result["latency_sec"] = 0.0
        return result
    except (OSError, ValueError, TypeError):
        return None


def _write_cached_result(path: Path, result: dict) -> None:
    if not result.get("passed"):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": datetime.now(timezone.utc).isoformat(), "result": result}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_evaluation_run(selected_ids=None, profile: Optional[str] = None) -> tuple[str, list[dict], int]:
    requested_profile = (profile or os.getenv("EVALUATION_DEFAULT_PROFILE", "smoke")).strip().lower()
    if requested_profile not in {"smoke", "targeted", "full"}:
        raise ValueError("profile은 smoke, targeted, full 중 하나여야 합니다.")

    valid_by_id = {str(test["id"]): test for test in TEST_CASES}
    if requested_profile == "full":
        tests = list(TEST_CASES)
        max_tokens = _env_int("EVALUATION_FULL_MAX_TOTAL_TOKENS", 500_000)
        return requested_profile, tests, max_tokens

    if selected_ids is not None:
        requested_profile = "targeted"
        selected = []
        for case_id in selected_ids:
            normalized = str(case_id).strip()
            if normalized in valid_by_id and normalized not in selected:
                selected.append(normalized)
        max_cases = _env_int("EVALUATION_TARGETED_MAX_CASES", 5)
        if len(selected) > max_cases:
            raise ValueError(
                f"targeted 평가는 최대 {max_cases}개까지 실행할 수 있습니다. "
                "30개 전체 평가는 profile=full을 명시해야 합니다."
            )
        tests = [valid_by_id[case_id] for case_id in selected]
    else:
        tests = [valid_by_id[str(case_id)] for case_id in _smoke_case_ids()]
    return requested_profile, tests, _env_int("EVALUATION_MAX_TOTAL_TOKENS", 60_000)


def _summary(
    results: Iterable[dict],
    elapsed: float,
    token_usage: dict,
    *,
    planned_tests: Optional[int] = None,
    stopped_reason: Optional[str] = None,
) -> dict:
    rows = list(results)
    total = len(rows)
    def ratio(key: str) -> float:
        applicable = [row for row in rows if isinstance(row.get(key), bool)]
        return round(sum(1 for row in applicable if row[key]) / len(applicable) * 100, 1) if applicable else 0.0
    return {
        "total_tests": total,
        "planned_tests": planned_tests if planned_tests is not None else total,
        "pass_count": sum(1 for row in rows if row["passed"]),
        "fail_count": sum(1 for row in rows if not row["passed"]),
        "average_score": round(sum(row["score"] for row in rows) / total, 1) if total else 0.0,
        "average_latency_sec": round(elapsed / total, 2) if total else 0.0,
        "schema_pass_rate": ratio("schema_passed"),
        "structural_pass_rate": ratio("structural_passed"),
        "compile_pass_rate": ratio("compile_passed"),
        "dry_run_pass_rate": ratio("dry_run_passed"),
        "intent_coverage": round(sum(row.get("intent_coverage", 0) for row in rows) / total * 100, 1) if total else 0.0,
        "token_usage": token_usage,
        "cached_count": sum(1 for row in rows if row.get("cached")),
        "stopped_reason": stopped_reason,
    }


async def run_evaluation_suite(
    selected_ids=None,
    *,
    profile: Optional[str] = None,
    use_cache: Optional[bool] = None,
    max_total_tokens: Optional[int] = None,
) -> AsyncIterator[str]:
    try:
        active_profile, tests, configured_token_budget = _resolve_evaluation_run(selected_ids, profile)
    except ValueError as exc:
        yield _sse({"type": "error", "message": str(exc)})
        return
    if not tests:
        yield _sse({"type": "complete", "summary": None, "results": []})
        return

    token_budget = max_total_tokens or configured_token_budget
    cache_enabled = _env_bool("EVALUATION_CACHE_ENABLED", True) if use_cache is None else use_cache
    estimated_case_tokens = _env_int("EVALUATION_ESTIMATED_CASE_TOKENS", 20_000)
    settings = load_llm_settings()
    source_fingerprint = _source_fingerprint()
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    started = time.perf_counter()
    results = []
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    stopped_reason = None
    yield _sse({
        "type": "start",
        "run_id": run_id,
        "total": len(tests),
        "version": EVALUATION_VERSION,
        "profile": active_profile,
        "max_total_tokens": token_budget,
        "cache_enabled": cache_enabled,
    })

    for index, test in enumerate(tests, start=1):
        if results and total_usage["total_tokens"] + estimated_case_tokens > token_budget:
            stopped_reason = (
                f"다음 케이스 예상 사용량을 포함하면 토큰 예산({token_budget:,})을 초과합니다."
            )
            break

        cache_path = _cache_path(test, settings, source_fingerprint)
        cached_result = _read_cached_result(cache_path) if cache_enabled else None
        if cached_result is not None:
            results.append(cached_result)
            yield _sse({
                "type": "progress", "current": index, "total": len(tests), "result": cached_result,
            })
            continue

        case_started = time.perf_counter()
        try:
            max_rate_limit_retries = int(os.getenv("EVALUATION_RATE_LIMIT_RETRIES", "2"))
            for rate_attempt in range(max_rate_limit_retries + 1):
                try:
                    reply, graph_data, usage, clarification = await run_agent_turn(
                        {"title": "", "description": "", "nodes": [], "edges": []}, test["prompt"],
                        thread_id=f"eval-{run_id}-{test['id']}-{rate_attempt}", complexity_level="low",
                    )
                    usage = dict(usage or {})
                    usage.pop("_generation_trace", None)
                    break
                except Exception as exc:
                    is_rate_limit = "429" in str(exc) or "rate_limit" in str(exc).lower()
                    if not is_rate_limit or rate_attempt >= max_rate_limit_retries:
                        raise
                    await asyncio.sleep(2 ** rate_attempt)
            if test.get("expected_outcome") == "clarification" and clarification:
                scored = {
                    "score": 100, "passed": True, "schema_passed": None,
                    "structural_passed": None, "compile_passed": None, "dry_run_passed": None,
                    "intent_coverage": 1.0, "generated_nodes": [], "missing_nodes": [],
                    "missing_paths": [], "missing_data": {}, "missing_handles": [],
                    "validation_errors": [], "outcome": "clarification",
                    "validation_issues": [],
                }
            else:
                scored = score_generated_graph(test, graph_data)
                scored["outcome"] = "graph" if graph_data.get("nodes") else "no_graph"
            for key in total_usage:
                total_usage[key] += int((usage or {}).get(key, 0) or 0)
            result = {
                "id": test["id"], "category": test["category"], "prompt": test["prompt"],
                "latency_sec": round(time.perf_counter() - case_started, 2),
                "reply": reply, "clarification": clarification, "token_usage": usage or {}, **scored,
            }
        except Exception as exc:
            result = {
                "id": test["id"], "category": test["category"], "prompt": test["prompt"],
                "passed": False, "score": 0,
                "latency_sec": round(time.perf_counter() - case_started, 2),
                "schema_passed": False, "structural_passed": False, "compile_passed": False,
                "dry_run_passed": False,
                "intent_coverage": 0.0, "generated_nodes": [],
                "missing_nodes": test["expected_nodes"], "missing_paths": test.get("expected_paths", []),
                "missing_data": test.get("required_data", {}), "missing_handles": test.get("expected_handles", []),
                "validation_errors": [], "error": str(exc),
                "validation_issues": [],
            }
        results.append(result)
        if cache_enabled:
            _write_cached_result(cache_path, result)
        yield _sse({"type": "progress", "current": index, "total": len(tests), "result": result})

    summary = _summary(
        results,
        time.perf_counter() - started,
        total_usage,
        planned_tests=len(tests),
        stopped_reason=stopped_reason,
    )
    artifact = {
        "run_id": run_id, "version": EVALUATION_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(), "git_commit": _git_commit(),
        "provider": settings.provider, "models": settings.models,
        "profile": active_profile, "max_total_tokens": token_budget,
        "cache_enabled": cache_enabled, "source_fingerprint": source_fingerprint,
        "task_spec_prompt_version": TASK_SPEC_PROMPT_VERSION,
        "repair_prompt_version": FLOW_REPAIR_PROMPT_VERSION,
        "selected_case_ids": [test["id"] for test in tests],
        "executed_case_ids": [result["id"] for result in results],
        "summary": summary, "results": results,
    }
    summary["result_path"] = _save_results(run_id, artifact)
    yield _sse({"type": "complete", "run_id": run_id, "summary": summary, "results": results})
