import os
import threading
from typing import List, Dict, Any, Optional
import chromadb
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import json
import fitz  # PyMuPDF
import docx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

load_dotenv()

# DB paths
DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
TRANSLATED_COLLECTION = "pre_translated_templates"
RAW_N8N_COLLECTION = "raw_n8n_templates"

# 프로세스 하나에 PersistentClient 하나를 공유한다.
# 예전에는 get_vector_store 가 매 호출마다 Chroma(persist_directory=...) 로 새 PersistentClient 를
# 만들었는데, chromadb 의 시스템 레지스트리(_identifier_to_system)가 스레드 안전하지 않아,
# retrieve_chat_context 가 to_thread 로 동시에 여러 번 불리면 첫 초기화가 경쟁하며
# KeyError/'Could not connect to tenant' 로 터졌다(2026-09-01: AI 생성이 통째로 죽었다).
# 클라이언트를 락으로 한 번만 만들어 재사용하면 그 경쟁이 사라진다 — chromadb 도 PersistentClient
# 를 경로당 하나 재사용하도록 설계돼 있다.
_client_lock = threading.Lock()
_shared_client = None


def _get_client():
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:
                _shared_client = chromadb.PersistentClient(path=DB_DIR)
    return _shared_client


def get_vector_store(collection_name: str, embeddings: Embeddings = None) -> Chroma:
    """Returns a Chroma vector store instance backed by the shared client."""
    if embeddings is None:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    return Chroma(
        client=_get_client(),
        collection_name=collection_name,
        embedding_function=embeddings,
    )

def search_templates(query: str, complexity_level: str, k: int = 2) -> List[Dict[str, Any]]:
    """
    Search for templates based on complexity level.
    - medium: searches pre-translated React Flow templates
    - high: searches raw n8n templates
    """
    if complexity_level == "medium":
        store = get_vector_store(TRANSLATED_COLLECTION)
    elif complexity_level == "high":
        store = get_vector_store(RAW_N8N_COLLECTION)
    else:
        return []

    try:
        results = store.similarity_search(query, k=k)
        return [{"page_content": doc.page_content, "metadata": doc.metadata} for doc in results]
    except Exception as e:
        print(f"Error searching ChromaDB: {e}")
        return []

def process_and_store_chat_context(project_id: str, file_path: str, filename: str) -> int:
    """Extracts text from a file, chunks it, and stores it in the project's RAG context collection."""
    text = ""
    ext = file_path.lower().split(".")[-1]
    
    try:
        if ext == "pdf":
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text() + "\n"
        elif ext in ["doc", "docx"]:
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:
            # Try plain text
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
    except Exception as e:
        print(f"Error extracting text from {filename}: {e}")
        return 0

    if not text.strip():
        return 0

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs = splitter.create_documents([text], metadatas=[{"source": filename}])
    
    store = get_vector_store(f"chat_context_{project_id}")
    store.add_documents(docs)
    return len(docs)

def retrieve_chat_context(project_id: str, query: str, k: int = 4) -> str:
    """Retrieves relevant document chunks for the given project's context collection."""
    try:
        # 벡터 스토어 열기도 try 안에 둔다 — 여기서 실패해도 생성은 컨텍스트 없이 계속돼야 한다.
        # (RAG 컨텍스트는 부가 기능이고, 예전에는 이 줄이 try 밖이라 실패가 생성 전체를 죽였다.)
        store = get_vector_store(f"chat_context_{project_id}")
        # Avoid error if collection is empty
        if store._collection.count() == 0:
            return ""
        
        results = store.similarity_search(query, k=k)
        if not results:
            return ""
            
        context_str = "--- 문서 자료 ---\n"
        for doc in results:
            source = doc.metadata.get("source", "Unknown")
            context_str += f"[{source}]:\n{doc.page_content}\n\n"
        return context_str.strip()
    except Exception as e:
        print(f"Error retrieving context for project {project_id}: {e}")
        return ""


class _CategoryPick(BaseModel):
    category: str = Field(
        description="주어진 카테고리 목록 중 요청과 가장 관련 있는 것 하나. "
                    "애매하거나 딱 맞는 게 없으면 빈 문자열."
    )


class _TemplatePick(BaseModel):
    name: str = Field(
        description="후보 템플릿 중 사용자 요청과 가장 잘 맞는 템플릿의 name. "
                    "확신이 약하면 첫 번째 후보의 name을 반환한다."
    )


_known_categories_cache: Optional[List[str]] = None
_category_examples_cache: Optional[Dict[str, List[str]]] = None


