import os
import glob
import json
import asyncio
from typing import Optional, Tuple
from dotenv import load_dotenv

# Load env before importing meta_agent
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from meta_agent import NODE_CATALOG, FEWSHOT, FlowGraph, get_llm, validate_flow
from rag_utils import get_vector_store, TRANSLATED_COLLECTION
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage
from pydantic import ValidationError

# TODO(중 티어 커버리지/품질 — 2026-07-16 검증 게이트·카테고리 필터링·재시도 추가 후 남은 항목,
# 리스크 알고 지금은 미룸):
#   1) 커버리지 확대: 지금은 limit=10 기본값으로 317개 중 일부만 번역. limit을 올려 대부분을
#      번역/적재할지, 카테고리별로 균등 샘플링할지 정해서 확장할 것. rag_utils._classify_category()가
#      실제로 유효하려면(폴백만 타지 않으려면) 카테고리별로 최소 1개 이상은 있어야 한다.


async def _attempt_translate(chain, content: str) -> Tuple[Optional[FlowGraph], list]:
    """번역 1회 시도. 구조화 출력 실패든 validate_flow 실패든 (None, 실패사유들)로 통일해서 반환한다."""
    try:
        graph = await chain.ainvoke({"template_content": content})
    except Exception as e:
        return None, [f"구조화 출력 실패: {str(e)[:200]}"]
    ok, errs = validate_flow(graph)
    return (graph, []) if ok else (None, errs)


async def _translate_with_retry(chain, content: str) -> Tuple[Optional[FlowGraph], list]:
    """1회 시도 → 실패하면 사유를 프롬프트에 붙여 1회만 재시도(meta_agent.generate_safely와 동일 패턴)."""
    graph, errs = await _attempt_translate(chain, content)
    if graph is not None:
        return graph, []
    retry_content = content + f"\n\n(직전 변환이 아래 이유로 잘못됐다. 고쳐서 다시: {'; '.join(errs)})"
    return await _attempt_translate(chain, retry_content)


async def _process_file(sem: asyncio.Semaphore, chain, file_path: str, scraped_dir: str, idx: int, total: int):
    """파일 하나를 번역(+검증+재시도)까지 끝내고 (doc_json, metadata) 또는 실패 시 None을 반환.
    세마포어로 동시 실행 개수를 제한해 API 레이트리밋을 피한다."""
    async with sem:
        rel_path = os.path.relpath(file_path, scraped_dir)
        category = os.path.dirname(rel_path)
        filename = os.path.basename(rel_path)
        name = os.path.splitext(filename)[0]

        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        try:
            print(f"[{idx+1}/{total}] Translating: {name} (Category: {category})")
        except UnicodeEncodeError:
            print(f"[{idx+1}/{total}] Translating: (name contains emoji) (Category: {category})")

        # Extract only nodes and connections to reduce size
        try:
            raw_json = json.loads(raw_content)
            filtered_data = {
                "nodes": raw_json.get("nodes", []),
                "connections": raw_json.get("connections", {})
            }
            content = json.dumps(filtered_data, ensure_ascii=False)
        except Exception as e:
            print(f"  -> Warning: Invalid JSON ({e}). Falling back to raw content.")
            content = raw_content
            if len(content) > 100000:
                content = content[:100000] + "...(truncated)"

        # 검증 게이트 + 1회 재시도: LLM 구조화 출력이 스키마는 맞아도 순환/고아노드/필수필드
        # 누락 등 실행 불가능한 그래프일 수 있다. Medium 티어는 "사전 검증된 패턴"이 핵심
        # 가치이므로, 챗봇 생성 경로와 동일한 validate_flow()를 통과한 것만 DB에 넣는다.
        translated_graph, errs = await _translate_with_retry(chain, content)

        if translated_graph is None:
            print(f"  -> Failed ({name}, 재시도 후에도 실패): {'; '.join(errs)[:200]}")
            return None

        print(f"  -> Success: {name}")
        return (
            translated_graph.model_dump_json(),
            {"name": name, "category": category, "source": "translated_from_n8n"},
        )


