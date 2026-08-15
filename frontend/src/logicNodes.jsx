import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { Play, LogIn, LogOut, ArrowRight, Activity, Database, Sparkles, Code2 } from 'lucide-react';

const NodeWrapper = ({ title, icon, color, children, selected }) => (
  <div style={{
    background: '#1e293b',
    border: `2px solid ${selected ? '#3b82f6' : '#334155'}`,
    borderRadius: '8px',
    boxShadow: selected ? '0 0 0 4px rgba(59, 130, 246, 0.2)' : '0 4px 6px -1px rgba(0,0,0,0.2)',
    width: '250px',
    fontSize: '12px',
    color: '#e2e8f0',
    overflow: 'hidden'
  }}>
    <div style={{
      background: color,
      padding: '8px 12px',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      fontWeight: 'bold',
      color: 'white'
    }}>
      {icon} {title}
    </div>
    <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {children}
    </div>
  </div>
);

const ComponentSelect = ({ components, value, onChange }) => {
  // Flatten components for select
  const flatten = (comps) => {
    let result = [];
    comps.forEach(c => {
      result.push({ id: c.id, label: `${c.type} (${c.id.substring(0,6)}...)` });
      if (c.children) result = result.concat(flatten(c.children));
    });
    return result;
  };
  const flatComps = flatten(components || []);
  
  return (
    <select value={value || ''} onChange={onChange} style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}>
      <option value="" disabled>Select Component</option>
      {flatComps.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
    </select>
  );
};

export const TriggerNode = ({ data, selected }) => (
  <NodeWrapper title="Event Trigger" icon={<Play size={14} />} color="#ef4444" selected={selected}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>Target Component</label>
      <ComponentSelect components={data.components} value={data.componentId} onChange={e => data.onChange(data.id, 'componentId', e.target.value)} />
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>Event Type</label>
      <select value={data.eventType || 'onClick'} onChange={e => data.onChange(data.id, 'eventType', e.target.value)} style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}>
        <option value="onClick">On Click</option>
      </select>
    </div>
    <Handle type="source" position={Position.Right} id="trigger" style={{ background: '#ef4444', width: '10px', height: '10px', right: '-6px' }} />
  </NodeWrapper>
);

export const ActionNode = ({ data, selected }) => (
  <NodeWrapper title="UI Action" icon={<ArrowRight size={14} />} color="#3b82f6" selected={selected}>
    <Handle type="target" position={Position.Left} id="triggerIn" style={{ background: '#ef4444', width: '10px', height: '10px', left: '-6px', top: '20px' }} />
    <Handle type="target" position={Position.Left} id="dataIn" style={{ background: '#10b981', width: '10px', height: '10px', left: '-6px', top: '50px' }} />
    
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '10px' }}>
      <label>Target Component</label>
      <ComponentSelect components={data.components} value={data.componentId} onChange={e => data.onChange(data.id, 'componentId', e.target.value)} />
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>Action</label>
      <select value={data.actionType || 'setText'} onChange={e => data.onChange(data.id, 'actionType', e.target.value)} style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}>
        <option value="setText">Set Text (from dataIn)</option>
        <option value="setVisible">Set Visible (from dataIn)</option>
      </select>
    </div>
    
    <Handle type="source" position={Position.Right} id="triggerOut" style={{ background: '#ef4444', width: '10px', height: '10px', right: '-6px' }} />
  </NodeWrapper>
);

export const ValueNode = ({ data, selected }) => (
  <NodeWrapper title="Get Value" icon={<Database size={14} />} color="#10b981" selected={selected}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>Source Component</label>
      <ComponentSelect components={data.components} value={data.componentId} onChange={e => data.onChange(data.id, 'componentId', e.target.value)} />
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>Property</label>
      <select value={data.propertyType || 'value'} onChange={e => data.onChange(data.id, 'propertyType', e.target.value)} style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}>
        <option value="value">Input Value</option>
        <option value="text">Text Content</option>
      </select>
    </div>
    <Handle type="source" position={Position.Right} id="dataOut" style={{ background: '#10b981', width: '10px', height: '10px', right: '-6px' }} />
  </NodeWrapper>
);

export const WorkflowNode = ({ data, selected }) => (
  <NodeWrapper title="Execute Workflow" icon={<Sparkles size={14} />} color="#8b5cf6" selected={selected}>
    <Handle type="target" position={Position.Left} id="triggerIn" style={{ background: '#ef4444', width: '10px', height: '10px', left: '-6px', top: '20px' }} />
    <Handle type="target" position={Position.Left} id="payloadIn" style={{ background: '#10b981', width: '10px', height: '10px', left: '-6px', top: '50px' }} />
    
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '10px' }}>
      <label>Workflow Project ID</label>
      <input type="text" value={data.projectId || ''} onChange={e => data.onChange(data.id, 'projectId', e.target.value)} placeholder="Enter ID..." style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }} />
    </div>
    
    <Handle type="source" position={Position.Right} id="triggerOut" style={{ background: '#ef4444', width: '10px', height: '10px', right: '-6px', top: '20px' }} />
    <Handle type="source" position={Position.Right} id="dataOut" style={{ background: '#10b981', width: '10px', height: '10px', right: '-6px', top: '50px' }} />
  </NodeWrapper>
);

export const CodeNode = ({ data, selected }) => (
  <NodeWrapper title="Custom JS Code" icon={<Code2 size={14} />} color="#f59e0b" selected={selected}>
    <Handle type="target" position={Position.Left} id="triggerIn" style={{ background: '#ef4444', width: '10px', height: '10px', left: '-6px', top: '20px' }} />
    <Handle type="target" position={Position.Left} id="payloadIn" style={{ background: '#10b981', width: '10px', height: '10px', left: '-6px', top: '50px' }} />
    
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '10px' }}>
      <label style={{ fontSize: '10px' }}>return payload (from dataIn)</label>
      <textarea 
        value={data.jsCode || 'return payload;'} 
        onChange={e => data.onChange(data.id, 'jsCode', e.target.value)} 
        placeholder="return payload + 1;" 
        style={{ width: '100%', height: '80px', padding: '4px', background: '#0f172a', color: '#10b981', border: '1px solid #475569', borderRadius: '4px', fontFamily: 'monospace', fontSize: '11px', resize: 'vertical' }} 
      />
    </div>
    
    <Handle type="source" position={Position.Right} id="triggerOut" style={{ background: '#ef4444', width: '10px', height: '10px', right: '-6px', top: '20px' }} />
    <Handle type="source" position={Position.Right} id="dataOut" style={{ background: '#10b981', width: '10px', height: '10px', right: '-6px', top: '50px' }} />
  </NodeWrapper>
);

export const logicNodeTypes = {
  triggerNode: TriggerNode,
  actionNode: ActionNode,
  valueNode: ValueNode,
  workflowNode: WorkflowNode,
  codeNode: CodeNode
};
