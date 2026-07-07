import React, { useEffect } from 'react';
import { Handle, Position, useUpdateNodeInternals } from '@xyflow/react';

export const PromptNode = ({ id, data }) => {
  return (
    <div className="custom-node prompt">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        Prompt Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <label>User Prompt</label>
        <textarea 
          className="nodrag"
          defaultValue={data.userPrompt || ''}
          onChange={(e) => data.onChange(id, 'userPrompt', e.target.value)}
          placeholder="Enter user prompt..."
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
        LLM Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <label>Model</label>
        <select 
          className="nodrag"
          defaultValue={data.model || 'gemini-3.5-flash'}
          onChange={(e) => data.onChange(id, 'model', e.target.value)}
        >
          <option value="gemini-3.5-flash">Gemini 3.5 Flash</option>
        </select>
        
        <label>System Prompt</label>
        <textarea 
          className="nodrag"
          defaultValue={data.systemPrompt || 'You are a helpful assistant.'}
          onChange={(e) => data.onChange(id, 'systemPrompt', e.target.value)}
          placeholder="Enter system prompt..."
        />
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const ValueNode = ({ id, data }) => {
  return (
    <div className="custom-node value">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header">
        Value Node
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      <div className="node-body">
        <label>Static Value</label>
        <textarea 
          className="nodrag"
          defaultValue={data.value || ''}
          onChange={(e) => data.onChange(id, 'value', e.target.value)}
          placeholder="Enter a static value or template..."
        />
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
        <div style={{fontSize: '0.8rem', color: '#ccc'}}>Final Result</div>
      </div>
    </div>
  );
};

export const ConditionNode = ({ id, data }) => {
  // Ensure we have a default rules array
  const rules = data.rules || [{ id: `rule_${Date.now()}`, operator: '==', value: '' }];
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
              style={{ width: '35%', padding: '0.25rem', marginRight: '5px', backgroundColor: 'var(--bg-color)', color: 'white', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.75rem' }}
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
              style={{ flex: 1, padding: '0.25rem', backgroundColor: 'var(--bg-color)', color: 'white', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.75rem', minWidth: 0 }}
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
            style={{ background: 'rgba(255,255,255,0.1)', border: '1px dashed #ccc', color: '#ccc', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', width: '100%' }}
          >
            + Add Condition
          </button>
        </div>

        <div style={{ position: 'relative', marginTop: '1rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Else (Fallback)</span>
          <Handle 
            type="source" 
            position={Position.Right} 
            id="else" 
            style={{ right: '-16px', background: '#94a3b8' }} 
          />
        </div>

      </div>
    </div>
  );
};
