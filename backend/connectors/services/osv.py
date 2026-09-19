"""connectors/services/osv.py — osvScanNode 실행부 (백로그 34 DEV-2 2차, ADR-0034).

lockfile 텍스트 → 패키지 목록 → OSV `POST /v1/querybatch`(키 불필요·무료) → 취약점 목록. `npm audit`·`pip-audit` 를 서버에서 돌리지
않고 HTTP 만으로 한다 — 실행 환경에 언어 도구를 깔 필요가 없고 2GB VM 에 맞는다.

■ 파서
  package-lock.json(v1·v2·v3) · yarn.lock(v1) · requirements.txt · Pipfile.lock · poetry.lock · go.sum · Cargo.lock. 표준 라이브러리 +
  text_tools 의 TOML 파서로 읽는다. 자동 감지는 내용 모양으로 한다(파일 이름이 없다 — 앞 노드 출력으로 들어오기 때문).
  못 읽으면 OSV_LOCKFILE_UNRECOGNIZED(validation) — 어느 형식으로 시도했는지 detail 에 남긴다.

■ 조회
  querybatch 는 요청당 1,000개 상한이라 나눠 보낸다. 결과 배열은 질의 순서와 같다(빠지면 취약점 없음으로 본다). 상세(summary·심각도·
  수정 버전)는 `GET /v1/vulns/{id}` 를 취약점마다 한 번 — 상한 50개(그 뒤는 id·URL 만). POST 지만 저장소에 쓰지 않으므로 `idempotent=True`.

■ 결과는 실패가 아니다
  취약점이 있다는 것은 점검 결과다. `failOnVulnerable` 을 켠 경우에만 생성기가 OSV_VULNERABLE 로 승격해 error 갈래로 보낸다.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE = "OSV"
BASE_URL = "https://api.osv.dev"
BATCH_SIZE = 1000                 # OSV querybatch 상한
MAX_PACKAGES_DEFAULT = 1000
MAX_PACKAGES_HARD = 5000
MAX_DETAILS = 50
MAX_LOCKFILE_CHARS = 5_000_000

FORMATS = ("auto", "package-lock", "yarn", "requirements", "pipfile-lock", "poetry-lock", "go-sum", "cargo-lock")
ECOSYSTEM_BY_FORMAT = {
    "package-lock": "npm", "yarn": "npm", "requirements": "PyPI", "pipfile-lock": "PyPI", "poetry-lock": "PyPI",
    "go-sum": "Go", "cargo-lock": "crates.io",
}
SEVERITIES = ("LOW", "MODERATE", "HIGH", "CRITICAL")
SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITIES)}

_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9][A-Za-z0-9.+!_-]*)")
_GO_SUM_LINE = re.compile(r"^(\S+)\s+v(\S+?)(?:/go\.mod)?\s+h1:")
_YARN_HEADER = re.compile(r'^"?((?:@[^/\s"]+/)?[^@\s"]+)@')
_YARN_VERSION = re.compile(r'^\s+version\s+"?([^"\s]+)"?')


def _tool_error(reason: str, message: str, **details):
    from text_tools import ToolError

    return ToolError(reason, message, field="lockfile", safe_details=details)


# ── 파서 ──────────────────────────────────────────────────────────────────

def _pkg(name: str, version: str, ecosystem: str) -> Dict[str, str]:
    return {"name": name, "version": version, "ecosystem": ecosystem}


def parse_package_lock(text: str) -> List[Dict[str, str]]:
    doc = json.loads(text)
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    packages = doc.get("packages")
    if isinstance(packages, dict):                     # v2/v3
        for path, info in packages.items():
            if not path or not isinstance(info, dict) or not info.get("version"):
                continue
            name = info.get("name") or path.rsplit("node_modules/", 1)[-1]
            if info.get("link"):
                continue
            out[(name, info["version"])] = _pkg(name, str(info["version"]), "npm")
    else:                                              # v1

        def walk(deps: Any) -> None:
            if not isinstance(deps, dict):
                return
            for name, info in deps.items():
                if isinstance(info, dict) and info.get("version"):
                    out[(name, info["version"])] = _pkg(name, str(info["version"]), "npm")
                    walk(info.get("dependencies"))

        walk(doc.get("dependencies"))
    return list(out.values())


def parse_yarn_lock(text: str) -> List[Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    current: List[str] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            current = []
            for spec in line.rstrip(":").split(","):
                m = _YARN_HEADER.match(spec.strip())
                if m:
                    current.append(m.group(1))
            continue
        m = _YARN_VERSION.match(line)
        if m and current:
            for name in current:
                out[(name, m.group(1))] = _pkg(name, m.group(1), "npm")
    return list(out.values())


def parse_requirements(text: str) -> List[Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip().rstrip("\\").strip()
        if not line or line.startswith("-"):
            continue
        m = _REQ_LINE.match(line)
        if m:
            name = m.group(1).lower().replace("_", "-")
            out[(name, m.group(2))] = _pkg(name, m.group(2), "PyPI")
    return list(out.values())


def parse_pipfile_lock(text: str) -> List[Dict[str, str]]:
    doc = json.loads(text)
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for section in ("default", "develop"):
        for name, info in (doc.get(section) or {}).items():
            version = str((info or {}).get("version") or "") if isinstance(info, dict) else ""
            version = version.lstrip("=")
            if version:
                out[(name, version)] = _pkg(name.lower(), version, "PyPI")
    return list(out.values())


def _parse_toml_packages(text: str, ecosystem: str) -> List[Dict[str, str]]:
    import text_tools

    doc, _ = text_tools.parse_structured(text, "toml")
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for entry in (doc.get("package") or []) if isinstance(doc, dict) else []:
        if isinstance(entry, dict) and entry.get("name") and entry.get("version"):
            name = str(entry["name"])
            if ecosystem == "PyPI":
                name = name.lower()
            out[(name, str(entry["version"]))] = _pkg(name, str(entry["version"]), ecosystem)
    return list(out.values())


def parse_poetry_lock(text: str) -> List[Dict[str, str]]:
    return _parse_toml_packages(text, "PyPI")


def parse_cargo_lock(text: str) -> List[Dict[str, str]]:
    return _parse_toml_packages(text, "crates.io")


def parse_go_sum(text: str) -> List[Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for line in text.splitlines():
        m = _GO_SUM_LINE.match(line.strip())
        if m:
            out[(m.group(1), m.group(2))] = _pkg(m.group(1), m.group(2), "Go")
    return list(out.values())


_PARSERS = {
    "package-lock": parse_package_lock, "yarn": parse_yarn_lock, "requirements": parse_requirements,
    "pipfile-lock": parse_pipfile_lock, "poetry-lock": parse_poetry_lock, "go-sum": parse_go_sum, "cargo-lock": parse_cargo_lock,
}


def detect_format(text: str) -> Optional[str]:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            doc = json.loads(text)
        except ValueError:
            return None
        if isinstance(doc, dict):
            if "lockfileVersion" in doc or "packages" in doc or "dependencies" in doc and "name" in doc:
                return "package-lock"
            if "_meta" in doc and ("default" in doc or "develop" in doc):
                return "pipfile-lock"
        return None
    if "# THIS IS AN AUTOGENERATED FILE" in text[:400] or ("yarn lockfile" in text[:400].lower()):
        return "yarn"
    if re.search(r"^\[\[package\]\]", text, re.M):
        if re.search(r'^source\s*=\s*"registry\+https://github\.com/rust-lang/crates\.io-index"', text, re.M) or "Cargo" in text[:200]:
            return "cargo-lock"
        return "poetry-lock"
    if any(_GO_SUM_LINE.match(line.strip()) for line in text.splitlines()[:50]):
        return "go-sum"
    if any(_REQ_LINE.match(line.split("#", 1)[0].strip()) for line in text.splitlines()):
        return "requirements"
    if _YARN_VERSION.search(text) and re.search(r"^\S.*@.*:\s*$", text, re.M):
        return "yarn"
    return None


def parse_lockfile(text: Any, fmt: str = "auto") -> Tuple[str, List[Dict[str, str]]]:
    """(형식, 패키지 목록). 못 읽으면 OSV_LOCKFILE_UNRECOGNIZED."""
    text = text.decode("utf-8", "replace") if isinstance(text, bytes) else ("" if text is None else str(text))
    if not text.strip():
        raise _tool_error("OSV_LOCKFILE_UNRECOGNIZED", "lockfile 이 비어 있습니다.", detail="empty")
    if len(text) > MAX_LOCKFILE_CHARS:
        raise _tool_error("OSV_LOCKFILE_UNRECOGNIZED", f"lockfile 이 너무 큽니다(상한 {MAX_LOCKFILE_CHARS:,}자).", detail="too large")
    fmt = str(fmt or "auto").strip().lower()
    if fmt not in FORMATS:
        raise _tool_error("OSV_LOCKFILE_UNRECOGNIZED", f"형식은 {', '.join(FORMATS)} 중 하나여야 합니다: {fmt!r}", detail=fmt)
    detected = detect_format(text) if fmt == "auto" else fmt
    if detected is None:
        raise _tool_error("OSV_LOCKFILE_UNRECOGNIZED",
                          "lockfile 형식을 알아내지 못했습니다 — package-lock.json·yarn.lock·requirements.txt·Pipfile.lock·poetry.lock·go.sum·Cargo.lock 을 지원합니다.",
                          detail="undetected")
    try:
        packages = _PARSERS[detected](text)
    except Exception as exc:  # json/toml 파싱 오류 등
        raise _tool_error("OSV_LOCKFILE_UNRECOGNIZED", f"{detected} 로 읽는 중 실패했습니다: {str(exc)[:160]}", detail=detected) from None
    if not packages:
        raise _tool_error("OSV_LOCKFILE_UNRECOGNIZED", f"{detected} 에서 버전이 고정된 패키지를 하나도 찾지 못했습니다.", detail=detected)
    return detected, packages


# ── 조회 ──────────────────────────────────────────────────────────────────

def _headers() -> Dict[str, str]:
    return {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "WorkflowAI-OSVScan/1.0"}


def query_batch(session: ConnectorSession, packages: List[Dict[str, str]]) -> List[List[Dict[str, Any]]]:
    """패키지마다 취약점 요약 목록([{id, modified}])을 같은 순서로."""
    results: List[List[Dict[str, Any]]] = []
    for start in range(0, len(packages), BATCH_SIZE):
        chunk = packages[start:start + BATCH_SIZE]
        queries = [{"package": {"name": p["name"], "ecosystem": p["ecosystem"]}, "version": p["version"]} for p in chunk]
        response = session.post(f"{BASE_URL}/v1/querybatch", headers=_headers(), json={"queries": queries}, idempotent=True)
        body = response.body if isinstance(response.body, dict) else {}
        rows_raw = body.get("results")
        rows: List[Any] = rows_raw if isinstance(rows_raw, list) else []
        for index in range(len(chunk)):
            row = rows[index] if index < len(rows) and isinstance(rows[index], dict) else {}
            results.append([v for v in (row.get("vulns") or []) if isinstance(v, dict) and v.get("id")])
    return results


def severity_of(vuln: Dict[str, Any]) -> str:
    db_specific = vuln.get("database_specific") if isinstance(vuln.get("database_specific"), dict) else {}
    label = str(db_specific.get("severity") or "").upper()
    if label in SEVERITY_RANK:
        return label
    for affected in vuln.get("affected") or []:
        eco = affected.get("ecosystem_specific") if isinstance(affected, dict) and isinstance(affected.get("ecosystem_specific"), dict) else {}
        label = str(eco.get("severity") or "").upper()
        if label in SEVERITY_RANK:
            return label
    for entry in vuln.get("severity") or []:
        score = str((entry or {}).get("score") or "")
        m = re.search(r"/A:(N|L|H)", score)
        if score.startswith("CVSS:") and m:
            # 벡터에서 기본 점수를 계산하지 않는다 — 대략치는 오해를 부른다. 라벨이 없으면 UNKNOWN.
            break
    return "UNKNOWN"


def fixed_version_for(vuln: Dict[str, Any], package: Dict[str, str]) -> str:
    for affected in vuln.get("affected") or []:
        if not isinstance(affected, dict):
            continue
        pkg = affected.get("package") or {}
        if str(pkg.get("name") or "").lower() != package["name"].lower() or str(pkg.get("ecosystem") or "") != package["ecosystem"]:
            continue
        for rng in affected.get("ranges") or []:
            for event in (rng or {}).get("events") or []:
                if isinstance(event, dict) and event.get("fixed"):
                    return str(event["fixed"])
    return ""


def fetch_detail(session: ConnectorSession, vuln_id: str) -> Dict[str, Any]:
    response = session.get(f"{BASE_URL}/v1/vulns/{vuln_id}", headers=_headers())
    return response.body if isinstance(response.body, dict) else {}


def _passes(severity: str, minimum: str) -> bool:
    if minimum == "ALL":
        return True
    if severity not in SEVERITY_RANK:
        return False
    return SEVERITY_RANK[severity] >= SEVERITY_RANK[minimum]


def scan(definition, lockfile: Any, *, fmt: str = "auto", min_severity: str = "all", include_details: bool = True,
         max_packages: int = MAX_PACKAGES_DEFAULT, session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """lockfile → 취약점 목록. 취약점이 있어도 예외가 아니다 — 결과의 `vulnerable`·`alerts` 로 드러난다."""
    detected, packages = parse_lockfile(lockfile, fmt)
    minimum = str(min_severity or "all").strip().upper()
    if minimum not in ("ALL",) + SEVERITIES:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"최소 심각도는 all/{'/'.join(SEVERITIES)} 중 하나여야 한다: {min_severity!r}")
    try:
        limit = max(1, min(int(max_packages or MAX_PACKAGES_DEFAULT), MAX_PACKAGES_HARD))
    except (TypeError, ValueError):
        limit = MAX_PACKAGES_DEFAULT
    truncated = len(packages) > limit
    queried = packages[:limit]

    session = session or definition.new_session()
    per_package = query_batch(session, queried)

    details: Dict[str, Dict[str, Any]] = {}
    details_truncated = False
    if include_details:
        ids: List[str] = []
        for vulns in per_package:
            for v in vulns:
                if v["id"] not in ids:
                    ids.append(v["id"])
        for vuln_id in ids[:MAX_DETAILS]:
            details[vuln_id] = fetch_detail(session, vuln_id)
        details_truncated = len(ids) > MAX_DETAILS

    alerts: List[Dict[str, Any]] = []
    by_severity: Dict[str, int] = {name: 0 for name in SEVERITIES}
    by_severity["UNKNOWN"] = 0
    vulnerable_packages = 0
    unknown_skipped = 0
    for package, vulns in zip(queried, per_package):
        kept = 0
        for vuln in vulns:
            detail = details.get(vuln["id"], {})
            severity = severity_of(detail) if detail else "UNKNOWN"
            if not _passes(severity, minimum):
                if severity == "UNKNOWN":
                    unknown_skipped += 1
                continue
            kept += 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
            alerts.append({
                "package": package["name"], "version": package["version"], "ecosystem": package["ecosystem"],
                "id": vuln["id"], "aliases": [a for a in (detail.get("aliases") or []) if isinstance(a, str)][:10],
                "summary": str(detail.get("summary") or "")[:300], "severity": severity,
                "fixedVersion": fixed_version_for(detail, package) if detail else "",
                "url": f"https://osv.dev/vulnerability/{vuln['id']}", "modified": str(vuln.get("modified") or detail.get("modified") or ""),
            })
        if kept:
            vulnerable_packages += 1
    alerts.sort(key=lambda a: (-SEVERITY_RANK.get(a["severity"], -1), a["package"], a["id"]))
    return {
        "format": detected,
        "ecosystem": ECOSYSTEM_BY_FORMAT.get(detected, ""),
        "packages": len(packages),
        "queried": len(queried),
        "vulnerable": vulnerable_packages,
        "alertCount": len(alerts),
        "bySeverity": by_severity,
        "minSeverity": minimum.lower() if minimum == "ALL" else minimum,
        "unknownSeveritySkipped": unknown_skipped,
        "alerts": alerts,
        "truncated": truncated,
        "detailsTruncated": details_truncated,
        "telemetry": session.telemetry(),
    }
