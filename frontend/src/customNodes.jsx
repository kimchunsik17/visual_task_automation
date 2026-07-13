import React, { useEffect, useState } from 'react';
import { Handle, Position, useUpdateNodeInternals, NodeResizer } from '@xyflow/react';
import { Play, MessageSquare, BrainCircuit, Box, Terminal, Shuffle, LogOut, SplitSquareHorizontal, FileCode, Variable, Network, Repeat, Keyboard, Globe, Mail, MessageCircle, Clock, Braces, Merge, ArrowRightLeft, Database, UserCheck } from 'lucide-react';
import axios from 'axios';

export const StartNode = ({ id, data }) => {
  return (
    <div className="custom-node start" style={{ minWidth: '150px' }}>
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Play size={16} color="#10b981"/> ?úÏûë</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body" style={{ textAlign: 'center', padding: '10px' }}>
        <p style={{ margin: 0, fontSize: '0.85rem', color: '#cbd5e1' }}>?úÏûë??/p>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageSquare size={16} color="#3b82f6"/> ?ÑÎ°¨?ÑÌä∏</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>?¨Ïö©???ÑÎ°¨?ÑÌä∏</label>
        <textarea 
          className="nodrag"
          defaultValue={data.userPrompt || ''}
          onChange={(e) => data.onChange(id, 'userPrompt', e.target.value)}
          placeholder="?ÑÎ°¨?ÑÌä∏Î•??ÖÎ†•?òÏÑ∏??.."
        />
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>AI Î™®Îç∏</label>
        <select 
          className="nodrag"
          defaultValue={data.model || 'gemini-3.5-flash'}
          onChange={(e) => data.onChange(id, 'model', e.target.value)}
        >
          <optgroup label="Gemini">
            <option value="gemini-3.5-flash">Gemini 3.5 Flash</option>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Variable size={16} color="#ec4899"/> Î≥Ä??(Í∞?</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>Static Value or File</label>
        {data.filename ? (
          <div style={{ padding: '8px', backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span title={data.file_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>?ìé {data.filename}</span>
            <button className="nodrag" onClick={() => { data.onChange(id, 'file_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>??/button>
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <div style={{fontSize: '0.8rem', color: '#ccc'}}>Final Result</div>
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
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
            >??/button>

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
            style={{ background: 'rgba(255,255,255,0.1)', border: '1px dashed #ccc', color: '#ccc', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', width: '100%' }}
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
          <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <div style={{fontSize: '0.8rem', color: '#ccc'}}>Exit Loop</div>
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
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
            backgroundColor: '#1e293b',
            color: '#f8fafc',
            border: '1px solid #334155',
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <div style={{ fontSize: '0.75rem', color: '#ccc', textAlign: 'center' }}>
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>Template File</label>
        {data.filename ? (
          <div style={{ padding: '8px', backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span title={data.template_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>?ìé {data.filename}</span>
            <button className="nodrag" onClick={() => { data.onChange(id, 'template_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>??/button>
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
          Requires JSON input. Replaces {'{{key}}'} in Excel/PPT and fills ?ÑÎ¶Ñ?Ä in HWP.
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>Template File</label>
        {data.filename ? (
          <div style={{ padding: '8px', backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span title={data.template_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>?ìé {data.filename}</span>
            <button className="nodrag" onClick={() => { data.onChange(id, 'template_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>??/button>
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
  return (
    <div className="custom-node dynamic-input" style={{ minWidth: '220px' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Keyboard size={16} color="#d946ef"/> ?ôÏ†Å ?ÖÎ†•</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>?ÖÎ†• ?ÑÎ°¨?ÑÌä∏ ?ºÎ≤®</label>
        <input 
          type="text"
          className="nodrag"
          defaultValue={data.inputLabel || '?¨Ïö©???ÖÎ†•??Í∏∞Îã§Î¶ΩÎãà??..'}
          onChange={(e) => data.onChange(id, 'inputLabel', e.target.value)}
          placeholder="?? ?¥Î¶Ñ??Î¨¥Ïóá?∏Í???"
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
        />
        <label>?åÏä§?∏Ïö© ?ÖÎ†•Í∞?(?êÎîî???§Ìñâ??</label>
        <input 
          type="text"
          className="nodrag"
          defaultValue={data.testValue || ''}
          onChange={(e) => data.onChange(id, 'testValue', e.target.value)}
          placeholder="?åÏä§???§Ìñâ ???¨Ïö©??Í∞?
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
        />
        <label style={{ marginTop: '0.5rem', color: 'var(--text-muted)', fontSize: '0.75rem' }}>* Î∞∞Ìè¨ Î™®Îìú?êÏÑú ?¨Ïö©?êÏóêÍ≤?Î≥¥Ïùº ?ÖÎ†•Ïπ∏ÏûÖ?àÎã§.</label>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Globe size={16} color="#0ea5e9"/> ???¨Î°§??/div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>?ÄÍ≤?URL</label>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Mail size={16} color="#f43f5e"/> ?¥Î©î???ÑÏÜ°</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>?òÏã†???¥Î©î??/label>
        <input 
          type="email"
          className="nodrag"
          defaultValue={data.toEmail || ''}
          onChange={(e) => data.onChange(id, 'toEmail', e.target.value)}
          placeholder="receiver@example.com"
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
        />
        <label style={{ marginTop: '0.5rem' }}>?úÎ™©</label>
        <input 
          type="text"
          className="nodrag"
          defaultValue={data.subject || 'Auto Flow ?åÎ¶º'}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageCircle size={16} color="#facc15"/> Ïπ¥Ïπ¥???åÎ¶º??/div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>* ?¥Ï†Ñ ?∏Îìú??Í≤∞Í≥ºÍ∞íÏù¥ Ïπ¥Ïπ¥?§ÌÜ° Î©îÏãúÏßÄÎ°??ÑÏÜ°?©Îãà??</p>
        <label style={{ marginTop: '0.5rem' }}>?òÏã†??(?µÏÖò)</label>
        <input 
          type="text"
          className="nodrag"
          defaultValue={data.receiver || ''}
          onChange={(e) => data.onChange(id, 'receiver', e.target.value)}
          placeholder="?ÑÌôîÎ≤àÌò∏ ?êÎäî ID"
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Clock size={16} color="#3b82f6"/> Delay (?ÄÍ∏?</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>?ÄÍ∏??úÍ∞Ñ (Ï¥?</label>
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>?åÏã± Î™®Îìú</label>
        <select 
          className="nodrag"
          defaultValue={data.mode || 'parse'}
          onChange={(e) => data.onChange(id, 'mode', e.target.value)}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginTop: '0.5rem' }}
        >
          <option value="parse">String to JSON (?åÏã±)</option>
          <option value="stringify">JSON to String (Î¨∏Ïûê?¥Ìôî)</option>
          <option value="extract">Extract Key (?πÏ†ï ??Ï∂îÏ∂ú)</option>
        </select>
        {data.mode === 'extract' && (
          <input 
            type="text"
            className="nodrag"
            placeholder="Ï∂îÏ∂ú?????¥Î¶Ñ (?? result)"
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Merge size={16} color="#ec4899"/> Merge (?∞Ïù¥??Î≥ëÌï©)</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>Î≥ëÌï© Î∞©Ïãù</label>
        <select 
          className="nodrag"
          defaultValue={data.mergeStrategy || 'join_newline'}
          onChange={(e) => data.onChange(id, 'mergeStrategy', e.target.value)}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginTop: '0.5rem' }}
        >
          <option value="join_newline">Ï§ÑÎ∞îÍøàÏúºÎ°??©ÏπòÍ∏?/option>
          <option value="join_comma">?ºÌëúÎ°??©ÏπòÍ∏?/option>
          <option value="array">JSON Î∞∞Ïó¥Î°?ÎßåÎì§Í∏?/option>
        </select>
        <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', color: 'var(--text-muted)' }}>?¨Îü¨ ?∏ÎìúÎ•??ºÏ™Ω ?∏Îì§???∞Í≤∞?òÏÑ∏??</p>
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
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Database size={16} color="#059669"/> ?∞Ïù¥?∞Î≤†?¥Ïä§</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>?∞Í≤∞ Î¨∏Ïûê??(URI)</label>
        <input 
          type="text"
          className="nodrag"
          placeholder="sqlite:///data.db ?êÎäî postgresql://..."
          defaultValue={data.connectionString || ''}
          onChange={(e) => data.onChange(id, 'connectionString', e.target.value)}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
        />
        <label>SQL ÏøºÎ¶¨</label>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><UserCheck size={16} color="#f43f5e"/> ?¨Ïö©???πÏù∏</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>??/button>
      </div>
      <div className="node-body">
        <label>?πÏù∏ ?îÏ≤≠ Î©îÏãúÏßÄ</label>
        <textarea 
          className="nodrag"
          rows={2}
          placeholder="?§Ïùå ?®Í≥ÑÎ°?ÏßÑÌñâ?òÏãúÍ≤†Ïäµ?àÍπå?"
          defaultValue={data.message || '?πÏù∏???ÑÏöî?©Îãà??'}
          onChange={(e) => data.onChange(id, 'message', e.target.value)}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', resize: 'vertical' }}
        />
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};