async def translate_and_ingest(limit: int = 10, reset: bool = False, concurrency: int = 5):
    scraped_dir = os.path.join(os.path.dirname(__file__), "scraped_templates")
    if not os.path.exists(scraped_dir):
        print(f"Error: Directory {scraped_dir} not found.")
        return

    json_files = glob.glob(os.path.join(scraped_dir, "**", "*.json"), recursive=True)
    if not json_files:
        print("No .json files found to ingest.")
        return

    # Select representative templates (first `limit` templates, can be shuffled or sorted)
    # Let's take every Nth template to get a diverse mix
    step = max(1, len(json_files) // limit)
    selected_files = json_files[::step][:limit]
    
    print(f"Selected {len(selected_files)} templates for translation out of {len(json_files)}.")

    # Initialize LLM with structured output — get_llm()과 동일한 모델(gpt-4o-mini)을 써서
    # meta_agent.translate_n8n_to_flow(상 티어 실시간 번역)와 일관성을 맞춘다. validate_flow
    # 게이트 + 1회 재시도가 있어 mini의 실수는 DB 오염이 아니라 수율 저하로만 나타난다.
    llm = get_llm().with_structured_output(FlowGraph, method="function_calling")
    
    mapping_guide = """
[n8n 고급 노드 매핑 필수 가이드]
- n8n의 `n8n-nodes-base.switch` 또는 `n8n-nodes-base.if` 노드: 반드시 `conditionNode`로 변환하라.
- n8n의 `n8n-nodes-base.splitInBatches` 또는 반복/루프 노드: 반드시 `distributorNode`나 `loopNode`로 변환하라.
- n8n의 병합/Merge 기능 노드: 반드시 여러 경로를 합치는 `mergeNode`로 변환하라.
- n8n의 Webhook 트리거: `webhookNode`로 변환하라.
- **[매우 중요]** Notion, Qdrant, ElevenLabs, Airtable 등 카탈로그(28종)에 명시되지 않은 외부 서비스 연동 노드는 절대 새로운 노드 이름을 상상해서(Hallucinate) 만들지 말고, 무조건 범용 API 호출 노드인 `httpRequestNode`로 퉁쳐서(대체해서) 변환하라.
- 단순 선형 구조로 뭉뚱그리지 말고 원본의 분기, 병합, 반복 로직을 최대한 살려라.
"""
    system_content = "너는 노코드 템플릿 번역 전문가다. 원본 n8n 템플릿 JSON이 주어지면, 아래 규칙과 스키마에 맞게 우리의 React Flow 기반 노드 데이터로 완벽하게 100% 번역하라.\n\n" + mapping_guide + "\n\n" + NODE_CATALOG + "\n\n[예시 참고]\n" + FEWSHOT
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_content),
        HumanMessagePromptTemplate.from_template("다음 n8n 템플릿 로직을 파악하고 우리의 FlowGraph 형태로 변환해줘:\n\n{template_content}")
    ])
    
    chain = prompt | llm

    print(f"Starting translation process (parallel, max {concurrency} concurrent)...")

    sem = asyncio.Semaphore(concurrency)
    tasks = [
        _process_file(sem, chain, file_path, scraped_dir, i, len(selected_files))
        for i, file_path in enumerate(selected_files)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    docs = []
    metadatas = []
    success_count = 0
    fail_count = 0
    for r in results:
        if isinstance(r, Exception):
            fail_count += 1
            print(f"  -> Failed (unexpected error): {str(r)[:100]}")
        elif r is None:
            fail_count += 1
        else:
            doc, meta = r
            docs.append(doc)
            metadatas.append(meta)
            success_count += 1

    print(f"\nTranslation complete. Success: {success_count}, Failed: {fail_count}")

    if success_count > 0:
        store = get_vector_store(TRANSLATED_COLLECTION)
        if reset:
            try:
                store.delete_collection()
                store = get_vector_store(TRANSLATED_COLLECTION)
                print(f"Cleared existing '{TRANSLATED_COLLECTION}' collection before re-ingesting (미검증 기존 항목 제거).")
            except Exception as e:
                print(f"Warning: failed to clear existing collection: {e}")
        print(f"Ingesting {success_count} templates into ChromaDB ({TRANSLATED_COLLECTION})...")
        store.add_texts(texts=docs, metadatas=metadatas)
        print("Ingestion complete!")
    else:
        print("No templates were successfully translated. Skipping ingestion.")

if __name__ == "__main__":
    import sys
    limit_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    reset_arg = "--reset" in sys.argv
    asyncio.run(translate_and_ingest(limit_arg, reset=reset_arg))
