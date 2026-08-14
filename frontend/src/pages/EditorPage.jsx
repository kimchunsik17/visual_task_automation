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
import { Play, Code, Folder, Save, Share2, ArrowLeft, Wand2, Settings, Sparkles, Send, Bot, BrainCircuit, History, TerminalSquare, X, Square, Network, TestTube, ChevronsDown, ChevronsUp, Undo2, Redo2, Plus, MoreVertical } from 'lucide-react';
import Sidebar from '../Sidebar';
import TemplateModal from '../TemplateModal';
import DeployModal from '../DeployModal';
import TutorialOverlay from '../TutorialOverlay';
import { useAuth } from '../AuthContext';
import { customConfirm } from '../CustomConfirm';
import { StartNode, PromptNode, LLMNode, OutputNode, ConditionNode, ValueNode, LoopNode, BreakNode, PythonNode, TokenizerNode, DistributorNode, FileModifierNode, TemplateAnalyzerNode, DynamicInputNode, WebCrawlerNode, EmailNode, KakaoNode, DelayNode, JsonParserNode, MergeNode, HttpRequestNode, DatabaseNode, HumanApprovalNode, MultiAgentNode, DynamicNode, ScheduleNode, DiscordNode, DiscordTriggerNode, TelegramNode, TelegramTriggerNode, NotionNode, DetachedTextNode, WebhookNode } from '../customNodes';
import { NodeRegistry } from '../nodeRegistry';
import dagre from 'dagre';
import ReactMarkdown from 'react-markdown';

const EDITOR_TUTORIAL_STEPS = [
  {
    target: '.sidebar',
    title: '노드 팔레트',
    description: '워크플로우에 쓸 수 있는 모든 노드가 여기 있어요. 원하는 노드를 캔버스로 드래그해서 놓아보세요.',
    placement: 'right',
  },
  {
    target: '.flow-wrapper',
    title: '캔버스',
    description: '노드를 배치하고 서로 연결해서 워크플로우를 그리는 공간이에요. 노드를 클릭하면 세부 설정도 바꿀 수 있어요.',
    placement: 'right',
  },
  {
    target: '[data-tutorial="ai-assistant-btn"]',
    title: 'AI 워크플로우 어시스턴트',
    description: '말로 설명하면 AI가 노드를 대신 만들어주거나 지금 만든 워크플로우를 수정해줘요. 막힐 때 가장 먼저 써보세요.',
    placement: 'left',
  },
  {
    target: '[data-tutorial="quality-gate-group"]',
    title: '평가 & 자동 개선',
    description: '실제로 실행하기 전에 "평가"로 미리 테스트해보고, "자동 개선"으로 부족한 부분을 AI가 보완하게 할 수 있어요.',
    placement: 'bottom',
  },
  {
    target: '.btn-run',
    title: '실행',
    description: '워크플로우가 준비되면 이 버튼으로 직접 실행해서 결과를 확인해보세요.',
    placement: 'bottom',
  },
];

const getLayoutedElements = (nodes, edges, direction = 'LR') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  // Average estimated node dimensions
  const fallbackWidth = 320;
  const fallbackHeight = 200;

  // ranksep: horizontal distance between layers (LR)
  // nodesep: vertical distance between nodes in the same layer
  dagreGraph.setGraph({ 
    rankdir: direction, 
    ranksep: 150, 
    nodesep: 80,
    edgesep: 50
  });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { 
      width: node.measured?.width || fallbackWidth, 
      height: node.measured?.height || fallbackHeight 
    });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  // Force all edges to bezier curves to prevent straight line overlaps
  const layoutedEdges = edges.map(edge => ({
    ...edge,
    type: 'bezier'
  }));

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const width = node.measured?.width || fallbackWidth;
    const height = node.measured?.height || fallbackHeight;
    // Shift dagre node position (anchor=center) to top-left
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - width / 2,
        y: nodeWithPosition.y - height / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges: layoutedEdges };
};

