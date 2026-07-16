import requests
import json
from pydantic import BaseModel, Field
from meta_agent import get_llm

class KeywordResponse(BaseModel):
    keyword: str = Field(description="A concise English search keyword (1-3 words) to find related templates.")

def extract_search_keyword(user_request: str) -> str:
    """사용자 요청에서 n8n API 검색을 위한 짧은 영문 키워드를 추출합니다."""
    llm = get_llm().with_structured_output(KeywordResponse, method="function_calling")
    prompt = (
        f"User request: '{user_request}'\n"
        "Provide a very short English search keyword (1-3 words, e.g. 'email automation', 'hiring', 'slack bot') "
        "to search for a relevant workflow template in the n8n template gallery."
    )
    try:
        res = llm.invoke([("user", prompt)])
        return res.keyword
    except Exception as e:
        print(f"Keyword extraction failed: {e}")
        return "automation"

def search_best_n8n_template(keyword: str) -> dict:
    """n8n API를 검색하여 비선형(분기/반복) 구조를 가진 복잡한 템플릿을 찾아 반환합니다."""
    url = f"https://api.n8n.io/api/templates/search?search={requests.utils.quote(keyword)}&rows=5"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        workflows = data.get("workflows", [])
        if not workflows:
            return None
            
        best_wf = None
        best_score = -1
        
        for wf in workflows:
            score = 0
            nodes = wf.get("nodes", [])
            
            # 1. 노드 수 기반 점수 (15개까지는 노드당 2점)
            node_count = len(nodes)
            score += min(node_count, 15) * 2 
            
            # 2. 비선형 구조 가점
            types = [n.get("name", "") for n in nodes]
            if any("switch" in t.lower() or "if" in t.lower() for t in types):
                score += 15 # 조건 분기 가점
            if any("splitinbatches" in t.lower() or "loop" in t.lower() for t in types):
                score += 15 # 반복(Loop) 가점
            if any("merge" in t.lower() for t in types):
                score += 10 # 병합(Merge) 가점
                
            if score > best_score:
                best_score = score
                best_wf = wf
                
        return best_wf
    except Exception as e:
        print(f"n8n template search failed: {e}")
        return None

def get_n8n_workflow_json(template_id: int) -> str:
    """선택된 템플릿의 전체 워크플로우 JSON(nodes + connections)을 가져옵니다."""
    url = f"https://api.n8n.io/api/templates/workflows/{template_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        # 전체 JSON을 넘기면 토큰이 낭비되므로 nodes와 connections만 추출
        filtered_data = {
            "nodes": data.get("nodes", []),
            "connections": data.get("connections", {})
        }
        return json.dumps(filtered_data, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to fetch n8n workflow {template_id}: {e}")
        return None