def _get_known_categories() -> List[str]:
    """TRANSLATED_COLLECTION에 실제로 들어있는 category 메타데이터의 distinct 값들.
    scraped_templates/ 폴더명이 아니라 '지금 실제로 검색 가능한' 카테고리만 후보로 삼는다 —
    검증 게이트를 통과 못 해 컬렉션엔 없는 카테고리로 필터를 걸면 매번 폴백만 반복하게 되므로.
    프로세스 생존 기간 동안 한 번만 조회해 캐시한다(DB가 늘어나면 프로세스 재시작 필요)."""
    global _known_categories_cache
    if _known_categories_cache is not None:
        return _known_categories_cache
    try:
        store = get_vector_store(TRANSLATED_COLLECTION)
        raw = store._collection.get(include=["metadatas"])
        metadatas = raw.get("metadatas", []) or []
        cats = sorted({m.get("category") for m in metadatas if m and m.get("category")})
        _known_categories_cache = cats
        return cats
    except Exception as e:
        print(f"Error fetching categories from ChromaDB: {e}")
        _known_categories_cache = []
        return []


def _get_category_examples() -> Dict[str, List[str]]:
    """카테고리 이름 → 그 안에 실제로 들어있는 템플릿 이름들. 카테고리 이름만 보고는 안이 뭔지
    알 수 없어서(예: '사내 정책 문의 챗봇'을 OpenAI_and_LLMs로 잘못 고르는 경우가 실측 확인됨 —
    이름만으로는 HR_and_Recruitment보다 그럴듯해 보임) 분류 프롬프트에 실제 템플릿 이름을 예시로
    보여준다. _get_known_categories()와 마찬가지로 프로세스 생존 기간 캐시."""
    global _category_examples_cache
    if _category_examples_cache is not None:
        return _category_examples_cache
    try:
        store = get_vector_store(TRANSLATED_COLLECTION)
        raw = store._collection.get(include=["metadatas"])
        metadatas = raw.get("metadatas", []) or []
        examples: Dict[str, List[str]] = {}
        for m in metadatas:
            if not m:
                continue
            cat, name = m.get("category"), m.get("name")
            if cat and name:
                examples.setdefault(cat, []).append(name)
        _category_examples_cache = examples
        return examples
    except Exception as e:
        print(f"Error fetching category examples from ChromaDB: {e}")
        _category_examples_cache = {}
        return {}


def _classify_category(query: str) -> Optional[str]:
    """사용자 요청을 실제 존재하는 카테고리 중 하나로 분류. 실패/애매하면 None
    (호출자가 필터 없이 검색하도록)."""
    categories = _get_known_categories()
    if not categories:
        return None
    examples = _get_category_examples()
    from meta_agent import get_llm
    llm = get_llm().with_structured_output(_CategoryPick, method="function_calling")

    def _line(c: str) -> str:
        names = examples.get(c, [])
        if names:
            return f"- {c} (예: {', '.join(names)})"
        return f"- {c}"

    prompt = (
        f"사용자 요청: '{query}'\n\n"
        "아래 카테고리 목록 중 이 요청과 가장 관련 있는 것을 정확히 하나만 골라라. "
        "카테고리 이름만 보지 말고, 괄호 안 예시 템플릿 이름이 실제로 이 요청과 제일 가까운 "
        "카테고리를 우선해라. 애매하거나 딱 맞는 게 없으면 category를 빈 문자열로 반환해라.\n\n"
        "[카테고리 목록]\n" + "\n".join(_line(c) for c in categories)
    )
    try:
        res = llm.invoke([("user", prompt)])
        picked = (res.category or "").strip()
        return picked if picked in categories else None
    except Exception as e:
        print(f"Category classification failed: {e}")
        return None


def _summarize_template_candidate(doc: Document) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(doc.page_content)
    except (json.JSONDecodeError, TypeError):
        return None

    nodes = data.get("nodes", []) or []
    edges = data.get("edges", []) or []
    node_types: List[str] = []
    for n in nodes:
        node_type = n.get("type")
        if node_type and node_type not in node_types:
            node_types.append(node_type)

    return {
        "name": doc.metadata.get("name", ""),
        "category": doc.metadata.get("category", ""),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_types": node_types,
    }


