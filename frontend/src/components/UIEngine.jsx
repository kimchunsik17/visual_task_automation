import React, { useState } from 'react';
import axios from 'axios';
import { Rnd } from 'react-rnd';
import ReactMarkdown from 'react-markdown';
import { DEFAULT_CANVAS, INPUT_COMPONENT_TYPES, LAYOUT_STYLE_KEYS, inferButtonActionMode } from '../appBuilderSchema';

const LABEL_STYLE = { fontSize: '0.85rem', color: '#475569', fontWeight: 500 };

// 편집 화면에서 비어 있는 table 컴포넌트가 "표"로 보이게 하는 예시 행. 미리보기/배포에는 안 나온다.
const SAMPLE_TABLE_ROWS = [
  { 항목: '예시 A', 값: 12, 상태: '완료' },
  { 항목: '예시 B', 값: 7, 상태: '진행 중' },
  { 항목: '예시 C', 값: 3, 상태: '대기' },
];

const formatCell = (value) => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try { return JSON.stringify(value); } catch { return String(value); }
  }
  return String(value);
};

/**
 * table 컴포넌트 값 → { columns, rows }. 워크플로우 결과는 대개 JSON 문자열이라 파싱부터 한다.
 * 객체 배열이면 키의 합집합을 열로, 배열의 배열이면 첫 행을 머리글로, 객체 하나면 키/값 두 열로.
 * { rows | data | items | result(s): [...] } 처럼 한 겹 싸인 결과도 벗겨서 쓴다.
 */
const parseTableData = (raw) => {
  let data = raw;
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    try { data = JSON.parse(trimmed); } catch { return { error: true }; }
  }
  if (data === null || data === undefined || data === '') return null;
  if (Array.isArray(data)) {
    if (!data.length) return { columns: [], rows: [] };
    if (data.every((row) => Array.isArray(row))) {
      const [header, ...rest] = data;
      const columns = header.map(String);
      return { columns, rows: rest.map((row) => Object.fromEntries(columns.map((col, i) => [col, row[i]]))) };
    }
    const objects = data.map((row) => (row !== null && typeof row === 'object' && !Array.isArray(row) ? row : { value: row }));
    return { columns: [...new Set(objects.flatMap((row) => Object.keys(row)))], rows: objects };
  }
  if (typeof data === 'object') {
    const nested = ['rows', 'data', 'items', 'result', 'results'].map((key) => data[key]).find(Array.isArray);
    if (nested) return parseTableData(nested);
    return { columns: ['키', '값'], rows: Object.entries(data).map(([key, value]) => ({ 키: key, 값: value })) };
  }
  return { error: true };
};

