import time
import uuid
import json
from meta_agent import run_agent_turn

# 평가용 하드코딩 테스트 케이스
# 각 테스트 케이스는 프롬프트와 에이전트가 반드시 생성해야 하는 핵심 노드 타입을 지정합니다.
TEST_CASES = [
    {
        "id": 1,
        "category": "Basic",
        "prompt": "매일 아침 9시에 서울 날씨 정보를 가져와서 슬랙으로 보내줘.",
        "expected_nodes": ["scheduleNode", "llmNode", "slackNode"]
    },
    {
        "id": 2,
        "category": "E-commerce",
        "prompt": "네이버 스마트스토어에 새 주문이 들어오면 고객에게 카카오톡 알림톡을 보내고 디스코드로 관리자에게 알려줘.",
        "expected_nodes": ["webhookNode", "kakaoNode", "discordNode"]
    },
    {
        "id": 3,
        "category": "Data Processing",
        "prompt": "이메일로 온 첨부파일 내용을 파이썬 스크립트로 전처리한 다음 데이터베이스에 저장해.",
        "expected_nodes": ["emailNode", "pythonNode"]
    },
    {
        "id": 4,
        "category": "Payments",
        "prompt": "토스 결제 링크를 생성해서 카카오톡으로 발송해줘.",
        "expected_nodes": ["paymentLinkNode", "kakaoNode"]
    },
    {
        "id": 5,
        "category": "Condition",
        "prompt": "만약 리뷰 점수가 3점 미만이면 디스코드로 경고를 보내고, 아니면 이메일로 감사 인사를 보내줘.",
        "expected_nodes": ["conditionNode", "discordNode", "emailNode"]
    }
]

def get_test_cases():
    return TEST_CASES

def run_evaluation_suite(selected_ids=None):
    """
    Generator function to run tests and yield progress and results as JSON strings.
    Suitable for Server-Sent Events (SSE).
    """
    tests_to_run = TEST_CASES
    if selected_ids is not None:
        tests_to_run = [t for t in TEST_CASES if str(t["id"]) in selected_ids]
        
    total_tests = len(tests_to_run)
    if total_tests == 0:
        yield json.dumps({"type": "complete", "summary": None, "results": []}) + "\n"
        return

    yield json.dumps({"type": "start", "total": total_tests}) + "\n"
    
    total_score = 0
    total_latency = 0
    results = []
    
    for idx, test in enumerate(tests_to_run):
        start_time = time.time()
        
        # 임의의 thread_id로 격리된 환경에서 에이전트 실행
        thread_id = f"eval_{uuid.uuid4().hex}"
        empty_graph = {"nodes": [], "edges": []}
        
        try:
            # 에이전트 실행
            reply, new_graph = run_agent_turn(empty_graph, test["prompt"], thread_id=thread_id)
            
            latency = time.time() - start_time
            generated_node_types = [n.get("type") for n in new_graph.get("nodes", [])]
            
            # 예상된 노드들이 전부 포함되었는지 확인
            missing_nodes = [nt for nt in test["expected_nodes"] if not any(nt.lower() in gn.lower() for gn in generated_node_types)]
            passed = len(missing_nodes) == 0
            
            # 점수 부여 (간단히 Pass면 100점, Fail이면 비율)
            if passed:
                score = 100
            else:
                expected_len = len(test["expected_nodes"])
                score = int(((expected_len - len(missing_nodes)) / expected_len) * 100)
            
            result_obj = {
                "id": test["id"],
                "category": test["category"],
                "prompt": test["prompt"],
                "passed": passed,
                "score": score,
                "latency_sec": round(latency, 2),
                "generated_nodes": generated_node_types,
                "missing_nodes": missing_nodes,
                "reply": reply
            }
            
            total_score += score
            total_latency += latency
            results.append(result_obj)
            
            # SSE로 진행 상황 전송
            yield json.dumps({"type": "progress", "current": idx + 1, "total": total_tests, "result": result_obj}) + "\n"
            
        except Exception as e:
            latency = time.time() - start_time
            result_obj = {
                "id": test["id"],
                "category": test["category"],
                "prompt": test["prompt"],
                "passed": False,
                "score": 0,
                "latency_sec": round(latency, 2),
                "generated_nodes": [],
                "missing_nodes": test["expected_nodes"],
                "error": str(e)
            }
            results.append(result_obj)
            yield json.dumps({"type": "progress", "current": idx + 1, "total": total_tests, "result": result_obj}) + "\n"
    
    # 최종 통계 계산
    avg_score = round(total_score / total_tests, 1)
    avg_latency = round(total_latency / total_tests, 2)
    pass_count = sum(1 for r in results if r["passed"])
    
    summary = {
        "total_tests": total_tests,
        "pass_count": pass_count,
        "fail_count": total_tests - pass_count,
        "average_score": avg_score,
        "average_latency_sec": avg_latency
    }
    
    yield json.dumps({"type": "complete", "summary": summary, "results": results}) + "\n"
