"""community_posts.py — 질문·답변·댓글·좋아요 (ADR-0021, 우선 백로그 23 COMMUNITY-1·3).

**가시성 판정이 한 곳에 있다.** 목록·검색·상세가 각자 판단하면 한 경로만 빠뜨려도 친구 공개 글이
전체에 노출되거나 차단한 사람의 글이 그대로 보인다. `visible_post_query()` 가 그 한 곳이다.

가시성은 두 축이 겹친다.

  1. **공개 범위**(§9-10) — `public` 은 누구나, `friends` 는 작성자의 친구만.
  2. **차단**(ADR-0020) — 서로 차단한 상대의 글은 양방향으로 빠진다.

둘 다 **API 응답에서** 적용한다. 화면에서만 숨기면 API 를 직접 부르는 경로가 그대로 남는다.

채택은 질문자만 한다 — 무엇이 자기 문제를 풀었는지는 질문자만 안다. `accepted_answer_id` 와
`is_accepted` 는 **한 트랜잭션**에서 함께 바뀐다. 어긋나면 "해결됨인데 채택 답변이 없는" 질문이 생긴다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Set

POST_KINDS = ("question", "showcase", "tip")
VISIBILITIES = ("public", "friends")
MAX_TITLE = 200
MAX_BODY = 20000
MAX_TAGS = 5
MAX_TAG_LENGTH = 24

# 목록 정렬. Q&A 에서 가장 중요한 화면은 인기 글이 아니라 **아직 답이 없는 질문**이다 —
# 답변률이 떨어지면 커뮤니티가 죽는다.
SORTS = ("unanswered", "recent", "popular", "resolved")


class PostError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 규칙 위반."""


# ── 입력 정리 ───────────────────────────────────────────────────────────
_SCRIPT_RE = re.compile(r"<\s*/?\s*(script|iframe|object|embed|style|link|meta)\b[^>]*>", re.I)
_EVENT_ATTR_RE = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_JS_URL_RE = re.compile(r"(?:javascript|data|vbscript)\s*:", re.I)


def sanitize_markdown(text: str, *, limit: int = MAX_BODY) -> str:
    """**서버에서** 정리한다. 클라이언트 렌더러만 믿으면 API 를 직접 부르는 경로가 남는다.

    마크다운을 파싱하지 않고 위험한 조각만 없앤다 — 렌더러가 무엇이든(marked·react-markdown)
    스크립트·이벤트 핸들러·javascript: URL 이 살아 나가지 못하게 한다.
    """
    body = str(text or "")[:limit]
    body = _SCRIPT_RE.sub("", body)
    body = _EVENT_ATTR_RE.sub("", body)
    body = _JS_URL_RE.sub("blocked:", body)
    return body.strip()


def normalize_tags(raw: Any) -> List[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    tags = []
    for item in raw:
        tag = re.sub(r"[^0-9a-z가-힣-]", "", str(item or "").strip().lower())[:MAX_TAG_LENGTH]
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:MAX_TAGS]


# ── 가시성 ──────────────────────────────────────────────────────────────
def friend_ids(db, user_id: Optional[int]) -> Set[int]:
    import models

    if not user_id:
        return set()
    return {row.friend_id for row in
            db.query(models.Friendship).filter(models.Friendship.user_id == user_id).all()}


def visible_post_query(db, viewer_id: Optional[int]):
    """가시성이 적용된 게시글 쿼리. **목록·검색·상세가 모두 이것을 쓴다.**"""
    import community_safety
    import models

    query = db.query(models.Post).filter(
        models.Post.status == "published", models.Post.deleted_at.is_(None)
    )

    hidden = community_safety.hidden_user_ids(db, viewer_id)
    if hidden:
        query = query.filter(
            (models.Post.author_id.is_(None)) | (~models.Post.author_id.in_(hidden))
        )

    if viewer_id:
        # 친구 공개 글은 작성자의 친구와 작성자 본인에게만 보인다.
        allowed = friend_ids(db, viewer_id) | {viewer_id}
        query = query.filter(
            (models.Post.visibility == "public") | (models.Post.author_id.in_(allowed))
        )
    else:
        # 비로그인 사용자에게 친구 공개 글은 존재하지 않는다.
        query = query.filter(models.Post.visibility == "public")
    return query


