import os
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, PrivateAttr, model_validator
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
    global_js: str = Field(default="", description="Global Javascript code defining handlers.")
    logic_nodes: List[LogicNode] = Field(description="Blueprint logic nodes (triggerNode, valueNode, actionNode, workflowNode).")
    logic_edges: List[LogicEdge] = Field(description="Edges connecting the logic nodes.")
    workflow_mappings: dict = Field(default_factory=dict, description="If a workflow is needed, map a button's component ID to 'NEW_WORKFLOW_ID'.")
    _token_usage: dict = PrivateAttr(default_factory=dict)

    @property
    def token_usage(self) -> dict:
        return self._token_usage

    @token_usage.setter
    def token_usage(self, value: dict) -> None:
        self._token_usage = value or {}

    @model_validator(mode='before')
    @classmethod
    def coerce_empty_dict_to_list(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if isinstance(data.get('logic_nodes'), dict) and not data['logic_nodes']:
                data['logic_nodes'] = []
            if isinstance(data.get('logic_edges'), dict) and not data['logic_edges']:
                data['logic_edges'] = []
        return data

def _usage_from_message(message: Any) -> dict:
    usage = getattr(message, "usage_metadata", None) or {}
    if not usage:
        metadata = getattr(message, "response_metadata", None) or {}
        usage = metadata.get("token_usage") or metadata.get("usage") or {}
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }

def _merge_token_usage(*usages: dict) -> dict:
    return {
        key: sum(int((usage or {}).get(key, 0) or 0) for usage in usages)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }

SYSTEM_PROMPT = """\
당신은 최고의 AI 앱 빌더입니다. 사용자의 요청(자연어)과 현재 앱 상태를 분석하여 앱의 UI와 클라이언트 로직을 생성합니다.

[역할]
1. UI 컴포넌트(components) 구성
2. 컴포넌트 간의 상호작용 로직(logic_nodes, logic_edges) 구성
3. 앱이 데이터를 저장하거나 백엔드 통신이 필요한지 파악 (requires_backend_workflow)

[UI 구조 제약]
지원하는 컴포넌트 타입: container, text, input, button, textarea, dropdown, checkbox, divider, image
각 컴포넌트는 id, type, props 필드를 가지며 container만 children을 가질 수 있습니다.
Current State의 page_settings와 ui_graph_data.canvas에 있는 실제 캔버스 너비, 높이, 자동 높이 및 rootStyle을 페이지 제약으로 사용하세요.
사용자가 페이지 설정 변경을 명시하지 않았다면 현재 캔버스와 rootStyle을 유지하고, 모든 최상위 컴포넌트를 현재 캔버스 안에 배치하세요.
최상위 컴포넌트의 props.position은 {{"x": 숫자, "y": 숫자}} 형식으로 지정하세요.
container 내부 children의 position은 container 기준 로컬 좌표입니다.
container는 props.layoutMode를 absolute, row, column, grid 중 하나로 지정하세요. 편집 가능한 자유 배치를 기본으로 absolute를 사용하고, 사용자가 반응형 흐름 배치를 요구한 경우에만 row, column, grid를 사용하세요.
props.style에 픽셀 단위 width와 height를 반드시 명시하고 컴포넌트끼리 겹치거나 캔버스 밖으로 나가지 않게 하세요.
terminal은 앱 UI 컴포넌트가 아니라 App Builder의 별도 실행 로그 패널이므로 절대 생성하지 마세요. 실행 결과는 text 또는 읽기 전용 textarea로 표시하세요.

[로직 노드 제약]
- triggerNode: 이벤트(예: onClick) 시작점
- workflowNode: 백엔드 워크플로우를 호출하는 노드. data.projectId를 'NEW_WORKFLOW_ID'로 설정.
- valueNode: 입력창 등에서 값을 가져올 때 사용 (propertyType: 'value')
- actionNode: 화면을 변경하거나 알림을 띄움

[로직 연결(Edge) 필수 제약]
logic_edges 생성 시 노드 간 연결 부위(Handle)를 반드시 명시해야 합니다. (sourceHandle, targetHandle)
- triggerNode: 나가는 흐름은 sourceHandle="trigger"
- valueNode: 나가는 데이터는 sourceHandle="dataOut"
- actionNode: 들어오는 흐름은 targetHandle="triggerIn", 들어오는 데이터는 targetHandle="dataIn". 나가는 흐름은 sourceHandle="triggerOut"
- workflowNode: 들어오는 흐름은 targetHandle="triggerIn", 들어오는 데이터는 targetHandle="payloadIn". 나가는 흐름/데이터는 "triggerOut"/"dataOut"

[백엔드 워크플로우 처리 규칙]
요청이 "DB 저장", "이메일 전송", "검색" 등을 요구하면 requires_backend_workflow=true로 설정하고, 
backend_workflow_prompt에 챗봇(meta_agent)이 워크플로우를 생성할 수 있도록 명확한 자연어 명령을 작성하세요.
그리고 workflow_mappings에 {{"버튼ID": "NEW_WORKFLOW_ID"}} 형태로 매핑 정보를 기록하세요.

반드시 JSON 형태로 응답하세요.
"""