const formatLogValue = (value) => {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

export default function UIEngine({ 
  components = [], 
  logicGraph = null,
  globalJs = '',
  isPreview = false, 
  onSelectComponent = null,
  onDropComponent = null,
  onTransformStart = null,
  onUpdateTransform = null,
  selectedIds = [],
  canvasWidth = DEFAULT_CANVAS.width,
  canvasHeight = DEFAULT_CANVAS.height,
  rootStyle = {},
  onExecutionEvent = null,
  // 익명 업로드 귀속용(ADR-0010). 배포된 앱 뷰어가 이 앱이 연결된 워크플로우 id 를 넘긴다 —
  // 공개 프로젝트면 소유자 용량으로 업로드가 허용된다. 없으면 로그인 토큰만 시도한다.
  uploadProjectId = null,
  // 편집 화면이 아트보드를 transform: scale 로 축소해 보일 때의 배율. Rnd 가 드래그/리사이즈
  // 델타를 화면 픽셀 → 아트보드 좌표로 바꾸는 데 쓰고, 컨테이너 drop 좌표도 이걸로 나눈다.
  editorScale = 1,
}) {
  // 컴포넌트 값 저장소는 하나다(백로그 15). 예전에는 "사용자 입력"(inputValues, inputKey 기준)과
  // "Blueprint 가 바꾼 상태"(componentStates, 컴포넌트 id 기준)가 서로 다른 저장소여서,
  // 워크플로우 결과를 출력 textarea 에 써도 화면(다른 저장소를 읽음)에는 안 나오는 버그가 났다.
  // 이제 모든 동적 상태는 컴포넌트 id 를 키로 이 저장소 하나에 저장한다. inputKey 는 저장 키가
  // 아니라 워크플로우 payload 의 필드 이름일 뿐이다.
  const [componentState, setComponentState] = useState({});
  const [loadingAction, setLoadingAction] = useState(null);
  const stateRef = React.useRef({});
  const handlersRef = React.useRef({});
  const componentsRef = React.useRef(components);
  const runWorkflowRef = React.useRef(null);
  const emitExecutionEvent = React.useCallback((level, message, details = null) => {
    if (onExecutionEvent) {
      onExecutionEvent({
        level,
        message,
        details,
        timestamp: new Date().toISOString(),
      });
    }
  }, [onExecutionEvent]);

  React.useEffect(() => {
    componentsRef.current = components;
  }, [components]);

  React.useEffect(() => {
    stateRef.current = componentState;
  }, [componentState]);

  React.useEffect(() => {
    if (!globalJs) {
      handlersRef.current = {};
      return;
    }
    let jsCode = globalJs.trim();
    if (jsCode.startsWith('```')) {
      jsCode = jsCode.replace(/^```[a-zA-Z]*\n?/, '').replace(/\n?```$/, '');
    }
    
    // inputs 는 inputKey(없으면 컴포넌트 id)로 읽는 "뷰"다 — 저장 자체는 컴포넌트 id 로
    // 한 곳에서 한다. 기존 Global JS 코드(inputs.xxx / appState[id].text)와 호환된다.
    const inputsProxy = new Proxy({}, {
      get: (target, prop) => valueByInputKey(String(prop))
    });
    const appStateProxy = new Proxy({}, {
      get: (target, prop) => stateRef.current[prop]
    });

    try {
      const capturedLevels = { log: 'info', info: 'info', debug: 'info', warn: 'warning', error: 'error' };
      const runtimeConsole = new Proxy(console, {
        get(target, property) {
          const original = target[property];
          if (capturedLevels[property] && typeof original === 'function') {
            return (...args) => {
              original.apply(target, args);
              emitExecutionEvent(capturedLevels[property], args.map(formatLogValue).join(' '));
            };
          }
          return typeof original === 'function' ? original.bind(target) : original;
        },
      });
      const fn = new Function('inputs', 'appState', 'setAppState', 'runWorkflow', 'console', jsCode);
      const res = fn(
        inputsProxy,
        appStateProxy,
        setAppState,
        (...args) => runWorkflowRef.current(...args),
        runtimeConsole
      );
      handlersRef.current = typeof res === 'object' && res !== null ? res : {};
    } catch (err) {
      console.error("Global JS Evaluation Error:", err);
      emitExecutionEvent('error', `Global JS 초기화 실패: ${err.message}`);
      handlersRef.current = {};
    }
  }, [globalJs, emitExecutionEvent]);

  React.useEffect(() => {
    if (isPreview) {
      const states = {};
      const traverse = (comps) => {
        comps.forEach(c => {
          states[c.id] = { ...c.props };
          // 슬라이더는 건드리지 않아도 값이 있다 — 기본값을 저장소에 넣어 payload 에 실리게 한다.
          if (c.type === 'slider' && states[c.id].value === undefined) {
            states[c.id].value = Number(c.props.defaultValue ?? c.props.min ?? 0);
          }
          if (c.children) traverse(c.children);
        });
      };
      traverse(components);
      setComponentState(states);
    }
  }, [components, isPreview]);

  const executeLogic = async (triggerCompId, eventType) => {
    if (!logicGraph?.nodes || !logicGraph?.edges) return false;
    
    const triggers = logicGraph.nodes.filter(n => 
      n.type === 'triggerNode' && n.data.componentId === triggerCompId && (n.data.eventType || 'onClick') === eventType
    );
    
    // 체인이 도는 동안 트리거한 버튼을 비활성화한다. 예전에는 workflowNode 가 노드 id 로
    // setLoadingAction 을 불러서 버튼(컴포넌트 id 비교)에 로딩이 표시되지 않았다.
    setLoadingAction(triggerCompId);
    try {
      for (const trigger of triggers) {
         await runLogicChain(trigger.id);
      }
    } finally {
      setLoadingAction(null);
    }
    return triggers.length > 0;
  };

  const runLogicChain = async (nodeId, payload = null, visited = new Set(), branch = 'success') => {
     if (!logicGraph || !logicGraph.edges) return;
     if (visited.has(nodeId)) throw new Error('Blueprint에 순환 실행 경로가 있습니다.');
     const nextVisited = new Set(visited).add(nodeId);
     // 제어 흐름 엣지만 따라간다. branch 로 성공(triggerOut 등)과 실패(errorOut) 경로를
     // 구분한다 — Submit 노드가 실패했을 때 성공 경로가 이어서 돌면 안 된다.
     const edges = logicGraph.edges.filter(e => {
       if (e.source !== nodeId) return false;
       const isControl = e.sourceHandle === 'trigger' || e.sourceHandle === 'triggerOut'
         || e.sourceHandle === 'errorOut' || e.targetHandle === 'triggerIn';
       if (!isControl) return false;
       return (branch === 'error') === (e.sourceHandle === 'errorOut');
     });
     
     for (const edge of edges) {
        const nextNode = logicGraph.nodes.find(n => n.id === edge.target);
        if (!nextNode) continue;
        
        let nextPayload = payload;

        if (nextNode.type === 'actionNode') {
           const dataEdge = logicGraph.edges.find(e => e.target === nextNode.id && e.targetHandle === 'dataIn');
           let actionData = payload;
           
           if (dataEdge) {
              const dataNode = logicGraph.nodes.find(n => n.id === dataEdge.source);
              if (dataNode && dataNode.type === 'valueNode') {
                 // 저장소가 하나이므로 propertyType(value/text)은 같은 값을 읽는다 —
                 // 예전 그래프와의 호환을 위해 필드만 남아 있다.
                 actionData = valueOfComponent(dataNode.data.componentId);
              }
           }
           
           const targetId = nextNode.data.componentId;
           const actionType = nextNode.data.actionType;
           if (targetId) {
             if (actionType === 'setText') writeComponentValue(targetId, actionData);
             else setAppState(targetId, 'visible', actionData);
           }
           await runLogicChain(nextNode.id, actionData, nextVisited);
        }
        else if (nextNode.type === 'workflowNode') {
           let projectId = nextNode.data.projectId;
           if (projectId) {
             if (isNaN(projectId) || String(projectId).includes('WORKFLOW_ID')) {
               let foundId = null;
               const searchId = (comps) => {
                 for (const c of comps) {
                   if (c.props?.workflowId && !isNaN(c.props.workflowId)) {
                     foundId = c.props.workflowId;
                     return;
                   }
                   if (c.children) searchId(c.children);
                 }
               };
               searchId(componentsRef.current);
               if (foundId) projectId = foundId;
               else throw new Error("유효한 워크플로우 ID가 설정되지 않았습니다. 패널에서 설정해주세요.");
             }
             setLoadingAction(nodeId);
             try {
                // Collect payload if attached
                const dataEdge = logicGraph.edges.find(e => e.target === nextNode.id && e.targetHandle === 'payloadIn');
                let reqPayload = payload;
                if (dataEdge) {
                   const dataNode = logicGraph.nodes.find(n => n.id === dataEdge.source);
                   if (dataNode && dataNode.type === 'valueNode') {
                      reqPayload = valueOfComponent(dataNode.data.componentId);
                   }
                }

                const body = typeof reqPayload === 'string'
                  ? { input_text: reqPayload }
                  : (reqPayload || namedInputPayload());
                nextPayload = await runWorkflow(projectId, body);
                setActionResult(nextPayload);
             } catch (err) {
                console.error("Workflow Node Error:", err);
                throw err;
             } finally {
                setLoadingAction(null);
             }
           } else {
             throw new Error('Workflow 노드에 프로젝트가 연결되지 않았습니다.');
           }
           await runLogicChain(nextNode.id, nextPayload, nextVisited);
        }
        else if (nextNode.type === 'submitNode') {
           // 전송 노드(백로그 16): 무엇을 어떤 이름으로 보낼지 명시한다.
           let projectId = nextNode.data.projectId;
           if (isNaN(projectId) || String(projectId || '').includes('WORKFLOW_ID')) {
              // AI 생성 직후 등 아직 실제 id 가 없으면 workflowNode 와 같은 방식으로 찾는다.
              let foundId = null;
              const searchId = (comps) => {
                for (const c of comps) {
                  if (c.props?.workflowId && !isNaN(c.props.workflowId)) { foundId = c.props.workflowId; return; }
                  if (c.children) searchId(c.children);
                }
              };
              searchId(componentsRef.current);
              if (foundId) projectId = foundId;
              else throw new Error('Submit 노드에 워크플로우가 연결되지 않았습니다. Blueprint 탭에서 선택해주세요.');
           }

           const fields = (nextNode.data.fields || []).filter(f => f && f.name && f.componentId);
           const submitPayload = fields.length
             ? Object.fromEntries(fields.map(f => [f.name, valueOfComponent(f.componentId)]))
             : namedInputPayload();

           try {
              nextPayload = await runWorkflow(projectId, submitPayload);
           } catch (err) {
              const detail = err.response?.data?.detail || err.message;
              const hasErrorPath = logicGraph.edges.some(e => e.source === nextNode.id && e.sourceHandle === 'errorOut');
              if (hasErrorPath) {
                 // 실패 경로가 연결돼 있으면 그쪽으로 흐름을 넘기고 성공 경로는 멈춘다.
                 await runLogicChain(nextNode.id, String(detail), nextVisited, 'error');
                 continue;
              }
              throw err; // 실패 경로가 없으면 기존처럼 알림으로 드러낸다
           }
           setActionResult(nextPayload);
           await runLogicChain(nextNode.id, nextPayload, nextVisited);
        }
        else if (nextNode.type === 'outputNode') {
           // 출력 노드(백로그 16): 결과의 어느 부분을 어느 컴포넌트에 보여줄지 명시한다.
           let outputValue = payload;
           const dataEdge = logicGraph.edges.find(e => e.target === nextNode.id && e.targetHandle === 'dataIn');
           if (dataEdge) {
              const dataNode = logicGraph.nodes.find(n => n.id === dataEdge.source);
              if (dataNode && dataNode.type === 'valueNode') {
                 outputValue = valueOfComponent(dataNode.data.componentId);
              }
              // submitNode.dataOut 등에서 오는 엣지는 체인 payload 가 이미 그 값이다.
           }

           const path = String(nextNode.data.resultPath || '').trim();
           if (path) {
              // 결과가 JSON 문자열이면 파싱해서 점 경로로 꺼낸다. 실패하면 원본을 그대로 쓴다 —
              // 경로 오타 때문에 화면이 빈 것보다 전체 결과라도 보이는 편이 낫다.
              try {
                 let parsed = typeof outputValue === 'string' ? JSON.parse(outputValue) : outputValue;
                 for (const part of path.split('.')) {
                    if (parsed === null || parsed === undefined) break;
                    parsed = parsed[part];
                 }
                 if (parsed !== undefined && parsed !== null) outputValue = parsed;
                 else emitExecutionEvent('warning', `Output: 결과에서 '${path}' 경로를 찾지 못해 전체 결과를 표시합니다.`);
              } catch {
                 emitExecutionEvent('warning', `Output: 결과가 JSON 이 아니라 '${path}' 경로를 적용하지 못했습니다.`);
              }
           }

           if (nextNode.data.format === 'json' && typeof outputValue === 'object') {
              outputValue = JSON.stringify(outputValue, null, 2);
           } else if (typeof outputValue === 'object' && outputValue !== null) {
              outputValue = JSON.stringify(outputValue);
           }

           if (nextNode.data.componentId) {
              writeComponentValue(nextNode.data.componentId, outputValue ?? '');
           } else {
              setActionResult(outputValue ?? '');
           }
           await runLogicChain(nextNode.id, payload, nextVisited);
        }
        else if (nextNode.type === 'codeNode') {
           const jsCode = nextNode.data.jsCode || 'return payload;';
           try {
              // Extract payload from dataIn
              const dataEdge = logicGraph.edges.find(e => e.target === nextNode.id && e.targetHandle === 'payloadIn');
              let reqPayload = payload;
              if (dataEdge) {
                 const dataNode = logicGraph.nodes.find(n => n.id === dataEdge.source);
                 if (dataNode && dataNode.type === 'valueNode') {
                    reqPayload = valueOfComponent(dataNode.data.componentId);
                 }
              }

              // Evaluate JS Code
              // Using new Function to create an isolated scope for the user code
              const userFunc = new Function('payload', 'appState', jsCode);
              nextPayload = userFunc(reqPayload, stateRef.current);
           } catch (err) {
              console.error("Code Node Error:", err);
              nextPayload = "Error: " + err.message;
           }
           await runLogicChain(nextNode.id, nextPayload, nextVisited);
        }
     }
  };
  const [actionResult, setActionResult] = useState(null);
  // 지금 드래그/리사이즈 중인 컴포넌트. 예전에는 "조상이 선택됨"만으로 자손의 pointerEvents 를
  // 꺼버려서, 컨테이너를 한 번 선택하면 그 안의 컴포넌트를 클릭할 수도 드래그할 수도 없었다
  // (선택을 해제해야만 다시 만질 수 있었는데, 화면에 아무 힌트가 없었다).
  const [transformingId, setTransformingId] = useState(null);

  const runWorkflow = async (projectId, payload) => {
    let targetProjectId = projectId;
    if (isNaN(targetProjectId) || String(targetProjectId).includes('WORKFLOW_ID')) {
      let foundId = null;
      const searchId = (comps) => {
        for (const c of comps) {
          if (c.props?.workflowId && !isNaN(c.props.workflowId)) {
            foundId = c.props.workflowId;
            return;
          }
          if (c.children) searchId(c.children);
        }
      };
      searchId(componentsRef.current);
      if (foundId) {
        targetProjectId = foundId;
      } else {
        alert("유효한 워크플로우 ID가 지정되지 않았습니다. 우측 패널에서 연결할 프로젝트 ID를 설정해주세요.", 'error');
        throw new Error("Invalid Workflow ID");
      }
    }
    const inputs = payload === undefined || payload === null
      ? namedInputPayload()
      : (typeof payload === 'object' ? payload : { input_text: payload });
    emitExecutionEvent('info', `Workflow #${targetProjectId} 실행 시작`);
    try {
      const res = await axios.post(`/api/projects/${targetProjectId}/run`, {
        inputs
      }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      emitExecutionEvent('success', `Workflow #${targetProjectId} 실행 완료`, res.data.result);
      return res.data.result;
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      emitExecutionEvent('error', `Workflow #${targetProjectId} 실행 실패: ${detail}`);
      throw err;
    }
  };
  runWorkflowRef.current = runWorkflow;

  const setAppState = (id, key, value) => {
    // text 와 value 는 같은 레코드의 별칭이다 — Global JS 가 어느 쪽으로 쓰든
    // 화면(입력 계열은 value, text 계열은 text 를 읽음)이 같은 값을 본다.
    const patch = { [key]: value, ...(key === 'text' ? { value } : key === 'value' ? { text: value } : {}) };
    // stateRef 는 렌더 뒤 effect 로 동기화되는데, 같은 체인의 다음 노드나 onChange 트리거는
    // 렌더 전에 값을 읽는다. 바로 반영해 두어야 "방금 쓴 값"을 읽는다.
    stateRef.current = { ...stateRef.current, [id]: { ...(stateRef.current[id] || {}), ...patch } };
    setComponentState(prev => ({ ...prev, [id]: { ...(prev[id] || {}), ...patch } }));
  };

  // Removed getHandlers() - handled by useEffect now

  const INPUT_LIKE_TYPES = new Set(INPUT_COMPONENT_TYPES);

  const findComponentById = (comps, id) => {
    for (const c of comps || []) {
      if (c.id === id) return c;
      const found = c.children && findComponentById(c.children, id);
      if (found) return found;
    }
    return null;
  };

  const inputKeyOf = (comp) => comp?.props?.inputKey || comp?.id;

  // 이 컴포넌트가 지금 갖고 있는 값. 사용자가 입력했든 Blueprint/Output 이 썼든 같은 저장소다.
  const valueOfComponent = (compId) => {
    const record = stateRef.current[compId] || {};
    if (record.value !== undefined) return record.value;
    if (record.text !== undefined) return record.text;
    return '';
  };

  // inputKey(없으면 컴포넌트 id) -> 값. Global JS 의 inputs 프록시가 쓴다.
  const valueByInputKey = (key) => {
    let found = null;
    const walk = (comps) => {
      for (const c of comps || []) {
        if (inputKeyOf(c) === key || c.id === key) { found = c; return; }
        if (c.children) { walk(c.children); if (found) return; }
      }
    };
    walk(componentsRef.current);
    return found ? valueOfComponent(found.id) : undefined;
  };

  // 워크플로우로 보낼 payload. 입력 계열 컴포넌트의 값을 inputKey 이름으로 모은다 —
  // 백엔드가 "첫 번째 값"을 추측하게 두지 않고 이름 있는 필드로 보낸다.
  const namedInputPayload = () => {
    const payload = {};
    const walk = (comps) => {
      (comps || []).forEach((c) => {
        if (INPUT_LIKE_TYPES.has(c.type)) payload[inputKeyOf(c)] = valueOfComponent(c.id);
        if (c.children) walk(c.children);
      });
    };
    walk(componentsRef.current);
    return payload;
  };

  // 컴포넌트에 값을 써넣는 유일한 통로. text 를 함께 쓰는 이유: text 컴포넌트의 렌더와
  // 기존 Global JS(appState[id].text)가 그 필드를 읽기 때문이다 — 별도 저장소가 아니라
  // 같은 레코드의 별칭이라 어긋날 수 없다.
  const writeComponentValue = (compId, value) => {
    stateRef.current = { ...stateRef.current, [compId]: { ...(stateRef.current[compId] || {}), value, text: value } };
    setComponentState((prev) => ({
      ...prev,
      [compId]: { ...(prev[compId] || {}), value, text: value },
    }));
  };

  const displayedInputValue = (comp, dynamicProps) => {
    if (!isPreview) return '';
    const record = componentState[comp.id] || {};
    if (record.value !== undefined) return record.value;
    if (record.text !== undefined) return record.text;
    return dynamicProps.text ?? dynamicProps.value ?? '';
  };

  // 파일 컴포넌트(백로그 18): 파일 자체가 아니라 서버가 검증해 저장한 경로를 값으로 갖는다.
  // 그 경로가 Submit payload 의 필드가 되어 워크플로우(tokenizerNode 등)로 흘러간다.
  const handleFileUpload = async (comp, file) => {
    if (!file) return;
    setAppState(comp.id, 'fileError', '');
    setAppState(comp.id, 'uploadPct', 0);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('purpose', comp.props.fileKind === 'video' ? 'video' : 'app');
      if (uploadProjectId) formData.append('project_id', String(uploadProjectId));
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        onUploadProgress: (evt) => {
          if (evt.total) setAppState(comp.id, 'uploadPct', Math.round((evt.loaded / evt.total) * 100));
        },
      });
      writeComponentValue(comp.id, res.data.file_path);
      setAppState(comp.id, 'fileName', file.name);
      emitExecutionEvent('success', `파일 업로드 완료: ${file.name}`);
    } catch (err) {
      const detail = err.response?.data?.detail || '업로드에 실패했습니다.';
      setAppState(comp.id, 'fileError', String(detail));
      emitExecutionEvent('error', `파일 업로드 실패: ${detail}`);
    } finally {
      setAppState(comp.id, 'uploadPct', null);
    }
  };

  const clearUploadedFile = (comp) => {
    writeComponentValue(comp.id, '');
    setAppState(comp.id, 'fileName', '');
    setAppState(comp.id, 'fileError', '');
  };

  const handleInputChange = async (comp, value) => {
    writeComponentValue(comp.id, value);
    if (!isPreview) return;

    if (comp.props.onChangeHandler) {
      const handlers = handlersRef.current;
      if (typeof handlers[comp.props.onChangeHandler] === 'function') {
        try {
          await handlers[comp.props.onChangeHandler](value);
        } catch (err) {
          console.error("onChangeHandler Error:", err);
          emitExecutionEvent('error', `${comp.props.onChangeHandler} 실행 실패: ${err.message}`);
        }
      }
    }

    // Blueprint 의 On Change 트리거. 값을 바꿀 때마다 체인이 돈다(실시간 미리보기·필터 같은 용도).
    const hasChangeTrigger = logicGraph?.nodes?.some((node) => node.type === 'triggerNode'
      && node.data?.componentId === comp.id && node.data?.eventType === 'onChange');
    if (hasChangeTrigger) {
      try {
        await executeLogic(comp.id, 'onChange');
      } catch (err) {
        console.error('onChange Blueprint error:', err);
        emitExecutionEvent('error', `onChange Blueprint 실행 실패: ${err.response?.data?.detail || err.message}`);
      }
    }
  };

  const handleActionClick = async (e, comp) => {
    if (!isPreview) {
      // In edit mode, clicking a button should just select it, not trigger action.
      if (onSelectComponent) {
        e.stopPropagation();
        onSelectComponent(comp);
      }
      return;
    }

    const hasBlueprintTrigger = logicGraph?.nodes?.some((node) =>
      node.type === 'triggerNode' &&
      node.data?.componentId === comp.id &&
      (node.data?.eventType || 'onClick') === 'onClick'
    );
    const actionMode = inferButtonActionMode(comp.props, hasBlueprintTrigger);

    if (actionMode === 'none') {
      // 예전에는 아무 흔적 없이 조용히 끝났다 — 사용자 입장에서는 "눌러도 실행이 안 되는"
      // 것과 구분되지 않는다. 실행 로그에는 이유를 남긴다.
      emitExecutionEvent('info', `'${comp.props.text || comp.id}' 버튼은 Click Action 이 None 이라 아무 동작도 하지 않습니다.`);
      return;
    }

    // Blueprint 트리거를 연결해뒀는데 Click Action 이 다른 값이면 그 트리거는 실행되지
    // 않는다. 화면에는 아무 표시가 없어서 "때때로 실행이 안 되는" 것처럼 보인다.
    if (hasBlueprintTrigger && !['blueprint', 'auto'].includes(actionMode)) {
      emitExecutionEvent(
        'warning',
        `'${comp.props.text || comp.id}' 버튼에 Blueprint 트리거가 연결돼 있지만 Click Action 이 '${actionMode}' 라 실행되지 않습니다.`
      );
    }

    const runScriptHandler = async () => {
      const handlers = handlersRef.current;
      if (typeof handlers[comp.props.onClickHandler] === 'function') {
        setLoadingAction(comp.id);
        emitExecutionEvent('info', `${comp.props.onClickHandler} 실행 시작`);
        try {
          const result = await handlers[comp.props.onClickHandler]();
          emitExecutionEvent('success', `${comp.props.onClickHandler} 실행 완료`, result);
        } catch (err) {
          console.error("onClickHandler Error:", err);
          emitExecutionEvent('error', `${comp.props.onClickHandler} 실행 실패: ${err.message}`);
          alert('코드 실행 중 오류 발생: ' + err.message);
        } finally {
          setLoadingAction(null);
        }
        return true;
      }
      return false;
    };

    if (actionMode === 'script') {
      if (!comp.props.onClickHandler || !(await runScriptHandler())) {
        alert('연결된 JavaScript 핸들러를 찾을 수 없습니다.', 'error');
      }
      return;
    }

    if (actionMode === 'blueprint') {
      try {
        const handled = await executeLogic(comp.id, 'onClick');
        if (!handled) alert('이 버튼에 연결된 Blueprint 트리거가 없습니다.', 'error');
      } catch (err) {
        console.error('Blueprint execution error:', err);
        alert('Blueprint 실행 중 오류 발생: ' + (err.response?.data?.detail || err.message));
      }
      return;
    }

    if (actionMode === 'auto') {
      if (comp.props.onClickHandler && await runScriptHandler()) return;
      try {
        if (await executeLogic(comp.id, 'onClick')) return;
      } catch (err) {
        console.error('Blueprint execution error:', err);
        alert('Blueprint 실행 중 오류 발생: ' + (err.response?.data?.detail || err.message));
        return;
      }
    }

    if (!comp.props.workflowId) {
      alert('버튼에 실행할 동작이 연결되지 않았습니다.', 'error');
      return;
    }

    if (String(comp.props.workflowId).includes('WORKFLOW_ID') || isNaN(comp.props.workflowId)) {
      alert('유효한 워크플로우 ID가 설정되지 않았습니다. 우측 패널에서 연결할 프로젝트 ID를 올바르게 숫자로 설정해주세요.', 'error');
      return;
    }

    setLoadingAction(comp.id);
    try {
      const result = await runWorkflow(comp.props.workflowId, namedInputPayload());
      setActionResult(result);
    } catch (err) {
      console.error(err);
      alert('워크플로우 실행 중 오류 발생: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoadingAction(null);
    }
  };

  const handleComponentClick = (e, comp) => {
    if (!isPreview && onSelectComponent) {
      e.stopPropagation();
      const isMulti = e.shiftKey || e.metaKey || e.ctrlKey;
      onSelectComponent(comp, isMulti);
    }
  };

  const renderComponent = (comp, parentLayoutMode = 'absolute', ancestorIsTransforming = false) => {
    const isSelected = selectedIds.includes(comp.id);
    
    // Merge base props with dynamic componentStates if in preview
    const dynamicProps = isPreview ? { ...comp.props, ...(componentState[comp.id] || {}) } : comp.props;
    
    const style = { ...(dynamicProps.style || {}) };
    if (comp.type !== 'container') {
      ['display', 'flexDirection', 'justifyContent', 'alignItems', 'gap'].forEach(k => delete style[k]);
    }
    // 위치는 props.position 이 정한다. style 의 left/top 이 살아 있으면 아래 baseStyle 의
    // position 과 합쳐져 이중 오프셋이 난다(정규화가 지우지만, 저장 전 데이터를 위해 여기서도 막는다).
    LAYOUT_STYLE_KEYS.forEach((key) => delete style[key]);

    const isHidden = dynamicProps.visible === false || dynamicProps.visible === 'false';
    if (isHidden && isPreview) return null;

    const pos = dynamicProps.position;
    const participatesInFlow = parentLayoutMode !== 'absolute';
    const isAbsolute = pos !== undefined && !participatesInFlow;

    const size = { 
      width: style.width || (['input', 'textarea', 'dropdown', 'button'].includes(comp.type) ? '100%' : (comp.type === 'image' ? '150px' : 'auto')), 
      height: style.height || (comp.type === 'image' ? '150px' : 'auto') 
    };

    const baseStyle = {
      ...style,
      // In editor mode: DO NOT set position/left/top — Rnd handles positioning.
      // In preview mode with position: use absolute positioning.
      // In preview mode without position: use relative (flow layout).
      ...(isPreview 
        ? (isAbsolute 
            ? { position: 'absolute', left: `${pos.x}px`, top: `${pos.y}px` }
            : { position: 'relative' })
        : { position: 'relative' }  // editor mode: Rnd handles position
      ),
      width: size.width,
      height: size.height,
      zIndex: 1,
      boxSizing: 'border-box',
      margin: 0,
      outline: isSelected && !isPreview ? '2px solid #3b82f6' : 'none',
      outlineOffset: '-2px',
      cursor: !isPreview ? 'move' : (comp.type === 'button' ? 'pointer' : 'default'),
      transition: isPreview ? 'none' : 'outline 0.1s ease',
      // 편집 화면에서 숨긴 컴포넌트는 지우지 않고 흐리게 둔다 — 그래야 다시 고르고 만질 수 있다.
      ...(isHidden ? { opacity: 0.35, filter: 'grayscale(0.6)' } : {}),
    };

    let innerContent = null;

    switch (comp.type) {
      case 'container': {
        const layoutMode = dynamicProps.layoutMode || 'absolute';
        const containerLayoutStyle = layoutMode === 'grid'
          ? {
              display: 'grid',
              gridTemplateColumns: style.gridTemplateColumns || 'repeat(2, minmax(0, 1fr))',
              gap: style.gap || '12px',
              alignItems: style.alignItems || 'stretch',
            }
          : layoutMode === 'row' || layoutMode === 'column'
            ? {
                display: 'flex',
                flexDirection: layoutMode,
                justifyContent: style.justifyContent || 'flex-start',
                alignItems: style.alignItems || 'stretch',
                gap: style.gap || '12px',
              }
            : { display: 'block' };
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            onDragOver={(e) => {
              if (!isPreview) e.preventDefault();
            }}
            onDrop={(e) => {
              if (!isPreview && onDropComponent) {
                e.preventDefault();
                e.stopPropagation();
                const data = e.dataTransfer.getData('application/json');
                if (data) {
                  const { type } = JSON.parse(data);
                  // Calculate local drop coordinates
                  const rect = e.currentTarget.getBoundingClientRect();
                  const dropX = (e.clientX - rect.left) / editorScale;
                  const dropY = (e.clientY - rect.top) / editorScale;
                  onDropComponent(comp.id, type, dropX, dropY);
                }
              }
            }}
            style={{
              ...baseStyle,
              backgroundColor: style.backgroundColor || 'transparent',
              padding: style.padding || '0',
              borderRadius: style.borderRadius || '0px',
              border: style.border || (!isPreview ? '1px dashed #cbd5e1' : 'none'),
              position: isAbsolute ? baseStyle.position : 'relative',
              ...containerLayoutStyle,
            }}
            className={dynamicProps.className}
          >
            {comp.children && comp.children.map((child) => renderComponent(
              child,
              layoutMode,
              // 부모를 실제로 끌고 있는 동안에만 자식이 포인터를 가로채지 않게 한다.
              // 그냥 선택만 한 상태에서는 자식도 평소처럼 고를 수 있어야 한다.
              ancestorIsTransforming || transformingId === comp.id
            ))}
          </div>
        );
        break;
      }

      case 'text':
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{
              fontSize: style.fontSize || '1rem',
              fontWeight: style.fontWeight || 'normal',
              color: style.color || '#1e293b',
              textAlign: style.textAlign || 'left',
              padding: style.padding || '0',
              display: 'flex',
              alignItems: 'center',
              whiteSpace: 'nowrap',
              ...baseStyle
            }}
            className={dynamicProps.className}
          >
            {dynamicProps.text || 'Text content'}
          </div>
        );
        break;

      case 'input':
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', ...baseStyle }}
            className={dynamicProps.className}
          >
            {dynamicProps.label && <label style={{ fontSize: '0.85rem', color: '#475569', fontWeight: 500 }}>{dynamicProps.label}</label>}
            <input
              type={dynamicProps.inputType || 'text'}
              placeholder={dynamicProps.placeholder || ''}
              value={displayedInputValue(comp, dynamicProps)}
              onChange={(e) => isPreview && handleInputChange(comp, e.target.value)}
              // AI 는 결과 표시용 textarea 를 "읽기 전용"으로 만들도록 안내받는다 — 그 의도를 지킨다.
              readOnly={!isPreview || !!dynamicProps.readOnly}
              style={{
                padding: style.padding || '0.75rem',
                borderRadius: style.borderRadius || '6px',
                border: style.border || '1px solid #cbd5e1',
                fontSize: style.fontSize || '1rem',
                backgroundColor: style.backgroundColor || '#ffffff',
                outline: 'none',
                width: '100%',
                height: '100%',
                boxSizing: 'border-box',
                pointerEvents: !isPreview ? 'none' : 'auto'
              }}
            />
          </div>
        );
        break;

      case 'button':
        innerContent = (
          <button
            onClick={(e) => handleActionClick(e, comp)}
            disabled={loadingAction === comp.id}
            style={{
              padding: style.padding || '0.75rem 1.5rem',
              backgroundColor: style.backgroundColor || '#3b82f6',
              color: style.color || '#ffffff',
              border: style.border || 'none',
              borderRadius: style.borderRadius || '6px',
              fontSize: style.fontSize || '1rem',
              fontWeight: style.fontWeight || '600',
              opacity: loadingAction === comp.id ? 0.7 : 1,
              whiteSpace: 'nowrap',
              ...baseStyle
            }}
            className={dynamicProps.className}
          >
            {loadingAction === comp.id ? '처리 중...' : (dynamicProps.text || 'Button')}
          </button>
        );
        break;

      case 'image':
        innerContent = (
          <img
            onClick={(e) => handleComponentClick(e, comp)}
            src={dynamicProps.imageUrl || 'https://via.placeholder.com/150'}
            alt="UI Image"
            style={{
              borderRadius: style.borderRadius || '0px',
              objectFit: 'cover',
              ...baseStyle,
              cursor: !isPreview ? 'move' : 'default',
            }}
            className={dynamicProps.className}
          />
        );
        break;

      case 'file': {
        const uploading = typeof dynamicProps.uploadPct === 'number';
        const acceptExtensions = dynamicProps.fileKind === 'video'
          ? '.mp4,.mov,.avi,.mkv,.webm,.flv,.mpeg,.mpg,.wmv'
          : '.csv,.doc,.docx,.gif,.hwp,.hwpx,.jpeg,.jpg,.json,.md,.pdf,.png,.ppt,.pptx,.txt,.webp,.xls,.xlsx';
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', ...baseStyle }}
            className={dynamicProps.className}
          >
            {dynamicProps.label && <label style={{ fontSize: '0.85rem', color: '#475569', fontWeight: 500 }}>{dynamicProps.label}</label>}
            {!isPreview ? (
              <div style={{ flex: 1, border: '2px dashed #cbd5e1', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', fontSize: '0.85rem', background: '#f8fafc' }}>
                📎 파일 업로드 ({dynamicProps.fileKind === 'video' ? '영상' : '문서/이미지'})
              </div>
            ) : dynamicProps.value ? (
              <div style={{ flex: 1, border: '1px solid #cbd5e1', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0 0.75rem', background: '#f0fdf4', fontSize: '0.85rem', color: '#166534', minHeight: '44px' }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                  ✓ {dynamicProps.fileName || dynamicProps.value}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); clearUploadedFile(comp); }}
                  style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '0.85rem', flexShrink: 0 }}
                >✕ 제거</button>
              </div>
            ) : (
              <label style={{ flex: 1, border: '2px dashed #94a3b8', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: uploading ? 'default' : 'pointer', color: '#475569', fontSize: '0.85rem', background: '#f8fafc', minHeight: '44px' }}>
                {uploading ? `업로드 중… ${dynamicProps.uploadPct}%` : '📎 파일 선택 또는 끌어다 놓기'}
                <input
                  type="file"
                  accept={acceptExtensions}
                  disabled={uploading}
                  style={{ display: 'none' }}
                  onChange={(e) => { handleFileUpload(comp, e.target.files?.[0]); e.target.value = ''; }}
                />
              </label>
            )}
            {dynamicProps.fileError && (
              <div style={{ fontSize: '0.75rem', color: '#dc2626' }}>{dynamicProps.fileError}</div>
            )}
          </div>
        );
        break;
      }

      case 'textarea':
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', ...baseStyle }}
            className={dynamicProps.className}
          >
            {dynamicProps.label && <label style={{ fontSize: '0.85rem', color: '#475569', fontWeight: 500 }}>{dynamicProps.label}</label>}
            <textarea
              placeholder={dynamicProps.placeholder || ''}
              value={displayedInputValue(comp, dynamicProps)}
              onChange={(e) => isPreview && handleInputChange(comp, e.target.value)}
              // AI 는 결과 표시용 textarea 를 "읽기 전용"으로 만들도록 안내받는다 — 그 의도를 지킨다.
              readOnly={!isPreview || !!dynamicProps.readOnly}
              style={{
                padding: style.padding || '0.75rem',
                borderRadius: style.borderRadius || '6px',
                border: style.border || '1px solid #cbd5e1',
                fontSize: style.fontSize || '1rem',
                backgroundColor: style.backgroundColor || '#ffffff',
                outline: 'none',
                width: '100%',
                height: '100%',
                boxSizing: 'border-box',
                resize: 'none',
                pointerEvents: !isPreview ? 'none' : 'auto'
              }}
            />
          </div>
        );
        break;

      case 'dropdown': {
        const options = (dynamicProps.options || 'Option 1, Option 2, Option 3').split(',').map(s => s.trim());
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', ...baseStyle }}
            className={dynamicProps.className}
          >
            {dynamicProps.label && <label style={{ fontSize: '0.85rem', color: '#475569', fontWeight: 500 }}>{dynamicProps.label}</label>}
            <select
              value={displayedInputValue(comp, dynamicProps)}
              onChange={(e) => isPreview && handleInputChange(comp, e.target.value)}
              disabled={!isPreview}
              style={{
                padding: style.padding || '0.75rem',
                borderRadius: style.borderRadius || '6px',
                border: style.border || '1px solid #cbd5e1',
                fontSize: style.fontSize || '1rem',
                backgroundColor: style.backgroundColor || '#ffffff',
                outline: 'none',
                width: '100%',
                height: '100%',
                boxSizing: 'border-box',
                pointerEvents: !isPreview ? 'none' : 'auto'
              }}
            >
              <option value="" disabled>Select...</option>
              {options.map((opt, i) => <option key={i} value={opt}>{opt}</option>)}
            </select>
          </div>
        );
        break;
      }

      case 'checkbox':
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', ...baseStyle }}
            className={dynamicProps.className}
          >
            <input
              type="checkbox"
              // 체크박스는 value 만 본다 — seeding 된 text(라벨 문구)가 truthy 라고 기본
              // 체크되면 안 된다.
              checked={isPreview ? !!(componentState[comp.id]?.value) : false}
              onChange={(e) => isPreview && handleInputChange(comp, e.target.checked)}
              disabled={!isPreview}
              style={{ cursor: isPreview ? 'pointer' : 'default' }}
            />
            {dynamicProps.label && <label style={{ fontSize: '0.9rem', color: '#475569', cursor: isPreview ? 'pointer' : 'default' }}>{dynamicProps.label}</label>}
          </div>
        );
        break;
      case 'terminal':
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            className={`terminal-container ${dynamicProps.className || ''}`}
            style={{
              backgroundColor: style.backgroundColor || '#1e1e1e',
              color: style.color || '#d4d4d4',
              fontFamily: 'monospace',
              padding: style.padding || '1rem',
              borderRadius: style.borderRadius || '8px',
              overflowY: 'auto',
              minHeight: style.height || '150px',
              width: '100%',
              boxSizing: 'border-box',
              ...baseStyle
            }}
          >
            {Array.isArray(dynamicProps.logs) ? dynamicProps.logs.map((log, i) => (
              <div key={i} style={{ marginBottom: '4px', whiteSpace: 'pre-wrap' }}>{log}</div>
            )) : (
              <div style={{ whiteSpace: 'pre-wrap' }}>{dynamicProps.text || '> Terminal Ready...'}</div>
            )}
          </div>
        );
        break;


      case 'radio': {
        const options = String(dynamicProps.options || '').split(',').map((s) => s.trim()).filter(Boolean);
        const current = displayedInputValue(comp, dynamicProps);
        const isRow = dynamicProps.direction === 'row';
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', ...baseStyle }}
            className={dynamicProps.className}
          >
            {dynamicProps.label && <label style={LABEL_STYLE}>{dynamicProps.label}</label>}
            <div style={{ display: 'flex', flexDirection: isRow ? 'row' : 'column', flexWrap: 'wrap', gap: isRow ? '0.25rem 1rem' : '0.35rem' }}>
              {options.map((option) => (
                <label
                  key={option}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: style.fontSize || '0.9rem', color: style.color || '#334155', cursor: isPreview ? 'pointer' : 'default' }}
                >
                  <input
                    type="radio"
                    name={comp.id}
                    value={option}
                    checked={isPreview && current === option}
                    onChange={() => isPreview && handleInputChange(comp, option)}
                    disabled={!isPreview}
                    style={{ pointerEvents: !isPreview ? 'none' : 'auto', accentColor: '#3b82f6' }}
                  />
                  {option}
                </label>
              ))}
              {options.length === 0 && <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>옵션을 입력하세요 (쉼표 구분)</span>}
            </div>
          </div>
        );
        break;
      }

      case 'slider': {
        const min = Number.isFinite(Number(dynamicProps.min)) ? Number(dynamicProps.min) : 0;
        const max = Number.isFinite(Number(dynamicProps.max)) && Number(dynamicProps.max) > min ? Number(dynamicProps.max) : min + 100;
        const step = Number(dynamicProps.step) > 0 ? Number(dynamicProps.step) : 1;
        const stored = displayedInputValue(comp, dynamicProps);
        const current = stored === '' || stored === null || stored === undefined || Number.isNaN(Number(stored))
          ? Number(dynamicProps.defaultValue ?? min)
          : Number(stored);
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', justifyContent: 'center', ...baseStyle }}
            className={dynamicProps.className}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <label style={LABEL_STYLE}>{dynamicProps.label || ''}</label>
              {dynamicProps.showValue !== false && (
                <span style={{ fontSize: '0.85rem', color: style.color || '#0f172a', fontVariantNumeric: 'tabular-nums' }}>{current}</span>
              )}
            </div>
            <input
              type="range"
              min={min}
              max={max}
              step={step}
              value={current}
              onChange={(e) => isPreview && handleInputChange(comp, Number(e.target.value))}
              disabled={!isPreview}
              style={{ width: '100%', margin: 0, accentColor: style.color || '#3b82f6', pointerEvents: !isPreview ? 'none' : 'auto', cursor: isPreview ? 'pointer' : 'default' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#94a3b8' }}>
              <span>{min}</span><span>{max}</span>
            </div>
          </div>
        );
        break;
      }

      case 'link':
        innerContent = (
          <a
            href={dynamicProps.href || '#'}
            target={dynamicProps.openInNewTab === false ? undefined : '_blank'}
            rel="noreferrer"
            onClick={(e) => {
              if (!isPreview) {
                e.preventDefault();
                handleComponentClick(e, comp);
              }
            }}
            className={dynamicProps.className}
            style={{
              display: 'flex',
              alignItems: 'center',
              color: style.color || '#2563eb',
              fontSize: style.fontSize || '1rem',
              fontWeight: style.fontWeight || '500',
              textDecoration: dynamicProps.underline === false ? 'none' : 'underline',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              ...baseStyle,
              cursor: !isPreview ? 'move' : 'pointer',
            }}
          >
            {dynamicProps.text || 'Link'}
          </a>
        );
        break;

      case 'markdown': {
        const raw = dynamicProps.text ?? dynamicProps.value;
        const content = raw === null || raw === undefined ? '' : (typeof raw === 'string' ? raw : formatCell(raw));
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            className={`ui-markdown ${dynamicProps.className || ''}`}
            style={{
              overflowY: 'auto',
              padding: style.padding || '0.75rem 1rem',
              fontSize: style.fontSize || '0.95rem',
              color: style.color || '#1e293b',
              backgroundColor: style.backgroundColor || 'transparent',
              lineHeight: 1.6,
              ...baseStyle,
            }}
          >
            {content.trim() ? (
              <ReactMarkdown>{content}</ReactMarkdown>
            ) : !isPreview ? (
              <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '0.85rem' }}>
                마크다운 출력 — Output 노드가 쓴 결과가 서식 있는 문서로 표시됩니다. 속성 패널에서 고정 내용을 넣을 수도 있습니다.
              </span>
            ) : null}
          </div>
        );
        break;
      }

      case 'table': {
        const raw = dynamicProps.text ?? dynamicProps.value;
        let parsed = parseTableData(raw);
        const showSample = !isPreview && !parsed;
        if (showSample) parsed = parseTableData(SAMPLE_TABLE_ROWS);
        const wanted = String(dynamicProps.columns || '').split(',').map((s) => s.trim()).filter(Boolean);
        const columns = parsed && !parsed.error ? (wanted.length ? wanted : parsed.columns) : [];
        const emptyText = dynamicProps.emptyText || '표시할 데이터가 없습니다.';
        const noticeStyle = { padding: '0.75rem 1rem', fontSize: '0.85rem', color: '#94a3b8', fontStyle: 'italic' };
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            className={dynamicProps.className}
            style={{
              overflow: 'auto',
              backgroundColor: style.backgroundColor || '#ffffff',
              border: style.border || '1px solid #e2e8f0',
              borderRadius: style.borderRadius || '8px',
              ...baseStyle,
            }}
          >
            {!parsed ? (
              <div style={noticeStyle}>{emptyText}</div>
            ) : parsed.error ? (
              <div style={{ ...noticeStyle, color: '#dc2626' }}>표 데이터를 해석할 수 없습니다 — JSON 배열(객체 배열)이 필요합니다.</div>
            ) : parsed.rows.length === 0 ? (
              <div style={noticeStyle}>{emptyText}</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: style.fontSize || '0.85rem', color: style.color || '#1e293b', opacity: showSample ? 0.55 : 1 }}>
                <thead>
                  <tr>
                    {columns.map((column) => (
                      <th key={column} style={{ textAlign: 'left', padding: '0.5rem 0.75rem', borderBottom: '2px solid #e2e8f0', background: '#f8fafc', position: 'sticky', top: 0, whiteSpace: 'nowrap', fontWeight: 600 }}>
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsed.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {columns.map((column) => (
                        <td key={column} style={{ padding: '0.45rem 0.75rem', borderBottom: '1px solid #f1f5f9', verticalAlign: 'top' }}>
                          {formatCell(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {showSample && (
              <div style={{ fontSize: '0.7rem', color: '#94a3b8', padding: '0.35rem 0.75rem' }}>
                예시 데이터 — 실행 시 Output 노드가 쓴 JSON 배열이 표시됩니다
              </div>
            )}
          </div>
        );
        break;
      }

      case 'progress': {
        const max = Number(dynamicProps.max) > 0 ? Number(dynamicProps.max) : 100;
        const raw = dynamicProps.value ?? dynamicProps.text;
        const numeric = Number(typeof raw === 'string' ? raw.replace('%', '').trim() : raw);
        const value = Number.isFinite(numeric) ? Math.max(0, Math.min(max, numeric)) : 0;
        const pct = Math.round((value / max) * 100);
        // 이 컴포넌트에서 backgroundColor 는 트랙, color 는 막대 색이다 — 바깥 상자에는 칠하지 않는다.
        const wrapperStyle = { ...baseStyle };
        delete wrapperStyle.backgroundColor;
        delete wrapperStyle.color;
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            className={dynamicProps.className}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', justifyContent: 'center', ...wrapperStyle }}
          >
            {(dynamicProps.label || dynamicProps.showValue !== false) && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: style.fontSize || '0.85rem', color: '#475569' }}>
                <span>{dynamicProps.label || ''}</span>
                {dynamicProps.showValue !== false && <span style={{ fontVariantNumeric: 'tabular-nums' }}>{pct}%</span>}
              </div>
            )}
            <div style={{ height: '10px', borderRadius: '999px', background: style.backgroundColor || '#e2e8f0', overflow: 'hidden' }}>
              <div style={{ width: `${pct}%`, height: '100%', background: style.color || '#3b82f6', borderRadius: '999px', transition: isPreview ? 'width 0.3s ease' : 'none' }} />
            </div>
          </div>
        );
        break;
      }

      case 'divider':
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{
              width: '100%',
              height: '100%',
              backgroundColor: style.backgroundColor || '#cbd5e1',
              ...baseStyle
            }}
            className={dynamicProps.className}
          />
        );
        break;

      default:
        return null;
    }

    const safePos = pos || { x: 0, y: 0 };

    if (isPreview || participatesInFlow) {
      return React.cloneElement(innerContent, {
        key: comp.id,
        style: {
          ...innerContent.props.style,
          ...(!isPreview && ancestorIsTransforming ? { pointerEvents: 'none' } : {}),
        },
      });
    }

    return (
      <Rnd
        key={comp.id}
        position={{ x: safePos.x, y: safePos.y }}
        size={{ width: size.width, height: size.height }}
        onDragStart={(e) => {
          handleComponentClick(e, comp);
          setTransformingId(comp.id);
          if (onTransformStart) onTransformStart(comp.id, 'drag');
        }}
        onDrag={(e, d) => {
          if (onUpdateTransform) onUpdateTransform(comp.id, { x: d.x, y: d.y, deltaX: d.deltaX, deltaY: d.deltaY }, e.shiftKey, true);
        }}
        onDragStop={(e, d) => {
          setTransformingId(null);
          if (onUpdateTransform) onUpdateTransform(comp.id, { x: d.x, y: d.y, deltaX: 0, deltaY: 0 }, e.shiftKey, false);
        }}
        onResizeStart={(e) => {
          handleComponentClick(e, comp);
          setTransformingId(comp.id);
          if (onTransformStart) onTransformStart(comp.id, 'resize');
        }}
        onResize={(e, direction, ref, delta, position) => {
          if (onUpdateTransform) onUpdateTransform(comp.id, { 
            width: ref.style.width, 
            height: ref.style.height, 
            x: position.x, 
            y: position.y 
          }, e.shiftKey, true);
        }}
        onResizeStop={(e, direction, ref, delta, position) => {
          setTransformingId(null);
          if (onUpdateTransform) onUpdateTransform(comp.id, { 
            width: ref.style.width, 
            height: ref.style.height, 
            x: position.x, 
            y: position.y 
          }, e.shiftKey, false);
        }}
        bounds="parent"
        scale={editorScale}
        disableDragging={ancestorIsTransforming}
        style={{ zIndex: isSelected ? 10 : 1, pointerEvents: ancestorIsTransforming ? 'none' : 'auto' }}
        enableResizing={ancestorIsTransforming ? false : {
          top: true, right: true, bottom: true, left: true,
          topRight: true, bottomRight: true, bottomLeft: true, topLeft: true,
        }}
      >
        {innerContent}
      </Rnd>
    );
  };

  const safeRootStyle = { ...rootStyle };
  delete safeRootStyle.position;

  return (
    <div style={{ position: 'relative', width: canvasWidth, height: canvasHeight, overflow: 'hidden', boxSizing: 'border-box', ...safeRootStyle }}>
      {/* map 은 콜백에 (element, index, array) 를 넘긴다. renderComponent 를 그대로 넘기면
          index 가 parentLayoutMode 로, 배열 전체가 ancestorIsTransforming 으로 들어가서
          (1) parentLayoutMode 가 'absolute' 가 아니게 되어 최상위 컴포넌트가 Rnd 로 감싸이지
          않고(=드래그·리사이즈 불가), (2) 배열이 truthy 라 pointerEvents 까지 꺼졌다(=선택 불가).
          인자를 명시적으로 하나만 넘긴다. */}
      {components.map((comp) => renderComponent(comp))}
      
      {/* Result display area for deployed apps */}
      {isPreview && actionResult && (
        <div style={{ marginTop: '2rem', padding: '1.5rem', background: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}>
          <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.1rem', color: '#0f172a' }}>실행 결과</h3>
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: '0.9rem', color: '#334155', background: '#f8fafc', padding: '1rem', borderRadius: '8px' }}>
            {typeof actionResult === 'object' ? JSON.stringify(actionResult, null, 2) : actionResult}
          </pre>
        </div>
      )}
    </div>
  );
}