def can_view(db, post, viewer_id: Optional[int]) -> bool:
    if post is None or post.status != "published" or post.deleted_at is not None:
        return False
    import community_safety

    if post.author_id and post.author_id in community_safety.hidden_user_ids(db, viewer_id):
        return False
    if post.visibility == "public":
        return True
    if not viewer_id:
        return False
    return post.author_id == viewer_id or post.author_id in friend_ids(db, viewer_id)


# ── 글 ──────────────────────────────────────────────────────────────────
def create_post(db, author, *, kind: str, title: str, body: str, tags=None,
                visibility: str = "public", image_artifact_ids=None):
    import models

    if kind not in POST_KINDS:
        raise PostError(f"허용되지 않는 글 종류입니다: {kind}")
    if visibility not in VISIBILITIES:
        raise PostError(f"허용되지 않는 공개 범위입니다: {visibility}")
    clean_title = sanitize_markdown(title, limit=MAX_TITLE)
    if not clean_title:
        raise PostError("제목을 입력해주세요.")

    post = models.Post(
        author_id=author.id, kind=kind, visibility=visibility,
        title=clean_title, body=sanitize_markdown(body),
        tags=normalize_tags(tags), image_artifact_ids=list(image_artifact_ids or []),
        created_at=datetime.datetime.utcnow(),
    )
    db.add(post)
    db.commit()
    return post


def edit_post(db, actor, post, **changes):
    if post.author_id != actor.id:
        raise PostError("본인의 글만 수정할 수 있습니다.")
    if "title" in changes:
        post.title = sanitize_markdown(changes["title"], limit=MAX_TITLE) or post.title
    if "body" in changes:
        post.body = sanitize_markdown(changes["body"])
    if "tags" in changes:
        post.tags = normalize_tags(changes["tags"])
    if "visibility" in changes:
        if changes["visibility"] not in VISIBILITIES:
            raise PostError("허용되지 않는 공개 범위입니다.")
        post.visibility = changes["visibility"]
    post.edited_at = datetime.datetime.utcnow()
    db.commit()
    return post


# ── 글 이미지 ───────────────────────────────────────────────────────────
def pin_images(db, artifact_ids):
    """글에 붙은 이미지는 만료되지 않게 고정한다.

    업로드는 보존 기간이 지나면 정리된다(ADR-0010). 그대로 두면 멀쩡한 글의 그림이 어느 날
    사라진다. 반대로 고정만 하고 풀지 않으면, 올렸다가 안 올린 그림이 영원히 쌓인다 —
    그래서 붙일 때 고정하고 글이 지워질 때 푸는 짝을 맞춘다.
    """
    import models

    ids = [str(a) for a in (artifact_ids or []) if a]
    if not ids:
        return 0
    rows = db.query(models.UploadedFile).filter(models.UploadedFile.artifact_id.in_(ids)).all()
    for row in rows:
        row.expires_at = None
    return len(rows)


def unpin_images(db, artifact_ids):
    """고정을 풀어 평소 보존 기간을 다시 매긴다. 곧바로 지우지 않는 이유는 글 삭제가
    soft delete 여서다 — 30일 안에 되살아날 수 있고, 그때 그림도 함께 있어야 한다."""
    import datetime as _dt

    import models
    import upload_security

    ids = [str(a) for a in (artifact_ids or []) if a]
    if not ids:
        return 0
    deadline = _dt.datetime.utcnow() + _dt.timedelta(days=upload_security.retention_days())
    rows = db.query(models.UploadedFile).filter(models.UploadedFile.artifact_id.in_(ids)).all()
    for row in rows:
        row.expires_at = deadline
    return len(rows)


def delete_post(db, actor, post, *, is_staff: bool = False):
    """soft delete. 신고 조사 중인 글이 사라지면 판단할 근거가 없어진다 — 30일 뒤 hard delete."""
    if post.author_id != actor.id and not is_staff:
        raise PostError("본인의 글만 삭제할 수 있습니다.")
    post.deleted_at = datetime.datetime.utcnow()
    post.status = "removed" if is_staff and post.author_id != actor.id else "hidden"
    unpin_images(db, post.image_artifact_ids)
    db.commit()
    return post


