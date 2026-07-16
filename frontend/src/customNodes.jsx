import React, { useEffect, useState } from 'react';
import { Handle, Position, useUpdateNodeInternals, NodeResizer, useStore } from '@xyflow/react';
import { Play, MessageSquare, BrainCircuit, Box, Terminal, Shuffle, LogOut, SplitSquareHorizontal, FileCode, Variable, Network, Repeat, Keyboard, Globe, Mail, MessageCircle, Clock, Braces, Merge, ArrowRightLeft, Database, UserCheck, Users, ChevronDown, ChevronRight, CreditCard } from 'lucide-react';
import axios from 'axios';

const calculateNodeCost = (tokens, model, currency) => {
  if (!tokens && tokens !== 0) return '-';

  // Approximate prices per 1M tokens (blended average of input/output for simplicity)
  let pricePer1M = 2.5;
  if (model) {
    if (model.includes('gpt-4o-mini')) pricePer1M = 0.3;
    else if (model.includes('gpt-4o')) pricePer1M = 10.0;
    else if (model.includes('gemini-3.5-flash')) pricePer1M = 0.15;
    else if (model.includes('gemini-1.5-flash') || model.includes('gemini-1.5-flash')) pricePer1M = 0.15;
    else if (model.includes('gemini-1.5-pro')) pricePer1M = 5.0;
    else if (model.includes('claude-3-5-sonnet')) pricePer1M = 9.0;
    else if (model.includes('claude-3-haiku')) pricePer1M = 0.75;
  }

  const usdCost = (tokens / 1000000) * pricePer1M;

  if (currency === 'KRW') {
    const krwRate = Number(localStorage.getItem('krwRate')) || 1400;
    return `₩${Math.round(usdCost * krwRate).toLocaleString()}`;
  }
  return usdCost < 0.0001 ? `$${usdCost.toFixed(6)}` : `$${usdCost.toFixed(4)}`;
};



const DetachedHandleRenderer = ({ id, fieldKey }) => {
  const updateNodeInternals = useUpdateNodeInternals();
  const detachedNodeId = `popout_${id}_${fieldKey}`;
  const detachedNodeX = useStore((s) => {
    const map = s.nodeLookup || s.nodeInternals;
    if (!map) return 0;
    const node = map.get(detachedNodeId);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });
  const parentNodeX = useStore((s) => {
    const map = s.nodeLookup || s.nodeInternals;
    if (!map) return 0;
    const node = map.get(id);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });

  const isOnLeft = detachedNodeX < parentNodeX;

  useEffect(() => {
    updateNodeInternals(id);
  }, [isOnLeft, id, updateNodeInternals]);

  return (
    <Handle
      className="popout-handle"
      type="target"
      position={isOnLeft ? Position.Left : Position.Right}
      id={`popout-${fieldKey}`}
      style={{
        left: isOnLeft ? '-10px' : '100%',
        top: '20px',
        background: '#ec4899',
        width: '10px',
        height: '10px',
        border: '2px solid white',
        borderRadius: '50%',
        transition: 'left 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        zIndex: 10
      }}
    />
  );
};

export const NodeDetachedHandles = ({ id, data }) => {
  if (!data) return null;
  const detachedKeys = Object.keys(data).filter(k => k.startsWith('isDetached_') && data[k]);
  return (
    <>
      {detachedKeys.map(k => {
        const fieldKey = k.replace('isDetached_', '');
        return <DetachedHandleRenderer key={fieldKey} id={id} fieldKey={fieldKey} />;
      })}
    </>
  );
};

export const DraggableTextarea = ({ id, fieldKey, value, onChange, placeholder, isDetached }) => {
  const [isEditing, setIsEditing] = useState(false);
  const updateNodeInternals = useUpdateNodeInternals();

  const detachedNodeId = `popout_${id}_${fieldKey}`;
  const detachedNodeX = useStore((s) => {
    const map = s.nodeLookup || s.nodeInternals;
    if (!map) return 0;
    const node = map.get(detachedNodeId);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });
  const parentNodeX = useStore((s) => {
    const map = s.nodeLookup || s.nodeInternals;
    if (!map) return 0;
    const node = map.get(id);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });

  

  const handleDragStart = (e) => {
    e.stopPropagation();
    e.dataTransfer.setData('application/reactflow-popout', JSON.stringify({ sourceId: id, key: fieldKey }));
    e.dataTransfer.effectAllowed = 'move';
  };

  if (isDetached) return null;

  return isEditing ? (
    <textarea
      className="nodrag"
      value={typeof value === 'object' ? JSON.stringify(value, null, 2) : (value || '')}
      onChange={(e) => onChange(id, fieldKey, e.target.value)}
      onBlur={() => setIsEditing(false)}
      autoFocus
      placeholder={placeholder || "텍스트를 입력하세요..."}
      style={{ minHeight: '80px', width: '100%' }}
    />
  ) : (
    <div
      className="nodrag"
      onDoubleClick={() => setIsEditing(true)}
      draggable
      onDragStart={handleDragStart}
      style={{
        minHeight: '80px',
        width: '100%',
        padding: '0.5rem',
        border: '1px dashed var(--border-color)',
        borderRadius: '4px',
        backgroundColor: 'var(--btn-active-bg)',
        color: value ? 'var(--text-color)' : 'var(--text-muted)',
        cursor: 'grab',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        fontSize: '0.85rem'
      }}
    >
      {typeof value === 'object' ? JSON.stringify(value) : (value || "더블클릭하여 수정하세요... (드래그하여 밖으로 분리)")}

    </div>
  );
};

