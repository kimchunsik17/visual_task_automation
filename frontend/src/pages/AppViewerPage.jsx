import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Send, Bot, User, Paperclip, X, Upload } from 'lucide-react';
import './MainPage.css'; // Reuse existing layout classes if needed

const AppViewerPage = () => {
  const { projectId } = useParams();
  const [project, setProject] = useState(null);
  const [deployMode, setDeployMode] = useState('chatbot');
  
  // For Form mode
  const [formInputs, setFormInputs] = useState({});
  const [formResult, setFormResult] = useState('');
  // For Chatbot mode
  const [chatHistory, setChatHistory] = useState([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [attachedFile, setAttachedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadingFile, setUploadingFile] = useState(false);
  const fileInputRef = useRef(null);
  
  const [isLoading, setIsLoading] = useState(true);
  const [isExecuting, setIsExecuting] = useState(false);
  const [dynamicNodes, setDynamicNodes] = useState([]);

  useEffect(() => {
    const fetchProject = async () => {
      try {
        // Here we ideally fetch public project info or user auth depending on visibility
        const res = await axios.get(`/api/projects/${projectId}`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
        });
        setProject(res.data);
        
        // Retrieve deploy mode from project (assuming backend sends it, fallback to 'chatbot')
        const mode = res.data.deploy_mode || 'chatbot';
        setDeployMode(mode);

        // Find all dynamic input nodes
        const nodes = res.data.graph_data?.nodes || [];
        const dynNodes = nodes.filter(n => n.type === 'dynamicInputNode');
        setDynamicNodes(dynNodes);
        
        const initialForm = {};
        dynNodes.forEach(n => {
          initialForm[n.id] = '';
        });
        setFormInputs(initialForm);

      } catch (error) {
        console.error(error);
        const errorMsg = error.response?.data?.detail || error.message;
        alert(`프로젝트를 불러오지 못했습니다. 에러: ${errorMsg}`);
      } finally {
        setIsLoading(false);
      }
    };
    fetchProject();
  }, [projectId]);

  const executeFlow = async (inputs) => {
    setIsExecuting(true);
    try {
      const res = await axios.post(`/api/deploy/${projectId}/execute`, { inputs }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      return { result: res.data.result, tokens: res.data.token_usage || null };
    } catch (error) {
      console.error(error);
      return '실행 중 오류가 발생했습니다.';
    } finally {
      setIsExecuting(false);
    }
  };

  const handleFormFileChange = async (nodeId, file) => {
    if (!file) return;
    setUploadingFile(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setFormInputs(prev => ({ ...prev, [nodeId]: res.data.file_path }));
    } catch (err) {
      alert('업로드 실패');
    } finally {
      setUploadingFile(false);
    }
  };

  const handleChatFile = async (file) => {
    if (!file) return;
    setUploadingFile(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setAttachedFile({ path: res.data.file_path, name: file.name });
    } catch (err) {
      alert('업로드 실패');
    } finally {
      setUploadingFile(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };
  
  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };
  
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleChatFile(e.dataTransfer.files[0]);
    }
  };

  const handleFormSubmit = async (e) => {
    e.preventDefault();
    setFormResult(''); // Clear previous
    const res = await executeFlow(formInputs);
    setFormResult(res.result);
  };

  const handleChatSubmit = async (e) => {
    e.preventDefault();
    if (!currentMessage.trim() && !attachedFile) return;

    let userMsg = currentMessage;
    if (attachedFile) {
      userMsg = `[Attached File: ${attachedFile.path}]\n\n${userMsg}`;
    }

    setChatHistory(prev => [...prev, { role: 'user', content: userMsg }]);
    setCurrentMessage('');
    
    const targetNode = dynamicNodes.length > 0 ? dynamicNodes[0] : null;
    const targetNodeId = targetNode ? targetNode.id : 'default_input';
    
    let finalInput = userMsg;
    // 만약 타겟 노드가 파일 입력을 받는 노드이고 파일이 첨부되어 있다면, 텍스트 대신 파일 경로만 전달
    if (targetNode?.data?.inputType === 'file' && attachedFile) {
      finalInput = attachedFile.path;
    }
    
    setAttachedFile(null);

    const res = await executeFlow({ [targetNodeId]: finalInput });
    
    // 객체(Object) 등 문자열이 아닌 결과값이 반환될 경우 렌더링 오류를 막기 위해 변환
    const finalContent = typeof res.result === 'object' ? JSON.stringify(res.result, null, 2) : String(res.result || '');
    
    setChatHistory(prev => [...prev, { role: 'bot', content: finalContent }]);
  };

  if (isLoading) return <div style={{ color: 'var(--text-color)', padding: '2rem' }}>로딩 중...</div>;
  if (!project) return <div style={{ color: 'var(--text-color)', padding: '2rem' }}>프로젝트를 찾을 수 없습니다.</div>;

  return (
    <div style={{ backgroundColor: 'var(--bg-color)', minHeight: '100vh', display: 'flex', flexDirection: 'column', color: 'var(--text-color)' }}>
      <header style={{ padding: '1rem 2rem', borderBottom: '1px solid var(--border-color)', backgroundColor: 'var(--card-bg)' }}>
        <h1 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600 }}>{project.title}</h1>
        {project.description && <p style={{ margin: '0.5rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>{project.description}</p>}
      </header>

      <main style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: '2rem' }}>
        {deployMode === 'form' ? (
          <div style={{ width: '100%', maxWidth: '600px', backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '2rem' }}>
            <form onSubmit={handleFormSubmit}>
              {dynamicNodes.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>이 워크플로우에는 동적 입력 노드가 없습니다. 바로 실행해 보세요.</p>
              ) : (
                dynamicNodes.map(node => (
                  <div key={node.id} style={{ marginBottom: '1.5rem' }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                      {node.data?.inputLabel || '입력'}
                    </label>
                    {node.data?.inputType === 'file' ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <input
                          type="file"
                          onChange={(e) => handleFormFileChange(node.id, e.target.files[0])}
                          style={{ color: 'var(--text-muted)' }}
                          disabled={uploadingFile}
                        />
                        {uploadingFile && <span style={{ fontSize: '0.8rem', color: '#fbbf24' }}>업로드 중...</span>}
                        {formInputs[node.id] && <span style={{ fontSize: '0.8rem', color: '#10b981', wordBreak: 'break-all' }}>업로드 완료: {formInputs[node.id]}</span>}
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={formInputs[node.id] || ''}
                        onChange={(e) => setFormInputs({...formInputs, [node.id]: e.target.value})}
                        style={{ width: '100%', padding: '0.8rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'rgba(255,255,255,0.03)', color: 'var(--text-color)' }}
                        required
                      />
                    )}
                  </div>
                ))
              )}
              <button 
                type="submit" 
                className="btn-run" 
                disabled={isExecuting}
                style={{ width: '100%', padding: '1rem', fontSize: '1.1rem', marginTop: '1rem' }}
              >
                {isExecuting ? '실행 중...' : '실행하기'}
              </button>
            </form>
            {formResult && (
              <div style={{ marginTop: '2rem', padding: '1.5rem', backgroundColor: 'rgba(59, 130, 246, 0.1)', border: '1px solid #3b82f6', borderRadius: '8px' }}>
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: '#60a5fa' }}>실행 결과</h3>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{formResult}</pre>
              </div>
            )}
          </div>
        ) : (
          /* Chatbot Mode */
          <div 
            style={{ 
              width: '100%', maxWidth: '800px', backgroundColor: 'var(--card-bg)', border: `2px ${isDragging ? 'dashed #3b82f6' : 'solid var(--border-color)'}`, 
              borderRadius: '12px', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 150px)', position: 'relative', transition: 'border 0.2s ease'
            }}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {isDragging && (
              <div style={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.8)', zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', borderRadius: '10px' }}>
                <Upload size={48} color="#3b82f6" style={{ marginBottom: '1rem' }} />
                <h3 style={{ margin: 0, color: '#3b82f6' }}>파일을 여기에 드롭하세요</h3>
              </div>
            )}
            
            <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {chatHistory.length === 0 ? (
                <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <Bot size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                  <p>대화를 시작해 보세요. 워크플로우가 실행됩니다.</p>
                </div>
              ) : (
                chatHistory.map((msg, idx) => (
                  <div key={idx} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                    <div style={{ display: 'flex', gap: '0.8rem', maxWidth: '80%', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                      <div style={{ width: '36px', height: '36px', borderRadius: '50%', backgroundColor: msg.role === 'user' ? '#3b82f6' : '#8b5cf6', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
                      </div>
                      <div style={{ padding: '1rem', borderRadius: '12px', backgroundColor: msg.role === 'user' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255, 255, 255, 0.05)', color: msg.isMeta ? '#94a3b8' : '#e2e8f0', whiteSpace: 'pre-wrap', fontSize: msg.isMeta ? '0.85rem' : '1rem' }}>
                        {msg.content}
                      </div>
                    </div>
                  </div>
                ))
              )}
              {isExecuting && (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div style={{ padding: '1rem', borderRadius: '12px', backgroundColor: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-muted)' }}>
                    실행 중...
                  </div>
                </div>
              )}
            </div>
            
            <div style={{ padding: '1rem', borderTop: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {attachedFile && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', backgroundColor: 'rgba(59, 130, 246, 0.1)', padding: '0.5rem 1rem', borderRadius: '8px', width: 'fit-content' }}>
                  <Paperclip size={14} color="#3b82f6" />
                  <span style={{ fontSize: '0.85rem', color: '#60a5fa' }}>{attachedFile.name}</span>
                  <button onClick={() => setAttachedFile(null)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '0 4px' }}>
                    <X size={14} />
                  </button>
                </div>
              )}
              {uploadingFile && (
                <div style={{ fontSize: '0.8rem', color: '#fbbf24', marginLeft: '0.5rem' }}>파일 업로드 중...</div>
              )}
              <form onSubmit={handleChatSubmit} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  style={{ display: 'none' }} 
                  onChange={(e) => handleChatFile(e.target.files[0])} 
                />
                <button 
                  type="button" 
                  onClick={() => fileInputRef.current?.click()} 
                  disabled={isExecuting || uploadingFile}
                  style={{ padding: '0.8rem', borderRadius: '8px', backgroundColor: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                >
                  <Paperclip size={20} />
                </button>
                <input
                  type="text"
                  value={currentMessage}
                  onChange={(e) => setCurrentMessage(e.target.value)}
                  placeholder="메시지를 입력하거나 파일을 드래그 하세요..."
                  style={{ flex: 1, padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)', backgroundColor: 'rgba(255,255,255,0.03)', color: 'var(--text-color)', outline: 'none' }}
                  disabled={isExecuting || uploadingFile}
                />
                <button type="submit" className="btn-run" disabled={isExecuting || uploadingFile || (!currentMessage.trim() && !attachedFile)} style={{ padding: '0 1.5rem', borderRadius: '8px' }}>
                  <Send size={20} />
                </button>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default AppViewerPage;