# ── 답변 ────────────────────────────────────────────────────────────────
def create_answer(db, author, post, *, body: str):
    import models

    if post.kind != "question":
        raise PostError("질문에만 답변할 수 있습니다.")
    clean = sanitize_markdown(body)
    if not clean:
        raise PostError("답변 내용을 입력해주세요.")

    answer = models.Answer(post_id=post.id, author_id=author.id, body=clean,
                           created_at=datetime.datetime.utcnow())
    db.add(answer)
    post.answer_count = (post.answer_count or 0) + 1
    db.commit()
    return answer


def accept_answer(db, actor, post, answer):
    """채택은 **질문자만** 한다. 관리자도 대신하지 않는다 — 무엇이 문제를 풀었는지는 질문자만 안다."""
    import models

    if post.author_id != actor.id:
        raise PostError("질문한 사람만 답변을 채택할 수 있습니다.")
    if answer.post_id != post.id:
        raise PostError("이 질문의 답변이 아닙니다.")

    # 채택은 질문당 하나다. 이전 채택을 내리고 새것을 올리는 것을 한 트랜잭션에서 한다 —
    # 나눠 하면 "해결됨인데 채택 답변이 없는" 상태가 생긴다.
    db.query(models.Answer).filter(
        models.Answer.post_id == post.id, models.Answer.is_accepted.is_(True)
    ).update({models.Answer.is_accepted: False}, synchronize_session=False)
    answer.is_accepted = True
    post.accepted_answer_id = answer.id
    db.commit()
    return answer


def unaccept_answer(db, actor, post):
    import models

    if post.author_id != actor.id:
        raise PostError("질문한 사람만 채택을 바꿀 수 있습니다.")
    db.query(models.Answer).filter(models.Answer.post_id == post.id).update(
        {models.Answer.is_accepted: False}, synchronize_session=False)
    post.accepted_answer_id = None
    db.commit()


def list_answers(db, post, viewer_id: Optional[int]) -> List:
    """채택된 답변이 맨 위, 그다음 좋아요·최신순."""
    import community_safety
    import models

    hidden = community_safety.hidden_user_ids(db, viewer_id)
    query = db.query(models.Answer).filter(
        models.Answer.post_id == post.id, models.Answer.deleted_at.is_(None),
        models.Answer.status == "published",
    )
    if hidden:
        query = query.filter(
            (models.Answer.author_id.is_(None)) | (~models.Answer.author_id.in_(hidden)))
    return query.order_by(
        models.Answer.is_accepted.desc(), models.Answer.like_count.desc(), models.Answer.id.desc()
    ).all()


# ── 댓글 ────────────────────────────────────────────────────────────────
def create_comment(db, author, *, target_type: str, target_id: int, body: str):
    import models

    # 커뮤니티 템플릿의 소개 페이지에도 같은 표를 쓴다 — 댓글 표를 따로 파면 신고·차단·정화가
    # 두 벌이 되고, 그중 한쪽만 고쳐지는 날이 온다.
    if target_type not in ("post", "answer", "template"):
        raise PostError("댓글을 달 수 없는 대상입니다.")
    clean = sanitize_markdown(body, limit=2000)
    if not clean:
        raise PostError("댓글 내용을 입력해주세요.")
    row = models.Comment(target_type=target_type, target_id=int(target_id), author_id=author.id,
                         body=clean, created_at=datetime.datetime.utcnow())
    db.add(row)
    if target_type == "template":
        # 목록에서 쓰는 집계 사본. 정본은 이 comments 행이다.
        template = db.query(models.Template).filter(models.Template.id == int(target_id)).first()
        if template is not None:
            template.comment_count = (template.comment_count or 0) + 1
    db.commit()
    return row


def delete_comment(db, actor, comment, *, is_staff: bool = False):
    """soft delete. 신고 조사 중에 근거가 사라지면 안 되므로 글·답변과 같은 방식을 쓴다."""
    import models

    if not is_staff and comment.author_id != actor.id:
        raise PostError("본인 댓글만 지울 수 있습니다.")
    if comment.deleted_at is not None:
        return comment
    comment.deleted_at = datetime.datetime.utcnow()
    comment.status = "removed" if is_staff and comment.author_id != actor.id else "deleted"
    if comment.target_type == "template":
        template = db.query(models.Template).filter(
            models.Template.id == int(comment.target_id)).first()
        if template is not None:
            template.comment_count = max(0, (template.comment_count or 0) - 1)
    db.commit()
    return comment


