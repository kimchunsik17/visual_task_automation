# LLM Auto-Generate Feature Implementation Guide

이 문서는 "LLM을 활용한 워크플로우 자동 생성 및 대화형 UI" 기능을 실제 구현하실 다음 개발자분을 위한 가이드입니다.
현재 프론트엔드 메인 페이지(`MainPage.jsx`)는 ChatGPT와 유사한 대화형(Chat) 레이아웃으로 변경되어 있으며, 백엔드 API와의 연동 시나리오를 완성하기 위해 세부 비즈니스 로직(LLM 파싱 등)과 약간의 UI 확장이 필요합니다.

## 1. 개요 (현재 상태 vs 목표 상태)
- **현재 상태**: 사용자가 메인 페이지 채팅창에 자연어로 프롬프트를 입력하면, 약 1초 뒤 UI에 "현재 llm 업무 자동화 기능은 구현 중에 있습니다."라는 목업(Mock) 메시지가 렌더링됩니다.
- **목표 상태**: 
  1. 사용자가 프롬프트를 입력하면 프론트엔드가 백엔드 API로 요청을 보냅니다.
  2. 백엔드에서는 LLM(Gemini, ChatGPT, Claude 등)을 호출하여 사용자의 요구사항을 분석합니다.
  3. LLM은 단순한 답변 텍스트와 함께 **적절한 노드 구성 및 엣지(연결선)가 포함된 JSON 데이터**를 반환해야 합니다.
  4. 프론트엔드에서는 챗봇의 답변 텍스트를 보여줌과 동시에, "이 워크플로우를 에디터에서 열기" 같은 버튼을 렌더링합니다.
  5. 버튼 클릭 시 에디터 페이지(`/editor`)로 라우팅하며, state로 해당 JSON 데이터를 넘겨주어 즉시 캔버스에 그려지도록 합니다.

## 2. 프론트엔드 보완해야 할 내용 (TODO)
- **파일 경로**: `frontend/src/pages/MainPage.jsx`의 `handleAutoGenerate` 함수
- **로직 변경**:
  - 현재 `setTimeout`으로 처리된 목업 코드를 제거하고, 백엔드 API (예: `axios.post('/api/chat/generate', { prompt: userMessage })`)를 호출하도록 수정합니다.
  - 응답에 포함된 노드 데이터가 존재할 경우, 채팅 버블(`chat-bubble`) 안에 에디터로 넘어가는 버튼을 추가로 렌더링하도록 UI를 확장해 주세요.
  - *참고: 이전에 에디터 페이지 상단에 있던 'Auto Gen' 버튼 로직과 동일하게 동작하면 됩니다.*

## 3. 백엔드 구현해야 할 내용 (TODO)
- **파일 경로**: `backend/main.py`
- **대상 엔드포인트 예시**:
  ```python
  @app.post("/api/chat/generate")
  def chat_generate_workflow(payload: AutoGenPayload, user: models.User = Depends(get_current_user_required)):
      # TODO: LLM 로직 호출 및 노드 JSON 생성
      # return {"message": "워크플로우를 생성했습니다.", "nodes": [...], "edges": [...]}
  ```

### 3.1. 제안하는 아키텍처
LLM 호출 로직이 `main.py`에 있으면 파일이 너무 방대해지므로, 별도의 모듈을 생성하는 것을 권장합니다.
- (권장) `backend/llm_generator.py` 파일을 새로 만들어 로직 분리.
- `main.py`에서는 `from llm_generator import generate_workflow_from_prompt` 형태로 호출.

### 3.2. 반환해야 하는 JSON 규격 (매우 중요)
프론트엔드 에디터로 전달해야 하는 JSON 형식은 다음과 같아야 에러 없이 렌더링됩니다. 각 노드의 `type`은 반드시 프론트엔드에 등록된 노드 타입 중 하나여야 합니다 (`startNode`, `promptNode`, `llmNode`, `outputNode`, `conditionNode`, `valueNode`, `loopNode`, `breakNode`, `pythonNode` 등).

```json
{
  "message": "요청하신 해커뉴스 크롤링 워크플로우 초안을 구성해 보았습니다. 에디터에서 열어 수정해 보세요!",
  "workflow": {
    "nodes": [
      {
        "id": "node_auto_1",
        "type": "startNode",
        "position": { "x": 100, "y": 100 },
        "data": {}
      },
      {
        "id": "node_auto_2",
        "type": "llmNode",
        "position": { "x": 400, "y": 100 },
        "data": {
          "model": "gemini-1.5-flash",
          "temperature": 0.7,
          "system_prompt": "요청에 따라 자동 생성된 프롬프트입니다."
        }
      }
    ],
    "edges": [
      {
        "id": "edge_auto_1",
        "source": "node_auto_1",
        "target": "node_auto_2"
      }
    ]
  }
}
```

### 3.3. LLM 프롬프팅 팁
- LLM 시스템 프롬프트에 사용 가능한 "Node Type"과 "Data Fields"를 명확히 알려주어야 구조화된 JSON을 안정적으로 생성해 냅니다.
- 위치(`position.x`, `position.y`) 값도 LLM이 적당히 계산해서 주도록 유도하거나, 백엔드에서 배열 순서대로 일정 간격(예: x += 300)을 더해주어 정렬하는 것도 좋은 방법입니다.

수고하세요! 🚀
