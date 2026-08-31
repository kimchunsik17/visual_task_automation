"""node_knowledge.py — Node Knowledge Index와 hybrid retrieval shadow mode (ADR-0013, 우선 백로그 5번).

생성기의 노드 타입 선별은 지금까지 별도 LLM 호출(meta_agent.select_relevant_node_types)이었다.
노드가 늘수록 타입 이름만으로는 선별이 어긋나고, 호출 자체가 지연시간과 비용을 더한다. 이
모듈은 그 호출을 대체할 후보인 hybrid retrieval(별칭 lexical 매칭 + vector 유사도 검색)을
만들고, 먼저 **shadow mode로만** 돌린다 — 생성에는 여전히 LLM 선별 결과를 쓰고, 두 선별의
결과와 최종 그래프에 실제로 쓰인 노드를 generation trace에 나란히 기록해서 Recall이 기준을
넘는지 데이터로 확인한 뒤에만 기본 경로를 바꾼다(로드맵 §4.7 RAG Phase A·B).

원칙(로드맵 §4.7):
  - 구조화된 NodeDefinition이 정답 원본이고, vector DB는 "어떤 노드가 관련 있는가"만 좁힌다.
  - embedding provider가 없거나 죽어도 선별이 중단되지 않는다 — lexical 별칭 매칭으로 폴백.
  - embedding 모델이 바뀌면 기존 vector와 섞지 않는다 — 컬렉션 이름에 model_id가 들어간다.
  - 문서는 NodeDefinition/카탈로그에서만 만들고, 사용자 입력·credential은 색인하지 않는다.

색인 문서(node_capabilities_v1)는 노드 하나당 1개다: 카탈로그 설명 + 한/영 별칭을 text로,
타입·버전·역할·부수효과 등을 metadata로 담는다. 정확한 필드 계약은 여기서 읽지 않는다 —
검색 후 registry(node_definition/NODE_CATALOG)에서 타입으로 다시 조회한다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

import node_definition

load_dotenv()  # 단독 CLI(--sync 등) 실행에서도 OPENAI_API_KEY 등을 읽기 위함

INDEX_VERSION = "v1"
COLLECTION_PREFIX = f"node_capabilities_{INDEX_VERSION}"
DEFAULT_TOP_K = 10  # 로드맵 초기값 8~12. Recall@10을 기준 지표로 쓰므로 10에서 시작한다.
# rag_utils와 같은 저장소를 쓰되(운영 배포 단순화), 테스트는 NODE_INDEX_DB_DIR로 격리한다.
_DEFAULT_DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def shadow_mode_enabled() -> bool:
    """생성 경로에서 hybrid 선별을 LLM 선별과 나란히(결과는 기록만) 돌릴지."""
    return _env_flag("NODE_RETRIEVAL_SHADOW", True)


def retrieval_top_k() -> int:
    try:
        return max(1, int(os.getenv("NODE_RETRIEVAL_TOP_K", str(DEFAULT_TOP_K))))
    except ValueError:
        return DEFAULT_TOP_K


# ── 별칭 테이블 ──────────────────────────────────────────────────────────
# 노드 타입별 한/영 사용자 표현. NodeDefinition으로 이전이 끝난 노드는 정의 파일이 이
# 역할을 넘겨받는 게 목표지만(RAG Phase D), 아직 카탈로그 문자열에만 사는 노드가 34종이라
# 여기서 함께 관리한다. 별칭은 소문자 부분 문자열 매칭에 쓰이므로 2글자 이상, 그리고
# "보내"처럼 어느 요청에나 나오는 표현은 넣지 않는다(정밀도가 무너진다).
NODE_ALIASES: Dict[str, List[str]] = {
    "startNode": ["시작점", "start"],
    "scheduleNode": ["매일", "매주", "매월", "매시간", "분마다", "시간마다", "정기적", "주기적",
                     "스케줄", "크론", "cron", "아침마다", "정각", "밤마다", "요일마다"],
    "promptNode": ["프롬프트", "지시문", "prompt"],
    "llmNode": ["llm", "gpt", "요약", "번역", "분류", "분석해", "작성해", "생성해", "다듬",
                "감성 분석", "인공지능", "정리해"],
    "tokenizerNode": ["pdf", "pptx", "hwp", "문서에서", "텍스트 추출", "업로드한", "문서 파일",
                      "첨부 파일"],
    "templateAnalyzerNode": ["서식", "양식", "빈칸", "템플릿 파일", "채워야 할"],
    "fileModifierNode": ["새 파일로", "파일로 저장", "docx", "서식에 채워", "문서로 만들",
                         "파일을 생성"],
    # 한국형 노드 계획 Phase 1 — 서식 없이 처음부터 만드는 쪽. fileModifierNode(빈칸 채우기)와
    # 헷갈리기 쉬워서 "한글 문서"·"hwpx" 처럼 포맷을 짚는 말을 별칭으로 둔다.
    "hwpxDocumentNode": ["한글 문서", "hwpx", "한글파일", "보고서 작성", "공문", "회의록"],
    # 포맷 스튜디오 계획 Phase 1 — 빈칸이 선언된 포맷(문서·포스터)에 값을 채워 파일을 만든다.
    # hwpxDocumentNode(코드로 .hwpx 만들기)·fileModifierNode(기존 서식 파일 채우기)와 겹치는
    # 말이 많아서, "양식/서식/포맷"과 산출물 종류를 짚는 말을 별칭으로 둔다.
    "formatNode": ["문서 포맷", "양식", "서식", "포맷", "시말서", "제안서", "입사지원서",
                   "회의록 양식", "공문 양식", "포스터", "팜플렛", "전단지", "카드뉴스",
                   "문서 만들기", "문서 생성", "엑셀로 저장", "워드 문서", "PDF 문서"],
    # 한국형 노드 계획 Phase 2 — 네이버에서 "찾는" 쪽. webSearchNode(인터넷 전반)와 구분되게
    # 서비스 이름을 짚는 말을 별칭으로 둔다.
    "naverSearchNode": ["네이버 검색", "네이버 블로그", "카페글", "네이버에서 찾", "블로그 검색"],
    "jusoNode": ["도로명주소", "주소 검색", "우편번호", "지번주소", "영문주소", "주소 정리",
                 "주소 정규화", "주소 변환"],
    "dataGoKrNode": ["공공데이터", "공공데이터포털", "기상청", "날씨", "예보", "보도자료",
                     "정부 데이터", "공공 API"],
    # 트리거는 "감시·알림" 쪽 말로 갈린다 — 같은 네이버라도 한 번 찾는 것과 계속 지켜보는 것은 다르다.
    "naverSearchTriggerNode": ["새 글 올라오면", "네이버 감시", "키워드 알림", "새 블로그 글",
                               "언급되면", "모니터링"],
    # 게시는 되돌릴 수 없다 — "올려/작성/게시" 같은 명시적인 말에만 걸리게 한다.
    "naverCafeNode": ["카페에 올려", "카페 글쓰기", "카페에 게시", "카페 가입", "네이버 카페"],
    "posterGeneratorNode": ["포스터", "홍보 이미지", "배너", "카드뉴스", "png", "이미지로 저장"],
    "imageGenerationNode": ["AI 이미지", "이미지 생성", "그림 생성", "이미지 수정", "그림 수정", "인페인팅", "이미지 피드백"],
    # 조건 분기는 "장애면/있으면/비었으면"처럼 어미로만 드러나는 경우가 많아 정규식 별칭
    # ("re:" 접두사, 문서 text에는 넣지 않는다)을 함께 쓴다.
    "conditionNode": ["조건", "분기", "이면", "아니면", "만약", "미만", "이상이면", "초과",
                      "이하", "경우에만", "따라 다르게", "점수가",
                      "re:(으면|다면|라면)", r"re:[가-힣]면\s"],
    "distributorNode": ["각각", "목록의", "리스트의", "병렬", "분배", "나눠서", "모든 항목",
                        "하나씩"],
    "breakNode": ["중단", "멈춰", "break", "빠져나"],
    "webhookNode": ["웹훅", "webhook", "콜백", "외부에서 호출"],
    "discordTriggerNode": ["디스코드 메시지가 오면", "디스코드에서 메시지", "디스코드 명령",
                           "디스코드로 물어보면"],
    "telegramTriggerNode": ["텔레그램 메시지가 오면", "텔레그램에서 메시지", "텔레그램으로 물어보면"],
    "youtubeTriggerNode": ["새 영상이 올라오면", "새 댓글이 달리면", "유튜브에 올라오면",
                           "라이브 시작"],
    "rssTriggerNode": ["rss", "피드", "새 글이 올라오면", "블로그에 글이", "atom"],
    "gmailTriggerNode": ["메일이 오면", "메일이 도착", "지메일에 새", "받은편지함에"],
    "gmailNode": ["지메일", "gmail", "메일 답장", "임시저장", "메일에 라벨"],
    "googleDriveNode": ["드라이브", "drive", "구글 드라이브", "파일을 올려", "공유 링크"],
    "telegramNode": ["텔레그램", "telegram"],
    "httpRequestNode": ["api", "http", "rest", "엔드포인트", "요청을 보내", "post", "get 요청",
                        "호출해"],
    "jsonParserNode": ["json", "파싱", "키 값", "필드만", "필드를 추출", "값만 추출"],
    "databaseNode": ["sql", "데이터베이스", "db에서", "쿼리", "테이블에서", "조회해"],
    "googleSheetsNode": ["시트", "스프레드시트", "sheets", "행 추가", "표에 기록"],
    "googleCalendarNode": ["캘린더", "일정", "calendar", "미팅을 등록", "약속을 등록"],
    "youtubeNode": ["유튜브", "youtube", "영상 업로드", "영상을 올리", "재생목록", "동영상"],
    "notionNode": ["노션", "notion", "페이지로 저장", "데이터베이스에 새 페이지"],
    "delayNode": ["기다렸다가", "대기", "분 후에", "지연", "delay", "있다가", "잠시 후"],
    "dynamicInputNode": ["입력받은", "입력된", "입력한", "사용자 입력", "입력이", "붙여넣",
                         "실행할 때 입력"],
    "valueNode": ["고정값", "상수", "정해진 값", "고정된 텍스트"],
    "webCrawlerNode": ["크롤링", "크롤러", "스크랩", "웹페이지", "웹사이트에서", "뉴스를 가져",
                       "사이트에서 가져", "본문만", "기사 본문", "페이지 링크", "링크 모아"],
    "emailNode": ["이메일", "메일로", "email", "메일을 보내"],
    "loopNode": ["반복", "루프", "여러 번", "다시 시도", "번 반복", "반복해서"],
    "multiAgentNode": ["에이전트", "전문가", "라우팅", "알맞은 담당", "멀티 에이전트"],
    "pythonNode": ["파이썬", "python", "코드로", "전처리", "스크립트", "csv"],
    "discordNode": ["디스코드", "discord"],
    "kakaoNode": ["카카오", "카톡", "알림톡", "kakao"],
    "tossNode": ["토스", "결제 조회", "결제 정보를 조회", "결제 내역"],
    "paymentLinkNode": ["결제 링크", "결제창", "주문서", "결제 요청 링크", "결제 페이지"],
    "slackNode": ["슬랙", "slack"],
    "humanApprovalNode": ["승인", "결재", "허가", "사람이 확인", "검토 후", "거절하면",
                          "컨펌"],
    "mergeNode": ["병합", "합쳐", "합치", "모아서", "취합", "하나로 묶"],
    "outputNode": ["출력", "결과 화면", "화면에", "보여줘"],
}

# 카탈로그 문자열에만 사는 노드의 역할/부수효과. NodeDefinition이 있는 노드는 정의에서 읽고,
# 나머지는 이 표를 쓴다(노드가 정의 파일로 이전되면 여기서 지운다). 값은 생성 규칙이 아니라
# 검색 metadata 용도다 — 틀려도 검색 우선순위가 어긋날 뿐 실행에는 영향이 없다.
_CATALOG_ROLE_OVERRIDES: Dict[str, str] = {
    "startNode": "trigger", "scheduleNode": "trigger", "webhookNode": "trigger",
    "discordTriggerNode": "trigger", "telegramTriggerNode": "trigger",
}
_CATALOG_SIDE_EFFECTS: Dict[str, str] = {
    "emailNode": "external-write", "discordNode": "external-write", "kakaoNode": "external-write",
    "slackNode": "external-write", "telegramNode": "external-write",
    "googleSheetsNode": "external-write", "googleCalendarNode": "external-write",
    "notionNode": "external-write", "paymentLinkNode": "external-write",
    "tossNode": "external-read", "databaseNode": "external-read",
    "webCrawlerNode": "external-read",
}


def _catalog_entries() -> Dict[str, str]:
    # meta_agent가 이 모듈을 import하므로(shadow 선별), 카탈로그는 호출 시점에 가져온다.
    from meta_agent import NODE_CATALOG_ENTRIES

    return NODE_CATALOG_ENTRIES


def _entry_description(entry_text: str) -> str:
    """'- nodeType      : 설명...' 카탈로그 항목에서 접두사를 뗀 설명 본문."""
    body = re.sub(r"^- \w+\s*: ", "", entry_text)
    return re.sub(r"\n\s+", " ", body).strip()


def known_node_types() -> List[str]:
    return list(_catalog_entries().keys())


# ── 색인 문서 ────────────────────────────────────────────────────────────
def build_capability_documents() -> List[Dict[str, Any]]:
    """노드 하나당 검색 문서 1개. text는 embedding 대상이고 metadata는 필터/조회용이다.
    schema 전체를 embedding하지 않는다 — 정확한 필드 계약은 검색 후 registry에서 읽는다."""
    documents: List[Dict[str, Any]] = []
    for node_type, entry in _catalog_entries().items():
        defn = node_definition.get_definition(node_type)
        aliases = NODE_ALIASES.get(node_type, [])
        version = defn.version if defn else 1
        if defn is not None:
            role = defn.connector.role if defn.connector else (
                "trigger" if defn.category == "trigger" else "action"
            )
            service = defn.connector.service if defn.connector else None
            side_effect = defn.sideEffect
            capabilities = list(defn.capabilities)
            credential_providers = sorted({c.provider for c in defn.credentials})
        else:
            role = _CATALOG_ROLE_OVERRIDES.get(node_type, "action")
            service = None
            side_effect = _CATALOG_SIDE_EFFECTS.get(node_type, "none")
            capabilities = []
            credential_providers = []
        text = _entry_description(entry)
        readable_aliases = [alias for alias in aliases if not alias.startswith("re:")]
        if readable_aliases:
            text += "\n사용자 표현: " + ", ".join(readable_aliases)
        metadata = {
            "node_type": node_type,
            "version": version,
            "status": "active",
            "role": role,
            "service": service or "",
            "side_effect": side_effect,
            "capabilities": ",".join(capabilities),
            "credential_providers": ",".join(credential_providers),
            "locale": "ko",
            "index_version": INDEX_VERSION,
        }
        content_hash = hashlib.sha256(
            json.dumps({"text": text, "metadata": metadata}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        metadata["content_hash"] = content_hash
        documents.append({"id": f"{node_type}@{version}", "text": text, "metadata": metadata})
    return documents


# ── Embedding provider ──────────────────────────────────────────────────
class EmbeddingProvider:
    """로드맵 §4.7의 provider 추상화. 구현체는 문서/쿼리 embedding과 model_id만 제공한다."""

    model_id: str = ""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: Optional[str] = None):
        from langchain_openai import OpenAIEmbeddings

        model = model or os.getenv("NODE_EMBEDDING_OPENAI_MODEL", "text-embedding-3-small")
        self.model_id = f"openai:{model}"
        self._embeddings = OpenAIEmbeddings(model=model)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)


class LocalEmbeddingProvider(EmbeddingProvider):
    """OpenAI 호환 /v1/embeddings endpoint(Ollama, llama.cpp 등)를 쓰는 로컬 provider.
    check_embedding_ctx_length=False가 필수다 — 켜져 있으면 tiktoken으로 토큰 배열을 보내는데
    OpenAI가 아닌 서버는 그 형식을 거부한다."""

    def __init__(self, base_url: str, model: str, api_key: str = ""):
        from langchain_openai import OpenAIEmbeddings

        self.model_id = f"local:{model}"
        self._embeddings = OpenAIEmbeddings(
            model=model,
            base_url=base_url,
            api_key=api_key or "local",
            check_embedding_ctx_length=False,
            timeout=15,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)


def resolve_embedding_provider() -> Optional[EmbeddingProvider]:
    """환경 설정에서 provider를 고른다. 없으면 None — 호출부는 lexical 선별로 폴백한다.

    NODE_EMBEDDING_PROVIDER = auto(기본) | openai | local | off
      auto: 로컬 embedding 설정이 있으면 local, 아니면 OPENAI_API_KEY가 있으면 openai.
    """
    choice = os.getenv("NODE_EMBEDDING_PROVIDER", "auto").strip().lower()
    if choice == "off":
        return None
    local_base = (
        os.getenv("NODE_EMBEDDING_LOCAL_BASE_URL", "").strip()
        or (os.getenv("LLM_LOCAL_BASE_URL", "").strip()
            if os.getenv("LLM_ROUTING_MODE", "").strip().lower() in {"local", "hybrid"} else "")
    )
    local_model = os.getenv("NODE_EMBEDDING_LOCAL_MODEL", "").strip() or "bge-m3"
    try:
        if choice == "local" or (choice == "auto" and local_base):
            base = local_base or os.getenv("LLM_LOCAL_BASE_URL", "").strip()
            if not base:
                print("[node_knowledge] NODE_EMBEDDING_PROVIDER=local인데 base URL이 없다 — 폴백")
                return None
            return LocalEmbeddingProvider(
                base_url=base, model=local_model,
                api_key=os.getenv("NODE_EMBEDDING_LOCAL_API_KEY", "").strip(),
            )
        if choice in {"openai", "auto"}:
            if not os.getenv("OPENAI_API_KEY"):
                return None
            return OpenAIEmbeddingProvider()
    except Exception as e:
        print(f"[node_knowledge] embedding provider 초기화 실패({choice}): {e}")
        return None
    print(f"[node_knowledge] 알 수 없는 NODE_EMBEDDING_PROVIDER '{choice}' — 폴백")
    return None


# ── Chroma 색인 ─────────────────────────────────────────────────────────
def _collection_name(model_id: str) -> str:
    # 모델이 바뀌면 기존 vector와 섞지 않는다 — 컬렉션 이름에 model_id를 넣어 새로 색인한다.
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", model_id).strip("-").lower()
    return f"{COLLECTION_PREFIX}__{slug}"[:63].rstrip("-_")


def _db_dir() -> str:
    return os.getenv("NODE_INDEX_DB_DIR", "").strip() or _DEFAULT_DB_DIR


def _get_collection(provider: EmbeddingProvider, db_dir: Optional[str] = None):
    import chromadb

    client = chromadb.PersistentClient(path=db_dir or _db_dir())
    return client.get_or_create_collection(
        name=_collection_name(provider.model_id),
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": provider.model_id,
            "index_version": INDEX_VERSION,
        },
    )


def sync_node_index(
    provider: Optional[EmbeddingProvider] = None,
    db_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """카탈로그/정의에서 만든 문서를 컬렉션과 증분 동기화한다(content_hash 비교).
    추가/변경된 문서만 embedding하고, 사라진 노드의 문서는 지운다."""
    provider = provider or resolve_embedding_provider()
    if provider is None:
        return {"status": "skipped", "reason": "embedding provider 없음 (lexical 폴백으로 동작)"}
    documents = build_capability_documents()
    collection = _get_collection(provider, db_dir=db_dir)
    existing = collection.get(include=["metadatas"])
    existing_hashes = {
        doc_id: (meta or {}).get("content_hash")
        for doc_id, meta in zip(existing.get("ids", []), existing.get("metadatas", []) or [])
    }
    wanted_ids = {doc["id"] for doc in documents}
    stale_ids = [doc_id for doc_id in existing_hashes if doc_id not in wanted_ids]
    changed = [doc for doc in documents if existing_hashes.get(doc["id"]) != doc["metadata"]["content_hash"]]

    if changed:
        vectors = provider.embed_documents([doc["text"] for doc in changed])
        collection.upsert(
            ids=[doc["id"] for doc in changed],
            embeddings=vectors,
            documents=[doc["text"] for doc in changed],
            metadatas=[doc["metadata"] for doc in changed],
        )
    if stale_ids:
        collection.delete(ids=stale_ids)
    return {
        "status": "synced",
        "collection": _collection_name(provider.model_id),
        "embedding_model": provider.model_id,
        "total": len(documents),
        "upserted": len(changed),
        "removed": len(stale_ids),
        "unchanged": len(documents) - len(changed),
    }


def sync_node_index_in_background() -> None:
    """서버 시작을 embedding 호출로 막지 않기 위한 비동기 래퍼. 실패해도 서비스에는 영향이
    없다 — 색인이 없으면 hybrid 선별이 lexical로 폴백할 뿐이고, 생성은 LLM 선별을 쓴다."""

    def _run():
        try:
            print(f"[node_knowledge] index sync: {sync_node_index()}")
        except Exception as e:
            print(f"[node_knowledge] index sync 실패(lexical 폴백으로 동작): {e}")

    threading.Thread(target=_run, name="node-index-sync", daemon=True).start()


# ── 검색 ────────────────────────────────────────────────────────────────
# release 시 한 번 색인하고, query embedding은 정규화한 요청 hash로 짧게 cache한다(로드맵).
_query_cache: "OrderedDict[str, List[float]]" = OrderedDict()
_query_cache_lock = threading.Lock()
_QUERY_CACHE_MAX = 256


def _cached_query_embedding(provider: EmbeddingProvider, text: str) -> List[float]:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    key = provider.model_id + ":" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    with _query_cache_lock:
        if key in _query_cache:
            _query_cache.move_to_end(key)
            return _query_cache[key]
    vector = provider.embed_query(normalized)
    with _query_cache_lock:
        _query_cache[key] = vector
        while len(_query_cache) > _QUERY_CACHE_MAX:
            _query_cache.popitem(last=False)
    return vector


def lexical_candidates(user_request: str) -> List[str]:
    """별칭/타입 이름의 결정론적 부분 문자열 매칭. embedding 없이도 항상 동작하는 폴백이자
    hybrid의 1차 후보다."""
    text = user_request.lower()
    hits: List[str] = []
    for node_type in known_node_types():
        aliases = NODE_ALIASES.get(node_type, [])
        service_name = node_type[: -len("Node")] if node_type.endswith("Node") else node_type
        probes = [alias.lower() for alias in aliases if not alias.startswith("re:")]
        patterns = [alias[3:] for alias in aliases if alias.startswith("re:")]
        if len(service_name) >= 4:  # 'llm'처럼 짧은 건 별칭에서 다루고, 타입 이름은 4자 이상만
            probes.append(service_name.lower())
        if any(probe in text for probe in probes) or any(re.search(p, text) for p in patterns):
            hits.append(node_type)
    return hits


def vector_candidates(
    user_request: str,
    k: Optional[int] = None,
    provider: Optional[EmbeddingProvider] = None,
    db_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """컬렉션에서 active 노드 문서 top-k. provider/색인이 없으면 빈 리스트(호출부가 lexical로)."""
    provider = provider or resolve_embedding_provider()
    if provider is None:
        return []
    k = k or retrieval_top_k()
    collection = _get_collection(provider, db_dir=db_dir)
    if collection.count() == 0:
        return []
    vector = _cached_query_embedding(provider, user_request)
    result = collection.query(
        query_embeddings=[vector],
        n_results=min(k, collection.count()),
        where={"status": "active"},
        include=["metadatas", "distances"],
    )
    candidates: List[Dict[str, Any]] = []
    for meta, distance in zip(
        (result.get("metadatas") or [[]])[0],
        (result.get("distances") or [[]])[0],
    ):
        if not meta:
            continue
        candidates.append({
            "node_type": meta.get("node_type"),
            "score": round(1.0 - float(distance), 4),  # cosine distance → similarity
            "role": meta.get("role"),
            "side_effect": meta.get("side_effect"),
        })
    return candidates


# 검색 파이프라인 5단계(dependency closure)의 1차 구현: 어휘·유사도로는 드러나지 않고
# 그래프 구조에서만 필요해지는 노드를 결정론적으로 보강한다. 검색 점수와 무관하게 항상
# 적용한다(로드맵 원칙 3 — 필수 구조 규칙은 결정론적으로 주입).
_TRIGGER_TYPES = {
    "scheduleNode", "webhookNode", "discordTriggerNode", "telegramTriggerNode", "youtubeTriggerNode",
}
_BRANCHING_TYPES = {"conditionNode", "humanApprovalNode", "distributorNode"}


def dependency_closure(selected: List[str], lexical: Optional[List[str]] = None) -> List[str]:
    """선택된 후보가 구조적으로 끌고 오는 노드 타입(선택에 없던 것만)을 돌려준다.

    - 트리거가 없으면 수동 실행 흐름이므로 dynamicInputNode(실행 시 입력)가 필요할 가능성이
      높다 — "정보를 받아", "…를 변환해줘"처럼 입력을 말로 안 하는 요청에서 lexical/vector가
      일관되게 놓치던 타입이다. 트리거 존재 판단은 결정론적 근거(lexical 매칭)만 쓴다 —
      vector가 추측으로 고른 트리거(예: "일정 생성" 요청에 scheduleNode)가 이 보강을
      억제하면 안 된다.
    - 분기 노드(condition/humanApproval/distributor)가 있으면 갈래를 다시 모으는
      mergeNode를 함께 제공한다.
    """
    have = set(selected)
    deterministic = set(lexical) if lexical is not None else have
    closure: List[str] = []
    if not (deterministic & _TRIGGER_TYPES) and "dynamicInputNode" not in have:
        closure.append("dynamicInputNode")
    if (have & _BRANCHING_TYPES) and "mergeNode" not in have:
        closure.append("mergeNode")
    return closure


def hybrid_select_node_types(
    user_request: str,
    k: Optional[int] = None,
    provider: Optional[EmbeddingProvider] = None,
    db_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """lexical ∪ vector top-k 후보. LLM 호출이 없어 결정론적이고 빠르다.

    지금은 shadow 전용이다 — 반환값은 trace에 기록만 되고 생성 프롬프트에는 쓰이지 않는다.
    Recall gate(로드맵 §4.7 평가 세트) 통과 전에는 기본 selector로 승격하지 않는다.
    """
    started = time.perf_counter()
    lexical = lexical_candidates(user_request)
    vector: List[Dict[str, Any]] = []
    error: Optional[str] = None
    provider = provider if provider is not None else resolve_embedding_provider()
    if provider is not None:
        try:
            vector = vector_candidates(user_request, k=k, provider=provider, db_dir=db_dir)
        except Exception as e:  # vector 장애가 선별을 중단시키면 안 된다(원칙 5)
            error = f"{type(e).__name__}: {e}"
    vector_types = [c["node_type"] for c in vector if c.get("node_type")]
    selected: List[str] = []
    for node_type in lexical + vector_types:
        if node_type not in selected:
            selected.append(node_type)
    closure = dependency_closure(selected, lexical=lexical)
    selected += closure
    return {
        "selected_types": selected,
        "lexical_types": lexical,
        "vector_types": vector_types,
        "closure_types": closure,
        "vector_scores": {c["node_type"]: c["score"] for c in vector if c.get("node_type")},
        "source": "hybrid" if provider is not None and not error else "lexical-only",
        "embedding_model": provider.model_id if provider else None,
        "top_k": k or retrieval_top_k(),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "error": error,
    }


# ── 선별 트레이스 수집기 (RAG Phase A) ──────────────────────────────────
# run_agent_turn이 턴 시작에 수집기를 열고, 생성 함수(스레드에서 돌더라도 같은 컨텍스트가
# 복사되므로 같은 dict 객체를 본다)가 선별 이벤트를 붙이고, attach_trace가 회수한다.
# 수집기가 열려 있지 않으면(테스트, 단독 호출) 기록은 조용히 무시된다.
_selection_trace: ContextVar[Optional[Dict[str, Any]]] = ContextVar("node_selection_trace", default=None)


def begin_selection_trace() -> None:
    _selection_trace.set({"events": []})


def record_selection_event(event: Dict[str, Any]) -> None:
    collector = _selection_trace.get()
    if collector is not None:
        collector["events"].append(event)


def collect_selection_trace() -> Optional[Dict[str, Any]]:
    collector = _selection_trace.get()
    _selection_trace.set(None)
    if collector and collector["events"]:
        return collector
    return None


def summarize_selection(events: List[Dict[str, Any]], final_node_types: List[str]) -> Dict[str, Any]:
    """선별 이벤트들과 최종 그래프에 실제로 쓰인 노드를 비교한다(로드맵 Phase A 계측).

    - missing_vs_final : 최종 그래프에 쓰였는데 그 selector가 제공한 후보에 없던 타입
                         (LLM 쪽은 트리밍된 카탈로그 기준 — 여기 있으면 생성기가 카탈로그에
                         없는 노드를 썼다는 뜻이고, hybrid 쪽은 승격 시 recall 구멍이다)
    - unused           : 후보로 제공됐지만 최종 그래프에 안 쓰인 타입(프롬프트 노이즈)
    """
    final_types = sorted({t for t in final_node_types if t})

    def compare(offered: set) -> Dict[str, Any]:
        return {
            "offered_count": len(offered),
            "missing_vs_final": sorted(set(final_types) - offered),
            "unused": sorted(offered - set(final_types)),
        }

    llm_offered: set = set()
    hybrid_offered: set = set()
    llm_fallbacks = 0
    llm_token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for event in events:
        llm_offered.update((event.get("catalog") or {}).get("offered_types") or [])
        if (event.get("catalog") or {}).get("fallback_full_catalog"):
            llm_fallbacks += 1
        for key in llm_token_usage:
            llm_token_usage[key] += int(((event.get("llm") or {}).get("token_usage") or {}).get(key, 0) or 0)
        hybrid_offered.update((event.get("shadow") or {}).get("selected_types") or [])

    summary: Dict[str, Any] = {
        "schema_version": "node-selection-v1",
        "event_count": len(events),
        "final_node_types": final_types,
        "llm_selector": {
            **compare(llm_offered),
            "fallback_full_catalog_count": llm_fallbacks,
            "token_usage": llm_token_usage,
        },
        "events": events,
    }
    shadow_events = [e for e in events if (e.get("shadow") or {}).get("selected_types") is not None]
    if shadow_events:
        summary["hybrid_selector"] = {
            **compare(hybrid_offered),
            "source": shadow_events[-1]["shadow"].get("source"),
            "embedding_model": shadow_events[-1]["shadow"].get("embedding_model"),
        }
        both = llm_offered | hybrid_offered
        summary["agreement"] = {
            "jaccard": round(len(llm_offered & hybrid_offered) / len(both), 4) if both else 1.0,
            "llm_only": sorted(llm_offered - hybrid_offered),
            "hybrid_only": sorted(hybrid_offered - llm_offered),
        }
    return summary


# ── CLI ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Node Knowledge Index 관리")
    parser.add_argument("--sync", action="store_true", help="색인을 증분 동기화한다")
    parser.add_argument("--status", action="store_true", help="provider와 컬렉션 상태를 출력한다")
    parser.add_argument("--query", help="hybrid 선별을 한 번 실행해 결과를 출력한다")
    args = parser.parse_args()

    if args.sync:
        print(json.dumps(sync_node_index(), ensure_ascii=False, indent=2))
    if args.status:
        provider = resolve_embedding_provider()
        info: Dict[str, Any] = {"embedding_model": provider.model_id if provider else None}
        if provider:
            collection = _get_collection(provider)
            info["collection"] = _collection_name(provider.model_id)
            info["indexed"] = collection.count()
        info["document_count"] = len(build_capability_documents())
        print(json.dumps(info, ensure_ascii=False, indent=2))
    if args.query:
        print(json.dumps(hybrid_select_node_types(args.query), ensure_ascii=False, indent=2))
    if not (args.sync or args.status or args.query):
        parser.print_help()
