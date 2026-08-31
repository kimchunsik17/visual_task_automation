import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { Code2 } from 'lucide-react';
import { Icon } from './icons';

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
  <NodeWrapper title="Event Trigger" icon={<Icon name="bp-event-trigger" size={14} />} color="#ef4444" selected={selected}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>Target Component</label>
      <ComponentSelect components={data.components} value={data.componentId} onChange={e => data.onChange(data.id, 'componentId', e.target.value)} />
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>Event Type</label>
      <select value={data.eventType || 'onClick'} onChange={e => data.onChange(data.id, 'eventType', e.target.value)} style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}>
        <option value="onClick">On Click</option>
        <option value="onChange">On Change (입력 값 변경)</option>
      </select>
    </div>
    <Handle type="source" position={Position.Right} id="trigger" style={{ background: '#ef4444', width: '10px', height: '10px', right: '-6px' }} />
  </NodeWrapper>
);

export const ActionNode = ({ data, selected }) => (
  <NodeWrapper title="UI Action" icon={<Icon name="bp-ui-action" size={14} />} color="#3b82f6" selected={selected}>
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
  <NodeWrapper title="Get Value" icon={<Icon name="bp-get-value" size={14} />} color="#10b981" selected={selected}>
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
  <NodeWrapper title="Execute Workflow" icon={<Icon name="bp-workflow-execute" size={14} />} color="#8b5cf6" selected={selected}>
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
        style={{ width: '100%', height: '80px', padding: '4px', background: '#0f172a', color: '#10b981', border: '1px solid #475569', borderRadius: '4px', fontFamily: 'var(--font-mono)', fontSize: '11px', resize: 'vertical' }} 
      />
    </div>
    
    <Handle type="source" position={Position.Right} id="triggerOut" style={{ background: '#ef4444', width: '10px', height: '10px', right: '-6px', top: '20px' }} />
    <Handle type="source" position={Position.Right} id="dataOut" style={{ background: '#10b981', width: '10px', height: '10px', right: '-6px', top: '50px' }} />
  </NodeWrapper>
);


/**
 * 전송(Submit) 노드 (백로그 16).
 *
 * "버튼에 워크플로우를 직접 연결"하는 방식은 결과가 하단 패널에만 뜨고, payload 는 백엔드가
 * "첫 번째 값"을 추측했다. 이 노드는 무엇을 어떤 이름으로 보낼지(fields)와 실패 경로(errorOut)를
 * 명시한다. 필드를 비워두면 모든 입력 컴포넌트의 값을 inputKey 이름으로 보낸다.
 */
