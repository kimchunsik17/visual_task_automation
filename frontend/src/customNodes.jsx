import React, { useEffect, useState } from 'react';
import { Handle, Position, useUpdateNodeInternals, NodeResizer } from '@xyflow/react';
import { Play, MessageSquare, BrainCircuit, Box, Terminal, Shuffle, LogOut, SplitSquareHorizontal, FileCode, Variable, Network, Repeat, Keyboard, Globe, Mail, MessageCircle, Clock, Braces, Merge, ArrowRightLeft, Database, UserCheck, Users } from 'lucide-react';
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
    return `₩${Math.round(usdCost * 1400).toLocaleString()}`;
  }
  return usdCost < 0.0001 ? `$${usdCost.toFixed(6)}` : `$${usdCost.toFixed(4)}`;
};

export const StartNode = ({ id, data }) => {
  return (
    <div className="custom-node start" style={{ minWidth: '150px' }}>
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Play size={16} color="#10b981"/> 시작</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body" style={{ textAlign: 'center', padding: '10px' }}>
        <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>시작점</p>
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const PromptNode = ({ id, data }) => {
  return (
    <div className="custom-node prompt">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageSquare size={16} color="#3b82f6"/> 프롬프트</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <label>사용자 프롬프트</label>
        <textarea 
          className="nodrag"
          defaultValue={data.userPrompt || ''}
          onChange={(e) => data.onChange(id, 'userPrompt', e.target.value)}
          placeholder="프롬프트를 입력하세요..."
        />
        {data.isTokenTrackingMode && (
          <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid #3b82f6', borderRadius: '6px', fontSize: '0.75rem', color: '#94a3b8' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
              <span>예상 {data.tokenDisplayMode === 'cost' ? '금액' : '토큰'}:</span>
              <span style={{ color: '#60a5fa', fontWeight: 600 }}>{data.predictedTokens ? (data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.predictedTokens.min_tokens, null, data.costCurrency) : data.predictedTokens.min_tokens) : '-'}</span>
            </div>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const LLMNode = ({ id, data }) => {
  return (
    <div className="custom-node llm">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><BrainCircuit size={16} color="#8b5cf6"/> LLM Node</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
        <textarea 
          className="nodrag"
          defaultValue={data.systemPrompt || 'You are a helpful assistant.'}
          onChange={(e) => data.onChange(id, 'systemPrompt', e.target.value)}
          placeholder="System instructions..."
        />
        <label>User Prompt (Optional)</label>
        <textarea 
          className="nodrag"
          defaultValue={data.userPrompt || ''}
          onChange={(e) => data.onChange(id, 'userPrompt', e.target.value)}
          placeholder="Enter question or user prompt..."
        />
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
            <textarea 
              className="nodrag"
              style={{ fontFamily: 'monospace', fontSize: '0.75rem', height: '100px', background: '#1e293b', color: '#a7f3d0' }}
              value={data.jsonSchema || ''}
              onChange={(e) => data.onChange(id, 'jsonSchema', e.target.value)}
              placeholder="Enter JSON Schema..."
            />
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const ValueNode = ({ id, data }) => {
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
    <div className="custom-node value">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Variable size={16} color="#ec4899"/> 변수 (값)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <label>Static Value or File</label>
        {data.filename ? (
          <div style={{ padding: '8px', backgroundColor: 'var(--btn-active-bg)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span title={data.file_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📎 {data.filename}</span>
            <button className="nodrag" onClick={() => { data.onChange(id, 'file_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>✕</button>
          </div>
        ) : (
          <textarea 
            className="nodrag"
            value={data.value || ''}
            onChange={(e) => data.onChange(id, 'value', e.target.value)}
            placeholder="Enter a static value..."
          />
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
            <label htmlFor={`file-upload-${id}`} style={{ display: 'block', textAlign: 'center', padding: '4px 8px', backgroundColor: '#be185d', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
              {isUploading ? 'Uploading...' : 'Upload File (PDF, Excel, PPT, HWP)'}
            </label>
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const OutputNode = ({ id, data }) => {
  return (
    <div className="custom-node output">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        Output
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <div style={{fontSize: '0.8rem', color: 'var(--text-muted)'}}>Final Result</div>
      </div>
    </div>
  );
};

export const ConditionNode = ({ id, data }) => {
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
    <div className="custom-node condition" style={{ width: '280px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        Switch / Branch
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
    </div>
  );
};

export const LoopNode = ({ id, data, selected }) => {
  return (
    <>
      <NodeResizer minWidth={350} minHeight={250} isVisible={selected} lineClassName="border-blue-400" handleClassName="h-3 w-3 bg-white border-2 rounded" />
      <div 
        className={`custom-node loop`} 
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
        <div className="node-header" style={{ backgroundColor: '#ca8a04', borderRadius: '6px 6px 0 0', margin: '-2px -2px 0 -2px' }}>
          Loop Node (CoT Window)
          <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
        </div>
        <div className="node-body" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <label style={{ fontSize: '0.8rem', color: '#eab308' }}>Max Iters:</label>
            <input 
              type="number"
              className="nodrag"
              defaultValue={data.maxIterations || 5}
              onChange={(e) => data.onChange(id, 'maxIterations', e.target.value)}
              style={{ width: '60px', padding: '0.1rem', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.75rem' }}
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
             <span style={{color: 'rgba(234, 179, 8, 0.3)', fontSize: '0.9rem', pointerEvents: 'none'}}>
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
      </div>
    </>
  );
};

export const BreakNode = ({ id, data }) => {
  return (
    <div className="custom-node break" style={{ border: '1px solid #ef4444' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" style={{ backgroundColor: '#dc2626' }}>
        Break Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <div style={{fontSize: '0.8rem', color: 'var(--text-muted)'}}>Exit Loop</div>
      </div>
    </div>
  );
};

export const PythonNode = ({ id, data }) => {
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
    <div className="custom-node python" style={{ border: '1px solid #3b82f6', width: '300px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" style={{ backgroundColor: '#2563eb' }}>
        Python Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <label>Input: `input_data`, Output: `output_data`</label>
        <textarea
          className="nodrag"
          placeholder="output_data = str(input_data) + ' processed'"
          value={data.code || ''}
          onChange={(e) => data.onChange(id, 'code', e.target.value)}
          onKeyDown={handleKeyDown}
          style={{
            width: '100%',
            height: '120px',
            fontFamily: 'monospace',
            backgroundColor: 'var(--bg-color)',
            color: 'var(--text-color)',
            border: '1px solid var(--border-color)',
            padding: '8px',
            borderRadius: '4px',
            fontSize: '0.8rem',
            resize: 'vertical'
          }}
        />
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const TokenizerNode = ({ id, data }) => {
  return (
    <div className="custom-node tokenizer" style={{ border: '1px solid #10b981', width: '250px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" style={{ backgroundColor: '#059669' }}>
        Tokenizer Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const DistributorNode = ({ id, data }) => {
  return (
    <div className="custom-node distributor" style={{ border: '1px solid #8b5cf6', width: '220px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" style={{ backgroundColor: '#7c3aed' }}>
        Distributor (For-Each)
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center' }}>
          Iterates over list items.<br/>Outputs individual items.
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const FileModifierNode = ({ id, data }) => {
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
    <div className="custom-node file-modifier" style={{ border: '1px solid #f97316', width: '260px' }}>
      <Handle type="target" position={Position.Left} id="in" />

      <div className="node-header" style={{ backgroundColor: '#ea580c' }}>
        Auto Fill
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
            <label htmlFor={`file-upload-template-${id}`} style={{ display: 'block', textAlign: 'center', padding: '6px', backgroundColor: '#ea580c', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const TemplateAnalyzerNode = ({ id, data }) => {
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
    <div className="custom-node template-analyzer" style={{ border: '1px solid #14b8a6', width: '260px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" style={{ backgroundColor: '#0d9488' }}>
        Template Analyzer
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
            <label htmlFor={`file-upload-analyzer-${id}`} style={{ display: 'block', textAlign: 'center', padding: '6px', backgroundColor: '#0d9488', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
              {isUploading ? 'Uploading...' : 'Upload Blank Template'}
            </label>
          </div>
        )}
        
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
          Analyzes the template and extracts placeholders {'{{key}}'} as a JSON schema.
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const DynamicInputNode = ({ id, data }) => {
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
    <div className="custom-node dynamic-input" style={{ minWidth: '220px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Keyboard size={16} color="#d946ef"/> 동적 입력</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const WebCrawlerNode = ({ id, data }) => {
  return (
    <div className="custom-node crawler" style={{ minWidth: '250px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Globe size={16} color="#0ea5e9"/> 웹 크롤러</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const EmailNode = ({ id, data }) => {
  return (
    <div className="custom-node email" style={{ minWidth: '250px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Mail size={16} color="#f43f5e"/> 이메일 전송</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const KakaoNode = ({ id, data }) => {
  return (
    <div className="custom-node kakao" style={{ minWidth: '220px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageCircle size={16} color="#facc15"/> 카카오 알림톡</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>* 이전 노드의 결과값이 카카오톡 메시지로 전송됩니다.</p>
        <label style={{ marginTop: '0.5rem' }}>수신자 (옵션)</label>
        <input 
          type="text"
          className="nodrag"
          defaultValue={data.receiver || ''}
          onChange={(e) => data.onChange(id, 'receiver', e.target.value)}
          placeholder="전화번호 또는 ID"
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
        />
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const DelayNode = ({ id, data }) => {
  return (
    <div className="custom-node delay" style={{ minWidth: '180px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Clock size={16} color="#3b82f6"/> Delay (대기)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const JsonParserNode = ({ id, data }) => {
  return (
    <div className="custom-node json-parser" style={{ minWidth: '220px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Braces size={16} color="#eab308"/> JSON Parser</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const MergeNode = ({ id, data }) => {
  return (
    <div className="custom-node merge" style={{ minWidth: '200px' }}>
      <Handle type="target" position={Position.Left} id="in" style={{ height: '30px', width: '8px', borderRadius: '4px', background: '#ec4899' }} />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Merge size={16} color="#ec4899"/> Merge (데이터 병합)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const HttpRequestNode = ({ id, data }) => {
  return (
    <div className="custom-node http-request" style={{ minWidth: '250px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><ArrowRightLeft size={16} color="#0ea5e9"/> HTTP Request</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
        <textarea 
          className="nodrag"
          rows={3}
          placeholder='{"key": "value"}'
          defaultValue={data.body || ''}
          onChange={(e) => data.onChange(id, 'body', e.target.value)}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', resize: 'vertical' }}
        />
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const DatabaseNode = ({ id, data }) => {
  return (
    <div className="custom-node database" style={{ minWidth: '250px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Database size={16} color="#059669"/> 데이터베이스</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
        <textarea 
          className="nodrag"
          rows={3}
          placeholder="SELECT * FROM users;"
          defaultValue={data.query || ''}
          onChange={(e) => data.onChange(id, 'query', e.target.value)}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', resize: 'vertical' }}
        />
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const HumanApprovalNode = ({ id, data }) => {
  return (
    <div className="custom-node human-approval" style={{ minWidth: '220px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><UserCheck size={16} color="#f43f5e"/> 사용자 승인</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <label>승인 요청 메시지</label>
        <textarea 
          className="nodrag"
          rows={2}
          placeholder="다음 단계로 진행하시겠습니까?"
          defaultValue={data.message || '승인이 필요합니다.'}
          onChange={(e) => data.onChange(id, 'message', e.target.value)}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', resize: 'vertical' }}
        />
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

import { NodeRegistry } from './nodeRegistry';
import { Settings } from 'lucide-react';

export const DynamicNode = ({ id, data, type }) => {
  const meta = NodeRegistry[type] || {};
  return (
    <div className="custom-node" style={{ borderTop: `3px solid ${meta.color || '#3b82f6'}` }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" style={{ background: meta.headerColor || 'var(--btn-active-bg)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Settings size={16} color={meta.color}/> {meta.label || 'Task'}</div>
        <button className="btn-delete" onClick={() => data.onDelete && data.onDelete(id)}>✕</button>
      </div>
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const MultiAgentNode = ({ id, data }) => {
  return (
    <div className="custom-node multi-agent-node">
      <Handle type="target" position={Position.Top} id="tools" style={{ background: '#3b82f6', width: '12px', height: '12px', borderRadius: '4px' }} />
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Users size={16} color="#6366f1"/> Multi-Agent</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
            <textarea 
              className="nodrag"
              defaultValue={data.supervisorPrompt || '당신은 매니저입니다. 작업에 가장 적합한 전문가를 선택하세요.'}
              onChange={(e) => data.onChange(id, 'supervisorPrompt', e.target.value)}
              placeholder="System prompt for supervisor..."
            />
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
            <textarea 
              className="nodrag"
              defaultValue={data.agentPrompt || '당신은 자율 에이전트입니다. 주어진 도구를 사용하여 작업을 수행하세요.'}
              onChange={(e) => data.onChange(id, 'agentPrompt', e.target.value)}
              placeholder="System prompt for tool agent..."
            />
          </>
        )}
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const ScheduleNode = ({ id, data }) => {
  return (
    <div className="custom-node schedule" style={{ minWidth: '200px' }}>
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Clock size={16} color="#8b5cf6"/> 스케줄 (시작)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
          <small style={{display: 'block', marginTop: '4px', color: 'var(--text-muted)'}}>예: 0 7 * * * (매일 오전 7시)</small>
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const DiscordNode = ({ id, data }) => {
  return (
    <div className="custom-node discord">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageCircle size={16} color="#5865F2"/> 디스코드 발송</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
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
    </div>
  );
};