SYSTEM_PROMPT_CODE = """\
당신은 최고의 AI 앱 빌더(Code-Native)입니다. 사용자의 요청을 분석하여 UI와 **JavaScript 기반 클라이언트 로직**을 직접 생성합니다.
복잡한 Blueprint 노드(logic_nodes, logic_edges)는 완전히 무시하고 비워둡니다([]).

[역할]
1. UI 컴포넌트(components) 구성
2. 'global_js' 필드에 이벤트 핸들러 코드들을 정의하는 단일 자바스크립트 객체를 반환하도록 작성.
3. 컴포넌트의 props 내에 이벤트 핸들러(onClickHandler, onChangeHandler 등)를 'global_js'에 정의한 함수 이름 문자열로 연결. onClickCode 나 onChangeCode는 더 이상 사용하지 않습니다.
4. 백엔드 통신이 필요한지 파악 (requires_backend_workflow)

[UI 구조 제약]
지원하는 컴포넌트 타입: container, text, input, button, textarea, dropdown, checkbox, divider, image
각 컴포넌트는 id, type, props 필드를 가지며 container만 children을 가질 수 있습니다.
Current State의 page_settings와 ui_graph_data.canvas에 있는 실제 캔버스 너비, 높이, 자동 높이 및 rootStyle을 페이지 제약으로 사용하세요.
사용자가 페이지 설정 변경을 명시하지 않았다면 현재 캔버스와 rootStyle을 유지하고, 모든 최상위 컴포넌트를 현재 캔버스 안에 배치하세요.
최상위 컴포넌트의 props.position은 {{"x": 숫자, "y": 숫자}} 형식으로 지정하세요.
container 내부 children의 position은 container 기준 로컬 좌표입니다.
container는 props.layoutMode를 absolute, row, column, grid 중 하나로 지정하세요. 편집 가능한 자유 배치를 기본으로 absolute를 사용하고, 사용자가 반응형 흐름 배치를 요구한 경우에만 row, column, grid를 사용하세요.
props.style에 픽셀 단위 width와 height를 반드시 명시하고 컴포넌트끼리 겹치거나 캔버스 밖으로 나가지 않게 하세요.
terminal은 앱 UI 컴포넌트가 아니라 App Builder의 별도 실행 로그 패널이므로 절대 생성하지 마세요. 실행 결과는 text 또는 읽기 전용 textarea로 표시하세요.

[JavaScript 코드 생성 규칙 (매우 중요)]
- 모든 로직은 반드시 `global_js` 필드에 작성합니다.
- 'global_js' 필드는 단 하나의 익명 객체를 반환(`return {{ ... }};`)해야 합니다.
- **매우 중요 (상태 저장)**: 타이머나 지속적인 변수가 필요하다면, **절대로 화살표 함수 내에서 `this.timer`처럼 사용하지 마세요.** 반드시 `return {{ ... }};` 바깥(위)에 `let timer = null; let count = 0;` 처럼 클로저 변수를 선언하고 이를 참조하세요.
- 각 함수(onClickHandler, onChangeHandler) 내부에서 외부 통신이 필요한 경우 `runWorkflow(projectId, inputs)`를 호출합니다.
- 상태 업데이트가 필요한 경우 `setAppState(compId, propertyKey, value)`를 사용합니다.
- `appState[compId]?.[propertyKey]` 를 통해 다른 컴포넌트의 상태를 읽을 수 있습니다.
- `inputs[inputKey]` 를 통해 input 컴포넌트들의 값을 읽을 수 있습니다.
- `runWorkflow(projectId, payload)`: 백엔드 워크플로우 비동기 실행 함수. **주의: 반환값은 객체가 아니라 단순 텍스트 문자열(String)입니다.** (예: `const resultText = await runWorkflow(...)`)
- 실행 결과를 표시하려면 text 컴포넌트를 만들고 `setAppState('결과컴포넌트ID', 'text', '출력할 내용')` 을 사용하세요.

예시 (global_js 작성법):
"let count = 0;
return {{
  onSaveClick: async () => {{
    const resultText = await runWorkflow('NEW_WORKFLOW_ID', {{ name: inputs['nameInput'] }});
    setAppState('statusText', 'text', resultText);
  }},
  onNameChange: (val) => {{
    console.log(val);
  }}
}};"

예시 (UI 컴포넌트 props 연결):
버튼의 props: {{"text": "저장", "onClickHandler": "onSaveClick"}}
입력창의 props: {{"placeholder": "이름", "onChangeHandler": "onNameChange"}}

[백엔드 워크플로우 처리 규칙]
요청이 "DB 저장", "검색" 등을 요구하면 requires_backend_workflow=true로 설정하고, 
backend_workflow_prompt에 워크플로우 생성 프롬프트를 작성하세요.
실행은 global_js 내부에서 `runWorkflow('NEW_WORKFLOW_ID', {{ ... }})` 형태로 호출하세요. 
workflow_mappings는 {{"버튼ID": "NEW_WORKFLOW_ID"}} 로 지정합니다.

반드시 JSON 형태로 응답하세요.
"""

