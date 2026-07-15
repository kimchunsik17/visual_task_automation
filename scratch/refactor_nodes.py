import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# PromptNode
prompt_node_regex = re.compile(r'export const PromptNode = \(\{ id, data \}\) => \{[\s\S]*?return \([\s\S]*?\}\);?\s*\n\};')
new_prompt_node = """export const PromptNode = ({ id, data }) => {
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
        {isExpanded && <ChevronDown size={14} />}
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><MessageSquare size={16} color="#3b82f6"/> 프롬프트</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
        <label>사용자 프롬프트</label>
        <DraggableTextarea 
          id={id} 
          fieldKey="userPrompt" 
          value={data.userPrompt} 
          onChange={data.onChange} 
          placeholder="프롬프트를 입력하세요..." 
          isDetached={data.isDetached_userPrompt} 
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
      )}
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};"""

# ValueNode
value_node_regex = re.compile(r'export const ValueNode = \(\{ id, data \}\) => \{[\s\S]*?return \([\s\S]*?\}\);?\s*\n\};')
new_value_node = """export const ValueNode = ({ id, data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);
  const isAIModified = data.isAIModified;

  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8000/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        data.onChange(id, 'file_path', result.file_path);
        data.onChange(id, 'filename', result.filename);
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
        {isExpanded && <ChevronDown size={14} />}
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Variable size={16} color="#ec4899"/> 변수 (값)</div>
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
          <DraggableTextarea 
            id={id} 
            fieldKey="value" 
            value={data.value} 
            onChange={data.onChange} 
            placeholder="Enter a static value..." 
            isDetached={data.isDetached_value} 
          />
        )}
        
        {!data.filename && (
          <div style={{ marginTop: '8px' }}>
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }} 
              onChange={handleFileUpload} 
            />
            <button 
              className="btn-secondary" 
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              style={{ width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}
            >
              <Upload size={14} /> {isUploading ? '업로드 중...' : '파일 업로드'}
            </button>
          </div>
        )}
      </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};"""

content = prompt_node_regex.sub(new_prompt_node, content)
content = value_node_regex.sub(new_value_node, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("PromptNode and ValueNode refactored to use DraggableTextarea")
