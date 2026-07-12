# LLM 기반 워크플로우 자동 생성/수정 개발 가이드

이 문서는 사용자가 자연어 대화를 통해 React Flow 기반의 워크플로우를 수정(노드 추가/삭제/수정 등)할 수 있도록 백엔드(API)와 프론트엔드를 연동하는 방법을 설명하는 가이드입니다. (현재 프론트엔드의 `EditorPage.jsx`에는 채팅 UI 껍데기만 구현되어 있습니다.)

## 1. 아키텍처 및 흐름

1. **프론트엔드 (사용자 요청)**
   * 사용자가 프롬프트(예: "이메일 전송 노드를 추가해줘")를 입력하고 전송합니다.
   * `EditorPage.jsx`의 `handleSendChat` 함수에서 `axios.post('/api/workflow/auto-modify')` API를 호출합니다.
   * 이때 현재 워크플로우 상태(`nodes`, `edges`)와 사용자의 입력(`prompt`)을 Payload로 함께 보냅니다.

2. **백엔드 (LLM 처리 - FastAPI/LangChain)**
   * 전달받은 `nodes`와 `edges` 구조를 LLM에게 Context로 제공합니다.
   * 사용자의 `prompt`를 기반으로 어떤 노드를 수정/추가/삭제할지 LLM(예: GPT-4o, Claude 3.5 Sonnet)이 판단합니다.
   * LLM은 정해진 JSON 스키마(Structured Output)로 응답합니다.

3. **프론트엔드 (상태 업데이트)**
   * 백엔드로부터 JSON 응답을 받으면 프론트엔드는 이를 파싱하여 React Flow의 상태(`setNodes`, `setEdges`)를 업데이트합니다.

## 2. API 명세 제안

**`POST /api/workflow/auto-modify`**

### Request Payload (JSON)
```json
{
  "prompt": "이메일 전송 노드를 맨 끝에 추가해줘. 수신자는 test@test.com 이야.",
  "current_state": {
    "nodes": [
      { "id": "dndnode_0", "type": "startNode", "position": { "x": 100, "y": 100 }, "data": {} }
    ],
    "edges": []
  }
}
```

### Response Payload (JSON)
프론트엔드가 쉽게 처리할 수 있도록, LLM의 응답은 단순한 텍스트가 아닌 '액션(Action) 리스트' 형태의 JSON이어야 합니다.

```json
{
  "message": "이메일 노드를 추가했습니다.",
  "actions": [
    {
      "type": "add_node",
      "node": {
        "id": "dndnode_1",
        "type": "emailNode",
        "position": { "x": 300, "y": 100 },
        "data": { "toEmail": "test@test.com", "subject": "자동 생성 메일" }
      }
    },
    {
      "type": "add_edge",
      "edge": {
        "id": "edge_0_to_1",
        "source": "dndnode_0",
        "target": "dndnode_1",
        "sourceHandle": "out",
        "targetHandle": "in"
      }
    }
  ]
}
```

## 3. 프론트엔드 연동 가이드 (`EditorPage.jsx`)

현재 `EditorPage.jsx`의 `handleSendChat` 내부에는 `setTimeout`으로 목업(Mock) 처리가 되어 있습니다. 이를 아래와 같이 실제 API 호출 로직으로 교체해야 합니다.

```javascript
  const handleSendChat = async () => {
    if (!chatInput.trim()) return;
    
    const userMsg = chatInput;
    const newMessages = [...chatMessages, { role: 'user', content: userMsg }];
    setChatMessages(newMessages);
    setChatInput('');
    
    // 로딩 중 메시지 추가
    setChatMessages(prev => [...prev, { role: 'assistant', content: '분석 중...' }]);

    try {
      // 현재 노드, 엣지 데이터 가져오기
      const currentFlow = getCurrentFlowData();
      
      const res = await axios.post('/api/workflow/auto-modify', {
        prompt: userMsg,
        current_state: currentFlow
      }, getAuthHeaders());
      
      const data = res.data;
      
      // 1. 응답 메시지 업데이트
      setChatMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1].content = data.message;
        return copy;
      });

      // 2. Actions에 따른 상태 업데이트 로직 적용
      if (data.actions && data.actions.length > 0) {
        data.actions.forEach(action => {
          if (action.type === 'add_node') {
            // onNodeDataChange, deleteNode 등 콜백 바인딩 필수
            const newNode = {
              ...action.node,
              data: { ...action.node.data, onChange: onNodeDataChange, onDelete: deleteNode }
            };
            setNodes(nds => [...nds, newNode]);
          } else if (action.type === 'update_node') {
            // ...
          } else if (action.type === 'add_edge') {
            setEdges(eds => addEdge(action.edge, eds));
          }
          // ... 기타 액션 처리
        });
      }
    } catch (error) {
      console.error(error);
      setChatMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1].content = "오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
        return copy;
      });
    }
  };
```

## 4. 백엔드 개발 시 주의사항

1. **Structured Output 사용**: LangChain의 `with_structured_output` 혹은 OpenAI의 `response_format: { type: "json_object" }` 등을 사용하여 LLM이 일관된 포맷으로 `actions` 배열을 반환하도록 강제해야 합니다.
2. **좌표(`position`) 계산**: LLM이 새로운 노드의 `x`, `y` 좌표를 기존 노드들의 위치를 참조하여 적절한 위치(우측 또는 하단)에 생성하도록 프롬프트에 지시해야 겹침 현상을 방지할 수 있습니다.
3. **Handle 이름 검증**: 각 노드 타입마다 사용하는 `sourceHandle`과 `targetHandle`의 이름(`in`, `out`, `true`, `false` 등)이 다릅니다. LLM에게 노드별 핸들 속성을 시스템 프롬프트(Context)로 미리 제공해야 정확한 Edge 생성이 가능합니다.
