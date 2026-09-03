"""community_templates.py — 검증된 공유의 승격 (ADR-0023, 우선 백로그 12).

§4.12 의 글 공유가 "이렇게 만들었어요" 라면, 템플릿은 **"검증된 v1.2"** 다. 그 라벨이 거짓이 되지
않게 하는 것이 이 파일의 일이다.

게시 게이트(TEMPLATE-1) — 전부 통과해야 게시된다.

  1. 정화 통과            §4.12 `community_sanitize` 를 그대로 쓴다(두 벌 만들지 않는다)
  2. `dry_run` 구조 검사   깨진 워크플로우를 "검증됨" 으로 내보내지 않는다
  3. **본인 실행 성공 이력**  자기도 안 돌려본 워크플로우는 템플릿이 될 수 없다.
                          실행 로그 조회 하나라 **심사 인력 없이 걸러지는 가장 값싼 품질 게이트**다
  4. `pythonNode`         §4.15 의 실행 격리가 켜져 있을 때만 허용한다(영구 금지가 아니라 조건부)
  5. 고위험 노드          자동 게시하지 않고 검수 큐로 보낸다

**게이트 3번의 유일한 예외 — 공식 템플릿**(`publish_curated`, 2026-08-30).

운영자가 직접 만들어 올리는 템플릿은 실행 이력 요건을 면제한다. 이유는 하나다 — 100개 규모의
공식 템플릿은 Airtable·Outlook 같은 남의 서비스 자격증명이 있어야 실행되는데, 그걸 다 갖추는
것은 현실적이지 않다. 대신 **사람의 검수로 대체**하고, 그 사실을 `templates.is_curated` 와
버전의 `publish_gate.curated` 에 남긴다. 나머지 네 게이트(정화·구조·코드 노드·고위험)는
그대로 적용한다 — 면제하는 것은 "만든 사람이 돌려봤는가" 하나뿐이다.

숨은 예외로 두지 않는 이유: 나중에 "이 템플릿은 왜 실행 이력이 없지" 를 물었을 때 답이 행에
있어야 한다. 그리고 공식 여부는 사용자에게도 보여야 한다.

불변성 — 게시된 버전은 `status` 외 어떤 컬럼도 갱신하지 않는다. 고치려면 새 버전을 낸다.
잘못 낸 버전은 `yanked` 로 새 설치만 막고, 이미 설치한 사람의 것은 건드리지 않는다.

품질 신호 — 설치 수·별점이 아니라 **첫 실행 성공률**과 **7일 유지율**이다(§4.2 판단 유지).
우리는 실행 로그를 갖고 있어 이 신호를 실제로 계산할 수 있고, 조작하기도 어렵다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional

CATEGORIES = ("automation", "content", "data", "notification", "document", "etc")

# 소개 글은 읽고 판단하라고 쓰는 것이라 한 줄 요약(1000자)보다 넉넉해야 한다.
MAX_INTRO = 20000
MAX_INTRO_IMAGES = 10
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38})[a-z0-9]$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
RESERVED_SLUGS = {
    "official", "workflow", "workflow-ai", "admin", "system", "template", "templates",
    "new", "featured", "verified", "staff", "api", "app",
}
# dry_run 이 이미 분류하는 고위험 노드 — 자동 게시하지 않고 사람이 본다.
REVIEW_RISK_FLAGS = {"database", "payment", "arbitrary_url"}


class TemplateError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 규칙 위반."""


