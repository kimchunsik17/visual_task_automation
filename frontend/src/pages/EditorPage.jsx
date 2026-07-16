import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
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
import { Play, Code, Folder, Save, Share2, ArrowLeft, Wand2, Settings, Sparkles, Send, Bot, BrainCircuit, History, TerminalSquare, X, Square } from 'lucide-react';
import Sidebar from '../Sidebar';
import TemplateModal from '../TemplateModal';
import DeployModal from '../DeployModal';
import { useAuth } from '../AuthContext';
import { StartNode, PromptNode, LLMNode, OutputNode, ConditionNode, ValueNode, LoopNode, BreakNode, PythonNode, TokenizerNode, DistributorNode, FileModifierNode, TemplateAnalyzerNode, DynamicInputNode, WebCrawlerNode, EmailNode, KakaoNode, DelayNode, JsonParserNode, MergeNode, HttpRequestNode, DatabaseNode, HumanApprovalNode, MultiAgentNode, DynamicNode, ScheduleNode, DiscordNode, DetachedTextNode, WebhookNode } from '../customNodes';
import { NodeRegistry } from '../nodeRegistry';

const nodeTypes = {
  webhookNode: WebhookNode,
  detachedText: DetachedTextNode,
  startNode: StartNode,
  scheduleNode: ScheduleNode,
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
  multiAgentNode: MultiAgentNode,
  discordNode: DiscordNode,
};

// Auto-register dynamic nodes
Object.keys(NodeRegistry).forEach(key => {
  nodeTypes[key] = DynamicNode;
});

let id = 0;
const getId = () => `dndnode_${id++}`;

