# -*- coding: utf-8 -*-
"""official_templates.publish — 242개(기존 142 + 신규 100)를 공식 템플릿으로 게시한다.

    python -m official_templates.publish


`publish_curated` 를 쓴다 — 실행 이력 요건만 면제되고 정화·구조·코드노드·고위험 분류는
그대로 적용된다. 다시 돌려도 안전하다(이미 있는 slug 는 건너뛴다).
"""
import importlib.util
import json
import os
import re
import unicodedata

import community_templates as ct
import database
import models

# 게시 주체. 공식 템플릿의 소유자이자 검수자다.
OWNER_EMAIL = os.getenv("OFFICIAL_TEMPLATE_OWNER", "browny1213@pusan.ac.kr")
SEED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "seed_curated_templates.py")

# 기존 142개의 분류를 갤러리 6종으로 옮긴다.
LEGACY_CATEGORY = {
    "Batch_List_Processing_and_Digests": "data",
    "QA_Chatbots_and_Assistants": "automation",
    "Content_Generation": "content",
    "Approval_Workflows": "automation",
    "Classification_and_Routing": "automation",
    "Document_Processing": "document",
}
LEGACY_TAGS = {
    "Batch_List_Processing_and_Digests": ["일괄처리", "요약"],
    "QA_Chatbots_and_Assistants": ["챗봇", "질의응답"],
    "Content_Generation": ["콘텐츠", "생성"],
    "Approval_Workflows": ["승인", "결재"],
    "Classification_and_Routing": ["분류", "라우팅"],
    "Document_Processing": ["문서", "처리"],
}


def slugify(text, used):
    """한글 제목에서 주소를 만든다. 한글은 로마자 대신 **순번**으로 간다 —
    엉성한 음차보다 예측 가능한 편이 낫다."""
    ascii_part = re.sub(r"[^a-z0-9]+", "-",
                        unicodedata.normalize("NFKD", text).encode("ascii", "ignore")
                        .decode().lower()).strip("-")
    base = ascii_part or "wf"
    base = base[:32].strip("-") or "wf"
    if len(base) < 3:
        base = f"wf-{base}"
    # 예약어(api, app, template …)는 게시가 거부된다 — 순번을 붙여 피한다.
    slug, i = base, 1
    while slug in used or len(slug) < 3 or slug in ct.RESERVED_SLUGS:
        i += 1
        slug = f"{base}-{i}"[:40].strip("-")
    used.add(slug)
    return slug


def main():
    db = database.SessionLocal()
    owner = db.query(models.User).filter(models.User.email == OWNER_EMAIL).first()
    assert owner, f"{OWNER_EMAIL} 없음"

    used = {t.slug for t in db.query(models.Template).all()}
    existing_titles = {t.title for t in db.query(models.Template).all()}

    items = []

    # 1) 기존 142개
    spec = importlib.util.spec_from_file_location("seedmod", SEED_PATH)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    for name, cat, g in seed.TEMPLATES:
        graph = json.loads(g.model_dump_json())
        items.append({
            "title": name,
            "description": (graph.get("description") or "").strip() or f"{name} 자동화 워크플로우입니다.",
            "category": LEGACY_CATEGORY.get(cat, "automation"),
            "tags": LEGACY_TAGS.get(cat, ["자동화"]),
            "graph": graph,
            "source": f"n8n 커뮤니티 템플릿 로직 참고 ({cat})",
        })

    # 2) 신규 100개
    from . import TEMPLATES as NEW
    for t in NEW:
        items.append({
            "title": t["title"], "description": t["description"],
            "category": t["category"], "tags": t["tags"], "graph": t["graph"],
            "source": t.get("source") or "WorkFlow Ai 자체 제작",
            # 한글 제목은 slugify 에서 ASCII 만 남아 의미 없는 주소가 된다 —
            # 템플릿이 직접 준 주소가 있으면 그것을 쓴다.
            "slug": t.get("slug") or "",
        })

    published = review = skipped = failed = 0
    errors = []
    for it in items:
        if it["title"] in existing_titles:
            skipped += 1
            continue
        slug = it.get("slug") or slugify(it["title"], used)
        if it.get("slug"):
            used.add(slug)
        try:
            template, _v = ct.publish_curated(
                db, owner, graph=it["graph"], slug=slug, title=it["title"],
                description=it["description"], category=it["category"], tags=it["tags"],
                source=it["source"], reviewer="browny1213",
                changelog="첫 공개.")
        except Exception as exc:
            failed += 1
            errors.append((it["title"], str(exc)[:150]))
            db.rollback()
            continue
        if template.status == "published":
            published += 1
        else:
            review += 1

    print(f"게시 완료(바로 공개) : {published}")
    print(f"검토 대기(in_review) : {review}")
    print(f"건너뜀(이미 있음)     : {skipped}")
    print(f"실패                 : {failed}")
    for t, why in errors[:10]:
        print(f"   ✗ {t}\n       {why}")
    print()
    print("DB 총 템플릿:", db.query(models.Template).count(),
          "| 공식:", db.query(models.Template).filter(models.Template.is_curated.is_(True)).count())


if __name__ == "__main__":
    main()