def _rerank_template_candidates(query: str, candidates: List[Dict[str, Any]]) -> Optional[str]:
    if len(candidates) <= 1:
        return candidates[0]["name"] if candidates else None

    from meta_agent import get_llm
    llm = get_llm(complexity_level="medium").with_structured_output(_TemplatePick, method="function_calling")

    prompt_lines = []
    for idx, candidate in enumerate(candidates, start=1):
        prompt_lines.append(
            f"{idx}. name={candidate['name']}\n"
            f"   category={candidate['category']}\n"
            f"   title={candidate['title']}\n"
            f"   description={candidate['description']}\n"
            f"   node_count={candidate['node_count']}, edge_count={candidate['edge_count']}\n"
            f"   node_types={', '.join(candidate['node_types'])}"
        )

    prompt = (
        f"사용자 요청: '{query}'\n\n"
        "아래는 구조가 서로 다른 템플릿 후보들이다. 사용자의 요청을 가장 자연스럽게 구현할 수 있는 "
        "템플릿의 name 하나만 골라라. 요청과 무관한 복잡도를 억지로 높이지 말고, 필요한 구조를 가장 잘 "
        "담고 있는 템플릿을 선택하라.\n\n"
        "[후보 목록]\n" + "\n".join(prompt_lines)
    )

    try:
        result = llm.invoke([("user", prompt)])
        picked_name = (result.name or "").strip()
        if picked_name:
            return picked_name
    except Exception as e:
        print(f"Template reranking failed: {e}")
    return candidates[0]["name"] if candidates else None


MIN_TEMPLATE_RELEVANCE = 0.25

def search_and_parse_template(query: str, k: int = 3) -> Optional[Dict[str, Any]]:
    """Medium 모드 전용: Pre-translated DB에서 가장 유사한 템플릿을 검색해
    FlowGraph JSON dict로 반환.

    검색은 먼저 요청을 카테고리로 분류해 그 카테고리 안에서만 유사도 검색을 하고,
    분류가 안 되거나(None) 그 카테고리 안에 결과가 없으면 필터 없이 전체 재검색한다(폴백).

    k개를 검색해 유사도 순위가 가장 높은 것부터 파싱을 시도하고, 그중 파싱 가능하면서
    관련성 점수가 MIN_TEMPLATE_RELEVANCE 이상인 첫 번째 결과를 선택한다.
    (예전에는 유사도와 무관하게 노드 수가 가장 많은 것을 골랐는데, 이러면 실제로는 관련
    없는 템플릿이라도 노드 수만 많으면 뽑혀버려서 — 예: '간단한 번역'을 검색했는데 무관한
    '이력서 PDF 파싱' 템플릿이 선택되는 식 — 엉뚱한 구조가 그대로 강요되는 버그가 있었다.
    이후 유사도 1위를 그대로 신뢰하도록 고쳤는데, DB에 애초에 맞는 템플릿이 없는 쿼리
    (관련성 점수가 실제 좋은 매칭 대비 훨씬 낮음, 실측상 진짜 매칭은 ~0.3 이상, 무관한
    건 ~0.15~0.18)에서는 그마저도 억지로 무관한 템플릿을 골라버려서, 관련성 최소 기준을
    추가했다 — 기준 미달이면 아예 템플릿을 쓰지 않고 None을 반환해 low 모드로 폴백시킨다.)
    파싱 실패 또는 결과 없음 시 None을 반환 → 호출자가 low 모드(few-shot)로 fallback."""
    store = get_vector_store(TRANSLATED_COLLECTION)
    try:
        category = _classify_category(query)
        results = []
        if category:
            results = store.similarity_search_with_relevance_scores(query, k=k, filter={"category": category})
            if results:
                print(f"[RAG] category filter hit: '{category}' ({len(results)} results)")
            else:
                print(f"[RAG] category filter '{category}' returned no results — falling back to unfiltered search")

        if not results:
            results = store.similarity_search_with_relevance_scores(query, k=k)

        if not results:
            return None

        viable_results = []
        for doc, score in results:
            if score < MIN_TEMPLATE_RELEVANCE:
                print(f"[RAG] best match below relevance threshold ({score:.3f} < {MIN_TEMPLATE_RELEVANCE}) — no template used")
                break
            viable_results.append((doc, score))

        if not viable_results:
            return None

        candidate_summaries = []
        doc_by_name = {}
        for doc, _score in viable_results:
            summary = _summarize_template_candidate(doc)
            if not summary or not summary.get("name"):
                continue
            candidate_summaries.append(summary)
            doc_by_name[summary["name"]] = doc

        if not candidate_summaries:
            return None

        picked_name = _rerank_template_candidates(query, candidate_summaries)
        ordered_docs = []
        if picked_name and picked_name in doc_by_name:
            ordered_docs.append(doc_by_name[picked_name])
        ordered_docs.extend(doc for doc, _score in viable_results if doc not in ordered_docs)

        for doc in ordered_docs:
            try:
                return json.loads(doc.page_content)
            except (json.JSONDecodeError, Exception):
                continue

        return None
    except Exception as e:
        print(f"Error searching Pre-translated DB: {e}")
        return None
