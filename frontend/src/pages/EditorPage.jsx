import { useState, useCallback, useRef, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  ReactFlow,
  ReactFlowProvider,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';
import { Play, Code, Folder, Save, Share2, ArrowLeft, Wand2, Settings, Sparkles, Send, Bot } from 'lucide-react';
import Sidebar from '../Sidebar';
import TemplateModal from '../TemplateModal';
import DeployModal from '../DeployModal';
import { useAuth } from '../AuthContext';
import { StartNode, PromptNode, LLMNode, OutputNode, ConditionNode, ValueNode, LoopNode, BreakNode, PythonNode, TokenizerNode, DistributorNode, FileModifierNode, TemplateAnalyzerNode, DynamicInputNode, WebCrawlerNode, EmailNode, KakaoNode, DelayNode, JsonParserNode, MergeNode, HttpRequestNode, DatabaseNode, HumanApprovalNode } from '../customNodes';

const nodeTypes = {
  startNode: StartNode,
  promptNode: PromptNode,
  llmNode: LLMNode,
  outputNode: OutputNode,
  conditionNode: ConditionNode,
  valueNode: ValueNode,
  loopNode: LoopNode,
  breakNode: BreakNode,
  pythonNode: PythonNode,
  tokenizerNode: TokenizerNode,
  distributorNode: DistributorNode,
  fileModifierNode: FileModifierNode,
  templateAnalyzerNode: TemplateAnalyzerNode,
  dynamicInputNode: DynamicInputNode,
  webCrawlerNode: WebCrawlerNode,
  emailNode: EmailNode,
  kakaoNode: KakaoNode,
  delayNode: DelayNode,
  jsonParserNode: JsonParserNode,
  mergeNode: MergeNode,
  httpRequestNode: HttpRequestNode,
  databaseNode: DatabaseNode,
  humanApprovalNode: HumanApprovalNode,
};

let id = 0;
const getId = () => `dndnode_${id++}`;

function FlowContent() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, token } = useAuth();
  const reactFlowWrapper = useRef(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { screenToFlowPosition, getNodes, getEdges } = useReactFlow();
  const [response, setResponse] = useState('');
  const [isCompiled, setIsCompiled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
  const [tokenUsage, setTokenUsage] = useState(null);
  
  const [isTokenTrackingMode, setIsTokenTrackingMode] = useState(false);
  const [estimatedTokens, setEstimatedTokens] = useState(null);
  const [isTokenDrawerOpen, setIsTokenDrawerOpen] = useState(false);
  
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', content: '안녕하세요! 워크플로우 수정을 도와드릴까요? 원하시는 구성을 말씀해 주세요. (예: 이메일 전송 노드를 추가하고 슬랙 알림을 연결해줘)' }
  ]);
  const [chatInput, setChatInput] = useState('');

  const [projectTitle, setProjectTitle] = useState('Untitled Project');
  const [projectDescription, setProjectDescription] = useState('');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isPublic, setIsPublic] = useState(false);
  const [isOwner, setIsOwner] = useState(true); // Default true for new projects
  const [currentId, setCurrentId] = useState(projectId);

  // Configure Axios auth header
  const getAuthHeaders = () => token ? { headers: { Authorization: `Bearer ${token}` } } : {};

  useEffect(() => {
    if (projectId) {
      loadProject(projectId);
    } else if (location.state?.initialGraph) {
      const graph = location.state.initialGraph;
      setNodes(graph.nodes.map(n => ({
        ...n,
        data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode }
      })));
      setEdges(graph.edges || []);
      
      if (location.state?.prompt) {
        setProjectTitle("AI 생성 워크플로우");
      }
    }
      
    // Clear state to prevent re-triggering on reload
    if (location.state) {
      window.history.replaceState({}, document.title);
    }
  }, [projectId, location.state]);

  const loadProject = async (id) => {
    try {
      const res = await axios.get(`/api/projects/${id}`, getAuthHeaders());
      const data = res.data;
      setProjectTitle(data.title);
      setProjectDescription(data.description || '');
      setIsPublic(data.is_public);
      setIsOwner(user && user.id === data.owner_id);
      
      if (data.graph_data) {
        setNodes(data.graph_data.nodes.map(n => ({
          ...n,
          data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode }
        })));
        setEdges(data.graph_data.edges || []);
      }
    } catch (error) {
      console.error("Failed to load project", error);
      alert("Failed to load project or unauthorized.");
    }
  };

  const handleSave = async () => {
    try {
      const payload = {
        title: projectTitle,
        description: projectDescription,
        graph_data: getCurrentFlowData(),
        is_public: isPublic
      };

      if (currentId) {
        await axios.put(`/api/projects/${currentId}`, payload, getAuthHeaders());
        return true;
      } else {
        const res = await axios.post('/api/projects', payload, getAuthHeaders());
        setCurrentId(res.data.id);
        navigate(`/editor/${res.data.id}`, { replace: true });
        return true;
      }
    } catch (error) {
      console.error("Save failed", error);
      alert("프로젝트 저장에 실패했습니다.");
      return false;
    }
  };

  const handleOpenDeployModal = async () => {
    if (!currentId) {
      alert("먼저 프로젝트를 저장해 주세요.");
      return;
    }
    // Save latest state before deployment
    const saved = await handleSave();
    if (saved) {
      setIsDeployModalOpen(true);
    }
  };

  const toggleShare = () => {
    setIsPublic(!isPublic);
  };

  const onConnect = useCallback((params) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onNodeDataChange = useCallback((id, key, value) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          return { ...node, data: { ...node.data, [key]: value } };
        }
        return node;
      })
    );
  }, [setNodes]);

  const deleteNode = useCallback((idToDelete) => {
    setNodes((nds) => nds.filter((node) => node.id !== idToDelete));
    setEdges((eds) => eds.filter((edge) => edge.source !== idToDelete && edge.target !== idToDelete));
  }, [setNodes, setEdges]);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow');
      if (typeof type === 'undefined' || !type) {
        return;
      }

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNode = {
        id: getId(),
        type,
        position,
        data: { label: `${type} node`, onChange: onNodeDataChange, onDelete: deleteNode },
        zIndex: type === 'loopNode' ? -1 : 1,
      };

      setNodes((nds) => {
        if (type !== 'loopNode') {
          const loopNodes = nds.filter(n => n.type === 'loopNode');
          for (const ln of loopNodes) {
            const w = ln.measured?.width || ln.width || 250;
            const h = ln.measured?.height || ln.height || 200;
            if (position.x >= ln.position.x && position.x <= ln.position.x + w &&
                position.y >= ln.position.y && position.y <= ln.position.y + h) {
                newNode.parentNode = ln.id;
                newNode.position = {
                  x: position.x - ln.position.x,
                  y: position.y - ln.position.y
                };
                newNode.extent = 'parent';
                break;
            }
          }
        }
        return nds.concat(newNode);
      });
    },
    [screenToFlowPosition, setNodes, onNodeDataChange, deleteNode],
  );

  const { getIntersectingNodes } = useReactFlow();

  const onNodeDragStop = useCallback((event, node) => {
    if (node.type === 'loopNode') return;

    setNodes((nds) => {
      const intersections = getIntersectingNodes(node).filter((n) => n.type === 'loopNode');
      const loopNode = intersections[0];

      return nds.map((n) => {
        if (n.id === node.id) {
          if (loopNode && n.parentNode !== loopNode.id) {
            return {
              ...n,
              parentNode: loopNode.id,
              position: {
                x: n.position.x - loopNode.position.x,
                y: n.position.y - loopNode.position.y,
              },
              extent: 'parent',
            };
          } else if (!loopNode && n.parentNode) {
              const parent = nds.find(p => p.id === n.parentNode);
              const absX = n.position.x + (parent?.position.x || 0);
              const absY = n.position.y + (parent?.position.y || 0);
              
              const updatedNode = { ...n };
              delete updatedNode.parentNode;
              delete updatedNode.extent;
              
              return {
                ...updatedNode,
                position: { x: absX, y: absY }
              };
          }
        }
        
        if (n.type === 'loopNode' && n.zIndex !== -1) {
          return { ...n, zIndex: -1 };
        }
        return n;
      });
    });
  }, [getIntersectingNodes, setNodes]);

  const runFlow = async () => {
    setIsLoading(true);
    setIsCompiled(false);
    setResponse('Running graph on backend...');
    
    try {
      const payload = {
        nodes: nodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
        edges: edges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
      };

      const res = await axios.post('/api/execute', payload);
      setResponse(res.data.result || 'No content returned.');
      setTokenUsage(res.data.token_usage || null);
    } catch (error) {
      console.error(error);
      setResponse('Error communicating with backend: ' + (error.response?.data?.detail || error.message));
      setTokenUsage(null);
    } finally {
      setIsLoading(false);
    }
  };

  const compileFlow = async () => {
    setIsLoading(true);
    setIsCompiled(true);
    setResponse('Compiling graph to Python code...');
    
    try {
      const payload = {
        nodes: nodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
        edges: edges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
      };

      const res = await axios.post('/api/compile', payload);
      setResponse(res.data.code || 'No code generated.');
    } catch (error) {
      console.error(error);
      setResponse('Error communicating with backend: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
  };

  const handleLoadTemplate = (templateData) => {
    const loadedNodes = templateData.nodes.map(n => ({
      ...n,
      data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode }
    }));
    setNodes(loadedNodes);
    setEdges(templateData.edges || []);
  };

  const getCurrentFlowData = () => {
    return {
      nodes: getNodes().map(n => {
        const nData = { ...n.data };
        delete nData.onChange;
        delete nData.onDelete;
        return { id: n.id, type: n.type, position: n.position, data: nData };
      }),
      edges: getEdges()
    };
  };

  const handleSendChat = () => {
    if (!chatInput.trim()) return;
    
    const newMessages = [...chatMessages, { role: 'user', content: chatInput }];
    setChatMessages(newMessages);
    setChatInput('');
    
    // Mock backend response
    setTimeout(() => {
      setChatMessages(prev => [
        ...prev, 
        { role: 'assistant', content: '요청하신 내용을 분석하여 워크플로우 업데이트를 준비 중입니다. (현재 UI 테스트 모드입니다. 추후 LLM API 연동이 필요합니다.)' }
      ]);
    }, 1000);
  };


  return (
    <div className="app-container">
      <header className="header" style={{ position: 'relative', padding: '0.8rem 1.5rem', background: '#0f172a', borderBottom: '1px solid #1e293b', zIndex: 50 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button onClick={() => navigate('/')} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', padding: 0 }}>
            <ArrowLeft size={18} />
          </button>
          
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button 
              onClick={() => setIsDrawerOpen(!isDrawerOpen)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'transparent', border: 'none', cursor: 'pointer', padding: '0.2rem 0.5rem', borderRadius: '4px' }}
              className="project-title-btn"
            >
              <span style={{ fontWeight: 600, color: 'var(--text-color)', fontSize: '1.1rem' }}>{projectTitle || 'Untitled Project'}</span>
              <Settings size={14} color="var(--text-muted)" />
            </button>
            <button
              onClick={() => setIsTokenDrawerOpen(!isTokenDrawerOpen)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: isTokenTrackingMode ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
                border: '1px solid',
                borderColor: isTokenTrackingMode ? '#3b82f6' : 'var(--border-color)',
                color: isTokenTrackingMode ? '#60a5fa' : 'var(--text-muted)',
                cursor: 'pointer', padding: '0.2rem 0.5rem', borderRadius: '6px',
                fontSize: '0.8rem', gap: '4px'
              }}
              title="토큰 통계 보기"
            >
              <BrainCircuit size={14} /> 통계
            </button>

            {isTokenDrawerOpen && (
              <div style={{ 
                position: 'absolute', top: '100%', left: '100%', marginTop: '0.5rem', marginLeft: '1rem',
                background: 'var(--card-bg)', border: '1px solid var(--border-color)', 
                borderRadius: '8px', padding: '1.5rem', width: '320px',
                boxShadow: '0 10px 25px rgba(0,0,0,0.5)', zIndex: 100 
              }}>
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: '#60a5fa', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>워크플로우 토큰 통계</h3>
                
                <div style={{ marginBottom: '1rem' }}>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>1회 실행 예상 토큰량 (Min ~ Max)</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-color)' }}>
                    {estimatedTokens ? `${estimatedTokens.total_estimated_tokens} ~ ${estimatedTokens.total_max_tokens}` : '-'}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>마지막 실행 실제 토큰 사용량</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#10b981' }}>
                    {tokenUsage ? tokenUsage.total_tokens : '-'}
                  </div>
                </div>
              </div>
            )}

            {isDrawerOpen && (
              <div style={{ 
                position: 'absolute', top: '100%', left: 0, marginTop: '0.5rem', 
                background: 'var(--card-bg)', border: '1px solid var(--border-color)', 
                borderRadius: '8px', padding: '1rem', width: '300px',
                boxShadow: '0 10px 25px rgba(0,0,0,0.5)', zIndex: 100 
              }}>
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>프로젝트 제목</label>
                  <input 
                    type="text" 
                    value={projectTitle} 
                    onChange={(e) => setProjectTitle(e.target.value)}
                    disabled={!isOwner}
                    style={{ 
                      width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', 
                      color: 'var(--text-color)', fontSize: '0.9rem', padding: '0.5rem', borderRadius: '4px', outline: 'none',
                      boxSizing: 'border-box'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>프로젝트 명세 (Description)</label>
                  <textarea 
                    value={projectDescription} 
                    onChange={(e) => setProjectDescription(e.target.value)}
                    disabled={!isOwner}
                    rows={4}
                    placeholder="이 워크플로우에 대한 설명이나 기획 의도를 적어두세요."
                    style={{ 
                      width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', 
                      color: 'var(--text-color)', fontSize: '0.9rem', padding: '0.5rem', borderRadius: '4px', outline: 'none',
                      resize: 'none', boxSizing: 'border-box'
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {isOwner && (
            <>
              <button 
                className="btn-secondary" 
                onClick={toggleShare}
                style={{ background: isPublic ? 'rgba(16, 185, 129, 0.1)' : 'transparent', color: isPublic ? '#10b981' : 'var(--text-muted)', borderColor: isPublic ? '#10b981' : '#334155' }}
              >
                <Share2 size={16} />
                {isPublic ? '공개됨' : '비공개'}
              </button>
              <button className="btn-secondary" onClick={() => { handleSave().then(s => s && alert("저장되었습니다.")); }}>
                <Save size={16} />
                저장
              </button>
              {currentId && (
                <button className="btn-secondary" onClick={handleOpenDeployModal} style={{ borderColor: '#8b5cf6', color: '#8b5cf6' }}>
                  <Wand2 size={16} />
                  배포
                </button>
              )}
            </>
          )}
          <button className="btn-secondary" onClick={async () => {
            try {
              const payload = {
                nodes: nodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
                edges: edges.map(e => ({ source: e.source, target: e.target }))
              };
              const res = await axios.post('/api/estimate', payload);
              if (res.data.status === 'success') {
                setEstimatedTokens(res.data);
                if (!isTokenTrackingMode) setIsTokenTrackingMode(true);
                alert(`[예상 소모 토큰량]\n최소 ${res.data.total_estimated_tokens} ~ 최대 ${res.data.total_max_tokens} tokens`);
              } else {
                alert('토큰 계산 실패: ' + res.data.message);
              }
            } catch (error) {
              console.error(error);
              alert('예상 토큰 계산 중 오류가 발생했습니다.');
            }
          }} style={{ borderColor: '#f59e0b', color: '#f59e0b' }}>
            예상 토큰 계산
          </button>
          
          <button 
            className="btn-secondary" 
            onClick={() => setIsTokenTrackingMode(!isTokenTrackingMode)}
            style={{ 
              borderColor: isTokenTrackingMode ? '#3b82f6' : 'var(--border-color)', 
              color: isTokenTrackingMode ? '#3b82f6' : 'var(--text-muted)' 
            }}
          >
            추적 모드 {isTokenTrackingMode ? 'ON' : 'OFF'}
          </button>
          <button className="btn-run" onClick={() => setIsTemplateModalOpen(true)} style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', color: 'var(--text-color)' }}>
            <Folder size={16} />
          </button>
          <button className="btn-run" onClick={runFlow} disabled={isLoading}>
            <Play size={18} />
            {isLoading ? '실행 중...' : '실행'}
          </button>
        </div>
      </header>
      
      <main className="main-content">
        <Sidebar />
        <div className="flow-wrapper" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={nodes.map(n => ({
              ...n,
              data: {
                ...n.data,
                isTokenTrackingMode,
                predictedTokens: estimatedTokens?.node_details?.[n.id] || null,
                actualTokens: tokenUsage?.nodes?.[n.id] || null
              }
            }))}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeDragStop={onNodeDragStop}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={{ 
              style: { strokeWidth: 2, stroke: 'var(--text-muted)' },
              type: 'smoothstep'
            }}
            deleteKeyCode={['Backspace', 'Delete']}
            fitView
            colorMode="dark"
          >
            <Controls />
            <MiniMap 
              nodeColor={(node) => {
                switch (node.type) {
                  case 'startNode': return '#22c55e';
                  case 'promptNode': return '#10b981';
                  case 'llmNode': return '#8b5cf6';
                  case 'outputNode': return '#f59e0b';
                  case 'loopNode': return '#eab308';
                  case 'breakNode': return '#ef4444';
                  case 'pythonNode': return '#3b82f6';
                  case 'tokenizerNode': return '#10b981';
                  case 'distributorNode': return '#8b5cf6';
                  case 'fileModifierNode': return '#f97316';
                  case 'delayNode': return '#3b82f6';
                  case 'jsonParserNode': return '#eab308';
                  case 'mergeNode': return '#ec4899';
                  case 'httpRequestNode': return '#0ea5e9';
                  case 'databaseNode': return '#059669';
                  case 'humanApprovalNode': return '#f43f5e';
                  default: return '#eee';
                }
              }}
            />
            <Background variant="dots" gap={12} size={1} color="#334155" />
          </ReactFlow>
        </div>
        
        <aside className="response-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <h2>Execution Result</h2>
          {tokenUsage && (
            <div style={{ padding: '0.8rem', margin: '0 1rem 1rem', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid #3b82f6', borderRadius: '8px', fontSize: '0.85rem' }}>
              <div style={{ fontWeight: 'bold', color: '#60a5fa', marginBottom: '0.5rem' }}>토큰 사용량 (Token Usage)</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
                <span>총 소모 토큰: {tokenUsage.total_tokens}</span>
                <span>입력: {tokenUsage.total_input} / 출력: {tokenUsage.total_output}</span>
              </div>
            </div>
          )}
          <div className="response-content" style={{ flex: 1, overflowY: 'auto' }}>
            {isCompiled ? (
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.85rem' }}>
                <code>{response || 'Run or Compile the flow to see the results here.'}</code>
              </pre>
            ) : (
              (response && typeof response === 'string' && (response.startsWith('uploads/') || response.startsWith('uploads\\'))) ? (
                <div>
                  <p>File generated successfully:</p>
                  <a 
                    href={`http://localhost:8000/${response.replace(/\\/g, '/')}`} 
                    target="_blank" rel="noreferrer"
                    style={{ display: 'inline-block', padding: '8px 16px', background: '#3b82f6', color: 'var(--text-color)', textDecoration: 'none', borderRadius: '4px', marginTop: '10px' }}
                  >
                    Download File
                  </a>
                </div>
              ) : (
                <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{response || 'Run or Compile the flow to see the results here.'}</div>
              )
            )}
          </div>
        </aside>
      </main>

      <TemplateModal 
        isOpen={isTemplateModalOpen} 
        onClose={() => setIsTemplateModalOpen(false)}
        onLoad={handleLoadTemplate}
        currentFlowData={getCurrentFlowData}
      />

      {isDeployModalOpen && currentId && (
        <DeployModal 
          isOpen={isDeployModalOpen} 
          onClose={() => setIsDeployModalOpen(false)} 
          project={{ id: currentId, title: projectTitle }} 
          onDeployConfigSaved={(mode) => {
             // Navigate to deploy viewer
             if (mode === 'chatbot' || mode === 'form') {
                 window.open(`/app/${currentId}`, '_blank');
             }
          }}
        />
      )}

      {/* LLM Assistant Floating Button */}
      <button 
        onClick={() => setIsAssistantOpen(!isAssistantOpen)}
        style={{
          position: 'fixed',
          bottom: '2rem',
          right: '2rem',
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #8b5cf6, #3b82f6)',
          border: 'none',
          boxShadow: '0 4px 14px rgba(139, 92, 246, 0.4)',
          color: 'var(--text-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          zIndex: 1000,
          transition: 'transform 0.2s',
          transform: isAssistantOpen ? 'scale(0.9)' : 'scale(1)'
        }}
      >
        <Sparkles size={24} />
      </button>

      {/* LLM Assistant Panel (Glassmorphism UI) */}
      <div style={{
        position: 'fixed',
        bottom: '5rem',
        right: '2rem',
        width: '360px',
        height: '550px',
        maxHeight: '80vh',
        background: 'rgba(15, 23, 42, 0.85)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '16px',
        boxShadow: '0 10px 40px rgba(0, 0, 0, 0.5)',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 999,
        transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        opacity: isAssistantOpen ? 1 : 0,
        pointerEvents: isAssistantOpen ? 'auto' : 'none',
        transform: isAssistantOpen ? 'translateY(0)' : 'translateY(20px)'
      }}>
        {/* Header */}
        <div style={{
          padding: '1rem',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          background: 'rgba(255, 255, 255, 0.02)',
          borderTopLeftRadius: '16px',
          borderTopRightRadius: '16px'
        }}>
          <Bot size={20} color="#a78bfa" />
          <h3 style={{ margin: 0, fontSize: '1rem', color: 'var(--text-color)', fontWeight: 600 }}>AI 워크플로우 어시스턴트</h3>
        </div>

        {/* Chat Messages */}
        <div style={{
          flex: 1,
          padding: '1rem',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem'
        }}>
          {chatMessages.map((msg, i) => (
            <div key={i} style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start'
            }}>
              <div style={{
                maxWidth: '85%',
                padding: '0.75rem 1rem',
                borderRadius: '12px',
                background: msg.role === 'user' ? 'var(--primary-color)' : 'var(--btn-active-bg)',
                color: msg.role === 'user' ? '#fff' : 'var(--text-color)',
                fontSize: '0.9rem',
                lineHeight: '1.4',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border-color)',
                borderBottomRightRadius: msg.role === 'user' ? '4px' : '12px',
                borderBottomLeftRadius: msg.role === 'assistant' ? '4px' : '12px'
              }}>
                {msg.content}
              </div>
            </div>
          ))}
        </div>

        {/* Chat Input */}
        <div style={{
          padding: '1rem',
          borderTop: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          gap: '0.5rem',
          background: 'rgba(0, 0, 0, 0.2)',
          borderBottomLeftRadius: '16px',
          borderBottomRightRadius: '16px'
        }}>
          <input
            type="text"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendChat()}
            placeholder="AI에게 수정사항을 요청하세요..."
            style={{
              flex: 1,
              background: 'var(--btn-active-bg)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '0.75rem 1rem',
              color: 'var(--text-color)',
              outline: 'none',
              fontSize: '0.9rem'
            }}
          />
          <button 
            onClick={handleSendChat}
            disabled={!chatInput.trim()}
            style={{
              background: chatInput.trim() ? 'var(--primary-color)' : 'var(--btn-active-bg)',
              border: 'none',
              borderRadius: '8px',
              width: '44px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-color)',
              cursor: chatInput.trim() ? 'pointer' : 'not-allowed',
              transition: 'background 0.2s'
            }}
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

function EditorPage() {
  return (
    <ReactFlowProvider>
      <FlowContent />
    </ReactFlowProvider>
  );
}

export default EditorPage;