def normalize_slug(raw: str) -> str:
    slug = str(raw or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise TemplateError("주소는 소문자·숫자·하이픈 3~40자여야 하고, 하이픈으로 시작하거나 끝날 수 없습니다.")
    if "--" in slug:
        raise TemplateError("하이픈을 연달아 쓸 수 없습니다.")
    if slug in RESERVED_SLUGS:
        raise TemplateError("이미 예약된 주소입니다. 다른 주소를 골라주세요.")
    return slug


# ── 게시 게이트 ─────────────────────────────────────────────────────────
def has_successful_run(db, project_id: int, owner_user_id: int) -> Optional[datetime.datetime]:
    """**자기도 안 돌려본 워크플로우는 템플릿이 될 수 없다.**

    실행 로그 조회 하나로 끝나므로 심사 인력이 필요 없다. "가져왔는데 안 된다"가 첫 경험이 되는
    것을 막는 가장 값싼 방법이다.
    """
    import models
    from usage_tracking import OUTCOME_SUCCESS

    row = db.query(models.FlowExecutionLog).filter(
        models.FlowExecutionLog.project_id == project_id,
        models.FlowExecutionLog.outcome == OUTCOME_SUCCESS,
    ).order_by(models.FlowExecutionLog.id.desc()).first()
    return row.execution_time if row else None


def evaluate_gate(db, project, owner_user) -> Dict[str, Any]:
    """게시 가능 여부와 **그 이유**를 함께 돌려준다. 왜 안 되는지가 즉시 보여야 한다."""
    import community_sanitize
    import node_definition
    import python_runtime

    checks: List[Dict[str, Any]] = []

    # 1·5. 정화와 위험 노드
    snapshot = report = None
    try:
        snapshot, report = community_sanitize.sanitize_graph(project.graph_data or {})
        checks.append({"id": "sanitize", "ok": True, "label": "비밀 값 정화"})
    except community_sanitize.SanitizeRefused as exc:
        checks.append({"id": "sanitize", "ok": False, "label": "비밀 값 정화",
                       "detail": str(exc)})

    # 4. pythonNode — 영구 금지가 아니라 §4.15 격리에 연동된 조건부 게이트다.
    node_types = report.node_types if report else []
    isolation = python_runtime.isolation_enabled()
    if "pythonNode" in node_types and not isolation:
        checks.append({"id": "python", "ok": False, "label": "코드 노드",
                       "detail": "코드 노드는 실행 격리가 배포되면 게시할 수 있습니다."})
    else:
        checks.append({"id": "python", "ok": True, "label": "코드 노드"})

    # 2. 구조 검사
    if snapshot is not None:
        from dry_run import dry_run_workflow

        checked = dry_run_workflow(snapshot)
        ok = checked.structural_passed and checked.compile_passed
        checks.append({"id": "dry_run", "ok": ok, "label": "구조 검사",
                       **({} if ok else {"detail": "; ".join(checked.issues[:2])})})
    else:
        checks.append({"id": "dry_run", "ok": False, "label": "구조 검사",
                       "detail": "정화를 통과하지 못해 검사할 수 없습니다."})

    # 3. 실행 성공 이력
    ran_at = has_successful_run(db, project.id, owner_user.id)
    checks.append({"id": "executed", "ok": ran_at is not None, "label": "본인 계정 실행 성공",
                   **({} if ran_at else {"detail": "게시하기 전에 이 워크플로우를 한 번 성공적으로 실행해주세요."})})

    risk_flags = report.risk_flags if report else []
    needs_review = bool(set(risk_flags) & REVIEW_RISK_FLAGS)
    return {
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "needsReview": needs_review,
        "nodeTypes": node_types,
        "requiredCredentials": report.required_credentials if report else [],
        "riskFlags": risk_flags,
        "compatibility": _compatibility(node_types) if report else {},
        "executedAt": ran_at.isoformat() if ran_at else None,
    }


def _compatibility(node_types: List[str]) -> Dict[str, Any]:
    """게시 시점의 노드 정의 버전을 기록한다.

    ⚠️ 이 값이 의미를 가지려면 **`version` 을 올리는 규칙**이 있어야 한다 — "기존 그래프가 그대로
    동작하지 않는 변경일 때만" 올린다. 규칙 없이 올리면 멀쩡한 템플릿이 차단되고, 안 올리면
    깨진 템플릿이 통과한다.
    """
    import node_definition

    versions = {}
    for node_type in node_types:
        definition = node_definition.get_definition(node_type)
        if definition is not None:
            versions[node_type] = definition.version
    return {"graphSchemaVersion": 1, "nodeTypeVersions": versions}


# ── 게시 ────────────────────────────────────────────────────────────────
def publish(db, owner_user, *, project, slug: str, title: str, description: str = "",
            category: str = "etc", tags=None, version: str = "1.0.0", changelog: str = ""):
    """검증된 공유를 정식 템플릿으로 승격한다."""
    import community_posts
    import community_sanitize
    import models

    if category not in CATEGORIES:
        raise TemplateError(f"허용되지 않는 분류입니다: {category}")
    if not SEMVER_RE.match(str(version)):
        raise TemplateError("버전은 1.0.0 형식이어야 합니다.")
    if project is None or project.user_id != owner_user.id:
        raise TemplateError("본인의 워크플로우만 템플릿으로 올릴 수 있습니다.")

    gate = evaluate_gate(db, project, owner_user)
    if not gate["ok"]:
        failed = [c["label"] for c in gate["checks"] if not c["ok"]]
        raise TemplateError("게시 조건을 통과하지 못했습니다: " + ", ".join(failed))

    normalized = normalize_slug(slug)
    if db.query(models.Template).filter(models.Template.slug == normalized).first():
        raise TemplateError("이미 사용 중인 주소입니다.")

    snapshot, report = community_sanitize.sanitize_graph(project.graph_data or {})
    share = models.WorkflowShare(
        owner_type="template", owner_id=0, source_project_id=project.id,
        source_revision=getattr(project, "current_revision", None),
        graph_snapshot=snapshot, schema_version=1,
        node_types=report.node_types, required_credentials=report.required_credentials,
        risk_flags=report.risk_flags, created_at=datetime.datetime.utcnow(),
    )
    db.add(share)
    db.flush()

    template = models.Template(
        owner_id=owner_user.id, slug=normalized,
        title=community_posts.sanitize_markdown(title, limit=120),
        description=community_posts.sanitize_markdown(description, limit=1000),
        category=category, tags=community_posts.normalize_tags(tags),
        # 고위험 노드가 있으면 자동 게시하지 않고 사람이 본다.
        status="in_review" if gate["needsReview"] else "published",
        created_at=datetime.datetime.utcnow(),
    )
    if template.status == "published":
        template.published_at = datetime.datetime.utcnow()
    db.add(template)
    db.flush()
    share.owner_id = template.id

    row = models.TemplateVersion(
        template_id=template.id, version=version, workflow_share_id=share.id,
        changelog=community_posts.sanitize_markdown(changelog, limit=2000),
        compatibility=gate["compatibility"],
        publish_gate={"executionVerifiedAt": gate["executedAt"],
                      "dryRunPassedAt": datetime.datetime.utcnow().isoformat(),
                      "reviewedBy": None},
        status="published", published_at=datetime.datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    template.latest_version_id = row.id
    db.commit()
    return template, row


def publish_curated(db, owner_user, *, graph: Dict[str, Any], slug: str, title: str,
                    description: str = "", category: str = "etc", tags=None,
                    version: str = "1.0.0", changelog: str = "", source: str = "",
                    reviewer: str = ""):
    """운영자가 직접 만든 공식 템플릿을 올린다. **프로젝트가 필요 없다.**

    일반 `publish` 와 다른 점은 딱 하나 — "본인 계정 실행 성공" 요건을 면제한다(모듈 문서 참조).
    정화·구조 검사·코드 노드·고위험 분류는 그대로 적용하므로, 깨진 그래프는 여전히 못 올라간다.

    `source` 는 이 템플릿의 로직 출처(예: n8n 커뮤니티 템플릿 이름)를, `reviewer` 는 검수한
    사람을 남긴다. 실행 이력 대신 무엇으로 품질을 보장했는지가 기록에 있어야 한다.
    """
    import community_posts
    import community_sanitize
    import models
    import python_runtime
    from dry_run import dry_run_workflow

    if category not in CATEGORIES:
        raise TemplateError(f"허용되지 않는 분류입니다: {category}")
    if not SEMVER_RE.match(str(version)):
        raise TemplateError("버전은 1.0.0 형식이어야 합니다.")

    normalized = normalize_slug(slug)
    if db.query(models.Template).filter(models.Template.slug == normalized).first():
        raise TemplateError("이미 사용 중인 주소입니다.")

    # 1) 정화 — 일반 게시와 같은 함수를 쓴다(두 벌 만들지 않는다).
    snapshot, report = community_sanitize.sanitize_graph(graph or {})

    # 2) 구조 검사 — 깨진 것을 "공식" 으로 내보내지 않는다.
    checked = dry_run_workflow(snapshot)
    if not (checked.structural_passed and checked.compile_passed):
        raise TemplateError("구조 검사를 통과하지 못했습니다: " + "; ".join(checked.issues[:3]))

    # 3) 코드 노드 — 격리가 켜져 있을 때만.
    if "pythonNode" in report.node_types and not python_runtime.isolation_enabled():
        raise TemplateError("코드 노드는 실행 격리가 배포되면 게시할 수 있습니다.")

    needs_review = bool(set(report.risk_flags) & REVIEW_RISK_FLAGS)

    share = models.WorkflowShare(
        owner_type="template", owner_id=0, source_project_id=None, source_revision=None,
        graph_snapshot=snapshot, schema_version=1,
        node_types=report.node_types, required_credentials=report.required_credentials,
        risk_flags=report.risk_flags, created_at=datetime.datetime.utcnow(),
    )
    db.add(share)
    db.flush()

    template = models.Template(
        owner_id=owner_user.id if owner_user else None, slug=normalized,
        title=community_posts.sanitize_markdown(title, limit=120),
        description=community_posts.sanitize_markdown(description, limit=1000),
        category=category, tags=community_posts.normalize_tags(tags),
        status="in_review" if needs_review else "published",
        is_curated=True,
        created_at=datetime.datetime.utcnow(),
    )
    if template.status == "published":
        template.published_at = datetime.datetime.utcnow()
    db.add(template)
    db.flush()
    share.owner_id = template.id

    row = models.TemplateVersion(
        template_id=template.id, version=version, workflow_share_id=share.id,
        changelog=community_posts.sanitize_markdown(changelog, limit=2000),
        compatibility=_compatibility(report.node_types),
        # 실행 이력이 **없다는 사실과 그 대신 무엇을 했는지**를 함께 남긴다.
        publish_gate={
            "executionVerifiedAt": None,
            "dryRunPassedAt": datetime.datetime.utcnow().isoformat(),
            "curated": True,
            "curatedReason": "운영자 제작 공식 템플릿 — 실행 이력 대신 사람이 검수했다",
            "source": community_posts.sanitize_markdown(source, limit=200) if source else None,
            "reviewedBy": community_posts.sanitize_markdown(reviewer, limit=80) if reviewer else None,
        },
        status="published", published_at=datetime.datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    template.latest_version_id = row.id
    db.commit()
    return template, row


def can_edit(db, user, template) -> bool:
    """소개·분류 같은 **겉면**을 고칠 수 있는 사람.

    공식 템플릿은 계정 하나가 소유하지만 실제 주인은 운영이다 — 만든 사람이 자리를 비워도
    오탈자를 고칠 수 있어야 한다. 그래서 운영자에게 권한을 준다. 일반 템플릿은 올린 사람만.
    """
    import community_safety

    if not user:
        return False
    # `is_staff` 만 보면 안 된다 — DB role 이 아직 user 인 부트스트랩 어드민이 걸러진다.
    if community_safety.has_staff_access(user):
        return True
    return template.owner_id == user.id


def edit_template(db, actor, template, *, title=None, description=None, category=None,
                  tags=None, intro_body=None, intro_image_ids=None, thumbnail_artifact_id=None):
    """겉면만 고친다. **그래프는 여기서 바뀌지 않는다.**

    버전 스냅샷을 고치지 않는 것이 핵심이다 — 누군가 v1.0 을 가져갔는데 v1.0 의 내용이
    나중에 바뀌면 "v1.0 을 가져갔다"는 기록이 거짓말이 된다(Template 문서 참조). 로직을
    바꾸려면 `revise_curated` 로 **새 버전**을 낸다.
    """
    import community_posts

    if not can_edit(db, actor, template):
        raise TemplateError("이 템플릿을 수정할 권한이 없습니다.")

    if title is not None:
        clean = community_posts.sanitize_markdown(title, limit=120)
        if not clean:
            raise TemplateError("제목을 입력해주세요.")
        template.title = clean
    if description is not None:
        template.description = community_posts.sanitize_markdown(description, limit=1000)
    if category is not None:
        if category not in CATEGORIES:
            raise TemplateError(f"허용되지 않는 분류입니다: {category}")
        template.category = category
    if tags is not None:
        template.tags = community_posts.normalize_tags(tags)
    if intro_body is not None:
        template.intro_body = community_posts.sanitize_markdown(intro_body, limit=MAX_INTRO)
    if intro_image_ids is not None:
        ids = [str(a) for a in intro_image_ids if a][:MAX_INTRO_IMAGES]
        # 소개에서 뺀 그림은 고정을 풀어 준다 — 안 풀면 안 쓰는 파일이 영원히 쌓인다.
        removed = set(str(a) for a in (template.intro_image_ids or [])) - set(ids)
        community_posts.pin_images(db, ids)
        community_posts.unpin_images(db, sorted(removed))
        template.intro_image_ids = ids
    if thumbnail_artifact_id is not None:
        # 빈 문자열은 "섬네일 없음". 그 외에는 **소개에 실제로 있는 그림**이어야 한다 —
        # 아무 artifact id 나 받으면 남의 파일을 목록에 걸 수 있다.
        wanted = str(thumbnail_artifact_id).strip()
        if wanted and wanted not in [str(a) for a in (template.intro_image_ids or [])]:
            raise TemplateError("섬네일은 소개에 넣은 이미지 중에서 고를 수 있습니다.")
        template.thumbnail_artifact_id = wanted or None

    template.updated_at = datetime.datetime.utcnow()
    db.commit()
    return template


def revise_curated(db, actor, template, *, graph: Dict[str, Any], version: str,
                   changelog: str = "", reviewer: str = ""):
    """공식 템플릿의 **로직**을 고쳐 새 버전을 낸다. 기존 버전은 그대로 둔다.

    `publish_curated` 와 같은 검사를 그대로 받는다 — 고치다 깨진 것을 "공식" 으로 내보내지
    않는다. 프로젝트가 필요 없다는 점도 같다(운영자가 그래프를 직접 들고 온다).
    """
    import community_posts
    import community_sanitize
    import models
    import python_runtime
    from dry_run import dry_run_workflow

    if not can_edit(db, actor, template):
        raise TemplateError("이 템플릿을 수정할 권한이 없습니다.")
    if not template.is_curated:
        raise TemplateError("공식 템플릿만 이 경로로 고칠 수 있습니다. 일반 템플릿은 새 버전을 올려주세요.")
    if not SEMVER_RE.match(str(version)):
        raise TemplateError("버전은 1.0.0 형식이어야 합니다.")
    if db.query(models.TemplateVersion).filter(
            models.TemplateVersion.template_id == template.id,
            models.TemplateVersion.version == str(version)).first():
        raise TemplateError(f"이미 있는 버전입니다: {version}")

    snapshot, report = community_sanitize.sanitize_graph(graph or {})
    checked = dry_run_workflow(snapshot)
    if not (checked.structural_passed and checked.compile_passed):
        raise TemplateError("구조 검사를 통과하지 못했습니다: " + "; ".join(checked.issues[:3]))
    if "pythonNode" in report.node_types and not python_runtime.isolation_enabled():
        raise TemplateError("코드 노드는 실행 격리가 배포되면 게시할 수 있습니다.")

    share = models.WorkflowShare(
        owner_type="template", owner_id=template.id, source_project_id=None, source_revision=None,
        graph_snapshot=snapshot, schema_version=1,
        node_types=report.node_types, required_credentials=report.required_credentials,
        risk_flags=report.risk_flags, created_at=datetime.datetime.utcnow(),
    )
    db.add(share)
    db.flush()

    row = models.TemplateVersion(
        template_id=template.id, version=str(version), workflow_share_id=share.id,
        changelog=community_posts.sanitize_markdown(changelog, limit=2000),
        compatibility=_compatibility(report.node_types),
        publish_gate={
            "executionVerifiedAt": None,
            "dryRunPassedAt": datetime.datetime.utcnow().isoformat(),
            "curated": True,
            "curatedReason": "운영자 수정 — 실행 이력 대신 사람이 검수했다",
            "reviewedBy": community_posts.sanitize_markdown(reviewer, limit=80) if reviewer else None,
        },
        status="published", published_at=datetime.datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    template.latest_version_id = row.id
    template.updated_at = datetime.datetime.utcnow()
    db.commit()
    return template, row


def publish_version(db, owner_user, template, *, project, version: str, changelog: str = ""):
    """새 버전. **기존 버전은 건드리지 않는다** — 설치한 사람의 기록이 거짓이 되면 안 된다."""
    import models

    if template.owner_id != owner_user.id:
        raise TemplateError("본인의 템플릿만 새 버전을 올릴 수 있습니다.")
    if not SEMVER_RE.match(str(version)):
        raise TemplateError("버전은 1.0.0 형식이어야 합니다.")
    if db.query(models.TemplateVersion).filter(
            models.TemplateVersion.template_id == template.id,
            models.TemplateVersion.version == version).first():
        raise TemplateError("이미 있는 버전입니다.")

    gate = evaluate_gate(db, project, owner_user)
    if not gate["ok"]:
        failed = [c["label"] for c in gate["checks"] if not c["ok"]]
        raise TemplateError("게시 조건을 통과하지 못했습니다: " + ", ".join(failed))

    import community_posts
    import community_sanitize

    snapshot, report = community_sanitize.sanitize_graph(project.graph_data or {})
    share = models.WorkflowShare(
        owner_type="template", owner_id=template.id, source_project_id=project.id,
        source_revision=getattr(project, "current_revision", None),
        graph_snapshot=snapshot, schema_version=1, node_types=report.node_types,
        required_credentials=report.required_credentials, risk_flags=report.risk_flags,
        created_at=datetime.datetime.utcnow(),
    )
    db.add(share)
    db.flush()

    row = models.TemplateVersion(
        template_id=template.id, version=version, workflow_share_id=share.id,
        changelog=community_posts.sanitize_markdown(changelog, limit=2000),
        compatibility=gate["compatibility"],
        publish_gate={"executionVerifiedAt": gate["executedAt"],
                      "dryRunPassedAt": datetime.datetime.utcnow().isoformat()},
        status="published", published_at=datetime.datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    template.latest_version_id = row.id
    db.commit()

    # 설치자에게 알린다. **사본을 자동으로 고치지는 않는다** — 사용자가 이미 손댔을 수 있다.
    notify_installers(db, template, row)
    return row


def notify_installers(db, template, version) -> int:
    import models
    import notifications

    installer_ids = {
        row.installed_by for row in db.query(models.TemplateInstall)
        .join(models.TemplateVersion,
              models.TemplateInstall.template_version_id == models.TemplateVersion.id)
        .filter(models.TemplateVersion.template_id == template.id).all()
        if row.installed_by
    }
    for user_id in installer_ids:
        notifications.notify(
            db, user_id=user_id, kind="template_update", target_type="template",
            target_id=str(template.id), quiet=True, commit=False,
            body=f"'{template.title}' 템플릿에 새 버전 {version.version} 이 나왔습니다."
                 f"{' · ' + version.changelog[:60] if version.changelog else ''}",
        )
    db.commit()
    return len(installer_ids)


def yank_version(db, owner_user, version, *, reason: str = ""):
    """새 설치만 막는다. **이미 설치한 사람의 것은 건드리지 않는다** — 회수는 불가능하다."""
    import models

    template = db.query(models.Template).filter(models.Template.id == version.template_id).first()
    if template is None or template.owner_id != owner_user.id:
        raise TemplateError("본인의 템플릿만 내릴 수 있습니다.")
    version.status = "yanked"
    db.commit()
    return version


# ── 설치 ────────────────────────────────────────────────────────────────
def check_compatibility(db, version) -> Dict[str, Any]:
    """설치 시점에 지금 환경과 대조한다. 노드가 사라졌거나 버전이 올랐으면 조용히 깨지지 않게 막는다."""
    import node_definition

    recorded = (version.compatibility or {}).get("nodeTypeVersions") or {}
    missing, changed = [], []
    for node_type, recorded_version in recorded.items():
        definition = node_definition.get_definition(node_type)
        if definition is None:
            missing.append(node_type)
        elif definition.version != recorded_version:
            changed.append({"nodeType": node_type, "publishedWith": recorded_version,
                            "now": definition.version})
    return {"compatible": not missing and not changed, "missingNodeTypes": missing,
            "changedNodeTypes": changed}


def install(db, user, template, version):
    import community_shares
    import models

    if template.status in ("suspended", "draft", "in_review"):
        raise TemplateError("지금은 설치할 수 없는 템플릿입니다.")
    if version.status != "published":
        raise TemplateError("내려간 버전입니다. 최신 버전을 설치해주세요.")

    compatibility = check_compatibility(db, version)
    if not compatibility["compatible"]:
        raise TemplateError(
            "이 템플릿은 현재 노드 버전과 맞지 않습니다. 작성자가 새 버전을 올려야 합니다. "
            f"(문제 노드: {', '.join(compatibility['missingNodeTypes'] + [c['nodeType'] for c in compatibility['changedNodeTypes']])})"
        )

    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == version.workflow_share_id).first()
    project = community_shares.import_share(db, user, share)
    project.title = f"[{template.title}] {version.version}"
    project.description = (f"커뮤니티 템플릿 '{template.slug}' v{version.version} 에서 가져왔습니다.")

    db.add(models.TemplateInstall(
        template_version_id=version.id, installed_project_id=project.id,
        installed_by=user.id, installed_at=datetime.datetime.utcnow(),
    ))
    template.install_count = (template.install_count or 0) + 1
    db.commit()
    return project


def record_first_run(db, project_id: int, outcome: str) -> None:
    """가져간 뒤 실제로 돌았는지 — 별점보다 정직한 품질 신호다. 첫 실행 결과만 기록한다."""
    import models

    row = db.query(models.TemplateInstall).filter(
        models.TemplateInstall.installed_project_id == project_id,
        models.TemplateInstall.first_run_outcome.is_(None),
    ).first()
    if row is None:
        return
    row.first_run_outcome = "success" if outcome == "success" else "error"
    db.commit()


# ── 품질 신호와 카탈로그 ────────────────────────────────────────────────
def quality_signals(db, template) -> Dict[str, Any]:
    import models

    installs = db.query(models.TemplateInstall).join(
        models.TemplateVersion,
        models.TemplateInstall.template_version_id == models.TemplateVersion.id,
    ).filter(models.TemplateVersion.template_id == template.id).all()
    ran = [i for i in installs if i.first_run_outcome]
    succeeded = [i for i in ran if i.first_run_outcome == "success"]
    retained = [i for i in installs if i.retained_at_7d]
    return {
        "installs": len(installs),
        # 설치 수는 **보조 표시**다 — 정렬의 1차 기준이 아니다.
        "firstRunSuccessRate": round(len(succeeded) / len(ran), 3) if ran else None,
        "measuredRuns": len(ran),
        "retention7d": round(len(retained) / len(installs), 3) if installs else None,
    }


def graph_metadata(share) -> Dict[str, Any]:
    """목록·소개에서 "무슨 일을 얼마나 하는 워크플로우인가" 를 가늠하게 하는 값들.

    스냅샷에서 그때그때 센다 — 컬럼으로 두면 버전을 새로 낼 때 갱신을 잊는 날이 온다.
    """
    # 시작 노드 목록은 dry_run 이 정본이다. node_definition.trigger_types() 만 쓰면 아직
    # 정의로 옮기지 않은 startNode·webhookNode 를 놓쳐 대부분의 템플릿이 "시작 없음" 이 된다.
    import dry_run

    if share is None:
        return {"nodeCount": 0, "edgeCount": 0, "triggerType": None, "usesAi": False}
    graph = share.graph_snapshot or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    types = [n.get("type") for n in nodes]
    triggers = set(dry_run.TRIGGER_NODE_TYPES)
    incoming = {e.get("target") for e in edges}
    # 들어오는 연결이 없는 노드가 실제 시작점이다 — 종류만 보면 중간에 낀 것도 잡힌다.
    starts = [n.get("type") for n in nodes
              if n.get("id") not in incoming and n.get("type") in triggers]
    if not starts:
        starts = [t for t in types if t in triggers]
    return {
        # 캔버스 메모는 실행 노드가 아니다 — 세면 "9개 노드" 라고 적어 놓고 실제로는 6개가 돈다.
        "nodeCount": sum(1 for n in nodes if n.get("type") != "memoNode"),
        "memoCount": sum(1 for n in nodes if n.get("type") == "memoNode"),
        "edgeCount": len(edges),
        # 시작 방식은 "이걸 쓰려면 무엇이 필요한가" 를 가장 빨리 알려주는 한 가지다.
        "triggerType": starts[0] if starts else None,
        "usesAi": any(t in ("llmNode", "imageGenerationNode") for t in types),
    }


def graph_outline(share, *, max_nodes: int = 60) -> Dict[str, Any]:
    """소개 페이지에 그릴 **구조만** 뽑는다 — 종류·자리·연결. 값은 담지 않는다.

    가져오기 전에 "몇 단계짜리이고 어디서 갈라지는가" 를 보려는 것이라, 노드 안의 설정값은
    필요 없다. 값을 실으면 정화를 통과한 스냅샷이라도 공개 표면이 그만큼 넓어진다.
    """
    if share is None:
        return {"nodes": [], "edges": [], "truncated": False}
    graph = share.graph_snapshot or {}
    # 메모는 실행 구조가 아니다. 미리보기에 넣으면 흐름이 안 보인다.
    nodes = [n for n in (graph.get("nodes") or []) if n.get("type") != "memoNode"]
    truncated = len(nodes) > max_nodes
    nodes = nodes[:max_nodes]
    keep = {str(n.get("id")) for n in nodes}
    return {
        "nodes": [{
            "id": str(n.get("id")),
            "type": n.get("type"),
            "x": float((n.get("position") or {}).get("x", 0) or 0),
            "y": float((n.get("position") or {}).get("y", 0) or 0),
        } for n in nodes],
        "edges": [{
            "source": str(e.get("source")), "target": str(e.get("target")),
            "handle": e.get("sourceHandle") or "",
        } for e in (graph.get("edges") or [])
            if str(e.get("source")) in keep and str(e.get("target")) in keep],
        "truncated": truncated,
    }


def public_template(db, template, *, version=None, include_signals: bool = True) -> Dict[str, Any]:
    import community_identity
    import models

    latest = version or (db.query(models.TemplateVersion).filter(
        models.TemplateVersion.id == template.latest_version_id).first()
        if template.latest_version_id else None)
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == latest.workflow_share_id).first() if latest else None
    thumbnail = getattr(template, "thumbnail_artifact_id", None)
    payload = {
        "id": template.id, "slug": template.slug, "title": template.title,
        "description": template.description or "", "category": template.category,
        "tags": list(template.tags or []), "status": template.status,
        # 공식 템플릿은 실행 이력 대신 사람의 검수를 거쳤다 — 사용자가 그 차이를 알 수 있어야 한다.
        "isCurated": bool(getattr(template, "is_curated", False)),
        "author": community_identity.public_profile(
            community_identity.get_profile(db, template.owner_id)) if template.owner_id else None,
        "publishedAt": template.published_at.isoformat() if template.published_at else None,
        "updatedAt": template.updated_at.isoformat() if getattr(template, "updated_at", None) else None,
        "latestVersion": latest.version if latest else None,
        "latestVersionId": latest.id if latest else None,
        "changelog": latest.changelog if latest else "",
        "nodeTypes": list(share.node_types or []) if share else [],
        "requiredCredentials": list(share.required_credentials or []) if share else [],
        "riskFlags": list(share.risk_flags or []) if share else [],
        "likeCount": int(getattr(template, "like_count", 0) or 0),
        "commentCount": int(getattr(template, "comment_count", 0) or 0),
        # 목록 카드가 쓰는 그림. 소개에 넣은 이미지 중 고른 하나다.
        "thumbnailUrl": (f"/api/community/templates/{template.slug}/images/{thumbnail}"
                         if thumbnail else None),
        **graph_metadata(share),
    }
    if include_signals:
        payload["signals"] = quality_signals(db, template)
    return payload


def list_templates(db, *, category: Optional[str] = None, tag: Optional[str] = None,
                   query_text: Optional[str] = None, sort: str = "quality",
                   limit: int = 30) -> List:
    import models

    rows = db.query(models.Template).filter(models.Template.status == "published")
    if category:
        rows = rows.filter(models.Template.category == category)
    if tag:
        rows = rows.filter(models.Template.tags.cast(models.String).contains(f'"{tag}"'))
    if query_text:
        needle = f"%{query_text.strip()}%"
        rows = rows.filter((models.Template.title.ilike(needle))
                           | (models.Template.description.ilike(needle)))
    # **자르기 전에** 정렬해야 한다. 아래 quality 처럼 파이썬에서 다시 세우면 "최신 N개를
    # 그 기준으로 줄세운 것"이 되어 전체 상위와 달라진다 — 홈 화면의 인기 아이디어가 여기 기댄다.
    if sort == "installs":
        rows = rows.order_by(models.Template.install_count.desc(), models.Template.id.desc())
    elif sort == "likes":
        rows = rows.order_by(models.Template.like_count.desc(), models.Template.id.desc())
    elif sort == "recent":
        rows = rows.order_by(models.Template.updated_at.desc().nullslast(),
                             models.Template.id.desc())
    else:
        rows = rows.order_by(models.Template.id.desc())
    rows = rows.limit(max(1, min(limit, 100))).all()

    # 시연 노드 비가시화(opt-in, hidden_nodes.py) — 숨긴 노드를 쓰는 템플릿은 갤러리에서 뺀다.
    # 팔레트·생성 카탈로그만 막으면 갤러리 설치가 그 노드를 다시 캔버스에 올린다(계획 표면 3).
    import hidden_nodes
    rows = hidden_nodes.filter_templates(rows)

    if sort == "quality":
        # **첫 실행 성공률**이 1차 기준이다. 측정된 실행이 없으면 뒤로 보낸다 — 설치 수로
        # 대신 세우면 조작에 곧바로 노출된다.
        def key(template):
            signals = quality_signals(db, template)
            return (signals["firstRunSuccessRate"] is not None,
                    signals["firstRunSuccessRate"] or 0, signals["installs"])
        rows.sort(key=key, reverse=True)
    return rows
