from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    code: str
    message: str
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    repairable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


_RULES = [
    ("START_COUNT_INVALID", r"시작 노드.*정확히 1개", True),
    ("MISSING_TERMINAL", r"outputNode\(종료\)가 없다", True),
    ("DUPLICATE_NODE_ID", r"중복된 노드 id", False),
    ("DUPLICATE_EDGE_ID", r"중복된 엣지 id", False),
    ("DANGLING_EDGE", r"존재하지 않는 노드를 가리킨다", True),
    ("CONDITION_HANDLE_MISSING", r"conditionNode .*sourceHandle.*필요", True),
    ("CONDITION_HANDLE_INVALID", r"sourceHandle .*rules id/else와 일치하지", True),
    ("BRANCH_HANDLE_DUPLICATED", r"handle .*엣지가 .*개 연결", True),
    ("LOOP_HANDLE_INVALID", r"loopNode .*sourceHandle", True),
    ("MULTIPLE_LLM_INPUTS", r"promptNode\).*llmNode에서 들어오는 엣지가", True),
    ("UNSAFE_PATH_REJOIN", r"다시 합쳐진다.*merge", True),
    ("WEB_CRAWLER_INPUT_MISSING", r"webCrawlerNode\).*URL을 얻을 수 없다|webCrawlerNode\).*이전 노드도 없다", True),
    ("BREAK_OUTSIDE_LOOP", r"breakNode\).*상류에 distributorNode", True),
    ("FILE_MODIFIER_INPUT_MISSING", r"fileModifierNode\).*JSON을 얻을 수 없다|fileModifierNode\).*이전 노드가 없다", True),
    ("POSTER_INPUT_MISSING", r"posterGeneratorNode\).*HTML을 얻을 수 없다|posterGeneratorNode\).*이전 노드가 없다", True),
    ("CYCLE_DETECTED", r"순환\(cycle\)", False),
    ("OUTPUT_HAS_OUTGOING", r"outputNode .*나가는 엣지가 있다", True),
    ("UNREACHABLE_NODE", r"고아 노드라 절대 실행되지 않는다", True),
    ("LOOP_OUTPUT_EARLY", r"반복 안.*outputNode|반복 중 outputNode", True),
    ("NODE_DATA_INVALID", r"\([A-Za-z]+Node\).*(없다|허용되지|필수|유효하지|비어)", True),
]


def _extract_id(message: str, label: str) -> Optional[str]:
    if label == "edge":
        match = re.search(r"엣지\s+([A-Za-z0-9_.-]+)", message)
        return match.group(1) if match else None
    match = re.search(r"\b([A-Za-z0-9_.-]+)\([A-Za-z]+Node\)", message)
    if match:
        return match.group(1)
    match = re.search(r"(?:conditionNode|loopNode|outputNode)\s+([A-Za-z0-9_.-]+)", message)
    return match.group(1) if match else None


def issue_from_message(message: str) -> ValidationIssue:
    code = "VALIDATION_ERROR"
    repairable = False
    for candidate, pattern, can_repair in _RULES:
        if re.search(pattern, message):
            code = candidate
            repairable = can_repair
            break
    return ValidationIssue(
        code=code,
        message=message,
        node_id=_extract_id(message, "node"),
        edge_id=_extract_id(message, "edge"),
        repairable=repairable,
    )


def validation_issues(messages: list[str]) -> list[ValidationIssue]:
    return [issue_from_message(message) for message in messages]


def issue_signature(issues: list[ValidationIssue]) -> tuple[tuple[str, Optional[str], Optional[str]], ...]:
    return tuple(sorted((issue.code, issue.node_id, issue.edge_id) for issue in issues))
