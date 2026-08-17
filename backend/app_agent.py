import os
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

class UIComponent(BaseModel):
    id: str
    type: str = Field(description="Valid types: container, text, input, button, textarea, dropdown, checkbox, divider, image")
    props: dict
    children: Optional[List['UIComponent']] = None

class LogicNodeData(BaseModel):
    label: str
    componentId: Optional[str] = None
    eventType: Optional[str] = None
    actionType: Optional[str] = None
    propertyType: Optional[str] = None
    projectId: Optional[str] = None

class LogicNode(BaseModel):
    id: str
    type: str = Field(description="Valid types: triggerNode, valueNode, actionNode, workflowNode")
    position: dict = Field(default_factory=lambda: {"x": 0, "y": 0})
    data: LogicNodeData

class LogicEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None

class AppGeneratorResult(BaseModel):
    reply: str = Field(description="User-facing reply explaining what was created or modified.")
    new_title: str = Field(description="A concise title for the app.")
    requires_backend_workflow: bool = Field(description="True if the app needs to save data, send emails, scrape, or call external APIs.")
    backend_workflow_prompt: str = Field(default="", description="If requires_backend_workflow is True, provide a clear prompt for meta_agent to generate the backend workflow (e.g. '이름과 이메일을 입력받아 DB에 저장해줘').")
    ui_components: List[UIComponent] = Field(description="Hierarchical list of UI components.")
    root_style: dict = Field(description="CSS styles for the root canvas/page.")
    global_css: str = Field(default="", description="Custom CSS string.")
    logic_nodes: List[LogicNode] = Field(description="Blueprint logic nodes (triggerNode, valueNode, actionNode, workflowNode).")
    logic_edges: List[LogicEdge] = Field(description="Edges connecting the logic nodes.")
    workflow_mappings: dict = Field(default_factory=dict, description="If a workflow is needed, map a button's component ID to 'NEW_WORKFLOW_ID'.")

SYSTEM_PROMPT = """\
당신은 최고의 AI 앱 빌더입니다. 사용자의 요청(자연어)과 현재 앱 상태를 분석하여 앱의 UI와 클라이언트 로직을 생성합니다.

[역할]
1. UI 컴포넌트(components) 구성
2. 컴포넌트 간의 상호작용 로직(logic_nodes, logic_edges) 구성
3. 앱이 데이터를 저장하거나 백엔드 통신이 필요한지 파악 (requires_backend_workflow)

[UI 구조 제약]
지원하는 컴포넌트 타입: container, text, input, button, textarea, dropdown, checkbox, divider, image
각 컴포넌트는 id, type, props, children 필드를 가집니다.

[로직 노드 제약]
- triggerNode: 이벤트(예: onClick) 시작점
- workflowNode: 백엔드 워크플로우를 호출하는 노드. data.projectId를 'NEW_WORKFLOW_ID'로 설정.
- valueNode: 입력창 등에서 값을 가져올 때 사용 (propertyType: 'value')
- actionNode: 화면을 변경하거나 알림을 띄움

[백엔드 워크플로우 처리 규칙]
요청이 "DB 저장", "이메일 전송", "검색" 등을 요구하면 requires_backend_workflow=true로 설정하고, 
backend_workflow_prompt에 챗봇(meta_agent)이 워크플로우를 생성할 수 있도록 명확한 자연어 명령을 작성하세요.
그리고 workflow_mappings에 {"버튼ID": "NEW_WORKFLOW_ID"} 형태로 매핑 정보를 기록하세요.
"""

def get_llm(provider: str = "openai", complexity_level: str = "medium"):
    if provider == "gemini":
        model_name = "gemini-1.5-pro" if complexity_level == "high" else "gemini-1.5-flash"
        return ChatGoogleGenerativeAI(model=model_name, temperature=0.1).with_structured_output(AppGeneratorResult)
    else:
        model_name = "gpt-4o" if complexity_level == "high" else "gpt-4o-mini"
        return ChatOpenAI(model=model_name, temperature=0.1).with_structured_output(AppGeneratorResult)

async def generate_app(prompt: str, current_state: dict = None, provider: str = "openai", complexity_level: str = "medium") -> AppGeneratorResult:
    if current_state is None:
        current_state = {}
    llm = get_llm(provider=provider, complexity_level=complexity_level)
    
    chat_prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "Current State:\n{current_state}\n\nUser Request: {prompt}")
    ])
    
    chain = chat_prompt | llm
    
    state_str = json.dumps(current_state, ensure_ascii=False, indent=2)
    response = await chain.ainvoke({"current_state": state_str, "prompt": prompt})
    
    return response