function FlowContent() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, token } = useAuth();
  const reactFlowWrapper = useRef(null);

  const [appTheme, setAppTheme] = useState(document.documentElement.getAttribute('data-theme') || 'dark');
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setAppTheme(document.documentElement.getAttribute('data-theme') || 'dark');
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { screenToFlowPosition, getNodes, getEdges } = useReactFlow();
  const [response, setResponse] = useState('');
  const [isCompiled, setIsCompiled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
  const [tokenUsage, setTokenUsage] = useState(null);
  const [executionLogs, setExecutionLogs] = useState([]);
  const [isLive, setIsLive] = useState(false);

  const [isTokenTrackingMode, setIsTokenTrackingMode] = useState(false);
  const [estimatedTokens, setEstimatedTokens] = useState(null);
  const [isTokenDrawerOpen, setIsTokenDrawerOpen] = useState(false);
  const [systemLogs, setSystemLogs] = useState([]);
  const [isExecutionPanelOpen, setIsExecutionPanelOpen] = useState(false);
  const [executionPanelTab, setExecutionPanelTab] = useState('result'); // 'result' or 'logs'

  const tokenDisplayMode = localStorage.getItem('tokenDisplayMode') || 'tokens';
  const costCurrency = localStorage.getItem('costCurrency') || 'USD';

  const formatTokenDisplay = (tokens) => {
    if (!tokens && tokens !== 0) return '-';
    if (tokenDisplayMode === 'cost') {
      const usdCost = (tokens / 1000000) * 2.5; // 평균 $2.5 / 1M tokens
      const krwRate = Number(localStorage.getItem('krwRate')) || 1400;
      return costCurrency === 'KRW' ? `₩${Math.round(usdCost * krwRate).toLocaleString()}` : `$${usdCost.toFixed(4)}`;
    }
    return tokens.toLocaleString();
  };

  const [isAssistantOpen, setIsAssistantOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState(() => {
    if (location.state?.prompt) {
      return [
        { role: 'user', content: location.state.prompt },
        { role: 'assistant', content: `"${location.state.prompt}" 기능을 수행하는 봇 초안을 만들었어요!\n\n워크플로우 구성을 추가로 수정하거나 다듬을 부분이 있다면 언제든 말씀해 주세요.` }
      ];
    }
    return [
      { role: 'assistant', content: '안녕하세요! 워크플로우 수정을 도와드릴까요? 원하시는 구성을 말씀해 주세요. (예: 이메일 전송 노드를 추가하고 슬랙 알림을 연결해줘)' }
    ];
  });
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [complexityLevel, setComplexityLevel] = useState('low');

  const [projectTitle, setProjectTitle] = useState('Untitled Project');
  const [projectDescription, setProjectDescription] = useState('');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [visibility, setVisibility] = useState('private');
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
      setVisibility(data.visibility || 'private');
      setIsOwner(user && user.id === data.owner_id);

      if (data.graph_data) {
        setNodes(data.graph_data.nodes.map(n => ({
          ...n,
          data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode }
        })));
        setEdges(data.graph_data.edges || []);
        setIsLive(data.graph_data.is_live || false);
      }

      // 챗봇 대화 기록 불러오기
      if (token) {
        try {
          const chatRes = await axios.get(`/api/chat/session/${id}`, getAuthHeaders());
          if (chatRes.data.session && chatRes.data.session.messages) {
            setChatMessages(chatRes.data.session.messages);
          }
        } catch (chatErr) {
          console.error("Failed to load chat history", chatErr);
        }
      }

    } catch (error) {
      console.error("Failed to load project", error);
      alert("Failed to load project or unauthorized.");
    }
  };

  const handleSave = async (overrideVisibility = null) => {
    if (!user) {
      alert("프로젝트를 저장하려면 로그인이 필요합니다. 왼쪽 메뉴에서 구글 계정으로 로그인해주세요.");
      return null;
    }
    try {
      const payload = {
        title: projectTitle,
        description: projectDescription,
        graph_data: getCurrentFlowData(),
        visibility: overrideVisibility !== null ? overrideVisibility : visibility
      };

      if (currentId) {
        await axios.put(`/api/projects/${currentId}`, payload, getAuthHeaders());
        return currentId;
      } else {
        const res = await axios.post('/api/projects', payload, getAuthHeaders());
        setCurrentId(res.data.id);
        navigate(`/editor/${res.data.id}`, { replace: true });
        return res.data.id;
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

  const handleToggleLive = async () => {
    if (!currentId) {
      alert("프로젝트를 먼저 저장해 주세요.");
      return;
    }
    try {
      const res = await axios.post(`/api/projects/${currentId}/live`, { is_live: !isLive }, getAuthHeaders());
      if (res.data.status === 'success') {
        setIsLive(res.data.is_live);
        alert(res.data.is_live ? "라이브 모드가 시작되었습니다! (웹훅/스케줄/봇 대기중)" : "라이브 모드가 중지되었습니다.");
      }
    } catch (e) {
      console.error("Live toggle failed", e);
      alert("라이브 상태 변경에 실패했습니다.");
    }
  };




  const onNodesDelete = useCallback((nodesToDelete) => {
    setNodes((nds) => {
      let updatedNodes = [...nds];

      nodesToDelete.forEach(node => {
        if (node.type === 'detachedText') {
          updatedNodes = updatedNodes.map(n => {
            if (n.id === node.data.sourceId) {
              const newData = { ...n.data };
              newData[`isDetached_${node.data.fieldKey}`] = false;
              return { ...n, data: newData };
            }
            return n;
          });
        }
      });

      return updatedNodes;
    });
  }, [setNodes]);

  const onEdgesDelete = useCallback((edgesToDelete) => {
    setNodes((nds) => {
      let updatedNodes = [...nds];
      let nodesToDelete = new Set();

      edgesToDelete.forEach(edge => {
        const detachedNode = updatedNodes.find(n => (n.id === edge.source || n.id === edge.target) && n.type === 'detachedText');
        if (detachedNode) {
          nodesToDelete.add(detachedNode.id);

          updatedNodes = updatedNodes.map(n => {
            if (n.id === detachedNode.data.sourceId) {
              const newData = { ...n.data };
              newData[`isDetached_${detachedNode.data.fieldKey}`] = false;
              return { ...n, data: newData };
            }
            return n;
          });
        }
      });

      return updatedNodes.filter(n => !nodesToDelete.has(n.id));
    });
  }, [setNodes]);

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


      const popoutDataStr = event.dataTransfer.getData('application/reactflow-popout');
      if (popoutDataStr) {
        const popoutData = JSON.parse(popoutDataStr);
        const position = screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });

        const newNodeId = `popout_${popoutData.sourceId}_${popoutData.key}`;

        // Find source node to get initial text
        setNodes((nds) => {
          const sourceNode = nds.find(n => n.id === popoutData.sourceId);
          if (!sourceNode) return nds;

          const initialValue = sourceNode.data[popoutData.key];

          // Add new node
          const newNode = {
            id: newNodeId,
            type: 'detachedText',
            position,
            data: {
              label: '분리된 텍스트',
              onChange: onNodeDataChange,
              sourceId: popoutData.sourceId,
              fieldKey: popoutData.key,
              value: initialValue
            },
          };

          // Mark source as detached
          const updatedNodes = nds.map(n => {
            if (n.id === popoutData.sourceId) {
              return { ...n, data: { ...n.data, [`isDetached_${popoutData.key}`]: true } };
            }
            return n;
          });

          return updatedNodes.concat(newNode);
        });

        // Add edge
        setEdges((eds) => eds.concat({
          id: `e_${newNodeId}-${popoutData.sourceId}`,
          source: newNodeId,
          target: popoutData.sourceId,
          sourceHandle: 'out',
          targetHandle: `popout-${popoutData.key}`,
          animated: true,
          style: { stroke: '#ec4899', strokeWidth: 2 }
        }));

        return;
      }

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

    if (node.type === 'detachedText') {
      const intersections = getIntersectingNodes(node);
      const parentNode = intersections.find(n => n.id === node.data.sourceId);

      if (parentNode) {
        setEdges((eds) => eds.filter(e => e.source !== node.id && e.target !== node.id));
        setNodes((nds) => nds.filter(n => n.id !== node.id).map(n => {
          if (n.id === parentNode.id) {
            const newData = { ...n.data };
            newData[`isDetached_${node.data.fieldKey}`] = false;

            return { ...n, data: newData };
          }
          return n;
        }));
      }
      return;
    }

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
    // 자동 저장 (실행 전)
    const savedId = await handleSave();
    if (!savedId) {
      alert("프로젝트 저장에 실패하여 실행을 취소합니다.");
      return;
    }

    setIsLoading(true);
    setIsCompiled(false);
    setExecutionLogs([]); // Clear previous logs
    setResponse('Running graph on backend...');
    setIsExecutionPanelOpen(true);
    setExecutionPanelTab('result');

    try {
      const currentNodes = getNodes();
      const currentEdges = getEdges();

      const payload = {
        project_id: savedId,
        nodes: currentNodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
        edges: currentEdges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
      };

      const res = await axios.post('/api/execute', payload, getAuthHeaders());
      setResponse(res.data.result || 'No content returned.');
      setTokenUsage(res.data.token_usage || null);
      setExecutionLogs(res.data.logs || []);
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
      const currentNodes = getNodes();
      const currentEdges = getEdges();

      const payload = {
        nodes: currentNodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
        edges: currentEdges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
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

  const handleSendChat = async () => {
    if (!chatInput.trim()) return;

    const userMessage = chatInput;
    setChatMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setChatInput('');
    setIsChatLoading(true);

    // Clear existing AI modifications and highlights when starting a new AI request
    setNodes(nds => nds.map(nd => ({
      ...nd,
      data: { ...nd.data, isAIModified: false, aiChanges: null }
    })));

    try {
      const payload = {
        project_id: String(currentId || projectId || 'draft'),
        message: userMessage,
        graph_data: getCurrentFlowData(),
        complexity_level: complexityLevel,
      };
      const res = await axios.post('/api/chat', payload, getAuthHeaders());
      const { reply, graph_data } = res.data;

      if (reply) {
        setChatMessages(prev => [...prev, { role: 'assistant', content: reply }]);
      }

      // 챗봇이 flow를 바꿨으면 캔버스에 반영 — 기존 노드에 필요한 콜백(onChange/onDelete)을
      // handleLoadTemplate과 동일하게 다시 주입해줘야 편집/삭제가 계속 동작한다.
      if (graph_data) {
        const currentNodes = getNodes();
        const newLogs = [`> AI 작업 시작: "${userMessage}"`];

        const loadedNodes = (graph_data.nodes || []).map(n => {
          const oldNode = currentNodes.find(on => String(on.id) === String(n.id));
          const isNew = !oldNode;

          // data 중 onChange, onDelete 등을 제외하고 실제 내용만 비교
          const cleanOldData = oldNode ? { ...oldNode.data } : {};
          delete cleanOldData.onChange;
          delete cleanOldData.onDelete;
          delete cleanOldData.onClearAIHighlight;
          delete cleanOldData.isAIModified;

          const cleanNewData = { ...n.data };
          delete cleanNewData.onChange;
          delete cleanNewData.onDelete;
          delete cleanNewData.onClearAIHighlight;
          delete cleanNewData.isAIModified;
          delete cleanNewData.aiChanges;

          let aiChanges = [];
          if (oldNode) {
            for (const key of Object.keys(cleanNewData)) {
              if (JSON.stringify(cleanOldData[key]) !== JSON.stringify(cleanNewData[key])) {
                aiChanges.push({ key, old: cleanOldData[key], new: cleanNewData[key] });
              }
            }
          }

          const isModified = oldNode && JSON.stringify(cleanOldData) !== JSON.stringify(cleanNewData);

          if (isNew) {
            newLogs.push(`[생성] 새로운 노드가 추가되었습니다: ${n.type} (ID: ${n.id})`);
          } else if (isModified) {
            newLogs.push(`[수정] 노드가 변경되었습니다: ${n.type} (ID: ${n.id}) - 변경된 속성: ${aiChanges.map(c => c.key).join(', ')}`);
          }

          return {
            ...n,
            data: {
              ...n.data,
              isAIModified: isNew || isModified,
              aiChanges: (isNew || isModified) ? aiChanges : null,
              onChange: onNodeDataChange,
              onDelete: deleteNode,
              onClearAIHighlight: (nodeId) => {
                setNodes(nds => nds.map(nd => String(nd.id) === String(nodeId) ? { ...nd, data: { ...nd.data, isAIModified: false } } : nd));
              }
            },
          };
        });
        setNodes(loadedNodes);
        setEdges(graph_data.edges || []);

        if (newLogs.length > 1) {
          setSystemLogs(prev => [...prev, ...newLogs]);
          setIsTerminalOpen(true);
        }
      }
    } catch (error) {
      console.error(error);
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', content: `에러가 발생했습니다: ${error.response?.data?.detail || error.message}` }
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const enrichedNodes = useMemo(() => {
    return nodes.map(n => {
      const log = executionLogs.find(l => String(l.node_id) === String(n.id));

      let nodeClass = n.className || '';
      if (isLoading) {
        nodeClass = `${nodeClass} node-executing`.trim();
      } else if (log) {
        if (log.status === 'success') {
          nodeClass = `${nodeClass} node-success`.trim();
        } else if (log.status === 'error') {
          nodeClass = `${nodeClass} node-error`.trim();
        }
      }

      return {
        ...n,
        className: nodeClass,
        data: {
          ...n.data,
          isTokenTrackingMode,
          predictedTokens: estimatedTokens?.node_details?.[n.id] || null,
          actualTokens: tokenUsage?.nodes?.[n.id] || null,
          tokenDisplayMode,
          costCurrency,
          isExecuting: isLoading,
          executionStatus: log ? log.status : null
        }
      };
    });
  }, [nodes, isTokenTrackingMode, estimatedTokens, tokenUsage, tokenDisplayMode, costCurrency, isLoading, executionLogs]);

  return (
    <div className="app-container">
      <header className="header" style={{ position: 'relative', padding: '0.8rem 1.5rem', background: 'var(--card-bg)', borderBottom: '1px solid var(--border-color)', zIndex: 50 }}>
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
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>1회 실행 예상 (Min ~ Max)</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-color)' }}>
                    {estimatedTokens ? `${formatTokenDisplay(estimatedTokens.total_estimated_tokens)} ~ ${formatTokenDisplay(estimatedTokens.total_max_tokens)}` : '-'}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>마지막 실행 실제 소모량</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#10b981' }}>
                    {tokenUsage ? formatTokenDisplay(tokenUsage.total_tokens) : '-'}
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
                      width: '100%', background: 'var(--btn-active-bg)', border: '1px solid var(--border-color)',
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
                      width: '100%', background: 'var(--btn-active-bg)', border: '1px solid var(--border-color)',
                      color: 'var(--text-color)', fontSize: '0.9rem', padding: '0.5rem', borderRadius: '4px', outline: 'none',
                      resize: 'none', boxSizing: 'border-box'
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>

          {/* Project Management Group */}
          {isOwner && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '0.3rem 0.6rem' }}>
                <Share2 size={16} style={{ color: visibility === 'public' ? '#10b981' : visibility === 'friends' ? '#3b82f6' : 'var(--text-muted)' }} />
                <select
                  value={visibility}
                  onChange={(e) => {
                    const newVis = e.target.value;
                    setVisibility(newVis);
                    handleSave(newVis).then(s => s && console.log("Visibility updated automatically."));
                  }}
                  style={{ background: 'transparent', border: 'none', color: 'var(--text-color)', outline: 'none', fontSize: '0.85rem' }}
                >
                  <option value="private" style={{ background: 'var(--bg-color)', color: 'var(--text-color)' }}>비공개</option>
                  <option value="friends" style={{ background: 'var(--bg-color)', color: 'var(--text-color)' }}>친구공개</option>
                  <option value="public" style={{ background: 'var(--bg-color)', color: 'var(--text-color)' }}>공개</option>
                </select>
              </div>
              <button className="btn-secondary" onClick={() => { handleSave().then(s => s && alert("저장되었습니다.")); }} title="저장">
                <Save size={16} />
              </button>
            </div>
          )}

          <div style={{ width: '1px', height: '24px', background: 'var(--border-color)' }}></div>

          {/* Tools Group */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {nodes.some(n => ['webhookNode', 'scheduleNode', 'discordNode'].includes(n.type)) && (
              <button 
                className={`btn-primary ${isLive ? 'active-live' : ''}`} 
                onClick={handleToggleLive} 
                style={{ 
                  background: isLive ? '#ef4444' : '#10b981', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '6px',
                  boxShadow: isLive ? '0 0 10px rgba(239, 68, 68, 0.4)' : 'none'
                }} 
                title="라이브 시작/중지"
              >
                {isLive ? <Square size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" />}
                {isLive ? "라이브 중지" : "라이브 시작"}
              </button>
            )}
            <button className="btn-secondary" onClick={() => setIsTemplateModalOpen(true)} title="템플릿 불러오기">
              <Folder size={16} />
            </button>
            {currentId && (
              <button className="btn-secondary" onClick={() => navigate(`/project/${currentId}/runs`)} style={{ color: '#10b981', borderColor: '#10b981' }} title="실행 기록">
                <History size={16} />
              </button>
            )}
            {isOwner && currentId && (
              <button className="btn-secondary" onClick={handleOpenDeployModal} style={{ color: '#8b5cf6', borderColor: '#8b5cf6' }} title="배포">
                <Wand2 size={16} />
              </button>
            )}
          </div>

          <div style={{ width: '1px', height: '24px', background: 'var(--border-color)' }}></div>

          {/* Token Optimization Group */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button className="btn-secondary" onClick={async () => {
              try {
                const payload = {
                  nodes: nodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
                  edges: edges.map(e => ({ source: e.source, target: e.target }))
                };
                const res = await axios.post('/api/estimate', payload);
                if (res.data.status === 'success') {
                  setEstimatedTokens(res.data);
                  alert(`[예상 소모 ${tokenDisplayMode === 'cost' ? '비용' : '토큰량'}]\n최소 ${formatTokenDisplay(res.data.total_estimated_tokens)} ~ 최대 ${formatTokenDisplay(res.data.total_max_tokens)} ${tokenDisplayMode === 'cost' ? '' : 'tokens'}`);
                } else {
                  alert(`${tokenDisplayMode === 'cost' ? '비용' : '토큰'} 계산 실패: ` + res.data.message);
                }
              } catch (error) {
                console.error(error);
                alert('예상 토큰 계산 중 오류가 발생했습니다.');
              }
            }} style={{ color: '#f59e0b', borderColor: '#f59e0b' }} title="예상 비용 계산">
              <BrainCircuit size={16} />
            </button>
            <button
              className="btn-secondary"
              onClick={() => setIsTokenTrackingMode(!isTokenTrackingMode)}
              style={{
                borderColor: isTokenTrackingMode ? '#3b82f6' : 'var(--border-color)',
                color: isTokenTrackingMode ? '#3b82f6' : 'var(--text-muted)'
              }}
              title="비용 추적 모드"
            >
              추적 {isTokenTrackingMode ? 'ON' : 'OFF'}
            </button>
          </div>

          {/* Primary Action */}
          <button className="btn-run" onClick={runFlow} disabled={isLoading} style={{ marginLeft: '0.5rem' }}>
            <Play size={18} />
            {isLoading ? '실행 중...' : '실행'}
          </button>
        </div>
      </header>

      <main className="main-content">
        <Sidebar />
        <div className="flow-wrapper" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={enrichedNodes}
            edges={edges.map(e => ({
              ...e,
              animated: isLoading || e.animated,
              style: { ...e.style, stroke: isLoading ? '#10b981' : (e.style?.stroke || '#475569') }
            }))}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onEdgesDelete={onEdgesDelete}
            onNodesDelete={onNodesDelete}
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
            colorMode={appTheme}
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
            <Background variant="dots" gap={24} size={2} color={appTheme === 'dark' ? '#64748b' : '#94a3b8'} />
          </ReactFlow>
        </div>


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
            // Deployment config saved successfully
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
        background: 'var(--card-bg)',
        backdropFilter: 'blur(12px)',
        border: '1px solid var(--border-color)',
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
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          background: 'var(--btn-active-bg)',
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
          {isChatLoading && (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start'
            }}>
              <div style={{
                maxWidth: '85%',
                padding: '0.75rem 1rem',
                borderRadius: '12px',
                background: 'var(--btn-active-bg)',
                color: 'var(--text-color)',
                fontSize: '0.9rem',
                lineHeight: '1.4',
                border: '1px solid var(--border-color)',
                borderBottomLeftRadius: '4px'
              }}>
                <div className="typing-indicator" style={{ border: 'none', background: 'transparent', padding: 0, boxShadow: 'none', marginTop: 0 }}>
                  <div className="typing-dot"></div>
                  <div className="typing-dot"></div>
                  <div className="typing-dot"></div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Chat Input & Options */}
        <div style={{
          padding: '1rem',
          borderTop: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
          background: 'var(--btn-active-bg)',
          borderBottomLeftRadius: '16px',
          borderBottomRightRadius: '16px'
        }}>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.2rem' }}>
            {['low', 'medium', 'high'].map(level => (
              <label key={level} style={{
                fontSize: '0.8rem',
                color: complexityLevel === level ? '#fff' : 'var(--text-muted)',
                background: complexityLevel === level ? 'var(--primary-color)' : 'transparent',
                padding: '0.2rem 0.6rem',
                borderRadius: '12px',
                cursor: 'pointer',
                border: `1px solid ${complexityLevel === level ? 'var(--primary-color)' : 'var(--border-color)'}`,
                transition: 'all 0.2s'
              }}>
                <input 
                  type="radio" 
                  name="complexity" 
                  value={level} 
                  checked={complexityLevel === level} 
                  onChange={() => setComplexityLevel(level)} 
                  style={{ display: 'none' }} 
                />
                {level === 'low' ? '빠름' : level === 'medium' ? '일반' : '정밀'}
              </label>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
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

      {/* Unified Execution Panel */}
      {isExecutionPanelOpen && (
        <div style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          height: '35vh',
          minHeight: '250px',
          background: 'var(--card-bg)',
          borderTop: '1px solid var(--border-color)',
          zIndex: 900,
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 -10px 30px rgba(0,0,0,0.5)',
          transition: 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
          transform: 'translateY(0)'
        }}>
          {/* Header & Tabs */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'var(--bg-color)',
            borderBottom: '1px solid var(--border-color)',
            padding: '0 1rem'
          }}>
            <div style={{ display: 'flex' }}>
              <button
                onClick={() => setExecutionPanelTab('result')}
                style={{
                  padding: '1rem 1.5rem',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: executionPanelTab === 'result' ? '2px solid #60a5fa' : '2px solid transparent',
                  color: executionPanelTab === 'result' ? '#60a5fa' : 'var(--text-muted)',
                  fontWeight: executionPanelTab === 'result' ? 600 : 400,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  fontSize: '0.9rem'
                }}
              >
                <Play size={16} /> 결과 (Result)
              </button>
              <button
                onClick={() => setExecutionPanelTab('logs')}
                style={{
                  padding: '1rem 1.5rem',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: executionPanelTab === 'logs' ? '2px solid #a78bfa' : '2px solid transparent',
                  color: executionPanelTab === 'logs' ? '#a78bfa' : 'var(--text-muted)',
                  fontWeight: executionPanelTab === 'logs' ? 600 : 400,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  fontSize: '0.9rem'
                }}
              >
                <TerminalSquare size={16} /> 시스템 로그
              </button>
            </div>
            <button
              onClick={() => setIsExecutionPanelOpen(false)}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '0.5rem' }}
            >
              <X size={20} />
            </button>
          </div>

          {/* Content Area */}
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
            {executionPanelTab === 'result' && (
              <div style={{ padding: '1.5rem', flex: 1, display: 'flex', flexDirection: 'column' }}>
                {isTokenTrackingMode && tokenUsage && (
                  <div style={{ padding: '0.8rem', marginBottom: '1rem', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)', borderRadius: '8px', fontSize: '0.85rem' }}>
                    <div style={{ fontWeight: 'bold', color: '#60a5fa', marginBottom: '0.5rem' }}>
                      {tokenDisplayMode === 'cost' ? '소모 비용 (Estimated Cost)' : '토큰 사용량 (Token Usage)'}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
                      <span>총 {tokenDisplayMode === 'cost' ? '비용' : '소모 토큰'}: {formatTokenDisplay(tokenUsage.total_tokens)}</span>
                      <span>입력: {formatTokenDisplay(tokenUsage.total_input)} / 출력: {formatTokenDisplay(tokenUsage.total_output)}</span>
                    </div>
                  </div>
                )}
                <div style={{ flex: 1, background: 'var(--bg-color)', borderRadius: '8px', padding: '1rem', border: '1px solid var(--border-color)', overflowY: 'auto' }}>
                  {isCompiled ? (
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.9rem', color: 'var(--text-color)' }}>
                      <code>{response || 'Run or Compile the flow to see the results here.'}</code>
                    </pre>
                  ) : (
                    (response && typeof response === 'string' && (response.startsWith('uploads/') || response.startsWith('uploads\\'))) ? (
                      <div>
                        <p style={{ color: 'var(--text-color)' }}>File generated successfully:</p>
                        <a
                          href={`http://localhost:8000/${response.replace(/\\/g, '/')}`}
                          target="_blank" rel="noreferrer"
                          style={{ display: 'inline-block', padding: '8px 16px', background: '#3b82f6', color: '#fff', textDecoration: 'none', borderRadius: '6px', marginTop: '10px', fontWeight: 500 }}
                        >
                          Download File
                        </a>
                      </div>
                    ) : (
                      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: 'var(--text-color)', fontSize: '0.95rem', lineHeight: '1.6' }}>{response || '대기 중...'}</div>
                    )
                  )}
                </div>
              </div>
            )}

            {executionPanelTab === 'logs' && (
              <div style={{ flex: 1, padding: '1rem', background: '#1e1e1e', color: '#00ff00', fontFamily: 'monospace', fontSize: '0.85rem', overflowY: 'auto' }}>
                {systemLogs.length === 0 ? (
                  <span style={{ color: '#666' }}>로그가 없습니다.</span>
                ) : (
                  systemLogs.map((log, i) => (
                    <div key={i} style={{ wordBreak: 'break-all', marginBottom: '4px' }}>
                      {log.startsWith('>') ? <span style={{ color: '#00bfff', marginTop: '8px', display: 'inline-block' }}>{log}</span> : log}
                    </div>
                  ))
                )}
                <div ref={el => el?.scrollIntoView()} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Execution Panel Toggle Button (if closed) */}
      {!isExecutionPanelOpen && (response || systemLogs.length > 0) && (
        <button
          onClick={() => setIsExecutionPanelOpen(true)}
          style={{
            position: 'fixed',
            bottom: '1.5rem',
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'var(--card-bg)',
            color: 'var(--text-color)',
            border: '1px solid var(--border-color)',
            borderRadius: '20px',
            padding: '0.5rem 1.5rem',
            fontSize: '0.9rem',
            fontWeight: 500,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            zIndex: 800,
            transition: 'all 0.2s'
          }}
        >
          <Play size={16} color="#60a5fa" />
          실행 결과 보기
        </button>
      )}

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