def get_llm(provider: str = "openai", complexity_level: str = "low"):
    if provider == "gemini":
        model_name = "gemini-1.5-pro" if complexity_level == "high" else "gemini-1.5-flash"
        return ChatGoogleGenerativeAI(model=model_name, temperature=0.1).with_structured_output(AppGeneratorResult)
    else:
        if complexity_level == "low":
            model_name = "gpt-5.4-mini"
        elif complexity_level == "high":
            model_name = "gpt-5.6-sol"
        else:
            model_name = "gpt-5.6-terra"

        kwargs = {}
        if "gpt-5" not in model_name:
            kwargs["temperature"] = 0.1
        else:
            kwargs["model_kwargs"] = {"reasoning_effort": "none"}

        return ChatOpenAI(model=model_name, **kwargs).bind(response_format={"type": "json_object"})

async def generate_app(prompt: str, current_state: dict = None, provider: str = "openai", complexity_level: str = "low", generate_mode: str = "code") -> AppGeneratorResult:
    if current_state is None:
        current_state = {}
    llm = get_llm(provider=provider, complexity_level=complexity_level)
    
    sys_prompt = SYSTEM_PROMPT_CODE if generate_mode == "code" else SYSTEM_PROMPT
    current_ui = current_state.get("ui_graph_data") or {}
    page_context = current_state.get("page_settings") or {
        "canvas": current_ui.get("canvas") or {"width": 1024, "height": 768, "autoHeight": True},
        "rootStyle": current_ui.get("rootStyle") or {},
    }
    
    if provider == "gemini":
        chat_prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human", "Current Page Settings (must be respected):\n{page_context}\n\nCurrent State:\n{current_state}\n\nUser Request: {prompt}")
        ])
        chain = chat_prompt | llm
        state_str = json.dumps(current_state, ensure_ascii=False, indent=2)
        response = await chain.ainvoke({
            "page_context": json.dumps(page_context, ensure_ascii=False, indent=2),
            "current_state": state_str,
            "prompt": prompt,
        })
        response.token_usage = _usage_from_message(response)
        return response
    else:
        from langchain_core.output_parsers import PydanticOutputParser
        parser = PydanticOutputParser(pydantic_object=AppGeneratorResult)
        
        chat_prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt + "\n\n{format_instructions}"),
            ("human", "Current Page Settings (must be respected):\n{page_context}\n\nCurrent State:\n{current_state}\n\nUser Request: {prompt}")
        ])
        chain = chat_prompt | llm
        state_str = json.dumps(current_state, ensure_ascii=False, indent=2)
        raw_response = await chain.ainvoke({
            "page_context": json.dumps(page_context, ensure_ascii=False, indent=2),
            "current_state": state_str, 
            "prompt": prompt,
            "format_instructions": parser.get_format_instructions()
        })
        response = parser.invoke(raw_response)
        response.token_usage = _usage_from_message(raw_response)
        return response

