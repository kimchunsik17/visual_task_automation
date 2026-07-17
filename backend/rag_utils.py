import os
from typing import List, Dict, Any, Optional
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

def get_vector_store(collection_name: str, embeddings: Embeddings = None) -> Chroma:
    """Returns a Chroma vector store instance."""
    if embeddings is None:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=DB_DIR
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
    store = get_vector_store(f"chat_context_{project_id}")
    try:
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


def search_and_parse_template(query: str, k: int = 3) -> Optional[Dict[str, Any]]:
    """Medium 모드 전용: Pre-translated DB에서 가장 유사한 템플릿을 검색하고,
    노드 수가 가장 많은(= 비선형 구조일 확률이 높은) 것을 FlowGraph JSON dict로 반환.

    검색은 먼저 요청을 카테고리로 분류해 그 카테고리 안에서만 유사도 검색을 하고,
    분류가 안 되거나(None) 그 카테고리 안에 결과가 없으면 필터 없이 전체 재검색한다(폴백).

    k개를 검색한 뒤 파싱 가능한 것 중 노드 수가 가장 많은 것을 선택한다.
    파싱 실패 또는 결과 없음 시 None을 반환 → 호출자가 low 모드(few-shot)로 fallback."""
    store = get_vector_store(TRANSLATED_COLLECTION)
    try:
        category = _classify_category(query)
        results = []
        if category:
            results = store.similarity_search(query, k=k, filter={"category": category})
            if results:
                print(f"[RAG] category filter hit: '{category}' ({len(results)} results)")
            else:
                print(f"[RAG] category filter '{category}' returned no results — falling back to unfiltered search")

        if not results:
            results = store.similarity_search(query, k=k)

        if not results:
            return None

        best: Optional[Dict[str, Any]] = None
        best_node_count = 0
        for doc in results:
            try:
                parsed = json.loads(doc.page_content)
                node_count = len(parsed.get("nodes", []))
                if node_count > best_node_count:
                    best = parsed
                    best_node_count = node_count
            except (json.JSONDecodeError, Exception):
                continue

        return best
    except Exception as e:
        print(f"Error searching Pre-translated DB: {e}")
        return None