// 백엔드 auto_layout()은 새로 생성된 노드를 전부 같은 y좌표의 한 줄로만 배치한다(분기/병합
// 구조를 고려하지 않음). 분기가 있는 워크플로우에서는 노드들이 한 줄에 다닥다닥 겹쳐 보여서
// "노드가 중복돼서 나온다"는 것처럼 보이는 원인이 된다. 노드가 2개 이상인데 전부 y좌표가
// 같으면 이 패턴으로 보고, dagre로 제대로 된 2D 레이아웃을 다시 계산해서 덮어쓴다.
// (이미 여러 y값으로 흩어져 있는 — 즉 사용자가 손으로 배치했거나 이미 정렬된 — 그래프는
// 건드리지 않는다.)
const looksLikeUnlaidOutRow = (nodes) => {
  if (!nodes || nodes.length < 2) return false;
  const ys = new Set(nodes.map(n => n.position?.y));
  return ys.size <= 1;
};

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
  discordTriggerNode: DiscordTriggerNode,
  telegramNode: TelegramNode,
  telegramTriggerNode: TelegramTriggerNode,
  notionNode: NotionNode,
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
  const [isPaletteOpen, setIsPaletteOpen] = useState(false);
  const [isMobileToolsDrawerOpen, setIsMobileToolsDrawerOpen] = useState(false);
  const [isExecutionPanelOpen, setIsExecutionPanelOpen] = useState(false);
  const [executionPanelTab, setExecutionPanelTab] = useState('result'); // 'result' or 'logs' or 'evaluation'
  const [executionPanelHeight, setExecutionPanelHeight] = useState(300); // initial height in px

  // Evaluation States
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evalStep, setEvalStep] = useState(0);
  const [evaluationReport, setEvaluationReport] = useState(null);
  const [isAutoImproving, setIsAutoImproving] = useState(false);

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
  const [chatStage, setChatStage] = useState('대기 중');
  const [complexityLevel, setComplexityLevel] = useState('medium');
  const messagesEndRef = useRef(null);
  const abortControllerRef = useRef(null);

  // 챗봇이 그래프를 바꿀 때마다 스냅샷을 쌓아서 되돌리기/다시 실행을 지원한다. index 0은 챗봇이
  // 처음 손대기 "직전"의 캔버스 상태(베이스라인)이고, 그 뒤로 챗봇 턴마다 하나씩 쌓인다 — 이미
  // undo한 상태에서 챗봇이 새로 작업하면(redo 가능 구간을 무시하고 새 분기가 생기는 것과 같음)
  // 그 시점 이후의 "미래" 스냅샷은 버린다(표준 undo/redo 스택 동작과 동일).
  const [chatHistory, setChatHistory] = useState([]);
  const [chatHistoryIndex, setChatHistoryIndex] = useState(-1);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, isChatLoading]);

  const [expandAllCommand, setExpandAllCommand] = useState(null);
  const [projectTitle, setProjectTitle] = useState('Untitled Project');
  const [projectDescription, setProjectDescription] = useState('');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [visibility, setVisibility] = useState('private');
  const [isOwner, setIsOwner] = useState(true); // Default true for new projects
  const [currentId, setCurrentId] = useState(projectId);
  const [draftSessionId, setDraftSessionId] = useState(null);
  const [latestGenerationTraceId, setLatestGenerationTraceId] = useState(location.state?.traceId || null);

  // Configure Axios auth header
  const getAuthHeaders = () => token ? { headers: { Authorization: `Bearer ${token}` } } : {};

  useEffect(() => {
    if (projectId) {
      loadProject(projectId);
    } else if (location.state?.initialGraph) {
      const graph = location.state.initialGraph;
      const rawNodes = graph.nodes.map(n => ({
        ...n,
        data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange }
      }));
      if (looksLikeUnlaidOutRow(rawNodes)) {
        const layouted = getLayoutedElements(rawNodes, graph.edges || [], 'LR');
        setNodes(layouted.nodes);
        setEdges(layouted.edges);
      } else {
        setNodes(rawNodes);
        setEdges(graph.edges || []);
      }

      if (graph.title) {
        setProjectTitle(graph.title);
      } else if (location.state?.prompt) {
        setProjectTitle("AI 생성 워크플로우");
      }

      if (graph.description) {
        setProjectDescription(graph.description);
      }

      // 홈페이지(MainPage)에서 이어진 draft 채팅 세션이면, 같은 세션 id를 그대로 이어받아서
      // 채팅 스레드가 끊기지 않게 한다 — 안 그러면 에디터가 완전히 새 대화로 시작해서
      // 홈페이지에서 나눈 대화 맥락을 전혀 모르는 상태가 된다.
      if (location.state?.draftId) {
        const draftId = location.state.draftId;
        setDraftSessionId(draftId);
        if (token) {
          axios.get(`/api/chat/session/${draftId}`, getAuthHeaders())
            .then(res => {
              if (res.data.session && res.data.session.messages) {
                setChatMessages(res.data.session.messages);
              }
            })
            .catch(err => console.error("Failed to load draft chat history", err));
        }
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
          data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange }
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

  const handleSave = async (overrideVisibility = null, overrideFlowData = null, overrideTraceId = null) => {
    if (!user) {
      alert("프로젝트를 저장하려면 로그인이 필요합니다. 왼쪽 메뉴에서 구글 계정으로 로그인해주세요.");
      return null;
    }
    try {
      // overrideFlowData: setNodes/setEdges 직후 곧바로 저장해야 할 때(예: AI 생성 직후 자동 저장)
      // getCurrentFlowData()가 React Flow 내부 상태 반영 전이라 방금 만든 노드를 못 읽어오는
      // 타이밍 문제가 있었다(실제로 빈 그래프가 저장되는 걸 확인함) — 이럴 땐 이미 손에 들고 있는
      // 최신 graph_data를 그대로 쓰도록 우회 경로를 둔다.
      const payload = {
        title: projectTitle,
        description: projectDescription,
        graph_data: overrideFlowData || getCurrentFlowData(),
        visibility: overrideVisibility !== null ? overrideVisibility : visibility,
        generation_trace_id: overrideTraceId || latestGenerationTraceId,
      };

      if (currentId) {
        await axios.put(`/api/projects/${currentId}`, payload, getAuthHeaders());
        return currentId;
      } else {
        if (draftSessionId) {
          payload.draft_session_id = draftSessionId;
        }
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
        if (res.data.warning) {
          alert("⚠️ " + res.data.warning);
        } else {
          alert(res.data.is_live ? "라이브 모드가 시작되었습니다! (웹훅/스케줄/봇 대기중)" : "라이브 모드가 중지되었습니다.");
        }
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

  // ── Node expand/collapse push logic ──
  // Tracks which nodes are currently expanded
  const expandedNodesRef = useRef(new Set());
  // Tracks the push deltas applied to other nodes when a node was expanded
  // Format: { [expandedNodeId]: { [pushedNodeId]: { dx, dy } } }
  const pushDeltasRef = useRef({});

  const COLLAPSED_W = 140;   // px in flow coordinates
  const COLLAPSED_H = 140;
  const EXPANDED_W  = 320;   // approximate expanded width
  const EXPANDED_H  = 260;   // approximate expanded height
  const PUSH_MARGIN = 40;    // extra breathing room

  const onExpandChange = useCallback((expandedId, isExpanded) => {
    setNodes((nds) => {
      const expandedNode = nds.find(n => n.id === expandedId);
      if (!expandedNode) return nds;

      if (isExpanded) {
        expandedNodesRef.current.add(expandedId);
        
        const ex = expandedNode.position.x;
        const ey = expandedNode.position.y;
        const dw = EXPANDED_W - COLLAPSED_W;
        const dh = EXPANDED_H - COLLAPSED_H;
        
        const currentPushes = {};

        const newNds = nds.map(n => {
          if (n.id === expandedId) return n;
          const nx = n.position.x;
          const ny = n.position.y;

          let dx = 0;
          let dy = 0;

          // Push right: node is to the right of the expanding node
          if (nx > ex + COLLAPSED_W - 10) {
            dx = dw + PUSH_MARGIN;
          }
          // Push down: node is below the expanding node (and horizontally overlapping)
          if (ny > ey + COLLAPSED_H - 10 && nx < ex + EXPANDED_W + PUSH_MARGIN && nx + COLLAPSED_W > ex - PUSH_MARGIN) {
            dy = dh + PUSH_MARGIN;
          }

          if (dx === 0 && dy === 0) return n;
          
          currentPushes[n.id] = { dx, dy };
          return { ...n, position: { x: nx + dx, y: ny + dy } };
        });
        
        pushDeltasRef.current[expandedId] = currentPushes;
        return newNds;
        
      } else {
        expandedNodesRef.current.delete(expandedId);
        
        const appliedPushes = pushDeltasRef.current[expandedId];
        if (!appliedPushes) return nds;
        delete pushDeltasRef.current[expandedId];

        return nds.map(n => {
          if (n.id === expandedId) return n;
          const push = appliedPushes[n.id];
          if (!push) return n;
          
          return { ...n, position: { x: n.position.x - push.dx, y: n.position.y - push.dy } };
        });
      }
    });
  }, [setNodes]);

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
        data: { label: `${type} node`, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange },
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
    [screenToFlowPosition, setNodes, onNodeDataChange, deleteNode, onExpandChange],
  );

  const handleNodeTap = useCallback((type, label) => {
    // Determine screen center for the node spawn point on mobile
    const position = screenToFlowPosition({
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
    });

    const newNode = {
      id: getId(),
      type,
      position,
      data: { label: `${type} node`, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange },
      zIndex: type === 'loopNode' ? -1 : 1,
    };

    setNodes((nds) => nds.concat(newNode));
    setIsPaletteOpen(false); // Close palette after adding
  }, [screenToFlowPosition, setNodes, onNodeDataChange, deleteNode, onExpandChange]);

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

  const evaluateFlow = async () => {
    const savedId = await handleSave();
    if (!savedId) {
      alert("프로젝트 저장에 실패하여 평가를 취소합니다.");
      return;
    }

    // Warn about cost if necessary, or just run
    const confirmed = await customConfirm("워크플로우 평가는 다중 LLM 에이전트(Dataset 생성, 실행, 평가, 종합)를 활용하므로 다수의 API 호출이 발생합니다. (테스트 케이스 3개, 외부 API 노드가 있다면 그대로 1회 실행됩니다.)\n\n계속하시겠습니까?");
    if (!confirmed) return;

    setIsEvaluating(true);
    setEvalStep(0);
    setEvaluationReport(null);
    setIsExecutionPanelOpen(true);
    setExecutionPanelTab('evaluation');

    // Simulate progress steps
    const stepInterval = setInterval(() => {
      setEvalStep(prev => (prev < 3 ? prev + 1 : prev));
    }, 5000);

    try {
      const currentNodes = getNodes();
      const currentEdges = getEdges();

      const payload = {
        project_id: savedId,
        title: projectTitle,
        description: projectDescription,
        graph_data: {
          nodes: currentNodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
          edges: currentEdges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
        }
      };

      const res = await axios.post('/api/evaluate', payload, getAuthHeaders());
      if (res.data.status === 'success') {
        setEvaluationReport(res.data.report);
      } else {
        alert('평가 실패: ' + res.data.message);
      }
    } catch (error) {
      console.error(error);
      const detail = error.response?.data?.detail || error.message;
      alert(`평가 중 오류가 발생했습니다: ${detail}`);
    } finally {
      clearInterval(stepInterval);
      setIsEvaluating(false);
    }
  };

  const autoImproveFlow = async () => {
    const savedId = await handleSave();
    if (!savedId) {
      alert("프로젝트 저장에 실패하여 자동 개선을 취소합니다.");
      return;
    }

    const confirmed = await customConfirm("자동 개선은 평가와 수정을 기준 점수를 넘거나 최대 3회에 도달할 때까지 반복합니다. 평가 1회보다 훨씬 많은 API 호출과 토큰이 소모될 수 있습니다.\n\n계속하시겠습니까?");
    if (!confirmed) return;

    setIsAutoImproving(true);
    setEvaluationReport(null);
    setIsExecutionPanelOpen(true);
    setExecutionPanelTab('evaluation');

    try {
      const currentNodes = getNodes();
      const currentEdges = getEdges();

      const payload = {
        project_id: savedId,
        title: projectTitle,
        description: projectDescription,
        graph_data: {
          nodes: currentNodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
          edges: currentEdges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
        }
      };

      const res = await axios.post('/api/evaluate/autofix', payload, getAuthHeaders());
      if (res.data.status === 'success') {
        const report = res.data.report;
        setEvaluationReport(report);
        if (report.graph_data) {
          const rawNodes = report.graph_data.nodes.map(n => ({
            ...n,
            data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange }
          }));
          if (looksLikeUnlaidOutRow(rawNodes)) {
            const layouted = getLayoutedElements(rawNodes, report.graph_data.edges || [], 'LR');
            setNodes(layouted.nodes);
            setEdges(layouted.edges);
          } else {
            setNodes(rawNodes);
            setEdges(report.graph_data.edges || []);
          }
        }
      } else {
        alert('자동 개선 실패: ' + res.data.message);
      }
    } catch (error) {
      console.error(error);
      const detail = error.response?.data?.detail || error.message;
      alert(`자동 개선 중 오류가 발생했습니다: ${detail}`);
    } finally {
      setIsAutoImproving(false);
    }
  };

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
      data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange }
    }));
    setNodes(loadedNodes);
    setEdges(templateData.edges || []);
  };

  const getCurrentFlowData = () => {
    return {
      title: projectTitle !== 'Untitled Project' ? projectTitle : '',
      description: projectDescription,
      nodes: getNodes().map(n => {
        const nData = { ...n.data };
        delete nData.onChange;
        delete nData.onDelete;
        delete nData.onExpandChange;
        delete nData.onClearAIHighlight;
        delete nData.isAIModified;
        delete nData.aiChanges;
        return { id: n.id, type: n.type, position: n.position, data: nData };
      }),
      edges: getEdges()
    };
  };

  const handleClearAllHighlights = () => {
    setNodes(nds => nds.map(nd => ({
      ...nd,
      data: { ...nd.data, isAIModified: false, aiChanges: null }
    })));
  };

  const handleCancelChat = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  // 스냅샷에 저장된 노드는 onChange/onDelete 같은 콜백을 그대로 들고 있을 수도 있지만, 되돌리기
  // 시점에는 항상 "지금" 유효한 콜백으로 다시 꽂아준다(handleSendChat이 AI 결과를 반영할 때와
  // 동일한 방식) — stale 클로저를 참조할 위험을 아예 없앤다. 하이라이트 표시(isAIModified 등)는
  // 과거 시점 것이라 의미가 없으므로 복원 시 지운다.
  const applyHistorySnapshot = (snapshot) => {
    const restoredNodes = (snapshot.nodes || []).map(n => ({
      ...n,
      data: {
        ...n.data,
        isAIModified: false,
        aiChanges: null,
        onChange: onNodeDataChange,
        onDelete: deleteNode,
        onExpandChange,
        onClearAIHighlight: (nodeId) => {
          setNodes(nds => nds.map(nd => String(nd.id) === String(nodeId) ? { ...nd, data: { ...nd.data, isAIModified: false } } : nd));
        }
      }
    }));
    setNodes(restoredNodes);
    setEdges(snapshot.edges || []);
  };

  const handleUndoChat = () => {
    if (chatHistoryIndex <= 0) return;
    const targetIndex = chatHistoryIndex - 1;
    applyHistorySnapshot(chatHistory[targetIndex]);
    setChatHistoryIndex(targetIndex);
    setSystemLogs(prev => [...prev, `> ↩ 이전 상태로 되돌렸습니다${chatHistory[targetIndex].label ? ` ("${chatHistory[targetIndex].label}" 이전)` : ''}`]);
  };

  const handleRedoChat = () => {
    if (chatHistoryIndex < 0 || chatHistoryIndex >= chatHistory.length - 1) return;
    const targetIndex = chatHistoryIndex + 1;
    applyHistorySnapshot(chatHistory[targetIndex]);
    setChatHistoryIndex(targetIndex);
    setSystemLogs(prev => [...prev, `> ↪ 다시 실행했습니다${chatHistory[targetIndex].label ? ` ("${chatHistory[targetIndex].label}")` : ''}`]);
  };

  // Ctrl/Cmd+Z로 되돌리기, Ctrl/Cmd+Shift+Z(또는 Ctrl+Y)로 다시 실행. 입력창(input/textarea)에
  // 포커스가 있을 때는 가로채지 않는다 — 안 그러면 채팅창이나 노드 텍스트 필드에서 브라우저
  // 기본 텍스트 되돌리기가 안 먹히고 엉뚱하게 그래프가 되돌아가 버린다.
  useEffect(() => {
    const handleKeyDown = (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable) return;
      const isUndoKey = (e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z';
      const isRedoKey = (e.ctrlKey || e.metaKey) && (
        (e.shiftKey && e.key.toLowerCase() === 'z') || e.key.toLowerCase() === 'y'
      );
      if (isUndoKey) {
        e.preventDefault();
        handleUndoChat();
      } else if (isRedoKey) {
        e.preventDefault();
        handleRedoChat();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [chatHistory, chatHistoryIndex, isChatLoading]);

  const handleSendChat = async () => {
    if (!chatInput.trim()) return;

    const userMessage = chatInput;
    setChatMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setChatInput('');
    setIsChatLoading(true);
    setChatStage('유저의 의도를 파악하고 있어요');

    const stageSteps = [
      '유저의 의도를 파악하고 있어요',
      '워크플로우 구조를 검토하고 있어요',
      'AI 검증을 지나고 있어요',
      '수정안을 반영하고 있어요',
      '결과를 정리하고 있어요',
    ];
    let stageIndex = 0;
    const stageTimer = setInterval(() => {
      stageIndex = Math.min(stageIndex + 1, stageSteps.length - 1);
      setChatStage(stageSteps[stageIndex]);
    }, 2500);

    // 되돌리기 스택의 베이스라인 후보 — 이번 챗봇 턴이 그래프를 실제로 바꾸면, 지금(바뀌기
    // 직전) 상태를 히스토리 0번으로 삼아야 "되돌리기"가 챗봇이 손대기 이전으로 돌아갈 수 있다.
    const preEditNodes = getNodes();
    const preEditEdges = getEdges();

    // Clear existing AI modifications and highlights when starting a new AI request
    setNodes(nds => nds.map(nd => ({
      ...nd,
      data: { ...nd.data, isAIModified: false, aiChanges: null }
    })));

    try {
      const payload = {
        project_id: String(currentId || projectId || draftSessionId || 'draft'),
        message: userMessage,
        graph_data: getCurrentFlowData(),
        complexity_level: complexityLevel,
        training_consent: localStorage.getItem('llmTrainingConsent') === 'true',
      };
      
      abortControllerRef.current = new AbortController();
      const res = await axios.post('/api/chat', payload, {
        ...getAuthHeaders(),
        signal: abortControllerRef.current.signal
      });
      const { reply, graph_data, trace_id, generation_outcome } = res.data;

      if (trace_id && generation_outcome === 'graph') {
        setLatestGenerationTraceId(trace_id);
      }

      if (reply) {
        setChatMessages(prev => [...prev, { role: 'assistant', content: reply }]);
      }

      // 챗봇이 flow를 바꿨으면 캔버스에 반영 — 기존 노드에 필요한 콜백(onChange/onDelete)을
      // handleLoadTemplate과 동일하게 다시 주입해줘야 편집/삭제가 계속 동작한다.
      if (graph_data) {
        if (graph_data.title && (!projectTitle || projectTitle === 'Untitled Project' || projectTitle === 'AI 생성 워크플로우')) {
          setProjectTitle(graph_data.title);
        }
        if (graph_data.description && (!projectDescription || projectDescription === '')) {
          setProjectDescription(graph_data.description);
        }
        const currentNodes = getNodes();
        const newLogs = [`> AI 작업 시작: "${userMessage}"`];

        const loadedNodes = (graph_data.nodes || []).map(n => {
          const oldNode = currentNodes.find(on => String(on.id) === String(n.id));
          const isNew = !oldNode;

          const stripUIProps = (dataObj) => {
            if (!dataObj) return {};
            const clean = { ...dataObj };
            delete clean.onChange;
            delete clean.onDelete;
            delete clean.onExpandChange;
            delete clean.onClearAIHighlight;
            delete clean.isAIModified;
            delete clean.aiChanges;
            return clean;
          };

          const cleanOldData = stripUIProps(oldNode ? oldNode.data : null);
          const cleanNewData = stripUIProps(n.data);

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
              onExpandChange,
              onClearAIHighlight: (nodeId) => {
                setNodes(nds => nds.map(nd => String(nd.id) === String(nodeId) ? { ...nd, data: { ...nd.data, isAIModified: false } } : nd));
              }
            },
          };
        });
        let finalNodes = loadedNodes;
        let finalEdges = graph_data.edges || [];
        if (looksLikeUnlaidOutRow(loadedNodes)) {
          const layouted = getLayoutedElements(loadedNodes, graph_data.edges || [], 'LR');
          finalNodes = layouted.nodes;
          finalEdges = layouted.edges;
        }
        setNodes(finalNodes);
        setEdges(finalEdges);

        // 되돌리기/다시 실행 스택에 이번 턴을 쌓는다. 이미 되돌린 상태에서 챗봇이 새로 작업하면
        // 그 뒤에 남아있던 "다시 실행" 구간은 더 이상 의미가 없으므로 버리고 새 분기를 시작한다
        // (표준 undo/redo 스택 동작). 콜백 함수는 굳이 들고 있지 않고 복원 시 다시 꽂아준다.
        const stripUIPropsForHistory = (dataObj) => {
          const clean = { ...(dataObj || {}) };
          delete clean.onChange;
          delete clean.onDelete;
          delete clean.onExpandChange;
          delete clean.onClearAIHighlight;
          return clean;
        };
        setChatHistory(prevHistory => {
          const base = prevHistory.length === 0
            ? [{ nodes: preEditNodes.map(n => ({ ...n, data: stripUIPropsForHistory(n.data) })), edges: preEditEdges, label: null }]
            : prevHistory.slice(0, chatHistoryIndex + 1);
          const nextEntry = {
            nodes: finalNodes.map(n => ({ ...n, data: stripUIPropsForHistory(n.data) })),
            edges: finalEdges,
            label: userMessage,
          };
          const nextHistory = [...base, nextEntry];
          setChatHistoryIndex(nextHistory.length - 1);
          return nextHistory;
        });

        if (newLogs.length > 1) {
          setSystemLogs(prev => [...prev, ...newLogs]);
          setIsExecutionPanelOpen(true);
          setExecutionPanelTab('logs');
        }

        // 아직 한 번도 저장된 적 없는(currentId가 없는) 새 세션에서 AI가 처음으로 실제 노드를
        // 만들어낸 순간 자동으로 한 번 저장한다 — 저장 버튼을 누르기 전에 새로고침/이탈하면
        // 애써 생성한 워크플로우가 그냥 날아가는 문제를 막기 위함. handleSave 자체가 currentId
        // 유무로 생성/수정을 알아서 나누므로, 이후 저장은 여전히 사용자가 명시적으로 눌러야 한다
        // (이건 "처음 한 번"만을 위한 안전장치다).
        // setNodes/setEdges 직후라 React Flow 내부 상태가 아직 안 바뀌었을 수 있어서(실제로
        // getCurrentFlowData()가 방금 만든 노드를 못 읽어 빈 그래프가 저장되는 버그를 겪었다),
        // handleSave의 기본 경로 대신 방금 계산한 finalNodes/finalEdges를 직접 넘긴다.
        if (!currentId && !projectId && finalNodes.length > 0) {
          const stripUIPropsForSave = (dataObj) => {
            const clean = { ...(dataObj || {}) };
            delete clean.onChange;
            delete clean.onDelete;
            delete clean.onExpandChange;
            delete clean.onClearAIHighlight;
            delete clean.isAIModified;
            delete clean.aiChanges;
            return clean;
          };
          const overrideFlowData = {
            title: projectTitle !== 'Untitled Project' ? projectTitle : (graph_data.title || ''),
            description: projectDescription || graph_data.description || '',
            nodes: finalNodes.map(n => ({ id: n.id, type: n.type, position: n.position, data: stripUIPropsForSave(n.data) })),
            edges: finalEdges,
          };
          const savedId = await handleSave(
            null,
            overrideFlowData,
            generation_outcome === 'graph' ? trace_id : null,
          );
          if (savedId) {
            setSystemLogs(prev => [...prev, `> ✓ 워크플로우가 자동으로 저장되었습니다 (프로젝트 #${savedId})`]);
          }
        }
      }
    } catch (error) {
      if (axios.isCancel(error)) {
        setChatMessages(prev => [
          ...prev,
          { role: 'assistant', content: '사용자에 의해 생성이 취소되었습니다.' }
        ]);
        return;
      }
      console.error(error);
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', content: `에러가 발생했습니다: ${error.response?.data?.detail || error.message}` }
      ]);
    } finally {
      clearInterval(stageTimer);
      setChatStage('완료');
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
          executionStatus: log ? log.status : null,
          expandAllCommand
        }
      };
    });
  }, [nodes, isTokenTrackingMode, estimatedTokens, tokenUsage, tokenDisplayMode, costCurrency, isLoading, executionLogs, expandAllCommand]);

  return (
    <div className="app-container">
      <header className="header" style={{ position: 'relative', padding: '0.8rem 1.5rem', background: 'var(--card-bg)', borderBottom: '1px solid var(--border-color)', zIndex: 50 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button onClick={() => navigate(-1)} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', padding: 0 }}>
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

        <div className={`tools-container ${isMobileToolsDrawerOpen ? 'mobile-open' : ''}`} style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>

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
              <button className="btn-secondary desktop-only-tool" onClick={() => { handleSave().then(s => s && alert("저장되었습니다.")); }} title="저장">
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
            <button
              className="btn-secondary desktop-only-tool"
              onClick={handleUndoChat}
              disabled={chatHistoryIndex <= 0 || isChatLoading}
              title={chatHistoryIndex > 0 ? `되돌리기 ("${chatHistory[chatHistoryIndex]?.label || ''}" 이전으로)` : '되돌릴 챗봇 작업이 없습니다'}
            >
              <Undo2 size={16} />
            </button>
            <button
              className="btn-secondary desktop-only-tool"
              onClick={handleRedoChat}
              disabled={chatHistoryIndex < 0 || chatHistoryIndex >= chatHistory.length - 1 || isChatLoading}
              title={chatHistoryIndex >= 0 && chatHistoryIndex < chatHistory.length - 1 ? `다시 실행 ("${chatHistory[chatHistoryIndex + 1]?.label || ''}")` : '다시 실행할 작업이 없습니다'}
            >
              <Redo2 size={16} />
            </button>
            <button className="btn-secondary" onClick={() => {
              const layouted = getLayoutedElements(getNodes(), getEdges(), 'LR');
              setNodes([...layouted.nodes]);
              setEdges([...layouted.edges]);
            }} title="자동 정렬 (Beautify)" style={{ color: '#14b8a6', borderColor: '#14b8a6' }}>
              <Network size={16} /><span className="mobile-tool-label" style={{ color: '#14b8a6' }}>정렬</span>
            </button>
            <button className="btn-secondary" onClick={() => setExpandAllCommand({ action: 'expand', token: Date.now() })} title="모든 노드 펼치기">
              <ChevronsDown size={16} /><span className="mobile-tool-label">노드 펼치기</span>
            </button>
            <button className="btn-secondary" onClick={() => setExpandAllCommand({ action: 'collapse', token: Date.now() })} title="모든 노드 접기">
              <ChevronsUp size={16} /><span className="mobile-tool-label">노드 접기</span>
            </button>
            <button className="btn-secondary" onClick={() => setIsTemplateModalOpen(true)} title="템플릿 불러오기">
              <Folder size={16} /><span className="mobile-tool-label">템플릿</span>
            </button>
            {currentId && (
              <button className="btn-secondary" onClick={() => navigate(`/project/${currentId}/runs`, { state: { fromEditor: true } })} style={{ color: '#10b981', borderColor: '#10b981' }} title="실행 기록">
                <History size={16} /><span className="mobile-tool-label" style={{ color: '#10b981' }}>실행 기록</span>
              </button>
            )}
            {isOwner && currentId && (
              <button className="btn-secondary" onClick={handleOpenDeployModal} style={{ color: '#8b5cf6', borderColor: '#8b5cf6' }} title="배포">
                <Wand2 size={16} /><span className="mobile-tool-label" style={{ color: '#8b5cf6' }}>배포</span>
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
            <div style={{ position: 'relative' }}>
              <button
                className="btn-secondary"
                onClick={() => setIsTokenDrawerOpen(!isTokenDrawerOpen)}
                style={{
                  background: isTokenTrackingMode ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
                  borderColor: isTokenTrackingMode ? '#3b82f6' : 'var(--border-color)',
                  color: isTokenTrackingMode ? '#60a5fa' : 'var(--text-muted)',
                }}
                title="토큰 통계 보기"
              >
                <BrainCircuit size={16} /> 통계
              </button>

              {isTokenDrawerOpen && (
                <div style={{
                  position: 'absolute', top: '100%', left: '50%', transform: 'translateX(-50%)', marginTop: '0.5rem',
                  background: 'var(--card-bg)', border: '1px solid var(--border-color)',
                  borderRadius: '8px', padding: '1.5rem', width: '300px',
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
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: '0.5rem' }}>
            {/* Evaluation Action */}
            <div data-tutorial="quality-gate-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <button className="btn-secondary" onClick={evaluateFlow} disabled={isEvaluating || isLoading || isAutoImproving} style={{ color: '#10b981', borderColor: '#10b981' }}>
                <TestTube size={18} />
                {isEvaluating ? '평가 중...' : '평가'}
              </button>
              <button className="btn-secondary" onClick={autoImproveFlow} disabled={isEvaluating || isLoading || isAutoImproving} title="평가 점수가 기준 미달이면 개선 제안을 자동 반영합니다" style={{ color: '#8b5cf6', borderColor: '#8b5cf6' }}>
                <Sparkles size={18} />
                {isAutoImproving ? '자동 개선 중...' : '자동 개선'}
              </button>
            </div>
          </div>
        </div>

        {/* Primary Action and Mobile Toggle */}
        <div className="primary-action-container" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {isOwner && (
            <button className="btn-secondary mobile-only-tool" onClick={() => { handleSave().then(s => s && alert("저장되었습니다.")); }} title="저장">
              <Save size={18} />
            </button>
          )}
          <button className="btn-secondary mobile-only-tool" onClick={handleUndoChat} disabled={chatHistoryIndex <= 0 || isChatLoading} title="되돌리기">
            <Undo2 size={18} />
          </button>
          <button className="btn-secondary mobile-only-tool" onClick={handleRedoChat} disabled={chatHistoryIndex < 0 || chatHistoryIndex >= chatHistory.length - 1 || isChatLoading} title="다시 실행">
            <Redo2 size={18} />
          </button>
          <button className="btn-run" onClick={runFlow} disabled={isLoading || isEvaluating}>
            <Play size={18} />
            <span className="run-text">{isLoading ? '실행 중...' : '실행'}</span>
          </button>
          <button className="mobile-tools-toggle-btn" onClick={() => setIsMobileToolsDrawerOpen(true)}>
            <MoreVertical size={20} />
          </button>
        </div>
      </header>

      {isMobileToolsDrawerOpen && <div className="mobile-tools-overlay" onClick={() => setIsMobileToolsDrawerOpen(false)}></div>}

      <main className="main-content">
        <Sidebar isMobileOpen={isPaletteOpen} onClose={() => setIsPaletteOpen(false)} onNodeTap={handleNodeTap} />
        <div className="flow-wrapper" ref={reactFlowWrapper}>
          <button className="mobile-palette-toggle" onClick={() => setIsPaletteOpen(true)} title="노드 팔레트 열기">
            <Plus size={24} />
          </button>
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
            onEdgeContextMenu={(e, edge) => {
              e.preventDefault();
              customConfirm('이 연결선을 삭제하시겠습니까?', () => {
                setEdges((eds) => eds.filter((edg) => edg.id !== edge.id));
              });
            }}
            onConnect={onConnect}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeDragStop={onNodeDragStop}
            onPaneClick={handleClearAllHighlights}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={{
              style: { strokeWidth: 2, stroke: 'var(--text-muted)' },
              type: 'bezier'
            }}
            deleteKeyCode={['Backspace', 'Delete']}
            fitView
            colorMode={appTheme}
            panOnDrag={window.innerWidth <= 768 ? true : [1, 2]}
            selectionOnDrag={window.innerWidth > 768}
            selectionMode="partial"
            panOnScroll={window.innerWidth > 768}
            zoomOnScroll={true}
            onContextMenu={(e) => e.preventDefault()}
          >
            {window.innerWidth > 768 && <Controls />}
            {window.innerWidth > 768 && (
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
            )}
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
        className="chatbot-toggle-btn"
        data-tutorial="ai-assistant-btn"
        onClick={() => setIsAssistantOpen(!isAssistantOpen)}
        style={{
          transform: isAssistantOpen ? 'scale(0.9)' : 'scale(1)',
          opacity: isAssistantOpen ? 0 : 1,
          pointerEvents: isAssistantOpen ? 'none' : 'auto',
          transition: 'all 0.2s'
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
          <h3 style={{ margin: 0, fontSize: '1rem', color: 'var(--text-color)', fontWeight: 600, flex: 1 }}>AI 워크플로우 어시스턴트</h3>
          <button onClick={() => setIsAssistantOpen(false)} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '0.2rem', display: 'flex', alignItems: 'center' }}>
            <X size={18} />
          </button>
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
                borderBottomLeftRadius: msg.role === 'assistant' ? '4px' : '12px',
                wordBreak: 'break-word'
              }}>
                <ReactMarkdown components={{
                  p: ({node, ...props}) => <p style={{ margin: 0, paddingBottom: '0.5rem' }} {...props} />,
                  ul: ({node, ...props}) => <ul style={{ marginTop: '0.5rem', marginBottom: 0, paddingLeft: '1.5rem' }} {...props} />,
                  ol: ({node, ...props}) => <ol style={{ marginTop: '0.5rem', marginBottom: 0, paddingLeft: '1.5rem' }} {...props} />,
                  li: ({node, ...props}) => <li style={{ marginBottom: '0.25rem' }} {...props} />
                }}>
                  {msg.content}
                </ReactMarkdown>
              </div>
            </div>
          ))}
          {isChatLoading && (
            <div style={{
              width: '100%',
              maxWidth: '520px',
              padding: '1rem 1.05rem',
              borderRadius: '18px',
              background: 'linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.04))',
              border: '1px solid rgba(255,255,255,0.12)',
              boxShadow: '0 16px 40px rgba(0,0,0,0.18)',
              position: 'relative',
              overflow: 'hidden'
            }}>
              <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at top left, rgba(255,255,255,0.09), transparent 42%)', pointerEvents: 'none' }} />
              <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-start', gap: '0.85rem' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '999px', background: '#7dd3fc', boxShadow: '0 0 0 0 rgba(125,211,252,0.45)', animation: 'pulse 1.8s infinite', marginTop: '0.25rem' }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.78rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#cbd5e1' }}>Generating</span>
                    <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>Claude · Gemini style</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fff', fontSize: '0.95rem', fontWeight: 600, lineHeight: 1.35 }}>
                    <Sparkles size={14} />
                    <span>{chatStage}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
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
                {level === 'low' ? '빠름' : level === 'medium' ? '확장' : '정밀'}
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
            {isChatLoading ? (
              <button 
                onClick={handleCancelChat}
                style={{
                  background: '#ef4444',
                  border: 'none',
                  borderRadius: '8px',
                  width: '44px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                  cursor: 'pointer',
                  transition: 'background 0.2s'
                }}
                title="생성 취소"
              >
                <Square size={16} fill="currentColor" />
              </button>
            ) : (
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
            )}
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
          height: `${executionPanelHeight}px`,
          minHeight: '250px',
          maxHeight: '90vh',
          background: 'var(--card-bg)',
          borderTop: '1px solid var(--border-color)',
          zIndex: 900,
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 -10px 30px rgba(0,0,0,0.5)',
          transform: 'translateY(0)'
        }}>
          {/* Resize Handle */}
          <div 
            style={{
              height: '8px',
              width: '100%',
              background: 'transparent',
              cursor: 'ns-resize',
              position: 'absolute',
              top: '-4px',
              zIndex: 901,
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center'
            }}
            onMouseDown={(e) => {
              e.preventDefault();
              const startY = e.clientY;
              const startHeight = executionPanelHeight;
              
              const onMouseMove = (moveEvent) => {
                const delta = startY - moveEvent.clientY;
                setExecutionPanelHeight(Math.max(250, Math.min(window.innerHeight * 0.9, startHeight + delta)));
              };
              
              const onMouseUp = () => {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
              };
              
              document.addEventListener('mousemove', onMouseMove);
              document.addEventListener('mouseup', onMouseUp);
            }}
          >
            <div style={{ width: '40px', height: '4px', background: 'var(--border-color)', borderRadius: '2px', opacity: 0.5 }}></div>
          </div>

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
                  transition: 'all 0.2s'
                }}
              >
                <TerminalSquare size={16} /> 실행 로그 (Logs)
              </button>
              <button
                onClick={() => setExecutionPanelTab('evaluation')}
                style={{
                  padding: '1rem 1.5rem',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: executionPanelTab === 'evaluation' ? '2px solid #10b981' : '2px solid transparent',
                  color: executionPanelTab === 'evaluation' ? '#10b981' : 'var(--text-muted)',
                  fontWeight: executionPanelTab === 'evaluation' ? 600 : 400,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  transition: 'all 0.2s'
                }}
              >
                <TestTube size={16} /> 평가 결과 (Eval)
              </button>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <button
                onClick={() => setIsExecutionPanelOpen(false)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  padding: '0.5rem',
                  borderRadius: '4px',
                }}
              >
                <X size={18} />
              </button>
            </div>
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
                          href={`/${response.replace(/\\/g, '/')}`}
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
            
            {executionPanelTab === 'evaluation' && (
                <div style={{ padding: '1.5rem', flex: 1, display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto' }}>
                  {isAutoImproving ? (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', flexDirection: 'column', gap: '1.5rem' }}>
                      <div className="spinner" style={{ width: '50px', height: '50px', border: '4px solid rgba(139, 92, 246, 0.2)', borderTopColor: '#8b5cf6', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
                      <span style={{ color: 'var(--text-color)', fontSize: '0.95rem' }}>평가와 자동 수정을 반복하고 있습니다...</span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>기준 점수를 넘기거나 최대 시도 횟수에 도달하면 종료됩니다</span>
                    </div>
                  ) : isEvaluating ? (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', flexDirection: 'column', gap: '2rem' }}>
                      <div className="spinner" style={{ width: '50px', height: '50px', border: '4px solid rgba(16, 185, 129, 0.2)', borderTopColor: '#10b981', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
                      
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '300px' }}>
                        {[
                          "워크플로우 분석 및 Dataset 생성",
                          "테스트 케이스 시뮬레이션 실행",
                          "AI 심사위원의 결과 상세 채점",
                          "최종 리포트 종합 및 제안 도출"
                        ].map((stepText, idx) => {
                          const isActive = evalStep === idx;
                          const isDone = evalStep > idx;
                          return (
                            <div key={idx} style={{ 
                              display: 'flex', 
                              alignItems: 'center', 
                              gap: '1rem',
                              opacity: isDone ? 0.6 : isActive ? 1 : 0.3,
                              transition: 'opacity 0.3s'
                            }}>
                              <div style={{ 
                                width: '24px', height: '24px', 
                                borderRadius: '50%', 
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                background: isDone ? '#10b981' : isActive ? 'transparent' : 'rgba(255,255,255,0.1)',
                                border: isActive ? '2px solid #10b981' : 'none',
                                color: isDone ? '#fff' : isActive ? '#10b981' : '#888',
                                fontSize: '0.8rem',
                                fontWeight: 'bold'
                              }}>
                                {isDone ? '✓' : (idx + 1)}
                              </div>
                              <span style={{ 
                                color: isActive ? '#10b981' : 'var(--text-color)', 
                                fontWeight: isActive ? 600 : 400 
                              }}>
                                {stepText}
                                {isActive && <span style={{ animation: 'blink 1.5s infinite' }}>...</span>}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : evaluationReport ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                      {evaluationReport.attempts?.length > 1 && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid #8b5cf6', borderRadius: '8px', padding: '0.8rem 1rem' }}>
                          <Sparkles size={16} color="#8b5cf6" />
                          <span style={{ color: 'var(--text-color)', fontSize: '0.85rem' }}>자동 개선 시도:</span>
                          {evaluationReport.attempts.map((a, idx) => (
                            <span key={idx} style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                              {idx > 0 && ' → '}
                              <span style={{ fontWeight: 600, color: a.score >= 70 ? '#10b981' : '#f59e0b' }}>{a.score}점</span>
                            </span>
                          ))}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: '2rem', alignItems: 'center', background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', width: '100px', height: '100px', borderRadius: '50%', border: `8px solid ${evaluationReport.score >= 80 ? '#10b981' : evaluationReport.score >= 50 ? '#f59e0b' : '#ef4444'}` }}>
                          <span style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-color)' }}>{evaluationReport.score}</span>
                        </div>
                        <div style={{ flex: 1 }}>
                          <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--text-color)' }}>종합 평가 리포트</h3>
                          <p style={{ margin: 0, color: 'var(--text-muted)', lineHeight: 1.5 }}>{evaluationReport.summary}</p>
                        </div>
                      </div>
                      
                      <div>
                        <h4 style={{ margin: '0 0 1rem 0', color: 'var(--text-color)' }}>테스트 케이스 상세</h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                          {evaluationReport.test_results?.map((tc, idx) => (
                            <div key={idx} style={{ background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1.2rem' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                                <span style={{ fontWeight: 600, color: 'var(--text-color)' }}>Test Case {idx + 1}</span>
                                <span style={{ fontWeight: 600, color: tc.score >= 40 ? '#10b981' : tc.score >= 25 ? '#f59e0b' : '#ef4444' }}>Score: {tc.score}/50</span>
                              </div>
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                <div>
                                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>입력 (Input)</div>
                                  <div style={{ background: 'var(--card-bg)', padding: '0.8rem', borderRadius: '6px', fontSize: '0.9rem', whiteSpace: 'pre-wrap' }}>{tc.input}</div>
                                </div>
                                <div>
                                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>예상 동작 (Expected)</div>
                                  <div style={{ background: 'var(--card-bg)', padding: '0.8rem', borderRadius: '6px', fontSize: '0.9rem', whiteSpace: 'pre-wrap' }}>{tc.expected}</div>
                                </div>
                              </div>
                              <div>
                                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>실제 결과 (Actual)</div>
                                <div style={{ background: tc.error ? 'rgba(239, 68, 68, 0.1)' : 'var(--card-bg)', border: tc.error ? '1px solid rgba(239, 68, 68, 0.3)' : 'none', padding: '0.8rem', borderRadius: '6px', fontSize: '0.9rem', whiteSpace: 'pre-wrap' }}>
                                  {tc.error ? tc.error : tc.actual}
                                </div>
                              </div>
                              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-color)' }}>
                                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>AI 심사위원 피드백</div>
                                <div style={{ color: 'var(--text-color)', fontSize: '0.9rem', lineHeight: 1.5 }}>{tc.feedback}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                      
                      {evaluationReport.suggestions?.length > 0 && (
                        <div>
                          <h4 style={{ margin: '0 0 1rem 0', color: '#f59e0b' }}>💡 개선 제안</h4>
                          <ul style={{ margin: 0, paddingLeft: '1.5rem', color: 'var(--text-color)', lineHeight: 1.6 }}>
                            {evaluationReport.suggestions.map((sug, idx) => (
                              <li key={idx} style={{ marginBottom: '0.5rem' }}>{sug}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                      <span style={{ color: 'var(--text-muted)' }}>상단의 '평가' 버튼을 눌러 워크플로우를 채점해보세요.</span>
                    </div>
                  )}
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

      <TutorialOverlay steps={EDITOR_TUTORIAL_STEPS} storageKey="tutorial_editor_seen_v1" />
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
