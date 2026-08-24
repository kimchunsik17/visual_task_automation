import React, { useState } from 'react';
import axios from 'axios';
import { Rnd } from 'react-rnd';
import { DEFAULT_CANVAS, inferButtonActionMode } from '../appBuilderSchema';

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
}) {
  const [inputValues, setInputValues] = useState({});
  const [loadingAction, setLoadingAction] = useState(null);
  const [componentStates, setComponentStates] = useState({});
  const appStateRef = React.useRef({});
  const inputsRef = React.useRef({});
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
    inputsRef.current = inputValues;
    appStateRef.current = componentStates;
  }, [inputValues, componentStates]);

  React.useEffect(() => {
    if (!globalJs) {
      handlersRef.current = {};
      return;
    }
    let jsCode = globalJs.trim();
    if (jsCode.startsWith('```')) {
      jsCode = jsCode.replace(/^```[a-zA-Z]*\n?/, '').replace(/\n?```$/, '');
    }
    
    const inputsProxy = new Proxy({}, {
      get: (target, prop) => inputsRef.current[prop]
    });
    const appStateProxy = new Proxy({}, {
      get: (target, prop) => appStateRef.current[prop]
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
          if (c.children) traverse(c.children);
        });
      };
      traverse(components);
      setComponentStates(states);
    }
  }, [components, isPreview]);

  const executeLogic = async (triggerCompId, eventType) => {
    if (!logicGraph?.nodes || !logicGraph?.edges) return false;
    
    const triggers = logicGraph.nodes.filter(n => 
      n.type === 'triggerNode' && n.data.componentId === triggerCompId && (n.data.eventType || 'onClick') === eventType
    );
    
    for (const trigger of triggers) {
       await runLogicChain(trigger.id);
    }
    return triggers.length > 0;
  };

  const runLogicChain = async (nodeId, payload = null, visited = new Set()) => {
     if (!logicGraph || !logicGraph.edges) return;
     if (visited.has(nodeId)) throw new Error('Blueprint에 순환 실행 경로가 있습니다.');
     const nextVisited = new Set(visited).add(nodeId);
     const edges = logicGraph.edges.filter(e =>
       e.source === nodeId &&
       (e.sourceHandle === 'trigger' || e.sourceHandle === 'triggerOut' || e.targetHandle === 'triggerIn')
     );
     
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
                 const srcCompId = dataNode.data.componentId;
                 const srcProp = dataNode.data.propertyType;
                 if (srcProp === 'value') {
                    // Find inputKey for that component
                    let foundKey = null;
                    const searchInput = (comps) => {
                      comps.forEach(c => {
                        if (c.id === srcCompId) foundKey = c.props.inputKey || c.id;
                        if (c.children) searchInput(c.children);
                      });
                    };
                    searchInput(components);
                    actionData = inputValues[foundKey] || '';
                 } else if (srcProp === 'text') {
                    actionData = componentStates[srcCompId]?.text || '';
                 }
              }
           }
           
           const targetId = nextNode.data.componentId;
           const actionType = nextNode.data.actionType;
           if (targetId) {
             setComponentStates(prev => ({
               ...prev,
               [targetId]: {
                 ...prev[targetId],
                 [actionType === 'setText' ? 'text' : 'visible']: actionData
               }
             }));
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
                      let foundKey = null;
                      const searchInput = (comps) => {
                        comps.forEach(c => {
                          if (c.id === dataNode.data.componentId) foundKey = c.props.inputKey || c.id;
                          if (c.children) searchInput(c.children);
                        });
                      };
                      searchInput(components);
                      reqPayload = inputValues[foundKey] || '';
                   }
                }

                const body = typeof reqPayload === 'string'
                  ? { input_text: reqPayload }
                  : (reqPayload || inputsRef.current);
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
        else if (nextNode.type === 'codeNode') {
           const jsCode = nextNode.data.jsCode || 'return payload;';
           try {
              // Extract payload from dataIn
              const dataEdge = logicGraph.edges.find(e => e.target === nextNode.id && e.targetHandle === 'payloadIn');
              let reqPayload = payload;
              if (dataEdge) {
                 const dataNode = logicGraph.nodes.find(n => n.id === dataEdge.source);
                 if (dataNode && dataNode.type === 'valueNode') {
                    let foundKey = null;
                    const searchInput = (comps) => {
                      comps.forEach(c => {
                        if (c.id === dataNode.data.componentId) foundKey = c.props.inputKey || c.id;
                        if (c.children) searchInput(c.children);
                      });
                    };
                    searchInput(components);
                    reqPayload = inputValues[foundKey] || '';
                 }
              }

              // Evaluate JS Code
              // Using new Function to create an isolated scope for the user code
              const userFunc = new Function('payload', 'appState', jsCode);
              nextPayload = userFunc(reqPayload, appStateRef.current);
           } catch (err) {
              console.error("Code Node Error:", err);
              nextPayload = "Error: " + err.message;
           }
           await runLogicChain(nextNode.id, nextPayload, nextVisited);
        }
     }
  };
  const [actionResult, setActionResult] = useState(null);

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
        alert("유효한 워크플로우 ID가 지정되지 않았습니다. 우측 패널에서 연결할 프로젝트 ID를 설정해주세요.");
        throw new Error("Invalid Workflow ID");
      }
    }
    const inputs = payload === undefined || payload === null
      ? inputsRef.current
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
    setComponentStates(prev => ({
      ...prev,
      [id]: {
        ...(prev[id] || {}),
        [key]: value
      }
    }));
  };

  // Removed getHandlers() - handled by useEffect now

  const handleInputChange = async (comp, value) => {
    const key = comp.props.inputKey || comp.id;
    if (key) {
      setInputValues(prev => ({ ...prev, [key]: value }));
    }
    
    if (isPreview && comp.props.onChangeHandler) {
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

    if (actionMode === 'none') return;

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
        alert('연결된 JavaScript 핸들러를 찾을 수 없습니다.');
      }
      return;
    }

    if (actionMode === 'blueprint') {
      try {
        const handled = await executeLogic(comp.id, 'onClick');
        if (!handled) alert('이 버튼에 연결된 Blueprint 트리거가 없습니다.');
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
      alert('버튼에 실행할 동작이 연결되지 않았습니다.');
      return;
    }

    if (String(comp.props.workflowId).includes('WORKFLOW_ID') || isNaN(comp.props.workflowId)) {
      alert('유효한 워크플로우 ID가 설정되지 않았습니다. 우측 패널에서 연결할 프로젝트 ID를 올바르게 숫자로 설정해주세요.');
      return;
    }

    setLoadingAction(comp.id);
    try {
      const result = await runWorkflow(comp.props.workflowId, inputValues);
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

  const renderComponent = (comp, parentLayoutMode = 'absolute', hasSelectedAncestor = false) => {
    const isSelected = selectedIds.includes(comp.id);
    
    // Merge base props with dynamic componentStates if in preview
    const dynamicProps = isPreview ? { ...comp.props, ...(componentStates[comp.id] || {}) } : comp.props;
    
    const style = { ...(dynamicProps.style || {}) };
    if (comp.type !== 'container') {
      ['display', 'flexDirection', 'justifyContent', 'alignItems', 'gap'].forEach(k => delete style[k]);
    }

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
    };

    if (dynamicProps.visible === false || dynamicProps.visible === 'false') {
      return null;
    }

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
                  const dropX = e.clientX - rect.left;
                  const dropY = e.clientY - rect.top;
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
              hasSelectedAncestor || isSelected
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
              type="text"
              placeholder={dynamicProps.placeholder || ''}
              value={isPreview ? (inputValues[dynamicProps.inputKey || comp.id] || '') : ''}
              onChange={(e) => isPreview && handleInputChange(comp, e.target.value)}
              readOnly={!isPreview}
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
              value={isPreview ? (inputValues[dynamicProps.inputKey || comp.id] || '') : ''}
              onChange={(e) => isPreview && handleInputChange(comp, e.target.value)}
              readOnly={!isPreview}
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
              value={isPreview ? (inputValues[dynamicProps.inputKey || comp.id] || '') : ''}
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
              checked={isPreview ? (inputValues[dynamicProps.inputKey || comp.id] || false) : false}
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
          ...(!isPreview && hasSelectedAncestor ? { pointerEvents: 'none' } : {}),
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
          if (onTransformStart) onTransformStart(comp.id, 'drag');
        }}
        onDrag={(e, d) => {
          if (onUpdateTransform) onUpdateTransform(comp.id, { x: d.x, y: d.y, deltaX: d.deltaX, deltaY: d.deltaY }, e.shiftKey, true);
        }}
        onDragStop={(e, d) => {
          if (onUpdateTransform) onUpdateTransform(comp.id, { x: d.x, y: d.y, deltaX: 0, deltaY: 0 }, e.shiftKey, false);
        }}
        onResizeStart={(e) => {
          handleComponentClick(e, comp);
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
          if (onUpdateTransform) onUpdateTransform(comp.id, { 
            width: ref.style.width, 
            height: ref.style.height, 
            x: position.x, 
            y: position.y 
          }, e.shiftKey, false);
        }}
        bounds="parent"
        disableDragging={hasSelectedAncestor}
        style={{ zIndex: isSelected ? 10 : 1, pointerEvents: hasSelectedAncestor ? 'none' : 'auto' }}
        enableResizing={hasSelectedAncestor ? false : {
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
      {components.map(renderComponent)}
      
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