export const StartNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node collapsed start ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Play size={16} color="#10b981" /> 시작</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body" style={{ textAlign: 'center', padding: '10px' }}>
          <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>시작점</p>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const PromptNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} prompt ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageSquare size={16} color="#3b82f6" /> 프롬프트</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>사용자 프롬프트</label>
          <DraggableTextarea id={id} fieldKey="userPrompt" value={data.userPrompt} onChange={data.onChange} placeholder="프롬프트를 입력하세요..." isDetached={data.isDetached_userPrompt} />
          {data.isTokenTrackingMode && (
            <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid #3b82f6', borderRadius: '6px', fontSize: '0.75rem', color: '#94a3b8' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                <span>예상 {data.tokenDisplayMode === 'cost' ? '금액' : '토큰'}:</span>
                <span style={{ color: '#60a5fa', fontWeight: 600 }}>{data.predictedTokens ? (data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.predictedTokens.min_tokens, null, data.costCurrency) : data.predictedTokens.min_tokens) : '-'}</span>
              </div>
            </div>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const LLMNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} llm ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><BrainCircuit size={16} color="#8b5cf6" /> LLM Node</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>AI 모델</label>
          <select
            className="nodrag"
            defaultValue={data.model || 'gemini-1.5-flash'}
            onChange={(e) => data.onChange(id, 'model', e.target.value)}
          >
            <optgroup label="Gemini">
              <option value="gemini-3.5-flash">Gemini 3.5 Flash</option>
              <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
              <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
            </optgroup>
            <optgroup label="ChatGPT">
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="gpt-4o">GPT-4o</option>
            </optgroup>
            <optgroup label="Claude">
              <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
              <option value="claude-3-5-sonnet-20240620">Claude 3.5 Sonnet</option>
            </optgroup>
          </select>

          <label>System Prompt</label>
          <DraggableTextarea id={id} fieldKey="systemPrompt" value={data.systemPrompt} onChange={data.onChange} placeholder="System instructions..." isDetached={data.isDetached_systemPrompt} />
          <label>User Prompt (Optional)</label>
          <DraggableTextarea id={id} fieldKey="userPrompt" value={data.userPrompt} onChange={data.onChange} placeholder="Enter question or user prompt..." isDetached={data.isDetached_userPrompt} />
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
            <input
              type="checkbox"
              id={`memory-${id}`}
              checked={data.useMemory || false}
              onChange={(e) => data.onChange(id, 'useMemory', e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            <label htmlFor={`memory-${id}`} style={{ margin: 0, cursor: 'pointer', fontSize: '0.8rem', color: '#cbd5e1' }}>
              💾 대화 기억하기 (DB 연동)
            </label>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
            <input
              type="checkbox"
              id={`structured-${id}`}
              checked={data.useStructuredOutput || false}
              onChange={(e) => {
                data.onChange(id, 'useStructuredOutput', e.target.checked);
                if (e.target.checked && !data.jsonSchema) {
                  data.onChange(id, 'jsonSchema', '{\n  "title": "Output",\n  "type": "object",\n  "properties": {\n    "answer": { "type": "string" }\n  }\n}');
                }
              }}
              style={{ cursor: 'pointer' }}
            />
            <label htmlFor={`structured-${id}`} style={{ margin: 0, cursor: 'pointer', fontSize: '0.8rem', color: '#cbd5e1' }}>
              [Structured Output 강제 (JSON)]
            </label>
          </div>
          {data.useStructuredOutput && (
            <>
              <label style={{ marginTop: '0.5rem', color: '#fcd34d' }}>JSON Schema</label>
              <DraggableTextarea id={id} fieldKey="jsonSchema" value={data.jsonSchema} onChange={data.onChange} placeholder="Enter JSON Schema..." isDetached={data.isDetached_jsonSchema} />
            </>
          )}
          {data.isTokenTrackingMode && (
            <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid #8b5cf6', borderRadius: '6px', fontSize: '0.75rem', color: '#94a3b8' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span>예상 {data.tokenDisplayMode === 'cost' ? '금액' : '토큰'} (최소~최대):</span>
                <span style={{ color: '#a78bfa', fontWeight: 600 }}>
                  {data.predictedTokens ? `${data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.predictedTokens.min_tokens, data.model, data.costCurrency) : data.predictedTokens.min_tokens} ~ ${data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.predictedTokens.max_tokens, data.model, data.costCurrency) : data.predictedTokens.max_tokens}` : '-'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(139, 92, 246, 0.2)', paddingTop: '4px' }}>
                <span>실제 소모:</span>
                <span style={{ color: '#10b981', fontWeight: 600 }}>
                  {data.actualTokens !== null ? (data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.actualTokens.total_tokens || 0, data.model, data.costCurrency) : (data.actualTokens.total_tokens || JSON.stringify(data.actualTokens))) : '-'}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const ValueNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const [isUploading, setIsUploading] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      if (response.data.status === 'success') {
        data.onChange(id, 'file_path', response.data.file_path);
        data.onChange(id, 'filename', response.data.filename);
      }
    } catch (error) {
      console.error('File upload failed:', error);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} value ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Variable size={16} color="#ec4899" /> 변수 (값)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Static Value or File</label>
          {data.filename ? (
            <div style={{ padding: '8px', backgroundColor: 'var(--btn-active-bg)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span title={data.file_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📎 {data.filename}</span>
              <button className="nodrag" onClick={() => { data.onChange(id, 'file_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>✕</button>
            </div>
          ) : (
            <DraggableTextarea id={id} fieldKey="value" value={data.value} onChange={data.onChange} placeholder="Enter a static value..." isDetached={data.isDetached_value} />
          )}

          {!data.filename && (
            <div style={{ marginTop: '8px' }}>
              <input
                type="file"
                id={`file-upload-${id}`}
                className="nodrag"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
                disabled={isUploading}
              />
              <label htmlFor={`file-upload-${id}`} className="nodrag" style={{ display: 'block', textAlign: 'center', padding: '4px 8px', backgroundColor: '#be185d', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
                {isUploading ? 'Uploading...' : 'Upload File (PDF, Excel, PPT, HWP)'}
              </label>
            </div>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const OutputNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} output ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        Output
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Final Result</div>
        </div>
      )}
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const ConditionNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  // Ensure we have a default rules array with stable IDs
  const rules = data.rules && data.rules.length > 0
    ? data.rules
    : [{ id: `${id}_rule_default`, operator: '==', value: '' }];
  const updateNodeInternals = useUpdateNodeInternals();

  useEffect(() => {
    updateNodeInternals(id);
  }, [rules.length, id, updateNodeInternals]);

  const addRule = () => {
    const newRules = [...rules, { id: `rule_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`, operator: '==', value: '' }];
    data.onChange(id, 'rules', newRules);
  };

  const removeRule = (ruleId) => {
    const newRules = rules.filter(r => r.id !== ruleId);
    data.onChange(id, 'rules', newRules);
  };

  const updateRule = (ruleId, key, value) => {
    const newRules = rules.map(r => r.id === ruleId ? { ...r, [key]: value } : r);
    data.onChange(id, 'rules', newRules);
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} condition ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ width: isExpanded ? '280px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        Switch / Branch
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">

          {rules.map((rule, index) => (
            <div key={rule.id} style={{ display: 'flex', alignItems: 'center', marginBottom: '0.5rem', position: 'relative' }}>
              <select
                className="nodrag"
                value={rule.operator}
                onChange={(e) => updateRule(rule.id, 'operator', e.target.value)}
                style={{ width: '35%', padding: '0.25rem', marginRight: '5px', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.75rem' }}
              >
                <option value="==">== (Equals)</option>
                <option value="Contains">Contains</option>
                <option value=">">&gt; (Greater)</option>
                <option value="<">&lt; (Less)</option>
                <option value=">=">&gt;=</option>
                <option value="<=">&lt;=</option>
              </select>

              <input
                type="text"
                className="nodrag"
                value={rule.value}
                onChange={(e) => updateRule(rule.id, 'value', e.target.value)}
                placeholder="Value"
                style={{ flex: 1, padding: '0.25rem', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.75rem', minWidth: 0 }}
              />

              <button
                onClick={() => removeRule(rule.id)}
                style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', marginLeft: '5px', padding: '0 5px' }}
                title="Remove Rule"
              >✕</button>

              {/* Handle positioned perfectly next to this row */}
              <Handle
                type="source"
                position={Position.Right}
                id={rule.id}
                style={{ right: '-16px', background: '#0ea5e9' }}
              />
            </div>
          ))}

          <div style={{ display: 'flex', justifyContent: 'center', marginTop: '0.5rem', marginBottom: '1rem' }}>
            <button
              className="nodrag"
              onClick={addRule}
              style={{ background: 'var(--btn-active-bg)', border: '1px dashed var(--border-color)', color: 'var(--text-muted)', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', width: '100%' }}
            >
              + Add Condition
            </button>
          </div>

          <div style={{ position: 'relative', marginTop: '1rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Else (Fallback)</span>
            <Handle
              type="source"
              position={Position.Right}
              id="else"
              style={{ right: '-16px', background: 'var(--text-muted)' }}
            />
          </div>

        </div>
      )}
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const LoopNode = ({ id, data, selected }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <>
      <NodeResizer minWidth={350} minHeight={250} isVisible={selected} lineClassName="border-blue-400" handleClassName="h-3 w-3 bg-white border-2 rounded" />
      <div
        className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} loop`}
        style={{
          width: '100%',
          height: '100%',
          backgroundColor: 'rgba(202, 138, 4, 0.1)',
          border: '2px dashed #ca8a04',
          borderRadius: '8px',
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        <Handle type="target" position={Position.Left} id="in" />
        <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ backgroundColor: '#ca8a04', borderRadius: '6px 6px 0 0', margin: '-2px -2px 0 -2px', cursor: 'pointer' }}>
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

          Loop Node (CoT Window)
          <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
        </div>
        {isExpanded && (
          <div className="node-body" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <label style={{ fontSize: '0.8rem', color: '#eab308' }}>Max Iters:</label>
              <input
                type="number"
                className="nodrag"
                defaultValue={data.maxIterations || 5}
                onChange={(e) => data.onChange(id, 'maxIterations', e.target.value)}
                style={{ width: isExpanded ? '60px' : undefined, padding: '0.1rem', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.75rem' }}
                min="1"
                max="100"
              />
            </div>

            {/* Internal Entry Point */}
            <div style={{ position: 'absolute', left: '10px', top: '50px', backgroundColor: 'var(--card-bg)', padding: '4px 8px', borderRadius: '4px', border: '1px solid #eab308', zIndex: 10 }}>
              <span style={{ fontSize: '0.7rem', color: '#eab308' }}>Loop Start</span>
              <Handle type="source" position={Position.Right} id="loop_start" style={{ right: '-8px', background: '#eab308' }} />
            </div>

            {/* Internal Exit Point */}
            <div style={{ position: 'absolute', right: '10px', bottom: '50px', backgroundColor: 'var(--card-bg)', padding: '4px 8px', borderRadius: '4px', border: '1px dashed #eab308', zIndex: 10 }}>
              <span style={{ fontSize: '0.7rem', color: '#eab308' }}>Loop Next</span>
              <Handle type="target" position={Position.Left} id="loop_next" style={{ left: '-8px', background: 'transparent', border: '2px solid #eab308' }} />
            </div>

            {/* Loop content area (visual guide only) */}
            <div style={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: 'rgba(234, 179, 8, 0.3)', fontSize: '0.9rem', pointerEvents: 'none' }}>
                Connect nodes here
              </span>
            </div>

            {/* Done handle placed at bottom right */}
            <div style={{ position: 'absolute', right: 0, bottom: '15px', width: '100%', textAlign: 'right', paddingRight: '10px' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Done</span>
              <Handle
                type="source"
                position={Position.Right}
                id="done"
                style={{ right: '-8px', background: 'var(--text-muted)' }}
              />
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export const BreakNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} break ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ border: '1px solid #ef4444' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ backgroundColor: '#dc2626', cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        Break Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Exit Loop</div>
        </div>
      )}
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const PythonNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const target = e.target;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const val = target.value;
      const newValue = val.substring(0, start) + '    ' + val.substring(end);

      data.onChange(id, 'code', newValue);

      // We need to set the cursor position back after the render
      setTimeout(() => {
        target.selectionStart = target.selectionEnd = start + 4;
      }, 0);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} python ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ border: '1px solid #3b82f6', width: isExpanded ? '300px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ backgroundColor: '#2563eb', cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        Python Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Input: `input_data`, Output: `output_data`</label>
          <DraggableTextarea id={id} fieldKey="code" value={data.code} onChange={data.onChange} placeholder="output_data = str(input_data) + " isDetached={data.isDetached_code} />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const TokenizerNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} tokenizer ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ border: '1px solid #10b981', width: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ backgroundColor: '#059669', cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        Tokenizer Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Parsing Method</label>
          <select
            className="nodrag"
            value={data.method || 'extract_text'}
            onChange={(e) => data.onChange(id, 'method', e.target.value)}
            style={{ width: '100%', padding: '0.4rem', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', marginTop: '0.5rem' }}
          >
            <option value="extract_text">Extract All Text</option>
            <option value="chunk_pages">Chunk by Page</option>
          </select>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Supports PDF, PPTX, Excel, HWP/HWPX
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const DistributorNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} distributor ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ border: '1px solid #8b5cf6', width: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ backgroundColor: '#7c3aed', cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        Distributor (For-Each)
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center' }}>
            Iterates over list items.<br />Outputs individual items.
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const FileModifierNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const [isUploading, setIsUploading] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('http://localhost:8000/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      if (response.data.status === 'success') {
        data.onChange(id, 'template_path', response.data.file_path);
        data.onChange(id, 'filename', response.data.filename);
      }
    } catch (error) {
      console.error('File upload failed:', error);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} file-modifier ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ border: '1px solid #f97316', width: isExpanded ? '260px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />

      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ backgroundColor: '#ea580c', cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        Auto Fill
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Template File</label>
          {data.filename ? (
            <div style={{ padding: '8px', backgroundColor: 'var(--btn-active-bg)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span title={data.template_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📎 {data.filename}</span>
              <button className="nodrag" onClick={() => { data.onChange(id, 'template_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>✕</button>
            </div>
          ) : (
            <div style={{ marginBottom: '8px' }}>
              <input
                type="file"
                id={`file-upload-template-${id}`}
                className="nodrag"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
                disabled={isUploading}
              />
              <label htmlFor={`file-upload-template-${id}`} className="nodrag" style={{ display: 'block', textAlign: 'center', padding: '6px', backgroundColor: '#ea580c', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
                {isUploading ? 'Uploading...' : 'Upload Template File'}
              </label>
            </div>
          )}

          <label>Output File Path</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.output_path || ''}
            onChange={(e) => data.onChange(id, 'output_path', e.target.value)}
            placeholder="e.g. output.hwp or output.xlsx"
            style={{ width: '100%', padding: '0.4rem', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', marginBottom: '8px' }}
          />

          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Requires JSON input. Replaces {'{{key}}'} in Excel/PPT and fills 누름틀 in HWP.
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const TemplateAnalyzerNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const [isUploading, setIsUploading] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('http://localhost:8000/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      if (response.data.status === 'success') {
        data.onChange(id, 'template_path', response.data.file_path);
        data.onChange(id, 'filename', response.data.filename);
      }
    } catch (error) {
      console.error('File upload failed:', error);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} template-analyzer ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ border: '1px solid #14b8a6', width: isExpanded ? '260px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ backgroundColor: '#0d9488', cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        Template Analyzer
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Template File</label>
          {data.filename ? (
            <div style={{ padding: '8px', backgroundColor: 'var(--btn-active-bg)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span title={data.template_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📎 {data.filename}</span>
              <button className="nodrag" onClick={() => { data.onChange(id, 'template_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>✕</button>
            </div>
          ) : (
            <div style={{ marginBottom: '8px' }}>
              <input
                type="file"
                id={`file-upload-analyzer-${id}`}
                className="nodrag"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
                disabled={isUploading}
              />
              <label htmlFor={`file-upload-analyzer-${id}`} className="nodrag" style={{ display: 'block', textAlign: 'center', padding: '6px', backgroundColor: '#0d9488', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
                {isUploading ? 'Uploading...' : 'Upload Blank Template'}
              </label>
            </div>
          )}

          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Analyzes the template and extracts placeholders {'{{key}}'} as a JSON schema.
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const DynamicInputNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const [uploading, setUploading] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      data.onChange(id, 'testValue', res.data.file_path);
    } catch (err) {
      console.error('File upload failed', err);
      alert('파일 업로드에 실패했습니다.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} dynamic-input ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Keyboard size={16} color="#d946ef" /> 동적 입력</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>입력 프롬프트 라벨</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.inputLabel || '사용자 입력을 기다립니다...'}
            onChange={(e) => data.onChange(id, 'inputLabel', e.target.value)}
            placeholder="예: 이름이 무엇인가요?"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          />

          <label>입력 타입</label>
          <select
            className="nodrag"
            value={data.inputType || 'text'}
            onChange={(e) => {
              data.onChange(id, 'inputType', e.target.value);
              data.onChange(id, 'testValue', ''); // Reset test value on type change
            }}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          >
            <option value="text">텍스트 (Text)</option>
            <option value="file">파일 (File)</option>
          </select>

          <label>테스트용 입력값 (에디터 실행용)</label>
          {(data.inputType === 'file') ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <input
                type="file"
                className="nodrag"
                onChange={handleFileUpload}
                disabled={uploading}
                style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}
              />
              {uploading && <span style={{ fontSize: '0.75rem', color: '#fbbf24' }}>업로드 중...</span>}
              {data.testValue && <span style={{ fontSize: '0.75rem', color: '#10b981', wordBreak: 'break-all' }}>업로드 완료: {data.testValue}</span>}
            </div>
          ) : (
            <input
              type="text"
              className="nodrag"
              value={data.testValue || ''}
              onChange={(e) => data.onChange(id, 'testValue', e.target.value)}
              placeholder="테스트 실행 시 사용할 값"
              style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
            />
          )}

          <label style={{ marginTop: '0.5rem', color: 'var(--text-muted)', fontSize: '0.75rem' }}>* 배포 모드에서 사용자에게 보일 입력 칸입니다.</label>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const WebCrawlerNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} crawler ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Globe size={16} color="#0ea5e9" /> 웹 크롤러</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>타겟 URL</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.url || ''}
            onChange={(e) => data.onChange(id, 'url', e.target.value)}
            placeholder="https://example.com"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
          />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const EmailNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} email ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Mail size={16} color="#f43f5e" /> 이메일 전송</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>수신자 이메일</label>
          <input
            type="email"
            className="nodrag"
            defaultValue={data.toEmail || ''}
            onChange={(e) => data.onChange(id, 'toEmail', e.target.value)}
            placeholder="receiver@example.com"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
          />
          <label style={{ marginTop: '0.5rem' }}>제목</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.subject || 'Auto Flow 알림'}
            onChange={(e) => data.onChange(id, 'subject', e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
          />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const KakaoNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} kakao ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageCircle size={16} color="#facc15" /> 카카오 알림톡</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>* 이전 노드의 결과값이 카카오톡 메시지로 전송됩니다.</p>
          <label style={{ marginTop: '0.5rem' }}>Access Token (필수)</label>
          <input
            type="password"
            className="nodrag"
            defaultValue={data.accessToken || ''}
            onChange={(e) => data.onChange(id, 'accessToken', e.target.value)}
            placeholder="Kakao REST API Access Token"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          />
          <label>수신자 (옵션)</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.receiver || ''}
            onChange={(e) => data.onChange(id, 'receiver', e.target.value)}
            placeholder="나에게 보내기(비워둠) 또는 수신자 uuid"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
          />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const DelayNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} delay ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '180px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Clock size={16} color="#3b82f6" /> Delay (대기)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>대기 시간 (초)</label>
          <input
            type="number"
            className="nodrag"
            defaultValue={data.seconds || 5}
            onChange={(e) => data.onChange(id, 'seconds', e.target.value)}
            min="1"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginTop: '0.5rem' }}
          />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const JsonParserNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} json-parser ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Braces size={16} color="#eab308" /> JSON Parser</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>파싱 모드</label>
          <select
            className="nodrag"
            defaultValue={data.mode || 'parse'}
            onChange={(e) => data.onChange(id, 'mode', e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginTop: '0.5rem' }}
          >
            <option value="parse">String to JSON (파싱)</option>
            <option value="stringify">JSON to String (문자열화)</option>
            <option value="extract">Extract Key (특정 키 추출)</option>
          </select>
          {data.mode === 'extract' && (
            <input
              type="text"
              className="nodrag"
              placeholder="추출할 키 이름 (예: result)"
              defaultValue={data.extractKey || ''}
              onChange={(e) => data.onChange(id, 'extractKey', e.target.value)}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginTop: '0.5rem' }}
            />
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const MergeNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} merge ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '200px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" style={{ height: '30px', width: isExpanded ? '8px' : undefined, borderRadius: '4px', background: '#ec4899' }} />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Merge size={16} color="#ec4899" /> Merge (데이터 병합)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>병합 방식</label>
          <select
            className="nodrag"
            defaultValue={data.mergeStrategy || 'join_newline'}
            onChange={(e) => data.onChange(id, 'mergeStrategy', e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginTop: '0.5rem' }}
          >
            <option value="join_newline">줄바꿈으로 합치기</option>
            <option value="join_comma">쉼표로 합치기</option>
            <option value="array">JSON 배열로 만들기</option>
          </select>
          <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', color: 'var(--text-muted)' }}>여러 노드를 왼쪽 핸들에 연결하세요.</p>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const HttpRequestNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} http-request ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><ArrowRightLeft size={16} color="#0ea5e9" /> HTTP Request</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Method</label>
          <select
            className="nodrag"
            defaultValue={data.method || 'GET'}
            onChange={(e) => data.onChange(id, 'method', e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          >
            <option value="GET">GET</option>
            <option value="POST">POST</option>
            <option value="PUT">PUT</option>
            <option value="DELETE">DELETE</option>
          </select>
          <label>URL</label>
          <input
            type="text"
            className="nodrag"
            placeholder="https://api.example.com/data"
            defaultValue={data.url || ''}
            onChange={(e) => data.onChange(id, 'url', e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          />
          <label>Headers (JSON)</label>
          <input
            type="text"
            className="nodrag"
            placeholder='{"Authorization": "Bearer token"}'
            defaultValue={data.headers || ''}
            onChange={(e) => data.onChange(id, 'headers', e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          />
          <label>Body (JSON)</label>
          <DraggableTextarea id={id} fieldKey="body" value={data.body} onChange={data.onChange} placeholder="{" isDetached={data.isDetached_body} />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const DatabaseNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} database ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Database size={16} color="#059669" /> 데이터베이스</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>연결 문자열 (URI)</label>
          <input
            type="text"
            className="nodrag"
            placeholder="sqlite:///data.db 또는 postgresql://..."
            defaultValue={data.connectionString || ''}
            onChange={(e) => data.onChange(id, 'connectionString', e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          />
          <label>SQL 쿼리</label>
          <DraggableTextarea id={id} fieldKey="query" value={data.query} onChange={data.onChange} placeholder="SELECT * FROM users;" isDetached={data.isDetached_query} />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const HumanApprovalNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} human-approval ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><UserCheck size={16} color="#f43f5e" /> 사용자 승인</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>승인 요청 메시지</label>
          <DraggableTextarea id={id} fieldKey="message" value={data.message} onChange={data.onChange} placeholder="다음 단계로 진행하시겠습니까?" isDetached={data.isDetached_message} />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

import { NodeRegistry } from './nodeRegistry';
import { Settings } from 'lucide-react';

export const DynamicNode = ({ id, data, type }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const meta = NodeRegistry[type] || {};
  return (
    <div className="custom-node" style={{ borderTop: `3px solid ${meta.color || '#3b82f6'}` }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ background: meta.headerColor || 'var(--btn-active-bg)', cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Settings size={16} color={meta.color} /> {meta.label || 'Task'}</div>
        <button className="btn-delete" onClick={() => data.onDelete && data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          {meta.fields?.map(f => (
            <div key={f.name}>
              <label>{f.label}</label>
              {f.type === 'textarea' ? (
                <textarea
                  className="nodrag"
                  defaultValue={data[f.name] || ''}
                  onChange={(e) => data.onChange && data.onChange(id, f.name, e.target.value)}
                  placeholder={f.placeholder}
                />
              ) : (
                <input
                  type={f.type}
                  className="nodrag"
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-color)', boxSizing: 'border-box' }}
                  defaultValue={data[f.name] || ''}
                  onChange={(e) => data.onChange && data.onChange(id, f.name, e.target.value)}
                  placeholder={f.placeholder}
                />
              )}
            </div>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const MultiAgentNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} multi-agent-node ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Top} id="tools" style={{ background: '#3b82f6', width: isExpanded ? '12px' : undefined, height: '12px', borderRadius: '4px' }} />
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Users size={16} color="#6366f1" /> Multi-Agent</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Agent Mode</label>
          <select
            className="nodrag"
            defaultValue={data.mode || 'supervisor'}
            onChange={(e) => data.onChange(id, 'mode', e.target.value)}
          >
            <option value="supervisor">Supervisor (Delegation)</option>
            <option value="group_chat">Group Chat (Debate)</option>
            <option value="tool_agent">Tool-using Agent</option>
          </select>

          {(!data.mode || data.mode === 'supervisor') && (
            <>
              <label>Supervisor Prompt</label>
              <DraggableTextarea id={id} fieldKey="supervisorPrompt" value={data.supervisorPrompt} onChange={data.onChange} placeholder="System prompt for supervisor..." isDetached={data.isDetached_supervisorPrompt} />
            </>
          )}

          {data.mode === 'group_chat' && (
            <>
              <label>Max Rounds</label>
              <input
                type="number"
                className="nodrag"
                defaultValue={data.maxRounds || 3}
                onChange={(e) => data.onChange(id, 'maxRounds', parseInt(e.target.value))}
              />
            </>
          )}

          {data.mode === 'tool_agent' && (
            <>
              <label>Agent Prompt</label>
              <DraggableTextarea id={id} fieldKey="agentPrompt" value={data.agentPrompt} onChange={data.onChange} placeholder="System prompt for tool agent..." isDetached={data.isDetached_agentPrompt} />
            </>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const ScheduleNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} schedule ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '200px' : undefined }}>
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Clock size={16} color="#8b5cf6" /> 스케줄 (시작)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div className="input-group">
            <label>Cron 표현식</label>
            <input
              type="text"
              className="nodrag"
              value={data.cronExpression || ''}
              onChange={(e) => data.onChange(id, 'cronExpression', e.target.value)}
              placeholder="0 7 * * *"
            />
            <small style={{ display: 'block', marginTop: '4px', color: 'var(--text-muted)' }}>예: 0 7 * * * (매일 오전 7시)</small>
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const DiscordNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} discord ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageCircle size={16} color="#5865F2" /> 디스코드 발송</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div className="input-group">
            <label>Bot Token 또는 Webhook URL</label>
            <input
              type="password"
              className="nodrag"
              value={data.botToken || ''}
              onChange={(e) => data.onChange(id, 'botToken', e.target.value)}
              placeholder="Bot token / Webhook"
            />
          </div>
          <div className="input-group">
            <label>채널 ID (Webhook시 생략)</label>
            <input
              type="text"
              className="nodrag"
              value={data.channelId || ''}
              onChange={(e) => data.onChange(id, 'channelId', e.target.value)}
              placeholder="1234567890"
            />
          </div>
        </div>
      )}
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};



export const DetachedTextNode = ({ id, data }) => {
  const [localValue, setLocalValue] = useState(data.value || '');
  const updateNodeInternals = useUpdateNodeInternals();

  const parentNodeX = useStore((s) => {
    const map = s.nodeLookup || s.nodeInternals;
    if (!map) return 0;
    const node = map.get(data.sourceId);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });

  const myNodeX = useStore((s) => {
    const map = s.nodeLookup || s.nodeInternals;
    if (!map) return 0;
    const node = map.get(id);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });

  // If myNodeX is less than parentNodeX, I am on the left. So my handle should be on my RIGHT.
  // If I am on the right, my handle should be on my LEFT.
  const isOnLeft = myNodeX < parentNodeX;

  useEffect(() => {
    updateNodeInternals(id);
  }, [isOnLeft, id, updateNodeInternals]);

  const handleChange = (e) => {
    const val = e.target.value;
    setLocalValue(val);
    data.onChange(data.sourceId, data.fieldKey, val);
  };

  return (
    <div className={`custom-node expanded detached-text-node`} style={{ minWidth: '300px' }}>
      <div className="node-header" style={{ padding: '0.5rem 1rem', background: 'var(--btn-active-bg)', cursor: 'grab' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}>
          <span>{data.label || 'Detached Text'}</span>
        </div>
      </div>
      <div className="node-body">
        <textarea
          className="nodrag"
          value={localValue}
          onChange={handleChange}
          placeholder="텍스트를 입력하세요..."
          style={{ minHeight: '150px' }}
        />
      </div>
      <Handle
        type="source"
        position={isOnLeft ? Position.Right : Position.Left}
        id="out"
        style={{
          transition: 'left 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          left: isOnLeft ? '100%' : '0%',
        }}
      />
      <NodeDetachedHandles id={id} data={data} />

    </div>
  );
};

export const WebhookNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} webhook-node ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: 'pointer', background: 'linear-gradient(135deg, #0ea5e9, #0284c7)' }}>
        {isExpanded ? <ChevronDown size={14} color="white"/> : <ChevronRight size={14} color="white"/>}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'white' }}><Globe size={16} /> {data.label || '웹훅 수신'}</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Webhook URL (경로)</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.webhookUrl || '/webhook/your-endpoint'}
            onChange={(e) => data.onChange(id, 'webhookUrl', e.target.value)}
            placeholder="/webhook/my-trigger"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          />
          <div style={{fontSize: '11px', color: '#666', marginTop: '4px'}}>
            이 URL로 POST 요청이 오면 플로우가 시작됩니다.
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};