def validate_app(app_data: AppGeneratorResult, generate_mode: str = "code") -> tuple[bool, List[str]]:
    errors = []
    
    # 1. Collect all component IDs
    valid_component_ids = set()
    def collect_ids(components: List[UIComponent]):
        for c in components:
            if c.id in valid_component_ids:
                errors.append(f"중복된 컴포넌트 ID가 있습니다: {c.id}")
            valid_component_ids.add(c.id)
            if c.children:
                collect_ids(c.children)
    
    collect_ids(app_data.ui_components)
    
    if generate_mode == "code":
        return (len(errors) == 0, errors)
    
    # 2. Check Logic Nodes
    valid_logic_node_ids = set()
    for ln in app_data.logic_nodes:
        if ln.id in valid_logic_node_ids:
            errors.append(f"중복된 로직 노드 ID가 있습니다: {ln.id}")
        valid_logic_node_ids.add(ln.id)
        
        # componentId check
        if ln.data.componentId and ln.data.componentId not in valid_component_ids:
            errors.append(f"로직 노드 '{ln.id}'가 존재하지 않는 컴포넌트 ID '{ln.data.componentId}'를 참조합니다.")
            
        # workflowNode check
        if ln.type == "workflowNode":
            if not ln.data.projectId:
                errors.append(f"workflowNode '{ln.id}'에 projectId가 없습니다.")
            elif ln.data.projectId != "NEW_WORKFLOW_ID" and ln.data.projectId not in app_data.workflow_mappings.values():
                errors.append(f"workflowNode '{ln.id}'의 projectId '{ln.data.projectId}'가 매핑에 없거나 'NEW_WORKFLOW_ID'가 아닙니다.")
                
    # 3. Check Logic Edges
    for edge in app_data.logic_edges:
        if edge.source not in valid_logic_node_ids:
            errors.append(f"엣지 '{edge.id}'의 source '{edge.source}'가 존재하지 않습니다.")
        if edge.target not in valid_logic_node_ids:
            errors.append(f"엣지 '{edge.id}'의 target '{edge.target}'가 존재하지 않습니다.")
        is_control_edge = edge.sourceHandle in {"trigger", "triggerOut"} and edge.targetHandle == "triggerIn"
        is_data_edge = edge.sourceHandle == "dataOut" and edge.targetHandle in {"dataIn", "payloadIn"}
        if not is_control_edge and not is_data_edge:
            errors.append(
                f"엣지 '{edge.id}'의 핸들 연결이 올바르지 않습니다: "
                f"{edge.sourceHandle} -> {edge.targetHandle}"
            )
            
    # 4. Check workflow mappings
    for comp_id, workflow_id in app_data.workflow_mappings.items():
        if comp_id not in valid_component_ids:
            errors.append(f"workflow_mappings에 지정된 컴포넌트 ID '{comp_id}'가 UI 컴포넌트 트리에 존재하지 않습니다.")
            
    return (len(errors) == 0, errors)

