import asyncio
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

import models
from graph import run_workflow

load_dotenv()
import os
has_langfuse = bool(os.getenv('LANGFUSE_PUBLIC_KEY')) and bool(os.getenv('LANGFUSE_SECRET_KEY'))
if has_langfuse:
    from langfuse.langchain import CallbackHandler
    
# --- Pydantic Models for Structured Output ---

class TestCase(BaseModel):
    input: str = Field(description="The input value to be passed to the workflow (simulating dynamicInputNode).")
    expected_behavior: str = Field(description="A clear description of what the workflow should output or do for this input.")
    evaluation_criteria: str = Field(description="Specific aspects to check in the actual output (e.g. 'Must contain a summary', 'Must output in JSON format').")

class DatasetGenerationResult(BaseModel):
    test_cases: List[TestCase] = Field(description="A list of 3 generated test cases based on the workflow's intent.")

class JudgeScore(BaseModel):
    correctness: int = Field(description="Score 1-10: Does the output meet the expected behavior?")
    completeness: int = Field(description="Score 1-10: Are all required steps and details included?")
    consistency: int = Field(description="Score 1-10: Is the format, tone, and structure appropriate and consistent?")
    error_handling: int = Field(description="Score 1-10: Did it execute without errors or handle invalid inputs well?")
    usefulness: int = Field(description="Score 1-10: Is the final output practically useful for the user?")
    feedback: str = Field(description="Detailed explanation of the scores and what went wrong/right.")

class TestCaseResult(BaseModel):
    test_case: TestCase
    actual_output: str
    error: Optional[str] = None
    scores: Optional[JudgeScore] = None
    total_score: int = 0

class EvaluationReport(BaseModel):
    score: int = Field(description="Overall workflow quality score (0-100).")
    summary: str = Field(description="A brief summary of the workflow's performance across all test cases.")
    suggestions: List[str] = Field(description="Actionable suggestions to improve the workflow design or prompts.")


# --- Evaluator Agents ---

def get_eval_llm(project_id=None):
    # Use gpt-4o-mini for cost-efficiency but decent logic
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    if has_langfuse:
        tags = ["evaluation"]
        handler = CallbackHandler()
        metadata = {}
        if project_id:
            metadata["langfuse_session_id"] = f"project-{project_id}"
        llm = llm.with_config(callbacks=[handler], metadata=metadata, tags=tags)
    return llm

def generate_golden_dataset(title: str, description: str, nodes: list, edges: list, project_id=None) -> List[TestCase]:
    """Generates test cases based on the workflow's structure and description."""
    llm = get_eval_llm(project_id).with_structured_output(DatasetGenerationResult)
    
    # Analyze if there's a dynamic input node to know what to provide
    input_labels = []
    nodes_summary = []
    for node in nodes:
        if node['type'] == 'dynamicInputNode':
            input_labels.append(node.get('data', {}).get('inputLabel', 'Unknown Input'))
            
        summary = {"type": node.get("type")}
        if "data" in node:
            for key in ["systemPrompt", "inputLabel", "apiEndpoint", "instruction", "url"]:
                if key in node["data"] and node["data"][key]:
                    summary[key] = node["data"][key]
        nodes_summary.append(summary)
            
    input_context = f"This workflow accepts dynamic inputs: {', '.join(input_labels)}." if input_labels else "This workflow does not take dynamic inputs. Use 'START' as input to trigger execution."
    nodes_info = json.dumps(nodes_summary, ensure_ascii=False)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert QA Engineer. Your job is to create a 'Golden Dataset' of 3 test cases to evaluate a no-code workflow. Provide diverse test cases including edge cases.\n\nCRITICAL RULE: DO NOT invent business logic, error messages, or constraints that are not explicitly defined in the workflow description or Nodes Info. If the workflow is a simple LLM prompt without strict error handling, the 'expected_behavior' for edge cases should reflect the natural LLM response (e.g., translating numbers just outputs the numbers), NOT a custom error message.\n\nAll text (input, expected_behavior, evaluation_criteria) MUST be written in Korean."),
        ("user", "Workflow Title: {title}\nWorkflow Description: {description}\nNodes Info: {nodes_info}\nEdges: {edges_count}\n\nContext: {input_context}\n\nGenerate the test cases.")
    ])
    
    chain = prompt | llm
    res = chain.invoke({
        "title": title,
        "description": description,
        "nodes_info": nodes_info,
        "edges_count": len(edges),
        "input_context": input_context
    })
    return res.test_cases

def evaluate_test_case(test_case: TestCase, actual_output: str, error: str, project_id=None) -> JudgeScore:
    """Evaluates a single test case result and returns a score breakdown."""
    llm = get_eval_llm(project_id).with_structured_output(JudgeScore)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an AI Judge evaluating a workflow's execution output. Score it across 5 criteria (1-10 each) and provide feedback. The feedback MUST be written in Korean."),
        ("user", "Expected Behavior: {expected}\nEvaluation Criteria: {criteria}\n\nActual Output:\n{output}\n\nError (if any):\n{error}\n\nEvaluate now.")
    ])
    
    chain = prompt | llm
    res = chain.invoke({
        "expected": test_case.expected_behavior,
        "criteria": test_case.evaluation_criteria,
        "output": actual_output or "No output",
        "error": error or "None"
    })
    return res

