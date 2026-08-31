"""export_node_definitions.py — 정의 파일을 프론트엔드가 읽을 번들로 내보낸다.

저장소 루트 node_definitions/*.json 과 credential_providers.json 이 정본이고, 프론트엔드는
Vite 루트(frontend/) 바깥을 import 할 수 없으므로 여기서 만든 번들을 읽는다(ADR-0005, ADR-0007).

    python backend/export_node_definitions.py          # 번들 갱신
    python backend/export_node_definitions.py --check  # 갱신이 필요한지만 확인(CI/테스트용)

정의 파일을 고친 뒤 이 스크립트를 다시 돌리지 않으면 backend/test_node_definitions.py 의
드리프트 테스트가 실패한다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import node_bindings
import node_definition
import workflow_patterns
from documents import format_presets
from connectors import providers as connector_providers
from node_errors import catalog as error_catalog

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GENERATED_DIR = REPO_ROOT / "frontend" / "src" / "generated"
BUNDLE_PATH = GENERATED_DIR / "nodeDefinitions.json"
PROVIDERS_BUNDLE_PATH = GENERATED_DIR / "credentialProviders.json"
# NodeError v1 catalog(ADR-0016) — 정본은 error_catalog.json, 클라이언트 번들과 문서는 여기서 생성한다.
ERROR_CATALOG_BUNDLE_PATH = GENERATED_DIR / "errorCatalog.json"
ERROR_CATALOG_DOC_PATH = REPO_ROOT / "Documents" / "ERROR_CATALOG.md"
# 디자인 패턴(문서 + LLM 생성 공용) — 정본은 workflow_patterns.json
PATTERNS_BUNDLE_PATH = GENERATED_DIR / "workflowPatterns.json"
# 문서 포맷 프리셋(포맷 스튜디오 계획 §4.2) — 정본은 document_formats/*.json
FORMATS_BUNDLE_PATH = GENERATED_DIR / "documentFormats.json"
# 바인딩 가능 필드(데이터 흐름 분리 계획 §4) — 정본은 backend/node_bindings.BINDABLE_FIELDS.
# 에디터의 필드 픽커가 "이 필드에 ⚡ 를 붙일 수 있는지"를 이 번들로 판단한다.
BINDABLE_BUNDLE_PATH = GENERATED_DIR / "bindableFields.json"


def render_bundle() -> str:
    payload = node_definition.definitions_payload()
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_providers_bundle() -> str:
    payload = connector_providers.registry_payload()
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_error_catalog_bundle() -> str:
    return json.dumps(error_catalog.payload(), ensure_ascii=False, indent=2) + "\n"


def render_error_catalog_doc() -> str:
    return error_catalog.render_markdown()


def render_patterns_bundle() -> str:
    return json.dumps(workflow_patterns.payload(), ensure_ascii=False, indent=2) + "\n"


def render_formats_bundle() -> str:
    return json.dumps(format_presets.payload(), ensure_ascii=False, indent=2) + "\n"


def render_bindable_bundle() -> str:
    payload = {"version": 1,
               "fields": {k: list(v) for k, v in sorted(node_bindings.BINDABLE_FIELDS.items())}}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _bundles() -> list[tuple[pathlib.Path, str]]:
    return [
        (BUNDLE_PATH, render_bundle()),
        (PROVIDERS_BUNDLE_PATH, render_providers_bundle()),
        (ERROR_CATALOG_BUNDLE_PATH, render_error_catalog_bundle()),
        (ERROR_CATALOG_DOC_PATH, render_error_catalog_doc()),
        (PATTERNS_BUNDLE_PATH, render_patterns_bundle()),
        (FORMATS_BUNDLE_PATH, render_formats_bundle()),
        (BINDABLE_BUNDLE_PATH, render_bindable_bundle()),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="쓰지 않고 최신 상태인지만 확인한다")
    args = parser.parse_args()

    if args.check:
        stale = [
            path for path, expected in _bundles()
            if not path.exists() or path.read_text(encoding="utf-8") != expected
        ]
        if not stale:
            print(f"최신 상태: {', '.join(p.name for p, _ in _bundles())}")
            return 0
        for path in stale:
            print(f"번들이 정본과 다르다 — `python backend/export_node_definitions.py` 를 실행하라: {path}")
        return 1

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for path, expected in _bundles():
        path.write_text(expected, encoding="utf-8")
    print(
        f"{len(node_definition.NODE_DEFINITIONS)}개 노드 정의와 "
        f"{len(connector_providers.PROVIDERS)}개 provider, "
        f"{len(error_catalog.all_codes())}개 오류 code, "
        f"{len(workflow_patterns.PATTERNS)}개 디자인 패턴, "
        f"{len(format_presets.PRESETS)}개 문서 포맷 프리셋, "
        f"{sum(len(v) for v in node_bindings.BINDABLE_FIELDS.values())}개 바인딩 필드를 "
        f"내보냈다: {GENERATED_DIR}, {ERROR_CATALOG_DOC_PATH}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
