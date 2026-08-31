"""official_templates — 운영자가 만든 공식 커뮤니티 템플릿 100종 (2026-08-30).

`seed_curated_templates.py` 의 142개와 다른 점은 **용도**다.

    seed_curated_templates.py  →  벡터 스토어. LLM 이 워크플로우를 생성할 때 참고하는 예시
    official_templates/        →  커뮤니티 갤러리. 사용자가 둘러보고 설치하는 템플릿

142개는 2026-08-28 에 만들어져 그때 있던 24종 노드만 쓴다. 이 묶음은 그 뒤 추가된
네이버·HWPX·도로명주소·Gmail·Drive·Sheets·Calendar·YouTube·RSS·노션·텔레그램 노드를 쓴다 —
**그때는 만들 수 없던 워크플로우**들이다.

I묶음(2026-08-31)은 필드 데이터 바인딩(ADR-0026)을 쓴다 — 값을 옮기기만 하는 자리에서 LLM 을
빼낸 흐름들이라, 대부분 LLM 을 아예 부르지 않는다.

게시는 `community_templates.publish_curated` 로 한다(실행 이력 요건만 면제, 나머지 게이트는
그대로). `python -m official_templates.publish` 로 올린다 — 이미 있는 제목은 건너뛴다.
"""
from . import a, b, c, d, e, f, g, h, i

MODULES = (a, b, c, d, e, f, g, h, i)
TEMPLATES = [t for m in MODULES for t in m.TEMPLATES]

__all__ = ["TEMPLATES", "MODULES"]