def summarize_evaluation(test_results: List[TestCaseResult], project_id=None) -> dict:
    """Creates a final summary and score from all test case results."""
    llm = get_eval_llm(project_id).with_structured_output(EvaluationReport)
    
    total_score = sum(r.total_score for r in test_results)
    max_possible = len(test_results) * 50
    normalized_score = int((total_score / max_possible) * 100) if max_possible > 0 else 0
    
    results_dump = []
    for i, r in enumerate(test_results):
        results_dump.append(f"Test {i+1}:\nExpected: {r.test_case.expected_behavior}\nActual: {r.actual_output}\nScore: {r.total_score}/50\nFeedback: {r.scores.feedback if r.scores else 'N/A'}\n")
        
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are the Master Evaluator. Review the test results of a workflow and provide a final summary and actionable suggestions to improve it. DO NOT hallucinate. The overall score is already calculated. The output (summary and suggestions) MUST be written in Korean."),
        ("user", "Overall Score: {score}/100\n\nDetailed Results:\n{results}\n\nProvide the summary and suggestions.")
    ])
    
    chain = prompt | llm
    res = chain.invoke({
        "score": normalized_score,
        "results": "\n".join(results_dump)
    })
    
    # Format the final report as a dict
    report_dict = res.dict() if hasattr(res, 'dict') else res.model_dump()
    report_dict['score'] = normalized_score
    report_dict['test_results'] = [
        {
            "input": r.test_case.input,
            "expected": r.test_case.expected_behavior,
            "actual": r.actual_output,
            "error": r.error,
            "score": r.total_score,
            "feedback": r.scores.feedback if r.scores else "Failed to score"
        }
        for r in test_results
    ]
    return report_dict

async def run_evaluation_pipeline(project_id: int, title: str, description: str, nodes: list, edges: list, db, yield_status=None):
    """
    Runs the entire evaluation pipeline:
    1. Generate 3 golden test cases
    2. Run the actual workflow with the test case inputs
    3. Evaluate each output using the Judge LLM
    4. Track token usage and save to DB
    """
    # OpenAI 토큰 추적을 위한 컨텍스트 매니저 사용
    try:
        from langchain_community.callbacks import get_openai_callback
        use_cb = True
    except ImportError:
        use_cb = False

    if yield_status: yield_status("생성 중...")

    eval_token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def _run_pipeline():
        try:
            test_cases = generate_golden_dataset(title, description, nodes, edges, project_id)
        except Exception as e:
            print(f"Failed to generate dataset: {e}")
            return {"error": "Failed to generate dataset"}

        results = []
        for i, tc in enumerate(test_cases):
            if yield_status: yield_status(f"실행 중... ({i+1}/3)")
            inputs = {"default_input": tc.input}
            try:
                result_text, tokens, logs = run_workflow(nodes, edges, db=db, **inputs)
                error_msg = None
                if "► Flow 1 Error:" in result_text or "Dynamic Execution Error:" in result_text or "Execution failed:" in result_text:
                    error_msg = result_text
            except Exception as e:
                result_text = ""
                error_msg = str(e)

            if yield_status: yield_status(f"평가 중... ({i+1}/3)")
            try:
                score = evaluate_test_case(tc, result_text, error_msg, project_id)
                total = sum([score.correctness, score.completeness, score.consistency, score.error_handling, score.usefulness])
            except Exception as e:
                print(f"Evaluation failed: {e}")
                score = None
                total = 0

            tcr = TestCaseResult(
                test_case=tc,
                actual_output=result_text,
                error=error_msg,
                scores=score,
                total_score=total
            )
            results.append(tcr)

        return summarize_evaluation(results)

    # 토큰 추적 래퍼
    if use_cb:
        import asyncio
        from langchain_community.callbacks import get_openai_callback
        with get_openai_callback() as cb:
            report = await _run_pipeline()
        eval_token_usage = {
            "input_tokens": cb.prompt_tokens,
            "output_tokens": cb.completion_tokens,
            "total_tokens": cb.total_tokens,
        }
    else:
        report = await _run_pipeline()

    if isinstance(report, dict) and "error" not in report:
        # 평가 토큰을 FlowExecutionLog에 저장
        try:
            import json as _json
            db_log = models.FlowExecutionLog(
                project_id=project_id,
                payload="Evaluation Pipeline",
                result=f"Score: {report.get('score', 0)}/100",
                total_tokens=eval_token_usage["total_tokens"],
                token_usage_details=eval_token_usage,
                status="evaluation",
            )
            db.add(db_log)
            db.commit()
        except Exception as e:
            print(f"Failed to save evaluation token log: {e}")
            db.rollback()

        # token_usage를 report에 포함
        report["token_usage"] = eval_token_usage

    return report