def list_comments(db, *, target_type: str, target_ids: List[int], viewer_id: Optional[int]):
    import community_safety
    import models

    if not target_ids:
        return []
    hidden = community_safety.hidden_user_ids(db, viewer_id)
    query = db.query(models.Comment).filter(
        models.Comment.target_type == target_type,
        models.Comment.target_id.in_(target_ids),
        models.Comment.deleted_at.is_(None), models.Comment.status == "published",
    )
    if hidden:
        query = query.filter(
            (models.Comment.author_id.is_(None)) | (~models.Comment.author_id.in_(hidden)))
    return query.order_by(models.Comment.id.asc()).all()


# ── 좋아요 ──────────────────────────────────────────────────────────────
def toggle_like(db, user, *, target_type: str, target_id: int) -> Dict[str, Any]:
    """자기 것에는 누를 수 없다 — 좋아요가 정렬 기준이므로 자기 부풀리기를 막는다."""
    import models

    model = {"post": models.Post, "answer": models.Answer,
             "template": models.Template}.get(target_type)
    if model is None:
        raise PostError("좋아요를 누를 수 없는 대상입니다.")
    target = db.query(model).filter(model.id == int(target_id)).first()
    if target is None:
        raise PostError("대상을 찾을 수 없습니다.")
    # 템플릿은 글쓴이 칸 이름이 owner_id 다. 자기 것 부풀리기 금지는 똑같이 적용한다.
    owner_id = getattr(target, "author_id", None) if target_type != "template" else target.owner_id
    if owner_id == user.id:
        raise PostError("자신의 글에는 좋아요를 누를 수 없습니다.")

    existing = db.query(models.Reaction).filter(
        models.Reaction.target_type == target_type, models.Reaction.target_id == int(target_id),
        models.Reaction.user_id == user.id, models.Reaction.kind == "like",
    ).first()
    if existing:
        db.delete(existing)
        target.like_count = max(0, (target.like_count or 0) - 1)
        liked = False
    else:
        db.add(models.Reaction(target_type=target_type, target_id=int(target_id),
                               user_id=user.id, kind="like",
                               created_at=datetime.datetime.utcnow()))
        target.like_count = (target.like_count or 0) + 1
        liked = True
    db.commit()
    return {"liked": liked, "likeCount": target.like_count}


# ── 목록 ────────────────────────────────────────────────────────────────
def list_posts(db, *, viewer_id: Optional[int], sort: str = "unanswered", kind: Optional[str] = None,
               tag: Optional[str] = None, error_code: Optional[str] = None,
               query_text: Optional[str] = None, before_id: Optional[int] = None,
               limit: int = 20) -> List:
    import models

    query = visible_post_query(db, viewer_id)
    if kind:
        query = query.filter(models.Post.kind == kind)
    if tag:
        # JSON 배열 안의 태그. 규모가 작아 문자열 포함으로 충분하고, 커지면 별도 테이블로 뺀다.
        query = query.filter(models.Post.tags.cast(models.String).contains(f'"{tag}"'))
    if error_code:
        # 같은 오류를 겪는 사람이 "나만 그런가"를 먼저 확인할 수 있어야 한다.
        post_ids = [row.post_id for row in db.query(models.ExecutionExcerpt).filter(
            models.ExecutionExcerpt.error_code == error_code).all()]
        query = query.filter(models.Post.id.in_(post_ids or [-1]))
    if query_text:
        needle = f"%{query_text.strip()}%"
        query = query.filter((models.Post.title.ilike(needle)) | (models.Post.body.ilike(needle)))
    if before_id:
        query = query.filter(models.Post.id < before_id)

    if sort == "unanswered":
        # 기본 화면 — 아직 답이 없는 질문이 위로 온다.
        query = query.order_by(models.Post.answer_count.asc(), models.Post.id.desc())
    elif sort == "popular":
        query = query.order_by(models.Post.like_count.desc(), models.Post.id.desc())
    elif sort == "resolved":
        query = query.filter(models.Post.accepted_answer_id.isnot(None)).order_by(models.Post.id.desc())
    else:
        query = query.order_by(models.Post.id.desc())
    return query.limit(max(1, min(limit, 50))).all()