export const SubmitNode = ({ data, selected }) => {
  const fields = Array.isArray(data.fields) ? data.fields : [];
  const setField = (index, key, value) => {
    const next = fields.map((f, i) => (i === index ? { ...f, [key]: value } : f));
    data.onChange(data.id, 'fields', next);
  };
  return (
    <NodeWrapper title="Submit (전송)" icon={<Icon name="bp-workflow-execute" size={14} />} color="#0ea5e9" selected={selected}>
      <Handle type="target" position={Position.Left} id="triggerIn" style={{ background: '#ef4444', width: '10px', height: '10px', left: '-6px', top: '20px' }} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '10px' }}>
        <label>Workflow</label>
        {Array.isArray(data.workflows) && data.workflows.length > 0 ? (
          <select value={data.projectId || ''} onChange={e => data.onChange(data.id, 'projectId', e.target.value)} style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}>
            <option value="">-- 선택 --</option>
            {data.workflows.map(wf => <option key={wf.id} value={wf.id}>{wf.title || `Workflow #${wf.id}`}</option>)}
          </select>
        ) : (
          <input type="text" value={data.projectId || ''} onChange={e => data.onChange(data.id, 'projectId', e.target.value)} placeholder="Project ID..." style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }} />
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px' }}>
        <label>보낼 필드 (비우면 모든 입력값)</label>
        {fields.map((field, index) => (
          <div key={index} style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
            <input
              type="text" value={field.name || ''} placeholder="필드명"
              onChange={e => setField(index, 'name', e.target.value)}
              style={{ width: '40%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}
            />
            <div style={{ flex: 1 }}>
              <ComponentSelect components={data.components} value={field.componentId} onChange={e => setField(index, 'componentId', e.target.value)} />
            </div>
            <button
              onClick={() => data.onChange(data.id, 'fields', fields.filter((_, i) => i !== index))}
              style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', padding: '0 2px' }}
            >✕</button>
          </div>
        ))}
        <button
          onClick={() => data.onChange(data.id, 'fields', [...fields, { name: '', componentId: '' }])}
          style={{ background: '#1e293b', border: '1px dashed #475569', color: '#94a3b8', borderRadius: '4px', padding: '3px', cursor: 'pointer', fontSize: '10px' }}
        >+ 필드 추가</button>
      </div>

      <div style={{ fontSize: '9px', color: '#64748b', marginTop: '6px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
        <span style={{ color: '#ef4444' }}>▶ 오른쪽 위: 성공 흐름 · 아래: 실패 흐름</span>
        <span style={{ color: '#10b981' }}>▶ 초록: 실행 결과 데이터</span>
      </div>

      <Handle type="source" position={Position.Right} id="triggerOut" style={{ background: '#ef4444', width: '10px', height: '10px', right: '-6px', top: '20px' }} />
      <Handle type="source" position={Position.Right} id="dataOut" style={{ background: '#10b981', width: '10px', height: '10px', right: '-6px', top: '50px' }} />
      <Handle type="source" position={Position.Right} id="errorOut" style={{ background: '#f59e0b', width: '10px', height: '10px', right: '-6px', top: '80px' }} />
    </NodeWrapper>
  );
};

/**
 * 출력(Output) 노드 (백로그 16). 결과를 어느 컴포넌트에, 어느 부분을 보여줄지 명시한다.
 * 대상을 비우면 화면 하단 "실행 결과" 패널로 간다(직접 연결 방식과 같은 동작).
 */
export const OutputNode = ({ data, selected }) => (
  <NodeWrapper title="Output (출력)" icon={<Icon name="bp-ui-action" size={14} />} color="#10b981" selected={selected}>
    <Handle type="target" position={Position.Left} id="triggerIn" style={{ background: '#ef4444', width: '10px', height: '10px', left: '-6px', top: '20px' }} />
    <Handle type="target" position={Position.Left} id="dataIn" style={{ background: '#10b981', width: '10px', height: '10px', left: '-6px', top: '50px' }} />

    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '10px' }}>
      <label>표시할 컴포넌트 (비우면 하단 패널)</label>
      <ComponentSelect components={data.components} value={data.componentId} onChange={e => data.onChange(data.id, 'componentId', e.target.value)} />
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>결과에서 꺼낼 경로 (선택)</label>
      <input
        type="text" value={data.resultPath || ''} placeholder="예: result.text (비우면 전체)"
        onChange={e => data.onChange(data.id, 'resultPath', e.target.value)}
        style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}
      />
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label>형식</label>
      <select value={data.format || 'text'} onChange={e => data.onChange(data.id, 'format', e.target.value)} style={{ width: '100%', padding: '4px', background: '#0f172a', color: 'white', border: '1px solid #475569', borderRadius: '4px' }}>
        <option value="text">텍스트</option>
        <option value="json">JSON (보기 좋게)</option>
      </select>
    </div>

    <Handle type="source" position={Position.Right} id="triggerOut" style={{ background: '#ef4444', width: '10px', height: '10px', right: '-6px' }} />
  </NodeWrapper>
);

export const logicNodeTypes = {
  triggerNode: TriggerNode,
  actionNode: ActionNode,
  valueNode: ValueNode,
  workflowNode: WorkflowNode,
  codeNode: CodeNode,
  submitNode: SubmitNode,
  outputNode: OutputNode
};