def normalize_generated_components(components: List[UIComponent]) -> None:
    for component in components:
        if component.type == "terminal":
            component.type = "text"
            component.props = component.props or {}
            component.props.setdefault("text", "실행 결과가 여기에 표시됩니다.")
            component.props.pop("logs", None)
        if component.children:
            normalize_generated_components(component.children)

async def generate_app_safely(prompt: str, current_state: dict = None, provider: str = "openai", complexity_level: str = "low", max_retries: int = 1, generate_mode: str = "code") -> AppGeneratorResult:
    app_data = await generate_app(prompt, current_state, provider, complexity_level, generate_mode)
    total_usage = dict(app_data.token_usage or {})
    normalize_generated_components(app_data.ui_components)
    ok, errs = validate_app(app_data, generate_mode)
    
    retries = 0
    while not ok and retries < max_retries:
        print(f"App validation failed. Retrying ({retries+1}/{max_retries}). Errors: {errs}")
        retries += 1
        retry_prompt = f"{prompt}\n\n(직전 생성이 아래 이유로 잘못됐다. 고쳐서 다시 생성해라: {'; '.join(errs)})"
        app_data = await generate_app(retry_prompt, current_state, provider, complexity_level, generate_mode)
        total_usage = _merge_token_usage(total_usage, app_data.token_usage)
        normalize_generated_components(app_data.ui_components)
        ok, errs = validate_app(app_data, generate_mode)
        
    if not ok:
        print(f"Warning: App validation failed even after retries: {errs}")
        # 실패하더라도 에디터에서 사용자가 고칠 수 있도록 최선을 다한 결과를 반환
    
    if generate_mode == "code":
        app_data.logic_nodes = []
        app_data.logic_edges = []

    app_data.token_usage = _merge_token_usage(total_usage)
    return auto_layout_app(app_data)

def auto_layout_app(app_data: AppGeneratorResult) -> AppGeneratorResult:
    # 1. UI Components Auto Layout (prevent overlapping at 0,0)
    def layout_ui(components: List[UIComponent], start_x: int = 20, start_y: int = 20):
        current_y = start_y
        for c in components:
            if "position" not in c.props or (c.props["position"].get("x") == 0 and c.props["position"].get("y") == 0):
                c.props["position"] = {"x": start_x, "y": current_y}
                current_y += 80 # Default spacing
            else:
                current_y = max(current_y, c.props["position"].get("y", 0) + 80)
            
            if c.children:
                layout_ui(c.children, 20, 20)
                
    layout_ui(app_data.ui_components)

    # 2. Logic Nodes Auto Layout (Topological sort)
    from collections import defaultdict, deque
    ids = [n.id for n in app_data.logic_nodes]
    adj = defaultdict(list)
    indeg = {i: 0 for i in ids}
    for e in app_data.logic_edges:
        if e.source in indeg and e.target in indeg:
            adj[e.source].append(e.target)
            indeg[e.target] += 1
            
    q = deque([i for i in ids if indeg[i] == 0])
    order = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    
    order += [i for i in ids if i not in order]
    
    base_x = 50
    base_y = 150
    for i, nid in enumerate(order):
        node = next(n for n in app_data.logic_nodes if n.id == nid)
        if node.position.get("x") == 0 and node.position.get("y") == 0:
            node.position = {"x": base_x + i * 220, "y": base_y + (i % 2) * 80} # slight vertical offset for readability
            
    return app_data
