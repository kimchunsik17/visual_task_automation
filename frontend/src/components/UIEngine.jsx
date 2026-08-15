import React, { useState } from 'react';
import axios from 'axios';
import { Rnd } from 'react-rnd';

export default function UIEngine({ 
  components = [], 
  logicGraph = null,
  isPreview = false, 
  onSelectComponent = null,
  onDropComponent = null,
  onUpdateTransform = null,
  selectedIds = [],
  canvasWidth = 800,
  canvasHeight = 800
}) {
  const [inputValues, setInputValues] = useState({});
  const [loadingAction, setLoadingAction] = useState(null);
  const [componentStates, setComponentStates] = useState({});
  const appStateRef = React.useRef({});

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
    if (!logicGraph || !logicGraph.nodes || !logicGraph.edges) return;
    
    const triggers = logicGraph.nodes.filter(n => 
      n.type === 'triggerNode' && n.data.componentId === triggerCompId && n.data.eventType === eventType
    );
    
    for (const trigger of triggers) {
       await runLogicChain(trigger.id);
    }
  };

  const runLogicChain = async (nodeId, payload = null) => {
     if (!logicGraph || !logicGraph.edges) return;
     const edges = logicGraph.edges.filter(e => e.source === nodeId && (e.sourceHandle === 'trigger' || e.sourceHandle === 'triggerOut'));
     
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
                        if (c.id === srcCompId) foundKey = c.props.inputKey;
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
           await runLogicChain(nextNode.id, actionData);
        }
        else if (nextNode.type === 'workflowNode') {
           const projectId = nextNode.data.projectId;
           if (projectId) {
             setLoadingAction(triggerCompId || nodeId); // Just simple loading UI
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
                          if (c.id === dataNode.data.componentId) foundKey = c.props.inputKey;
                          if (c.children) searchInput(c.children);
                        });
                      };
                      searchInput(components);
                      reqPayload = inputValues[foundKey] || '';
                   }
                }

                // If payload is a string, wrap in expected object, otherwise send as is
                const body = typeof reqPayload === 'string' ? { input_text: reqPayload } : (reqPayload || {});

                const res = await axios.post(`/api/projects/${projectId}/run`, body, {
                  headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
                });
                nextPayload = res.data.result || res.data;
             } catch (err) {
                console.error("Workflow Node Error:", err);
                nextPayload = "Error: " + err.message;
             } finally {
                setLoadingAction(null);
             }
           }
           await runLogicChain(nextNode.id, nextPayload);
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
                        if (c.id === dataNode.data.componentId) foundKey = c.props.inputKey;
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
           await runLogicChain(nextNode.id, nextPayload);
        }
     }
  };
  const [actionResult, setActionResult] = useState(null);

  const handleInputChange = (key, value) => {
    setInputValues(prev => ({ ...prev, [key]: value }));
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

    if (isPreview && logicGraph && logicGraph.nodes && logicGraph.edges.length > 0) {
      await executeLogic(comp.id, 'onClick');
      return;
    }

    // Fallback to legacy workflow mapping execution if LogicGraph doesn't catch it
    if (!comp.props.workflowId) {
      alert('연결된 워크플로우가 없습니다.');
      return;
    }

    setLoadingAction(comp.id);
    try {
      const res = await axios.post(`/api/deploy/${comp.props.workflowId}/execute`, {
        inputs: inputValues
      }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setActionResult(res.data.result);
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

  const renderComponent = (comp) => {
    const isSelected = selectedIds.includes(comp.id);
    
    // Merge base props with dynamic componentStates if in preview
    const dynamicProps = isPreview ? { ...comp.props, ...(componentStates[comp.id] || {}) } : comp.props;
    
    const style = dynamicProps.style || {};
    const pos = dynamicProps.position || { x: 0, y: 0 };
    const size = { 
      width: style.width || (comp.type === 'image' ? '150px' : 'auto'), 
      height: style.height || (comp.type === 'image' ? '150px' : 'auto') 
    };
    
    if (dynamicProps.visible === false || dynamicProps.visible === 'false') {
      return null;
    }
    
    const baseStyle = {
      ...style,
      boxSizing: 'border-box',
      width: '100%',
      height: '100%',
      margin: 0, // margin is handled by absolute position now
      outline: isSelected && !isPreview ? '2px solid #3b82f6' : 'none',
      outlineOffset: '-2px',
      cursor: !isPreview ? 'move' : (comp.type === 'button' ? 'pointer' : 'default'),
      transition: isPreview ? 'none' : 'outline 0.1s ease',
    };

    let innerContent = null;

    switch (comp.type) {
      case 'container':
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
              display: 'block', // absolute children
              position: 'relative',
              backgroundColor: style.backgroundColor || 'transparent',
              padding: style.padding || '0',
              borderRadius: style.borderRadius || '0px',
              border: style.border || (!isPreview ? '1px dashed #cbd5e1' : 'none'),
              ...baseStyle
            }}
            className={dynamicProps.className}
          >
            {comp.children && comp.children.map(child => renderComponent(child))}
          </div>
        );
        break;

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
              value={isPreview ? (inputValues[dynamicProps.inputKey] || '') : ''}
              onChange={(e) => isPreview && handleInputChange(dynamicProps.inputKey, e.target.value)}
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
              value={isPreview ? (inputValues[dynamicProps.inputKey] || '') : ''}
              onChange={(e) => isPreview && handleInputChange(dynamicProps.inputKey, e.target.value)}
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

      case 'dropdown':
        const options = (dynamicProps.options || 'Option 1, Option 2, Option 3').split(',').map(s => s.trim());
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', ...baseStyle }}
            className={dynamicProps.className}
          >
            {dynamicProps.label && <label style={{ fontSize: '0.85rem', color: '#475569', fontWeight: 500 }}>{dynamicProps.label}</label>}
            <select
              value={isPreview ? (inputValues[dynamicProps.inputKey] || '') : ''}
              onChange={(e) => isPreview && handleInputChange(dynamicProps.inputKey, e.target.value)}
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

      case 'checkbox':
        innerContent = (
          <div
            onClick={(e) => handleComponentClick(e, comp)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', ...baseStyle }}
            className={dynamicProps.className}
          >
            <input
              type="checkbox"
              checked={isPreview ? (inputValues[dynamicProps.inputKey] || false) : false}
              onChange={(e) => isPreview && handleInputChange(dynamicProps.inputKey, e.target.checked)}
              disabled={!isPreview}
              style={{ cursor: isPreview ? 'pointer' : 'default' }}
            />
            {dynamicProps.label && <label style={{ fontSize: '0.9rem', color: '#475569', cursor: isPreview ? 'pointer' : 'default' }}>{dynamicProps.label}</label>}
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

    if (isPreview) {
      return (
        <div key={comp.id} style={{ position: 'absolute', left: pos.x, top: pos.y, width: size.width, height: size.height }}>
          {innerContent}
        </div>
      );
    }

    return (
      <Rnd
        key={comp.id}
        position={{ x: pos.x, y: pos.y }}
        size={{ width: size.width, height: size.height }}
        onDragStart={(e) => handleComponentClick(e, comp)}
        onDrag={(e, d) => {
          if (onUpdateTransform) onUpdateTransform(comp.id, { x: d.x, y: d.y, deltaX: d.deltaX, deltaY: d.deltaY }, e.shiftKey, true);
        }}
        onDragStop={(e, d) => {
          if (onUpdateTransform) onUpdateTransform(comp.id, { x: d.x, y: d.y, deltaX: 0, deltaY: 0 }, e.shiftKey, false);
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
        style={{ zIndex: isSelected ? 10 : 1 }}
        enableResizing={{
          top: true, right: true, bottom: true, left: true, 
          topRight: true, bottomRight: true, bottomLeft: true, topLeft: true
        }}
      >
        {innerContent}
      </Rnd>
    );
  };

  return (
    <div style={{ position: 'relative', width: '100%', minHeight: '100%', overflow: 'hidden' }}>
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
