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
  applyNodeChanges,
  applyEdgeChanges,
  useReactFlow,
  useViewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './EditorPage.css';
import axios from 'axios';
import { Play, Code, Folder, Save, Share2, ArrowLeft, Wand2, Settings, Sparkles, BrainCircuit, History, TerminalSquare, X, Square, Network, TestTube, FlaskConical, ChevronsDown, ChevronsUp, Undo2, Redo2, Plus, MoreVertical, Keyboard, Copy, Scissors, Trash2, AlignHorizontalDistributeCenter, AlignVerticalDistributeCenter, AlignStartVertical, AlignStartHorizontal, Maximize2, Command, Search, ClipboardPaste, Check, Star, Replace, CornerDownRight , Lock, Unlock , AlertTriangle, LayoutTemplate, Zap} from 'lucide-react';
import Sidebar from '../Sidebar';
import TemplateModal from '../TemplateModal';
import DeployModal from '../DeployModal';
import TutorialOverlay from '../TutorialOverlay';
import FormatStudio from '../components/FormatStudio';
import OnboardingChecklist from '../OnboardingChecklist';
import { completeOnboardingStep } from '../onboardingProgress';
import { celebrateMilestone } from '../milestoneCelebrations';
import AIAssistantDrawer from '../components/AIAssistantDrawer';
import MockPanel from '../components/MockPanel';
import NodeErrorCard from '../components/NodeErrorCard';
import NodeInspector from '../components/NodeInspector';
import DataLayerOverlay from '../components/DataLayerOverlay';
import {
  clearPinnedOutput,
  collectPinnedOutputs,
  downstreamExternalNodes,
  isPinnedOutputStale,
  nodeWritesExternally,
  readPinnedOutput,
  readSampleInput as readStoredSampleInput,
  writePinnedOutput,
  writeSampleInput as writeStoredSampleInput,
} from '../nodeTestFixtures';
import { getNodeDefinition } from '../nodeDefinitions';
import { useAuth } from '../AuthContext';
import { customConfirm } from '../CustomConfirm';
import { describeSaveConflict } from '../saveConflict';
import {
  createClipboardFragment,
  createEditorSnapshot,
  createEditorCommandRegistry,
  arrangeSelectedNodes,
  findCommandForKeyboardEvent,
  formatEditorShortcut,
  isEditableShortcutTarget,
  makeEntityId,
  materializeClipboardFragment,
  absorbDetachedText,
  normalizeGraphIds,
  parseClipboardFragment,
  serializeClipboardFragment,
} from '../editorCommands';
import { useEditorHistory } from '../useEditorHistory';
import { EDITOR_NODE_CATALOG, getEditorNodeMeta, getReplacementCandidates } from '../editorNodeCatalog';
import { StartNode, PromptNode, LLMNode, OutputNode, ConditionNode, ValueNode, LoopNode, BreakNode, PythonNode, TokenizerNode, DistributorNode, FileModifierNode, TemplateAnalyzerNode, DynamicInputNode, WebCrawlerNode, EmailNode, KakaoNode, DelayNode, JsonParserNode, MergeNode, HttpRequestNode, DatabaseNode, HumanApprovalNode, MultiAgentNode, DynamicNode, ScheduleNode, DiscordNode, DiscordTriggerNode, TelegramNode, TelegramTriggerNode, NotionNode, WebhookNode, YoutubeNode, YoutubeTriggerNode , MemoNode , RssTriggerNode , GmailTriggerNode , GmailNode , GoogleDriveNode , NaverSearchNode , JusoNode , DataGoKrNode , NaverSearchTriggerNode , NaverCafeNode , HwpxDocumentNode, FormatNode, invalidateUserFormatsCache, formatFieldsSchema,
} from '../customNodes';
import { NodeRegistry } from '../nodeRegistry';
import { MEMO_MIN_NODE_HEIGHT } from '../memoSizing';
import {
  MEMO_DEFAULT_WIDTH,
  ensureMemoNodeDefaults,
  ensureMemoNodeDefaultsForList,
} from '../memoNodeDefaults';
import dagre from 'dagre';

// 실행 패널 탭. 탭 색은 정체가 아니라 상태다 — 활성은 모두 Blue, 상태는 배지로만
// (WORKFLOW_EDITOR_DESIGN_IMPROVEMENT_PLAN §5.6).
const EXECUTION_TABS = [
  { id: 'result', label: '결과', icon: Play },
  { id: 'logs', label: '로그', icon: TerminalSquare },
  { id: 'evaluation', label: '평가', icon: TestTube },
  { id: 'mock', label: '목업', icon: FlaskConical },
  { id: 'inspect', label: '검사', icon: Search },
  { id: 'problems', label: '문제', icon: AlertTriangle },
];
const EVALUATION_STEPS = [
  '워크플로우 분석 및 Dataset 생성',
  '테스트 케이스 시뮬레이션 실행',
  'AI 심사위원의 결과 상세 채점',
  '최종 리포트 종합 및 제안 도출',
];
const scoreTone = (score, good, ok) => (score >= good ? 'success' : score >= ok ? 'warning' : 'danger');

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
    target: '[data-tutorial="editor-more-btn"]',
    title: '에디터 도구',
    description: '정렬, 템플릿, 실행 기록, 비용 분석과 자동 개선 기능은 이 메뉴에서 찾을 수 있어요.',
    placement: 'bottom',
  },
  {
    target: '.btn-run',
    title: '실행',
    description: '워크플로우가 준비되면 이 버튼으로 직접 실행해서 결과를 확인해보세요.',
    placement: 'bottom',
  },
];

const ARRANGEMENT_OPTIONS = [
  { id: 'align-left', label: '왼쪽 정렬' },
  { id: 'align-center-horizontal', label: '가로 가운데 정렬' },
  { id: 'align-right', label: '오른쪽 정렬' },
  { id: 'align-top', label: '위쪽 정렬' },
  { id: 'align-center-vertical', label: '세로 가운데 정렬' },
  { id: 'align-bottom', label: '아래쪽 정렬' },
  { id: 'distribute-horizontal', label: '가로 간격 동일', minimum: 3 },
  { id: 'distribute-vertical', label: '세로 간격 동일', minimum: 3 },
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

// 수정 전 이미 설치한 템플릿도 열 수 있다. 서버 마이그레이션을 기다리지 않고, 같은 좌표에
// 포개진 노드가 있으면 에디터에서 한 번 더 복구해 저장 가능한 변경으로 표시한다.
const hasStackedNodePositions = (nodes) => {
  if (!nodes || nodes.length < 2) return false;
  return nodes.some((node, index) => nodes.slice(index + 1).some(other => {
    const first = node.position;
    const second = other.position;
    if (!Number.isFinite(first?.x) || !Number.isFinite(first?.y)
      || !Number.isFinite(second?.x) || !Number.isFinite(second?.y)) return true;
    return Math.abs(first.x - second.x) < 16 && Math.abs(first.y - second.y) < 16;
  }));
};

const nodeTypes = {
  webhookNode: WebhookNode,
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
  youtubeNode: YoutubeNode,
  youtubeTriggerNode: YoutubeTriggerNode,
  databaseNode: DatabaseNode,
  humanApprovalNode: HumanApprovalNode,
  multiAgentNode: MultiAgentNode,
  discordNode: DiscordNode,
  discordTriggerNode: DiscordTriggerNode,
  telegramNode: TelegramNode,
  telegramTriggerNode: TelegramTriggerNode,
  notionNode: NotionNode,
  memoNode: MemoNode,
  rssTriggerNode: RssTriggerNode,
  gmailTriggerNode: GmailTriggerNode,
  gmailNode: GmailNode,
  googleDriveNode: GoogleDriveNode,
  naverSearchNode: NaverSearchNode,
  jusoNode: JusoNode,
  dataGoKrNode: DataGoKrNode,
  naverSearchTriggerNode: NaverSearchTriggerNode,
  naverCafeNode: NaverCafeNode,
  hwpxDocumentNode: HwpxDocumentNode,
  formatNode: FormatNode,
};

// Auto-register dynamic nodes
Object.keys(NodeRegistry).forEach(key => {
  nodeTypes[key] = DynamicNode;
});

// id 는 서버 생성 코드의 식별자에 쓰이므로 하이픈이 없어야 한다(editorCommands.makeEntityId 참고).
const getEntityId = (prefix = 'node') => makeEntityId(prefix);
const getId = () => getEntityId('node');
const waitForExecutionFrame = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

const getExecutionEntryNodeIds = (nodes, edges) => {
  const incomingNodeIds = new Set((edges || []).map((edge) => String(edge.target)));
  const entryNodes = (nodes || []).filter((node) => !incomingNodeIds.has(String(node.id)));
  return (entryNodes.length > 0 ? entryNodes : (nodes || []).slice(0, 1)).map((node) => String(node.id));
};

const readStoredNodeTypes = (key) => {
  try {
    if (typeof localStorage === 'undefined') return [];
    const parsed = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(parsed) ? parsed.filter((type) => typeof type === 'string') : [];
  } catch {
    return [];
  }
};

const storeNodeTypes = (key, types) => {
  try {
    localStorage.setItem(key, JSON.stringify(types));
  } catch {
    // Private browsing or a full storage quota should not block editor actions.
  }
};

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

  const [nodes, setNodesState] = useNodesState([]);
  const [edges, setEdgesState] = useEdgesState([]);
  const { screenToFlowPosition, getNodes, getEdges, fitView } = useReactFlow();
  const { x: viewportX, y: viewportY, zoom: viewportZoom } = useViewport();
  const {
    reset: resetEditorHistory,
    commit: commitEditorHistory,
    undo: undoEditorHistory,
    redo: redoEditorHistory,
    markSaved: markEditorHistorySaved,
    isDirty: getEditorIsDirty,
    canUndo,
    canRedo,
    undoLabel,
    redoLabel,
  } = useEditorHistory();
  const nodesRef = useRef([]);
  const edgesRef = useRef([]);
  const historyTimerRef = useRef(null);
  const nextHistoryMetaRef = useRef({ label: '워크플로우 편집', delay: 0 });
  const pendingHistoryLabelRef = useRef(null);
  const nodeInputCompositionRef = useRef({
    isComposing: false,
    pending: new Map(),
    flushTimer: null,
  });

  const scheduleHistoryCommit = useCallback((labelOverride = null, delayOverride = null) => {
    const meta = nextHistoryMetaRef.current;
    const label = (meta.label !== '워크플로우 편집' ? meta.label : null)
      || pendingHistoryLabelRef.current
      || labelOverride
      || '워크플로우 편집';
    const delay = delayOverride ?? meta.delay ?? 0;
    nextHistoryMetaRef.current = { label: '워크플로우 편집', delay: 0 };
    pendingHistoryLabelRef.current = label;
    window.clearTimeout(historyTimerRef.current);
    historyTimerRef.current = window.setTimeout(() => {
      commitEditorHistory(nodesRef.current, edgesRef.current, label);
      pendingHistoryLabelRef.current = null;
    }, delay);
  }, [commitEditorHistory]);

  const flushHistoryCommit = useCallback(() => {
    if (!pendingHistoryLabelRef.current) return;
    window.clearTimeout(historyTimerRef.current);
    commitEditorHistory(nodesRef.current, edgesRef.current, pendingHistoryLabelRef.current);
    pendingHistoryLabelRef.current = null;
  }, [commitEditorHistory]);

  const markNextHistory = useCallback((label, delay = 0) => {
    nextHistoryMetaRef.current = { label, delay };
  }, []);

  const setNodes = useCallback((updater) => {
    setNodesState((currentNodes) => {
      const candidateNodes = typeof updater === 'function' ? updater(currentNodes) : updater;
      const nextNodes = ensureMemoNodeDefaultsForList(candidateNodes);
      nodesRef.current = nextNodes;
      scheduleHistoryCommit();
      return nextNodes;
    });
  }, [scheduleHistoryCommit, setNodesState]);

  const setEdges = useCallback((updater) => {
    setEdgesState((currentEdges) => {
      const nextEdges = typeof updater === 'function' ? updater(currentEdges) : updater;
      edgesRef.current = nextEdges;
      scheduleHistoryCommit();
      return nextEdges;
    });
  }, [scheduleHistoryCommit, setEdgesState]);

  const replaceGraph = useCallback((nextNodes, nextEdges, { saved = true } = {}) => {
    window.clearTimeout(historyTimerRef.current);
    pendingHistoryLabelRef.current = null;
    const normalizedNodes = ensureMemoNodeDefaultsForList(nextNodes);
    nodesRef.current = normalizedNodes;
    edgesRef.current = nextEdges;
    setNodesState(normalizedNodes);
    setEdgesState(nextEdges);
    resetEditorHistory(normalizedNodes, nextEdges, { saved });
  }, [resetEditorHistory, setEdgesState, setNodesState]);

  const onNodesChange = useCallback((changes) => {
    setNodesState((currentNodes) => {
      const nextNodes = applyNodeChanges(changes, currentNodes);
      nodesRef.current = nextNodes;
      if (changes.some((change) => change.type === 'remove' || change.type === 'add' || change.type === 'replace')) {
        scheduleHistoryCommit('노드 삭제');
      }
      return nextNodes;
    });
  }, [scheduleHistoryCommit, setNodesState]);

  // 메모 본문은 스크롤을 만들지 않고 노드 자체를 늘린다. 이 내부 레이아웃 보정은 메모 텍스트
  // 변경의 같은 history commit에 포함되며, 측정만으로 별도의 Undo 단계는 만들지 않는다.
  const resizeMemoNodeToContent = useCallback((nodeId, requiredHeight) => {
    const nextHeight = Math.max(MEMO_MIN_NODE_HEIGHT, Math.ceil(Number(requiredHeight) || 0));
    setNodesState((currentNodes) => {
      let changed = false;
      const nextNodes = currentNodes.map((node) => {
        if (String(node.id) !== String(nodeId) || node.type !== 'memoNode') return node;
        if (Math.abs((Number(node.height) || 0) - nextHeight) < 1) return node;
        changed = true;
        return { ...node, height: nextHeight };
      });
      if (!changed) return currentNodes;
      nodesRef.current = nextNodes;
      return nextNodes;
    });
  }, [setNodesState]);

  const onEdgesChange = useCallback((changes) => {
    setEdgesState((currentEdges) => {
      const nextEdges = applyEdgeChanges(changes, currentEdges);
      edgesRef.current = nextEdges;
      if (changes.some((change) => change.type === 'remove' || change.type === 'add' || change.type === 'replace')) {
        scheduleHistoryCommit('연결 변경');
      }
      return nextEdges;
    });
  }, [scheduleHistoryCommit, setEdgesState]);

  useEffect(() => () => {
    window.clearTimeout(historyTimerRef.current);
    window.clearTimeout(nodeInputCompositionRef.current.flushTimer);
  }, []);

  useEffect(() => {
    if (nodes.length > 0) completeOnboardingStep('workflow_created');
  }, [nodes.length]);
  const [response, setResponse] = useState('');
  const [isCompiled, setIsCompiled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
  const [tokenUsage, setTokenUsage] = useState(null);
  const [executionLogs, setExecutionLogs] = useState([]);
  const [executionNodeStates, setExecutionNodeStates] = useState({});
  // 포맷 스튜디오(문서 포맷 계획 Phase 2) — nodeId 가 있으면 "이 노드에 적용" 이 활성화된다.
  const [formatStudio, setFormatStudio] = useState({ isOpen: false, formatId: '', nodeId: null });
  // 실행 후 노드에 남는 성공/실패 하이라이트의 해제 여부 — 캔버스 빈 곳을 클릭하면 걷힌다.
  // 진행 중(running) 표시는 이 플래그와 무관하게 항상 보인다. 결과 배지(§7.2)도 유지된다.
  const [isExecHighlightDismissed, setIsExecHighlightDismissed] = useState(false);
  // NodeError v1(ADR-0016): 서버가 구조화한 실행 오류 목록과, 그것을 카드로 그릴지 여부(서버 플래그).
  const [executionErrors, setExecutionErrors] = useState([]);
  // 직전 목업 실행이 무엇이었는지 — 결과 탭이 "실제 실행이 아니다" 를 분명히 알린다(§7.1).
  const [mockRunSummary, setMockRunSummary] = useState(null);
  const [nodeErrorV1, setNodeErrorV1] = useState(true);
  const executionAnimationTokenRef = useRef(0);
  const [isLive, setIsLive] = useState(false);

  useEffect(() => () => {
    executionAnimationTokenRef.current += 1;
  }, []);

  const [isTokenTrackingMode, setIsTokenTrackingMode] = useState(false);
  const [estimatedTokens, setEstimatedTokens] = useState(null);
  const [isTokenDrawerOpen, setIsTokenDrawerOpen] = useState(false);
  const [systemLogs, setSystemLogs] = useState([]);
  const [isPaletteOpen, setIsPaletteOpen] = useState(false);
  const [isMobileToolsDrawerOpen, setIsMobileToolsDrawerOpen] = useState(false);
  const [isShortcutHelpOpen, setIsShortcutHelpOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState('');
  const [activeCommandIndex, setActiveCommandIndex] = useState(0);
  const [editorContextMenu, setEditorContextMenu] = useState(null);
  const [isArrangeMenuOpen, setIsArrangeMenuOpen] = useState(false);
  const [nodePicker, setNodePicker] = useState(null);
  const [nodePickerQuery, setNodePickerQuery] = useState('');
  const [activeNodePickerIndex, setActiveNodePickerIndex] = useState(0);
  const [favoriteNodeTypes, setFavoriteNodeTypes] = useState(() => readStoredNodeTypes('editorFavoriteNodeTypes'));
  const [recentNodeTypes, setRecentNodeTypes] = useState(() => readStoredNodeTypes('editorRecentNodeTypes'));
  const editorToolsMenuRef = useRef(null);
  const commandPaletteInputRef = useRef(null);
  const nodePickerInputRef = useRef(null);
  const sessionClipboardRef = useRef(null);
  const pasteSequenceRef = useRef(0);
  const altDragDuplicateRef = useRef(false);
  const connectionStartRef = useRef(null);
  const [isExecutionPanelOpen, setIsExecutionPanelOpen] = useState(false);
  const [executionPanelTab, setExecutionPanelTab] = useState('result'); // result | logs | evaluation | mock | inspect | problems
  const [inspectorNodeId, setInspectorNodeId] = useState(null);
  const [problemsReport, setProblemsReport] = useState(null);
  const [problemsLoading, setProblemsLoading] = useState(false);
  const [executionPanelHeight, setExecutionPanelHeight] = useState(300); // initial height in px

  // Evaluation States
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evalStep, setEvalStep] = useState(0);
  const [evaluationReport, setEvaluationReport] = useState(null);
  const [isAutoImproving, setIsAutoImproving] = useState(false);

  // AI에 첨부한 대상(백로그 28 POINT-1).
  //
  // ⚠️ 2026-08-30 **꺼 둠.** 범위 검증은 동작하는데 그 안에서 모델이 하는 일을 통제할 수 없었다 —
  // 노드 종류를 바꿔 달라고 하면 `update_node(node_type=...)` 를 쓰라고 지시문에 적어도
  // `delete_node` + `add_node` 를 써서 **연결선을 전부 날렸다.** 지시는 강제가 아니다.
  // 계약·resolver·검증기(`backend/pointing.py`)는 그대로 두고 UI 진입점만 막는다 —
  // 다시 열 때 이 상수만 true 로 바꾸면 된다.
  const POINTING_ENABLED = false;

  //
  // **선택만으로 자동 첨부하지 않는다.** 속성을 보려고 클릭한 것이 AI 편집 권한으로 이어지면
  // 안 되므로, 사용자가 "AI에 첨부"를 눌러야 여기 들어온다.
  const [pointedTargets, setPointedTargets] = useState([]);
  const [pointingScope, setPointingScope] = useState('target_only');

  const editorSelection = useMemo(() => {
    const selectedNodes = nodes.filter((node) => node.selected);
    const selectedEdges = edges.filter((edge) => edge.selected);
    return {
      nodes: selectedNodes,
      edges: selectedEdges,
      nodeIds: new Set(selectedNodes.map((node) => String(node.id))),
      edgeIds: new Set(selectedEdges.map((edge) => String(edge.id))),
      count: selectedNodes.length + selectedEdges.length,
    };
  }, [edges, nodes]);

  // 대상 하나의 내용 해시. **서버(`pointing.snapshot_hash`)와 같은 결과여야** 한다 —
  // 다르면 멀쩡한 대상이 전부 stale 로 튕겨 기능이 통째로 죽는다.
  //
  // ⚠️ 반드시 `JSON.parse(JSON.stringify(...))` 를 먼저 거친다. 그러지 않으면 `undefined`
  // 값이나 함수가 남은 채로 해싱되는데, **전송되는 JSON 에는 그 키가 아예 없다**
  // (`sourceHandle: undefined` 가 대표적이다). 서버는 없는 키를 보고, 우리는 있는 키로
  // 해시를 내서 항상 어긋난다 — 2026-08-30 에 실제로 이것 때문에 전부 stale 이었다.
  const stableStringify = useCallback((value) => {
    const wire = JSON.parse(JSON.stringify(value ?? null));   // 전송될 모양으로 맞춘다
    const walk = (v) => {
      if (v === null || typeof v !== 'object') return JSON.stringify(v);
      if (Array.isArray(v)) return `[${v.map(walk).join(',')}]`;
      return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${walk(v[k])}`).join(',')}}`;
    };
    return walk(wire);
  }, []);

  // 서버 `pointing.snapshot_hash` 와 같은 결과를 내야 한다 — sha256 hex 앞 32자.
  // `crypto.subtle` 은 보안 컨텍스트에서만 동작하므로, 없으면 해시를 빼고 보낸다
  // (서버는 해시가 없으면 stale 검사를 건너뛰고 revision 으로만 판정한다).
  const sha256Short = useCallback(async (text) => {
    if (!window.crypto?.subtle) return undefined;
    try {
      const bytes = new TextEncoder().encode(text);
      const digest = await window.crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(digest))
        .map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 32);
    } catch {
      return undefined;
    }
  }, []);

  // **서버가 해싱하는 것과 똑같은 것을 해싱해야 한다.**
  //
  // 서버는 `payload.graph_data`(= `getCurrentFlowData()`) 안의 항목을 해싱한다. 그 값은
  // `createEditorSnapshot` → `sanitizeNodeForSnapshot` 을 거쳐 함수·캔버스 전용 필드가
  // 걸러진 것이라, React Flow 의 `nodes` 원본과 **모양이 다르다.** 원본을 해싱했더니
  // 모든 대상이 "지목한 뒤 바뀌었습니다" 로 튕겼다(2026-08-30). 그래서 같은 출처에서 꺼낸다.
  //
  // `useCallback` 을 쓰지 않는다 — 의존성 배열에 `getCurrentFlowData` 를 넣으면 그 함수가
  // 아래에서 선언되므로 TDZ 오류가 난다. 평범한 함수의 **본문**은 호출 시점에 평가되므로 안전하다.
  const targetSnapshot = (kind, id) => {
    const flow = getCurrentFlowData();
    const source = kind === 'workflow_edge' ? (flow.edges || []) : (flow.nodes || []);
    return source.find((item) => String(item.id) === String(id)) || null;
  };

  const attachSelectionToAI = useCallback(() => {
    const picked = [
      ...editorSelection.nodes.map((n) => ({
        kind: 'workflow_node', id: String(n.id),
        label: n.data?.label || getEditorNodeMeta(n.type)?.label || n.type,
      })),
      ...editorSelection.edges.map((e) => ({
        kind: 'workflow_edge', id: String(e.id), label: '연결',
      })),
    ];
    if (!picked.length) return;
    setPointedTargets((prev) => {
      const seen = new Set(prev.map((t) => `${t.kind}:${t.id}`));
      return [...prev, ...picked.filter((t) => !seen.has(`${t.kind}:${t.id}`))].slice(0, 20);
    });
    setIsAssistantOpen(true);
  }, [editorSelection]);

  const detachTarget = useCallback((kind, id) => {
    setPointedTargets((prev) => prev.filter((t) => !(t.kind === kind && t.id === id)));
  }, []);

  // 첨부한 대상이 아직 캔버스에 있는지. **없어진 것을 다른 id 에 조용히 재연결하지 않는다.**
  const pointedStatus = useMemo(() => {
    const nodeIds = new Set(nodes.map((n) => String(n.id)));
    const edgeIds = new Set(edges.map((e) => String(e.id)));
    return pointedTargets.map((t) => ({
      ...t,
      missing: t.kind === 'workflow_edge' ? !edgeIds.has(t.id) : !nodeIds.has(t.id),
    }));
  }, [pointedTargets, nodes, edges]);

  const selectionToolbarStyle = useMemo(() => {
    if (typeof window === 'undefined' || window.innerWidth <= 720 || !editorSelection.nodes.length) {
      return { bottom: isExecutionPanelOpen ? executionPanelHeight + 18 : 22 };
    }
    const wrapperRect = reactFlowWrapper.current?.getBoundingClientRect();
    if (!wrapperRect) return { bottom: 22 };
    const nodeById = new Map(nodes.map((node) => [String(node.id), node]));
    const absolutePosition = (node) => {
      let x = Number(node.position?.x || 0);
      let y = Number(node.position?.y || 0);
      let parentId = node.parentNode;
      const visited = new Set();
      while (parentId && !visited.has(String(parentId))) {
        visited.add(String(parentId));
        const parent = nodeById.get(String(parentId));
        if (!parent) break;
        x += Number(parent.position?.x || 0);
        y += Number(parent.position?.y || 0);
        parentId = parent.parentNode;
      }
      return { x, y };
    };
    const bounds = editorSelection.nodes.map((node) => {
      const position = absolutePosition(node);
      return {
        left: position.x,
        top: position.y,
        right: position.x + Number(node.measured?.width || node.width || 240),
        bottom: position.y + Number(node.measured?.height || node.height || 160),
      };
    });
    const left = Math.min(...bounds.map((bound) => bound.left));
    const right = Math.max(...bounds.map((bound) => bound.right));
    const top = Math.min(...bounds.map((bound) => bound.top));
    const bottom = Math.max(...bounds.map((bound) => bound.bottom));
    const screenCenterX = wrapperRect.left + viewportX + ((left + right) / 2) * viewportZoom;
    const screenTop = wrapperRect.top + viewportY + top * viewportZoom;
    const screenBottom = wrapperRect.top + viewportY + bottom * viewportZoom;
    const toolbarTop = screenTop > 118 ? screenTop - 56 : screenBottom + 12;
    return {
      top: Math.max(64, Math.min(toolbarTop, window.innerHeight - 64)),
      bottom: 'auto',
      left: Math.max(180, Math.min(screenCenterX, window.innerWidth - 180)),
    };
  }, [editorSelection.nodes, executionPanelHeight, isExecutionPanelOpen, nodes, viewportX, viewportY, viewportZoom]);

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
  const [complexityLevel, setComplexityLevel] = useState('low');
  const abortControllerRef = useRef(null);

  const [expandAllCommand, setExpandAllCommand] = useState(null);
  // 데이터 레이어(계획 §5-2) — 꺼짐이 기본. 켜면 모든 바인딩을 점선으로 보여주고 필드 입력 포트가 열린다.
  const [isDataLayerOn, setIsDataLayerOn] = useState(false);
  const [projectTitle, setProjectTitle] = useState('Untitled Project');
  const [projectDescription, setProjectDescription] = useState('');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const projectControlRef = useRef(null);
  const [visibility, setVisibility] = useState('private');
  const [isOwner, setIsOwner] = useState(true); // Default true for new projects
  const [currentId, setCurrentId] = useState(projectId);
  const savedProjectMetadataRef = useRef(projectId ? null : {
    title: 'Untitled Project',
    description: '',
    visibility: 'private',
  });
  // 이 편집 세션이 출발한 저장 시점(ADR-0006). 저장할 때 서버로 돌려보내서, 그 사이 다른
  // 곳에서 저장된 게 있으면 조용히 덮어쓰지 않고 사용자에게 물어보게 한다.
  const [baseRevision, setBaseRevision] = useState(null);
  const [draftSessionId, setDraftSessionId] = useState(null);
  const [latestGenerationTraceId, setLatestGenerationTraceId] = useState(location.state?.traceId || null);

  useEffect(() => {
    if (!isMobileToolsDrawerOpen) return undefined;

    const closeOnOutsideClick = (event) => {
      if (!editorToolsMenuRef.current?.contains(event.target)) {
        setIsMobileToolsDrawerOpen(false);
      }
    };
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setIsMobileToolsDrawerOpen(false);
    };

    document.addEventListener('pointerdown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isMobileToolsDrawerOpen]);

  useEffect(() => {
    if (!isDrawerOpen) return undefined;

    const closeProjectSettings = (event) => {
      if (event.type === 'keydown' && event.key !== 'Escape') return;
      if (event.type === 'pointerdown' && projectControlRef.current?.contains(event.target)) return;
      setIsDrawerOpen(false);
    };

    document.addEventListener('pointerdown', closeProjectSettings);
    document.addEventListener('keydown', closeProjectSettings);
    return () => {
      document.removeEventListener('pointerdown', closeProjectSettings);
      document.removeEventListener('keydown', closeProjectSettings);
    };
  }, [isDrawerOpen]);

  // Configure Axios auth header
  const getAuthHeaders = () => token ? { headers: { Authorization: `Bearer ${token}` } } : {};

  useEffect(() => {
    if (projectId) {
      loadProject(projectId);
    } else if (location.state?.initialGraph) {
      savedProjectMetadataRef.current = null;
      const graph = location.state.initialGraph;
      const rawNodes = graph.nodes.map(n => ({
        ...n,
        data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange }
      }));
      if (looksLikeUnlaidOutRow(rawNodes)) {
        const layouted = getLayoutedElements(rawNodes, graph.edges || [], 'LR');
        replaceGraph(layouted.nodes, layouted.edges, { saved: false });
      } else {
        replaceGraph(rawNodes, graph.edges || [], { saved: false });
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
    } else {
      savedProjectMetadataRef.current = {
        title: 'Untitled Project',
        description: '',
        visibility: 'private',
      };
      replaceGraph([], [], { saved: true });
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
      savedProjectMetadataRef.current = {
        title: data.title,
        description: data.description || '',
        visibility: data.visibility || 'private',
      };
      setIsOwner(user && user.id === data.owner_id);
      setBaseRevision(data.current_revision ?? null);

      if (data.graph_data) {
        // 하이픈 UUID 로 저장된 노드 id 는 서버 보안 검증기가 거부한다 — 열 때 한 번 정규화한다.
        // 바뀐 게 있으면 저장 전 상태로 표시되어 다음 저장에서 고쳐진 id 가 반영된다.
        const normalized = normalizeGraphIds(data.graph_data.nodes || [], data.graph_data.edges || []);
        // 분리 텍스트(popout)는 폐기됐다(계획 §5-7) — 열 때 값을 원래 필드로 되돌리고 노드를 없앤다.
        const absorbed = absorbDetachedText(normalized.nodes, normalized.edges);
        const loadedNodes = absorbed.nodes.map(n => ({
          ...n,
          data: { ...n.data, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange }
        }));
        if (hasStackedNodePositions(loadedNodes)) {
          const layouted = getLayoutedElements(loadedNodes, absorbed.edges, 'LR');
          replaceGraph(layouted.nodes, layouted.edges, { saved: false });
          window.setTimeout(() => fitView({ padding: 0.18, duration: 320, maxZoom: 1.1 }), 60);
        } else {
          replaceGraph(loadedNodes, absorbed.edges, { saved: !normalized.changed && !absorbed.changed });
        }
        setIsLive(data.graph_data.is_live || false);
      } else {
        replaceGraph([], [], { saved: true });
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
      alert("Failed to load project or unauthorized.", 'error');
    }
  };

  const handleSave = async (overrideVisibility = null, overrideFlowData = null, overrideTraceId = null) => {
    if (!user) {
      alert("프로젝트를 저장하려면 로그인이 필요합니다. 왼쪽 메뉴에서 구글 계정으로 로그인해주세요.", 'warning');
      return null;
    }
    // overrideFlowData: setNodes/setEdges 직후 곧바로 저장해야 할 때(예: AI 생성 직후 자동 저장)
    // getCurrentFlowData()가 React Flow 내부 상태 반영 전이라 방금 만든 노드를 못 읽어오는
    // 타이밍 문제가 있었다(실제로 빈 그래프가 저장되는 걸 확인함) — 이럴 땐 이미 손에 들고 있는
    // 최신 graph_data를 그대로 쓰도록 우회 경로를 둔다.
    // 저장 충돌(409) 뒤 덮어쓰기로 다시 보내야 하므로 try 블록 바깥에서 만든다.
    const payload = {
      title: projectTitle,
      description: projectDescription,
      graph_data: overrideFlowData || getCurrentFlowData(),
      visibility: overrideVisibility !== null ? overrideVisibility : visibility,
      generation_trace_id: overrideTraceId || latestGenerationTraceId,
      base_revision: baseRevision,
    };

    try {
      if (currentId) {
        const res = await axios.put(`/api/projects/${currentId}`, payload, getAuthHeaders());
        setBaseRevision(res.data.current_revision ?? baseRevision);
        savedProjectMetadataRef.current = {
          title: payload.title,
          description: payload.description,
          visibility: payload.visibility,
        };
        markEditorHistorySaved(payload.graph_data.nodes || [], payload.graph_data.edges || []);
        completeOnboardingStep('workflow_saved');
        return currentId;
      } else {
        if (draftSessionId) {
          payload.draft_session_id = draftSessionId;
        }
        const res = await axios.post('/api/projects', payload, getAuthHeaders());
        setCurrentId(res.data.id);
        setBaseRevision(res.data.current_revision ?? null);
        savedProjectMetadataRef.current = {
          title: payload.title,
          description: payload.description,
          visibility: payload.visibility,
        };
        markEditorHistorySaved(payload.graph_data.nodes || [], payload.graph_data.edges || []);
        navigate(`/editor/${res.data.id}`, { replace: true });
        completeOnboardingStep('workflow_saved');
        return res.data.id;
      }
    } catch (error) {
      // 409 = 내가 편집을 시작한 뒤 다른 곳에서 이 워크플로우가 저장됐다. 예전에는 여기서
      // 그냥 덮어써서 앞선 변경이 조용히 사라졌다 — 이제는 사용자에게 선택을 넘긴다.
      const conflict = error?.response?.status === 409 ? error.response.data?.detail : null;
      if (conflict) {
        const overwrite = await customConfirm(describeSaveConflict(conflict));
        if (!overwrite) return false;
        try {
          const res = await axios.put(
            `/api/projects/${currentId}`,
            { ...payload, force_overwrite: true },
            getAuthHeaders()
          );
          setBaseRevision(res.data.current_revision ?? null);
          savedProjectMetadataRef.current = {
            title: payload.title,
            description: payload.description,
            visibility: payload.visibility,
          };
          markEditorHistorySaved(payload.graph_data.nodes || [], payload.graph_data.edges || []);
          completeOnboardingStep('workflow_saved');
          return currentId;
        } catch (retryError) {
          console.error("Save failed after overwrite", retryError);
          alert("프로젝트 저장에 실패했습니다.");
          return false;
        }
      }
      console.error("Save failed", error);
      alert("프로젝트 저장에 실패했습니다.");
      return false;
    }
  };

  const handleOpenDeployModal = async () => {
    if (!currentId) {
      alert("먼저 프로젝트를 저장해 주세요.", 'warning');
      return;
    }
    // Save latest state before deployment
    const saved = await handleSave();
    if (saved) {
      setIsDeployModalOpen(true);
      completeOnboardingStep('deploy_previewed');
    }
  };

  const handleToggleLive = async () => {
    if (!currentId) {
      alert("프로젝트를 먼저 저장해 주세요.", 'warning');
      return;
    }
    try {
      const res = await axios.post(`/api/projects/${currentId}/live`, { is_live: !isLive }, getAuthHeaders());
      if (res.data.status === 'success') {
        setIsLive(res.data.is_live);
        if (res.data.warning) {
          alert("⚠️ " + res.data.warning, 'warning');
        } else {
          alert(res.data.is_live ? "라이브 모드가 시작되었습니다! (웹훅/스케줄/봇 대기중)" : "라이브 모드가 중지되었습니다.");
        }
      }
    } catch (e) {
      console.error("Live toggle failed", e);
      alert("라이브 상태 변경에 실패했습니다.");
    }
  };





  // 필드 데이터 바인딩(계획 DATA_FLOW_SEPARATION_PLAN §5) — 픽커가 쓰는 컨텍스트.
  // 캔버스에 선을 그리지 않고 노드 data.bindings 에 저장한다.
  const applyBinding = useCallback((nodeId, field, spec) => {
    markNextHistory(spec ? '값 연결' : '값 연결 해제');
    setNodes((nds) => nds.map((node) => {
      if (String(node.id) !== String(nodeId)) return node;
      const bindings = { ...(node.data?.bindings || {}) };
      if (spec) bindings[field] = spec;
      else delete bindings[field];
      const data = { ...node.data };
      if (Object.keys(bindings).length) data.bindings = bindings;
      else delete data.bindings;
      return { ...node, data };
    }));
  }, [markNextHistory, setNodes]);

  const onConnect = useCallback((params) => {
    // 필드 입력 포트(bind:<필드>)로 떨어졌으면 실행 엣지를 만들지 않는다 — 정본은 data.bindings 다.
    // 경로는 비워 두고("출력 전체") 세부 경로는 픽커에서 고르게 한다.
    if (typeof params.targetHandle === 'string' && params.targetHandle.startsWith('bind:')) {
      applyBinding(params.target, params.targetHandle.slice(5), { source: String(params.source), path: '' });
      return;
    }
    markNextHistory('노드 연결');
    setEdges((eds) => addEdge(params, eds));
  }, [applyBinding, markNextHistory, setEdges]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const commitNodeDataChanges = useCallback((changes) => {
    if (changes.length === 0) return;
    completeOnboardingStep('node_configured');
    markNextHistory('노드 설정 변경', 650);
    const changesByNode = new Map();
    changes.forEach(({ id, key, value }) => {
      const nodeChanges = changesByNode.get(String(id)) || {};
      nodeChanges[key] = value;
      changesByNode.set(String(id), nodeChanges);
    });
    setNodes((nds) => nds.map((node) => {
      const nodeChanges = changesByNode.get(String(node.id));
      return nodeChanges ? { ...node, data: { ...node.data, ...nodeChanges } } : node;
    }));
  }, [markNextHistory, setNodes]);

  const onNodeDataChange = useCallback((id, key, value) => {
    const composition = nodeInputCompositionRef.current;
    const changeId = `${String(id)}\u0000${String(key)}`;

    // 한글·일본어·중국어 IME는 한 글자가 확정되기 전에도 change 이벤트를 보낸다.
    // 이때 React Flow 상태를 갱신하면 제어 입력이 다시 렌더링되며 조합 중인 자모가 끊긴다.
    if (composition.isComposing || composition.flushTimer !== null) {
      composition.pending.set(changeId, { id, key, value });
      return;
    }

    commitNodeDataChanges([{ id, key, value }]);
  }, [commitNodeDataChanges]);

  const handleNodeCompositionStart = useCallback((event) => {
    if (!event.target.closest?.('.react-flow__node input, .react-flow__node textarea')) return;
    nodeInputCompositionRef.current.isComposing = true;
  }, []);

  // 조합 플래그가 남아 버린 경우의 안전장치. 조합 도중 입력창이 blur 로 언마운트되면(DraggableTextarea 는
  // blur 시 사라진다) compositionend 가 오지 않아 isComposing 이 영원히 true 로 남고, 그 뒤의 모든 입력이
  // 버퍼에만 쌓여 화면에 반영되지 않았다("노드 텍스트 수정이 안 됨"). 버퍼를 비우고 즉시 커밋한다.
  const flushNodeInputComposition = useCallback(() => {
    const composition = nodeInputCompositionRef.current;
    composition.isComposing = false;
    if (composition.flushTimer) {
      window.clearTimeout(composition.flushTimer);
      composition.flushTimer = null;
    }
    const changes = [...composition.pending.values()];
    composition.pending.clear();
    if (changes.length) commitNodeDataChanges(changes);
  }, [commitNodeDataChanges]);

  const handleNodeInputBlur = useCallback((event) => {
    if (!event.target.closest?.('.react-flow__node input, .react-flow__node textarea')) return;
    if (nodeInputCompositionRef.current.isComposing || nodeInputCompositionRef.current.pending.size) {
      flushNodeInputComposition();
    }
  }, [flushNodeInputComposition]);

  // IME 조합 중의 keydown 은 event.isComposing 이 true 다. 우리 플래그만 true 인데 브라우저는 조합 중이
  // 아니라고 하면 플래그가 오래된 것이다 — 그 자리에서 되돌린다.
  const handleNodeInputKeyDown = useCallback((event) => {
    if (event.isComposing || event.key === 'Process') return;
    if (!nodeInputCompositionRef.current.isComposing) return;
    if (!event.target.closest?.('.react-flow__node input, .react-flow__node textarea')) return;
    flushNodeInputComposition();
  }, [flushNodeInputComposition]);


  const handleNodeCompositionEnd = useCallback((event) => {
    if (!event.target.closest?.('.react-flow__node input, .react-flow__node textarea')) return;
    const composition = nodeInputCompositionRef.current;
    composition.isComposing = false;
    window.clearTimeout(composition.flushTimer);
    // compositionend 뒤에 발생하는 마지막 input/change 이벤트까지 같은 버퍼에 담는다.
    composition.flushTimer = window.setTimeout(() => {
      composition.flushTimer = null;
      if (composition.isComposing) return;
      const changes = [...composition.pending.values()];
      composition.pending.clear();
      commitNodeDataChanges(changes);
    }, 0);
  }, [commitNodeDataChanges]);

  const deleteNode = useCallback((idToDelete) => {
    markNextHistory('노드 삭제');
    setNodes((nds) => nds.filter((node) => node.id !== idToDelete));
    setEdges((eds) => eds.filter((edge) => edge.source !== idToDelete && edge.target !== idToDelete));
  }, [markNextHistory, setNodes, setEdges]);

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

  const recordRecentNodeType = useCallback((type) => {
    setRecentNodeTypes((current) => {
      const next = [type, ...current.filter((item) => item !== type)].slice(0, 8);
      storeNodeTypes('editorRecentNodeTypes', next);
      return next;
    });
  }, []);

  const toggleFavoriteNodeType = useCallback((type) => {
    setFavoriteNodeTypes((current) => {
      const next = current.includes(type)
        ? current.filter((item) => item !== type)
        : [...current, type];
      storeNodeTypes('editorFavoriteNodeTypes', next);
      return next;
    });
  }, []);

  const buildEditorNode = useCallback((type, canvasPosition, { selected = true } = {}) => {
    const meta = getEditorNodeMeta(type);
    const newNode = {
      id: getId(),
      type,
      position: { ...canvasPosition },
      selected,
      data: {
        label: meta.label,
        onChange: onNodeDataChange,
        onDelete: deleteNode,
        onExpandChange,
      },
      zIndex: type === 'loopNode' ? -1 : 1,
    };

    if (type !== 'loopNode') {
      const parentLoop = nodesRef.current.find((node) => {
        if (node.type !== 'loopNode') return false;
        const width = node.measured?.width || node.width || 250;
        const height = node.measured?.height || node.height || 200;
        return canvasPosition.x >= node.position.x
          && canvasPosition.x <= node.position.x + width
          && canvasPosition.y >= node.position.y
          && canvasPosition.y <= node.position.y + height;
      });
      if (parentLoop) {
        newNode.parentNode = parentLoop.id;
        newNode.position = {
          x: canvasPosition.x - parentLoop.position.x,
          y: canvasPosition.y - parentLoop.position.y,
        };
        newNode.extent = 'parent';
      }
    }
    return ensureMemoNodeDefaults(newNode);
  }, [deleteNode, onExpandChange, onNodeDataChange]);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();
      markNextHistory('노드 추가');


      const type = event.dataTransfer.getData('application/reactflow');
      if (typeof type === 'undefined' || !type) {
        return;
      }
      const droppedLabel = event.dataTransfer.getData('application/reactflow-label');
      const nodeMeta = getEditorNodeMeta(type);
      recordRecentNodeType(type);

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNode = {
        id: getId(),
        type,
        position,
        data: { label: droppedLabel || nodeMeta.label, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange },
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
    [screenToFlowPosition, setNodes, setEdges, onNodeDataChange, deleteNode, onExpandChange, markNextHistory, recordRecentNodeType],
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
      data: { label: label || getEditorNodeMeta(type).label, onChange: onNodeDataChange, onDelete: deleteNode, onExpandChange },
      zIndex: type === 'loopNode' ? -1 : 1,
    };

    markNextHistory('노드 추가');
    setNodes((nds) => nds.concat(newNode));
    recordRecentNodeType(type);
    setIsPaletteOpen(false); // Close palette after adding
  }, [screenToFlowPosition, setNodes, onNodeDataChange, deleteNode, onExpandChange, markNextHistory, recordRecentNodeType]);

  const { getIntersectingNodes } = useReactFlow();

  const onNodeDragStop = useCallback((event, node) => {
    const historyLabel = altDragDuplicateRef.current ? 'Alt 드래그 복제' : '노드 이동';
    altDragDuplicateRef.current = false;
    scheduleHistoryCommit(historyLabel);

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
  }, [getIntersectingNodes, scheduleHistoryCommit, setEdges, setNodes]);

  const openNodeTypePicker = useCallback(({ mode = 'add', clientX, clientY, flowPosition, ...context }) => {
    const pickerWidth = 360;
    const pickerHeight = 470;
    setNodePicker({
      mode,
      flowPosition: flowPosition || screenToFlowPosition({ x: clientX, y: clientY }),
      x: Math.max(8, Math.min(clientX, window.innerWidth - pickerWidth - 8)),
      y: Math.max(64, Math.min(clientY, window.innerHeight - pickerHeight - 8)),
      ...context,
    });
    setNodePickerQuery('');
    setActiveNodePickerIndex(0);
    setEditorContextMenu(null);
  }, [screenToFlowPosition]);

  const nodePickerCandidates = useMemo(() => {
    if (!nodePicker) return [];
    let candidates = nodePicker.mode === 'replace'
      ? getReplacementCandidates(nodePicker.node?.type)
      : EDITOR_NODE_CATALOG;
    if (nodePicker.mode === 'insert' || nodePicker.mode === 'connect') {
      // 연결선 삽입/드롭 연결 대상은 실행 노드만 — 메모(주석)나 컨테이너는 제외한다.
      candidates = candidates.filter((candidate) => candidate.kind === 'node' || (nodePicker.mode === 'connect' && candidate.kind === 'container'));
    }
    const query = nodePickerQuery.trim().toLocaleLowerCase('ko');
    if (query) {
      candidates = candidates.filter((candidate) => (
        `${candidate.label} ${candidate.type} ${candidate.categoryLabel}`.toLocaleLowerCase('ko').includes(query)
      ));
    }
    const favoriteRank = new Map(favoriteNodeTypes.map((type, index) => [type, index]));
    const recentRank = new Map(recentNodeTypes.map((type, index) => [type, index]));
    return [...candidates].sort((a, b) => {
      const aFavorite = favoriteRank.has(a.type) ? favoriteRank.get(a.type) : Number.MAX_SAFE_INTEGER;
      const bFavorite = favoriteRank.has(b.type) ? favoriteRank.get(b.type) : Number.MAX_SAFE_INTEGER;
      if (aFavorite !== bFavorite) return aFavorite - bFavorite;
      const aRecent = recentRank.has(a.type) ? recentRank.get(a.type) : Number.MAX_SAFE_INTEGER;
      const bRecent = recentRank.has(b.type) ? recentRank.get(b.type) : Number.MAX_SAFE_INTEGER;
      if (aRecent !== bRecent) return aRecent - bRecent;
      return a.label.localeCompare(b.label, 'ko');
    });
  }, [favoriteNodeTypes, nodePicker, nodePickerQuery, recentNodeTypes]);

  const applyNodePickerSelection = useCallback(async (type) => {
    if (!nodePicker || !type || !isOwner) return;
    flushHistoryCommit();
    const meta = getEditorNodeMeta(type);

    if (nodePicker.mode === 'replace') {
      const sourceNode = nodesRef.current.find((node) => String(node.id) === String(nodePicker.node?.id));
      if (!sourceNode) return;
      const uiKeys = new Set(['label', 'onChange', 'onDelete', 'onExpandChange', 'onClearAIHighlight', 'isAIModified', 'aiChanges']);
      const universalFields = new Set(['name', 'description', 'timeout', 'retryCount']);
      const targetFields = new Set([...meta.fieldNames, ...universalFields]);
      const dataKeys = Object.keys(sourceNode.data || {}).filter((key) => !uiKeys.has(key) && typeof sourceNode.data[key] !== 'function');
      const preservedKeys = dataKeys.filter((key) => targetFields.has(key));
      const removedKeys = dataKeys.filter((key) => !targetFields.has(key));
      const confirmed = await customConfirm(
        `“${getEditorNodeMeta(sourceNode.type).label}” 노드를 “${meta.label}”(으)로 교체하시겠습니까?\n\n`
        + `연결 ${edgesRef.current.filter((edge) => edge.source === sourceNode.id || edge.target === sourceNode.id).length}개는 유지됩니다.\n`
        + `유지 설정: ${preservedKeys.length ? preservedKeys.join(', ') : '없음'}\n`
        + `초기화 설정: ${removedKeys.length ? removedKeys.join(', ') : '없음'}`
      );
      if (!confirmed) return;
      const preservedData = Object.fromEntries(preservedKeys.map((key) => [key, sourceNode.data[key]]));
      const nextNodes = ensureMemoNodeDefaultsForList(nodesRef.current.map((node) => String(node.id) === String(sourceNode.id) ? {
        ...node,
        type,
        zIndex: type === 'loopNode' ? -1 : 1,
        data: {
          label: meta.label,
          ...preservedData,
          onChange: onNodeDataChange,
          onDelete: deleteNode,
          onExpandChange,
        },
      } : node));
      const nextEdges = edgesRef.current.map((edge) => {
        const next = { ...edge };
        if (String(edge.source) === String(sourceNode.id)) delete next.sourceHandle;
        if (String(edge.target) === String(sourceNode.id)) delete next.targetHandle;
        return next;
      });
      nodesRef.current = nextNodes;
      edgesRef.current = nextEdges;
      setNodesState(nextNodes);
      setEdgesState(nextEdges);
      commitEditorHistory(nextNodes, nextEdges, `노드 교체: ${meta.label}`);
      recordRecentNodeType(type);
      setNodePicker(null);
      return;
    }

    const newNode = buildEditorNode(type, nodePicker.flowPosition);
    let nextEdges = edgesRef.current.map((edge) => edge.selected ? { ...edge, selected: false } : edge);
    let historyLabel = `노드 추가: ${meta.label}`;

    if (nodePicker.mode === 'connect' && nodePicker.connection?.nodeId) {
      const connection = nodePicker.connection;
      const edge = connection.handleType === 'target'
        ? {
            id: getEntityId('edge'),
            source: newNode.id,
            target: connection.nodeId,
            targetHandle: connection.handleId || undefined,
          }
        : {
            id: getEntityId('edge'),
            source: connection.nodeId,
            sourceHandle: connection.handleId || undefined,
            target: newNode.id,
          };
      nextEdges = [...nextEdges, edge];
      historyLabel = `연결하여 노드 추가: ${meta.label}`;
    } else if (nodePicker.mode === 'insert' && nodePicker.edge) {
      const original = edgesRef.current.find((edge) => String(edge.id) === String(nodePicker.edge.id));
      if (!original) return;
      const incoming = { ...original, id: getEntityId('edge'), target: newNode.id, selected: false };
      const outgoing = { ...original, id: getEntityId('edge'), source: newNode.id, selected: false };
      delete incoming.targetHandle;
      delete outgoing.sourceHandle;
      nextEdges = [
        ...nextEdges.filter((edge) => String(edge.id) !== String(original.id)),
        incoming,
        outgoing,
      ];
      historyLabel = `연결선에 노드 삽입: ${meta.label}`;
    }

    const nextNodes = [
      ...nodesRef.current.map((node) => ({ ...node, selected: false })),
      newNode,
    ];
    nodesRef.current = nextNodes;
    edgesRef.current = nextEdges;
    setNodesState(nextNodes);
    setEdgesState(nextEdges);
    commitEditorHistory(nextNodes, nextEdges, historyLabel);
    recordRecentNodeType(type);
    setNodePicker(null);
  }, [buildEditorNode, commitEditorHistory, deleteNode, flushHistoryCommit, isOwner, nodePicker, onExpandChange, onNodeDataChange, recordRecentNodeType, setEdgesState, setNodesState]);

  const addNodeAtViewportCenter = useCallback((type) => {
    flushHistoryCommit();
    const rect = reactFlowWrapper.current?.getBoundingClientRect();
    const canvasPosition = screenToFlowPosition({
      x: rect ? rect.left + rect.width / 2 : window.innerWidth / 2,
      y: rect ? rect.top + rect.height / 2 : window.innerHeight / 2,
    });
    const newNode = buildEditorNode(type, canvasPosition);
    const nextNodes = [...nodesRef.current.map((node) => ({ ...node, selected: false })), newNode];
    nodesRef.current = nextNodes;
    setNodesState(nextNodes);
    commitEditorHistory(nextNodes, edgesRef.current, `노드 추가: ${getEditorNodeMeta(type).label}`);
    recordRecentNodeType(type);
  }, [buildEditorNode, commitEditorHistory, flushHistoryCommit, recordRecentNodeType, screenToFlowPosition, setNodesState]);

  const handleConnectStart = useCallback((event, connection) => {
    connectionStartRef.current = connection;
  }, []);

  const handleConnectEnd = useCallback((event, connectionState) => {
    const connection = connectionStartRef.current;
    connectionStartRef.current = null;
    if (!connection || connectionState?.isValid || !isOwner) return;
    const target = event.target;
    if (!(target instanceof Element) || !target.classList.contains('react-flow__pane')) return;
    const point = event.changedTouches?.[0] || event;
    openNodeTypePicker({
      mode: 'connect',
      clientX: point.clientX,
      clientY: point.clientY,
      connection,
    });
  }, [isOwner, openNodeTypePicker]);

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
          edges: currentEdges.map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
        }
      };

      const res = await axios.post('/api/evaluate', payload, getAuthHeaders());
      if (res.data.status === 'success') {
        setEvaluationReport(res.data.report);
        completeOnboardingStep('workflow_tested');
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
          edges: currentEdges.map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
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

  const replayExecutionLogs = useCallback(async (logs, animationToken) => {
    const orderedLogs = [...(logs || [])].sort((left, right) => {
      const leftTime = left.start_time ? Date.parse(left.start_time) : 0;
      const rightTime = right.start_time ? Date.parse(right.start_time) : 0;
      return leftTime - rightTime;
    });

    setExecutionLogs([]);
    setExecutionNodeStates({});
    setIsExecHighlightDismissed(false);
    if (orderedLogs.length === 0) return;

    const runningDuration = Math.max(35, Math.min(620, Math.round(3300 / orderedLogs.length)));
    const settledDuration = Math.max(15, Math.min(140, Math.round(800 / orderedLogs.length)));

    for (const log of orderedLogs) {
      if (executionAnimationTokenRef.current !== animationToken) return;
      const nodeId = String(log.node_id);
      setExecutionNodeStates((current) => ({ ...current, [nodeId]: 'running' }));
      await waitForExecutionFrame(runningDuration);
      if (executionAnimationTokenRef.current !== animationToken) return;

      const finalStatus = log.status === 'error' ? 'error' : 'success';
      setExecutionNodeStates((current) => ({ ...current, [nodeId]: finalStatus }));
      setExecutionLogs((current) => [...current, log]);
      await waitForExecutionFrame(settledDuration);
    }
  }, []);

  const [pendingApproval, setPendingApproval] = useState(null);
  const [approvalComment, setApprovalComment] = useState('');
  const [approvalDeciding, setApprovalDeciding] = useState(false);

  const decideApproval = async (decision) => {
    if (!pendingApproval || approvalDeciding) return;
    setApprovalDeciding(true);
    try {
      const res = await axios.post(
        `/api/approvals/${pendingApproval.request_id}/decide`,
        { decision, comment: approvalComment },
        getAuthHeaders(),
      );
      setPendingApproval(null);
      setApprovalComment('');
      const animationToken = ++executionAnimationTokenRef.current;
      await replayExecutionLogs(res.data.logs || [], animationToken);
      setResponse(res.data.result || 'No content returned.');
      setTokenUsage(res.data.token_usage || null);
      if (res.data.approval_request) {
        // 재개 후 다음 승인 노드에서 다시 대기(연쇄 승인) — 모달을 이어서 띄운다.
        setPendingApproval(res.data.approval_request);
      }
    } catch (error) {
      alert('승인 처리 실패: ' + (error.response?.data?.detail || error.message));
    } finally {
      setApprovalDeciding(false);
    }
  };

  // 샘플 입력(§7.1)과 고정 출력(§7.3)은 프로젝트·노드 단위로 브라우저에만 저장한다 — 그래프에
  // 넣으면 테스트 픽스처가 저장·공유·AI 문맥에 섞인다. 저장 규칙은 nodeTestFixtures 에 있다.
  const readSampleInput = useCallback((nodeId) => readStoredSampleInput(projectId, nodeId), [projectId]);
  const writeSampleInput = useCallback((nodeId, value) => writeStoredSampleInput(projectId, nodeId, value), [projectId]);
  // 고정 출력이 바뀌면 Inspector 와 노드 배지가 다시 그려져야 한다.
  const [pinnedVersion, setPinnedVersion] = useState(0);
  const pinnedOutputs = useMemo(
    () => collectPinnedOutputs(projectId, nodes),
    [projectId, nodes, pinnedVersion],  // eslint-disable-line react-hooks/exhaustive-deps
  );
  const pinOutput = useCallback((node, value) => {
    if (!writePinnedOutput(projectId, node, value)) {
      alert('브라우저 저장 공간이 부족해 출력을 고정하지 못했습니다.', 'error');
      return;
    }
    setPinnedVersion((version) => version + 1);
  }, [projectId]);
  const unpinOutput = useCallback((nodeId) => {
    clearPinnedOutput(projectId, nodeId);
    setPinnedVersion((version) => version + 1);
  }, [projectId]);

  const focusNodeById = useCallback((nodeId) => {
    setNodes((currentNodes) => currentNodes.map((node) => ({ ...node, selected: String(node.id) === String(nodeId) })));
    fitView({ nodes: [{ id: String(nodeId) }], duration: 320, maxZoom: 1.1 });
  }, [fitView, setNodes]);

  const openInspector = useCallback((nodeId) => {
    setInspectorNodeId(String(nodeId));
    setIsExecutionPanelOpen(true);
    setExecutionPanelTab('inspect');
    setEditorContextMenu(null);
  }, []);

  const runFlow = async (rawOptions = null) => {
    // onClick={runFlow}로 불리면 첫 인자가 클릭 이벤트다 — 부분 실행 옵션만 골라낸다.
    const entryOptions = rawOptions && (rawOptions.entryNodeId || rawOptions.stopNodeId || rawOptions.scopeNodeIds)
      ? rawOptions : null;
    const entry = entryOptions && entryOptions.entryNodeId ? entryOptions : null;
    // 자동 저장 (실행 전)
    const savedId = await handleSave();
    if (!savedId) {
      alert("프로젝트 저장에 실패하여 실행을 취소합니다.");
      return;
    }

    const animationToken = ++executionAnimationTokenRef.current;
    setIsLoading(true);
    setIsCompiled(false);
    setExecutionLogs([]); // Clear previous logs
    setExecutionNodeStates({});
    setIsExecHighlightDismissed(false);
    setExecutionErrors([]);
    setMockRunSummary(null);   // 실제 실행이므로 목업 배지를 지운다
    setResponse('Running graph on backend...');
    setIsExecutionPanelOpen(true);
    setExecutionPanelTab('result');

    try {
      const currentNodes = getNodes();
      const currentEdges = getEdges();

      const payload = {
        project_id: savedId,
        nodes: currentNodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
        edges: currentEdges.map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle })),
        ...(entry ? { entry_node_id: String(entry.entryNodeId), entry_input: entry.entryInput || '' } : {}),
        // 범위 실행(§7.4)과 고정 출력(§7.3). 고정된 노드는 실행되지 않고 저장된 값이 하류로 간다.
        ...(entryOptions?.stopNodeId ? { stop_node_id: String(entryOptions.stopNodeId) } : {}),
        ...(entryOptions?.scopeNodeIds ? { scope_node_ids: entryOptions.scopeNodeIds.map(String) } : {}),
        ...(Object.keys(pinnedOutputs).length ? { pinned_outputs: pinnedOutputs } : {}),
      };

      const entryNodeIds = getExecutionEntryNodeIds(currentNodes, currentEdges);
      setExecutionNodeStates(Object.fromEntries(entryNodeIds.map((nodeId) => [nodeId, 'running'])));

      const res = await axios.post('/api/execute', payload, getAuthHeaders());
      await replayExecutionLogs(res.data.logs || [], animationToken);
      setResponse(res.data.result || 'No content returned.');
      setTokenUsage(res.data.token_usage || null);
      setExecutionErrors(Array.isArray(res.data.errors) ? res.data.errors : []);
      setNodeErrorV1(res.data.node_error_v1 !== false);
      // 승인 노드에서 대기로 멈춘 실행 — 실행자가 곧 승인자이므로 즉석에서 견본을 보여주고
      // 결정을 받는다(나중에 결정하면 승인 페이지에 그대로 남아 있다).
      if (res.data.approval_request) {
        setPendingApproval(res.data.approval_request);
      }
      // 성공 판정은 서버의 구조화 outcome(NodeError v1)을 우선하고, 없으면 예전 방식으로 본다.
      const runSucceeded = res.data.outcome
        ? res.data.outcome === 'success'
        : ((res.data.logs || []).every((log) => log.status !== 'error')
          && !String(res.data.result || '').includes('❌'));
      if (runSucceeded) celebrateMilestone('first-run');
      completeOnboardingStep('workflow_tested');
    } catch (error) {
      console.error(error);
      executionAnimationTokenRef.current += 1;
      setExecutionNodeStates({});
      setResponse('Error communicating with backend: ' + (error.response?.data?.detail || error.message));
      setTokenUsage(null);
    } finally {
      setIsLoading(false);
    }
  };

  // 오류 카드의 "해당 입력으로 이동" — 노드를 캔버스에서 찾고 검사 탭을 그 노드로 연다(ADR-0016 ERROR-4.1).
  const focusErrorField = useCallback((nodeId) => {
    setInspectorNodeId(String(nodeId));
    setExecutionPanelTab('inspect');
    setIsExecutionPanelOpen(true);
    focusNodeById(nodeId);
  }, [focusNodeById]);

  // 실제 실행 전 외부 전송 확인(§7.1) — 목업이 기본이고, 바깥으로 나가는 실행은 사용자가
  // 무엇이 나가는지 보고 결정한다. 확인 없이 발송되던 것이 Slice 4 재점검에서 나온 결함이다.
  const confirmExternalRun = useCallback(async (startId, { stopNodeId = null } = {}) => {
    const currentNodes = getNodes();
    const currentEdges = stopNodeId
      ? getEdges().filter((edge) => String(edge.source) !== String(stopNodeId))
      : getEdges();
    const external = downstreamExternalNodes(currentNodes, currentEdges, startId, getNodeDefinition);
    if (external.length === 0) return true;
    const names = external.slice(0, 5).map((node) => `· ${getEditorNodeMeta(node.type).label} (${node.id})`).join('\n');
    const more = external.length > 5 ? `\n… 외 ${external.length - 5}개` : '';
    return customConfirm(
      `실제 실행하면 아래 노드가 외부로 전송·기록합니다.\n\n${names}${more}\n\n`
      + '외부 호출 없이 확인만 하려면 취소하고 "목업" 버튼을 사용하세요.\n\n계속하시겠습니까?'
    );
  }, [getEdges, getNodes]);

  // "이 노드부터 실행"(§7.4 범위 실행) — 승인 재개와 같은 진입점 메커니즘을 재사용한다.
  const runFromNode = useCallback(async (nodeId) => {
    setEditorContextMenu(null);
    if (!(await confirmExternalRun(nodeId))) return;
    runFlow({ entryNodeId: nodeId, entryInput: readSampleInput(nodeId) });
  }, [confirmExternalRun, readSampleInput, runFlow]);  // eslint-disable-line react-hooks/exhaustive-deps

  // "여기까지 실행"(§7.4) — 이 노드의 결과까지만 만들고 하류로는 넘기지 않는다.
  const runUpToNode = useCallback(async (nodeId) => {
    setEditorContextMenu(null);
    if (!(await confirmExternalRun(getExecutionEntryNodeIds(getNodes(), getEdges())[0] || nodeId, { stopNodeId: nodeId }))) return;
    runFlow({ stopNodeId: nodeId });
  }, [confirmExternalRun, getEdges, getNodes, runFlow]);  // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * 목업 실행(§7.1·§7.4, Slice 4 완료 기준) — 외부 API 를 부르지 않고 이 노드만/여기부터 돌린다.
   * 실제 자격증명을 읽지 않으므로 아무것도 등록하지 않은 상태에서도 입력→출력을 확인할 수 있다.
   */
  const runNodeMock = useCallback(async (nodeId, { only = false, sampleInput = null, scopeNodeIds = null } = {}) => {
    setEditorContextMenu(null);
    const savedId = await handleSave();
    if (!savedId) {
      alert('프로젝트 저장에 실패하여 목업 실행을 취소합니다.');
      return;
    }
    const animationToken = ++executionAnimationTokenRef.current;
    setIsLoading(true);
    setIsCompiled(false);
    setExecutionLogs([]);
    setExecutionNodeStates({});
    setIsExecHighlightDismissed(false);
    setExecutionErrors([]);
    setResponse('목업으로 실행 중...');
    setIsExecutionPanelOpen(true);
    try {
      const res = await axios.post(`/api/projects/${savedId}/mock/run`, {
        graph_data: getCurrentFlowData(),
        start_node_id: String(nodeId),
        ...(only ? { stop_node_id: String(nodeId) } : {}),
        ...(scopeNodeIds ? { scope_node_ids: scopeNodeIds.map(String) } : {}),
        sample_input: sampleInput ?? readSampleInput(nodeId),
        ...(Object.keys(pinnedOutputs).length ? { pinned_outputs: pinnedOutputs } : {}),
        scenario: 'success',
      }, getAuthHeaders());
      await replayExecutionLogs(res.data.logs || [], animationToken);
      setResponse(res.data.result || '결과 없음');
      setExecutionErrors(Array.isArray(res.data.errors) ? res.data.errors : []);
      setMockRunSummary({
        nodeId: String(nodeId),
        only,
        success: res.data.success,
        requestCount: (res.data.requests || []).length,
      });
    } catch (error) {
      setResponse('목업 실행 실패: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
    // handleSave·getCurrentFlowData 는 이 컴포넌트 아래쪽에서 매 렌더 새로 만들어지는 평범한
    // 함수다. 의존성 배열은 렌더 중에 평가되므로 여기에 적으면 아직 초기화되지 않은 const 를
    // 읽어 "Cannot access '…' before initialization" 으로 앱이 죽는다(실제로 그렇게 죽었다).
    // 호출은 콜백 실행 시점이라 안전하다.
  }, [getAuthHeaders, pinnedOutputs, readSampleInput, replayExecutionLogs]);  // eslint-disable-line react-hooks/exhaustive-deps

  /** "선택 branch 실행"(§7.4) — 선택한 노드들만 목업으로 돌린다. 진입점은 선택 안에서 상류가 없는 노드다. */
  const runSelectionMock = useCallback(() => {
    const selected = editorSelection.nodes.map((node) => String(node.id));
    if (selected.length === 0) return;
    const scope = new Set(selected);
    const hasIncoming = new Set(
      getEdges().filter((edge) => scope.has(String(edge.source)) && scope.has(String(edge.target)))
        .map((edge) => String(edge.target)),
    );
    const entry = selected.find((id) => !hasIncoming.has(id)) || selected[0];
    runNodeMock(entry, { only: false, scopeNodeIds: selected });
  }, [editorSelection.nodes, getEdges, runNodeMock]);

  /** "이전 실행 데이터로 다시 실행"(§7.4) — 직전 실행에서 이 노드가 받은 입력을 그대로 쓴다. */
  const replayNodeWithLastInput = useCallback((nodeId) => {
    const sources = getEdges().filter((edge) => String(edge.target) === String(nodeId)).map((edge) => String(edge.source));
    const upstreamLog = executionLogs.find((log) => sources.includes(String(log.node_id)));
    runNodeMock(nodeId, { only: true, sampleInput: upstreamLog?.result_data ?? '' });
  }, [executionLogs, getEdges, runNodeMock]);

  const toggleNodeLock = useCallback((nodeId) => {
    // React Flow의 draggable=false가 이동을 막는다. 값은 노드에 저장돼 저장/불러오기 후에도 유지된다.
    markNextHistory('위치 잠금');
    setNodes((currentNodes) => currentNodes.map((node) => (
      String(node.id) === String(nodeId) ? { ...node, draggable: node.draggable === false } : node
    )));
    setEditorContextMenu(null);
  }, [markNextHistory, setNodes]);

  const addMemoAtPosition = useCallback((flowPosition) => {
    markNextHistory('메모 추가');
    const memoNode = {
      id: getId(),
      type: 'memoNode',
      position: flowPosition || screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 }),
      width: MEMO_DEFAULT_WIDTH,
      height: MEMO_MIN_NODE_HEIGHT,
      data: {
        text: '',
        memoContent: { version: 1, segments: [] },
        memoFontSize: 14,
        memoSize: { width: MEMO_DEFAULT_WIDTH, height: MEMO_MIN_NODE_HEIGHT },
        onChange: onNodeDataChange,
        onDelete: deleteNode,
        onExpandChange,
      },
    };
    setNodes((currentNodes) => [...currentNodes, memoNode]);
    setEditorContextMenu(null);
  }, [deleteNode, markNextHistory, onExpandChange, onNodeDataChange, screenToFlowPosition, setNodes]);

  // 문제 패널(§7.4): dry-run으로 스키마·구조·컴파일·차단 대상을 실행 없이 검사한다.
  const runProblemsCheck = useCallback(async () => {
    setProblemsLoading(true);
    try {
      const res = await axios.post('/api/dry-run', {
        project_id: projectId ? Number(projectId) : null,
        nodes: getNodes().map(n => ({ id: n.id, type: n.type, data: n.data })),
        edges: getEdges().map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle })),
      }, getAuthHeaders());
      setProblemsReport(res.data);
    } catch (error) {
      setProblemsReport({ success: false, issues: ['검사 요청 실패: ' + (error.response?.data?.detail || error.message)], steps: [] });
    } finally {
      setProblemsLoading(false);
    }
  }, [getEdges, getNodes, projectId]);

  const highlightOnboardingTarget = (selector) => {
    const target = [...document.querySelectorAll(selector)].find((element) => element.offsetParent !== null);
    if (!target) return;
    target.focus();
    target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
    target.classList.add('onboarding-target-pulse');
    window.setTimeout(() => target.classList.remove('onboarding-target-pulse'), 1600);
  };

  const handleOnboardingAction = (stepId) => {
    if (stepId === 'workflow_created') {
      setIsAssistantOpen(true);
      return;
    }
    if (stepId === 'node_configured') {
      const firstNode = getNodes()[0];
      if (!firstNode) return;
      setNodes((currentNodes) => currentNodes.map((node) => ({ ...node, selected: node.id === firstNode.id })));
      fitView({ nodes: [{ id: firstNode.id }], duration: 350, maxZoom: 1.1 });
      window.setTimeout(() => {
        const nodeElement = [...document.querySelectorAll('.react-flow__node')]
          .find((element) => element.dataset.id === firstNode.id);
        const nodeHeader = nodeElement?.querySelector('.node-header');
        if (nodeElement && !nodeElement.querySelector('.node-body')) nodeHeader?.click();
        nodeElement?.classList.add('onboarding-target-pulse');
        window.setTimeout(() => nodeElement?.classList.remove('onboarding-target-pulse'), 1600);
      }, 420);
      return;
    }
    if (stepId === 'workflow_tested') {
      // 실제 실행보다 목업을 먼저 제안한다 — API 키를 등록하지 않은 첫 사용자도 여기서는
      // 끝까지 돌려볼 수 있고, 토큰도 들지 않는다(로드맵 §4.5).
      setIsExecutionPanelOpen(true);
      setExecutionPanelTab('mock');
      highlightOnboardingTarget('[data-onboarding="run-mock"]');
      return;
    }
    if (stepId === 'workflow_saved') {
      highlightOnboardingTarget('[data-onboarding="save-workflow"]');
      return;
    }
    if (stepId === 'deploy_previewed') handleOpenDeployModal();
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
        edges: currentEdges.map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
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
    markNextHistory('템플릿 불러오기');
    setNodes(loadedNodes);
    setEdges(templateData.edges || []);
  };

  const getCurrentFlowData = () => {
    const snapshot = createEditorSnapshot(getNodes(), getEdges());
    return {
      title: projectTitle !== 'Untitled Project' ? projectTitle : '',
      description: projectDescription,
      nodes: snapshot.nodes,
      edges: snapshot.edges,
    };
  };

  const handleClearAllHighlights = () => {
    setNodes(nds => nds.map(nd => ({
      ...nd,
      data: { ...nd.data, isAIModified: false, aiChanges: null }
    })));
    // 실행 성공/실패 하이라이트도 같은 제스처로 걷는다 (실행 로그·결과 배지는 유지).
    setIsExecHighlightDismissed(true);
  };

  const handleCancelChat = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  // 히스토리에는 직렬화 가능한 그래프 데이터만 보관한다. 복원할 때 노드 UI가 사용하는 콜백을
  // 현재 렌더의 함수로 다시 주입해 stale closure와 함수 직렬화 문제를 피한다.
  const applyHistoryEntry = useCallback((entry) => {
    if (!entry?.snapshot) return;
    const restoredNodes = ensureMemoNodeDefaultsForList((entry.snapshot.nodes || []).map(n => ({
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
    })));
    nodesRef.current = restoredNodes;
    edgesRef.current = entry.snapshot.edges || [];
    setNodesState(restoredNodes);
    setEdgesState(entry.snapshot.edges || []);
  }, [deleteNode, onExpandChange, onNodeDataChange, setEdgesState, setNodes, setNodesState]);

  const handleUndo = useCallback(() => {
    flushHistoryCommit();
    const entry = undoEditorHistory();
    if (!entry) return;
    applyHistoryEntry(entry);
    setSystemLogs(prev => [...prev, `> ↩ ${entry.label || '이전 편집'} 상태로 되돌렸습니다.`]);
  }, [applyHistoryEntry, flushHistoryCommit, undoEditorHistory]);

  const handleRedo = useCallback(() => {
    flushHistoryCommit();
    const entry = redoEditorHistory();
    if (!entry) return;
    applyHistoryEntry(entry);
    setSystemLogs(prev => [...prev, `> ↪ ${entry.label || '다음 편집'} 상태를 다시 적용했습니다.`]);
  }, [applyHistoryEntry, flushHistoryCommit, redoEditorHistory]);

  const hydratePastedNode = useCallback((node) => ensureMemoNodeDefaults({
    ...node,
    data: {
      ...node.data,
      onChange: onNodeDataChange,
      onDelete: deleteNode,
      onExpandChange,
    },
  }), [deleteNode, onExpandChange, onNodeDataChange]);

  const copySelection = useCallback(async () => {
    const fragment = createClipboardFragment(nodesRef.current, edgesRef.current);
    if (!fragment.nodes.length) return null;
    sessionClipboardRef.current = fragment;
    pasteSequenceRef.current = 0;
    try {
      await navigator.clipboard?.writeText(serializeClipboardFragment(fragment));
    } catch (error) {
      console.info('System clipboard unavailable; using editor session clipboard.', error);
    }
    return fragment;
  }, []);

  const insertFragment = useCallback((fragment, label = '노드 붙여넣기') => {
    if (!fragment?.nodes?.length) return false;
    flushHistoryCommit();
    pasteSequenceRef.current += 1;
    const distance = 32 * pasteSequenceRef.current;
    const materialized = materializeClipboardFragment(fragment, { x: distance, y: distance });
    const pastedNodes = materialized.nodes.map(hydratePastedNode);
    const nextNodes = [
      ...nodesRef.current.map((node) => ({ ...node, selected: false })),
      ...pastedNodes,
    ];
    const nextEdges = [...edgesRef.current.map((edge) => ({ ...edge, selected: false })), ...materialized.edges];
    nodesRef.current = nextNodes;
    edgesRef.current = nextEdges;
    setNodesState(nextNodes);
    setEdgesState(nextEdges);
    commitEditorHistory(nextNodes, nextEdges, `${label} (${pastedNodes.length}개)`);
    return true;
  }, [commitEditorHistory, flushHistoryCommit, hydratePastedNode, setEdgesState, setNodesState]);

  // 노드를 Ctrl+C 하면 시스템 클립보드에 workflow-fragment JSON 이 들어간다. 그 상태로 노드 텍스트
  // 입력창에서 Ctrl+V 를 누르면 브라우저가 그 JSON 을 텍스트로 붙여 넣었고, 실행하면 JSON 이 결과로
  // 나왔다. 조각이면 텍스트 대신 캔버스에 노드로 붙인다 — 사용자가 복사한 것은 노드다.
  const handleNodeInputPaste = useCallback((event) => {
    if (!isEditableShortcutTarget(event.target)) return;
    const text = event.clipboardData?.getData('text/plain');
    const fragment = text ? parseClipboardFragment(text) : null;
    if (!fragment) return;
    event.preventDefault();
    insertFragment(fragment);
  }, [insertFragment]);

  const pasteSelection = useCallback(async () => {
    let fragment = null;
    try {
      const clipboardText = await navigator.clipboard?.readText();
      fragment = clipboardText ? parseClipboardFragment(clipboardText) : null;
    } catch (error) {
      console.info('System clipboard unavailable; using editor session clipboard.', error);
    }
    insertFragment(fragment || sessionClipboardRef.current);
  }, [insertFragment]);

  const duplicateSelection = useCallback(() => {
    const fragment = createClipboardFragment(nodesRef.current, edgesRef.current);
    if (!fragment.nodes.length) return;
    sessionClipboardRef.current = fragment;
    insertFragment(fragment, '노드 복제');
  }, [insertFragment]);

  const cutSelection = useCallback(async () => {
    const fragment = await copySelection();
    if (!fragment) return;
    flushHistoryCommit();
    const selectedIds = new Set(fragment.nodes.map((node) => String(node.id)));
    const nextNodes = nodesRef.current.filter((node) => !selectedIds.has(String(node.id)));
    const nextEdges = edgesRef.current.filter((edge) => (
      !selectedIds.has(String(edge.source)) && !selectedIds.has(String(edge.target))
    ));
    nodesRef.current = nextNodes;
    edgesRef.current = nextEdges;
    setNodesState(nextNodes);
    setEdgesState(nextEdges);
    commitEditorHistory(nextNodes, nextEdges, `노드 잘라내기 (${selectedIds.size}개)`);
  }, [commitEditorHistory, copySelection, flushHistoryCommit, setEdgesState, setNodesState]);

  const selectAllNodes = useCallback(() => {
    setNodesState((currentNodes) => {
      const nextNodes = currentNodes.map((node) => ({ ...node, selected: true }));
      nodesRef.current = nextNodes;
      return nextNodes;
    });
  }, [setNodesState]);

  const clearSelection = useCallback(() => {
    setNodesState((currentNodes) => {
      const nextNodes = currentNodes.map((node) => node.selected ? { ...node, selected: false } : node);
      nodesRef.current = nextNodes;
      return nextNodes;
    });
    setEdgesState((currentEdges) => {
      const nextEdges = currentEdges.map((edge) => edge.selected ? { ...edge, selected: false } : edge);
      edgesRef.current = nextEdges;
      return nextEdges;
    });
    setIsArrangeMenuOpen(false);
    setEditorContextMenu(null);
  }, [setEdgesState, setNodesState]);

  const deleteSelection = useCallback(() => {
    flushHistoryCommit();
    const selectedNodeIds = new Set(nodesRef.current.filter((node) => node.selected).map((node) => String(node.id)));
    const selectedEdgeIds = new Set(edgesRef.current.filter((edge) => edge.selected).map((edge) => String(edge.id)));
    if (!selectedNodeIds.size && !selectedEdgeIds.size) return;
    const nextNodes = nodesRef.current.filter((node) => !selectedNodeIds.has(String(node.id)));
    const nextEdges = edgesRef.current.filter((edge) => (
      !selectedEdgeIds.has(String(edge.id))
      && !selectedNodeIds.has(String(edge.source))
      && !selectedNodeIds.has(String(edge.target))
    ));
    nodesRef.current = nextNodes;
    edgesRef.current = nextEdges;
    setNodesState(nextNodes);
    setEdgesState(nextEdges);
    commitEditorHistory(nextNodes, nextEdges, `선택 항목 삭제 (${selectedNodeIds.size + selectedEdgeIds.size}개)`);
    setEditorContextMenu(null);
  }, [commitEditorHistory, flushHistoryCommit, setEdgesState, setNodesState]);

  const fitAllNodes = useCallback(() => {
    setEditorContextMenu(null);
    fitView({ duration: 320, padding: 0.18, maxZoom: 1.15 });
  }, [fitView]);

  const fitSelectedNodes = useCallback(() => {
    const selectedNodes = nodesRef.current.filter((node) => node.selected);
    if (!selectedNodes.length) return;
    setEditorContextMenu(null);
    fitView({
      nodes: selectedNodes.map((node) => ({ id: node.id })),
      duration: 320,
      padding: 0.28,
      maxZoom: 1.35,
    });
  }, [fitView]);

  const arrangeSelection = useCallback((arrangement, label) => {
    flushHistoryCommit();
    const nextNodes = arrangeSelectedNodes(nodesRef.current, arrangement);
    nodesRef.current = nextNodes;
    setNodesState(nextNodes);
    commitEditorHistory(nextNodes, edgesRef.current, label);
    setIsArrangeMenuOpen(false);
    setEditorContextMenu(null);
  }, [commitEditorHistory, flushHistoryCommit, setNodesState]);

  const autoLayoutGraph = useCallback(() => {
    flushHistoryCommit();
    const layouted = getLayoutedElements(nodesRef.current, edgesRef.current, 'LR');
    nodesRef.current = layouted.nodes;
    edgesRef.current = layouted.edges;
    setNodesState(layouted.nodes);
    setEdgesState(layouted.edges);
    commitEditorHistory(layouted.nodes, layouted.edges, '자동 정렬');
    setEditorContextMenu(null);
  }, [commitEditorHistory, flushHistoryCommit, setEdgesState, setNodesState]);

  const handleNodeDragStart = useCallback((event, node) => {
    if (!event.altKey || !isOwner) return;
    flushHistoryCommit();
    const sourceNodes = nodesRef.current.map((currentNode) => ({
      ...currentNode,
      selected: node.selected ? currentNode.selected : String(currentNode.id) === String(node.id),
    }));
    const fragment = createClipboardFragment(sourceNodes, edgesRef.current);
    if (!fragment.nodes.length) return;
    const materialized = materializeClipboardFragment(fragment, { x: 0, y: 0 });
    const duplicateNodes = materialized.nodes.map((duplicate) => ({
      ...hydratePastedNode(duplicate),
      selected: false,
    }));
    const nextNodes = [...nodesRef.current, ...duplicateNodes];
    const nextEdges = [...edgesRef.current, ...materialized.edges];
    nodesRef.current = nextNodes;
    edgesRef.current = nextEdges;
    setNodesState(nextNodes);
    setEdgesState(nextEdges);
    altDragDuplicateRef.current = true;
  }, [flushHistoryCommit, hydratePastedNode, isOwner, setEdgesState, setNodesState]);

  const openEditorContextMenu = useCallback((event, scope, payload = {}) => {
    event.preventDefault();
    event.stopPropagation();
    const width = 236;
    const estimatedHeight = scope === 'pane' ? 290 : scope === 'edge' ? 150 : 330;
    setEditorContextMenu({
      scope,
      ...payload,
      flowPosition: screenToFlowPosition({ x: event.clientX, y: event.clientY }),
      x: Math.max(8, Math.min(event.clientX, window.innerWidth - width - 8)),
      y: Math.max(8, Math.min(event.clientY, window.innerHeight - estimatedHeight - 8)),
    });
    setIsArrangeMenuOpen(false);
  }, [screenToFlowPosition]);

  const focusContextNode = useCallback((node) => {
    if (node.selected) return;
    setNodesState((currentNodes) => {
      const nextNodes = currentNodes.map((currentNode) => ({
        ...currentNode,
        selected: String(currentNode.id) === String(node.id),
      }));
      nodesRef.current = nextNodes;
      return nextNodes;
    });
    setEdgesState((currentEdges) => {
      const nextEdges = currentEdges.map((edge) => ({ ...edge, selected: false }));
      edgesRef.current = nextEdges;
      return nextEdges;
    });
  }, [setEdgesState, setNodesState]);

  const focusContextEdge = useCallback((edge) => {
    setNodesState((currentNodes) => {
      const nextNodes = currentNodes.map((node) => node.selected ? { ...node, selected: false } : node);
      nodesRef.current = nextNodes;
      return nextNodes;
    });
    setEdgesState((currentEdges) => {
      const nextEdges = currentEdges.map((currentEdge) => ({
        ...currentEdge,
        selected: String(currentEdge.id) === String(edge.id),
      }));
      edgesRef.current = nextEdges;
      return nextEdges;
    });
  }, [setEdgesState, setNodesState]);

  const fitContextEdge = useCallback(() => {
    if (!editorContextMenu?.edge) return;
    const edge = editorContextMenu.edge;
    fitView({
      nodes: [{ id: edge.source }, { id: edge.target }],
      duration: 320,
      padding: 0.4,
      maxZoom: 1.25,
    });
    setEditorContextMenu(null);
  }, [editorContextMenu, fitView]);

  const saveFromCommand = useCallback(() => {
    handleSave().then((saved) => {
      if (saved) setSystemLogs((previous) => [...previous, '> ✓ 워크플로우를 저장했습니다.']);
    });
  }, [handleSave]);

  const editorCommands = useMemo(() => createEditorCommandRegistry({
    undo: handleUndo,
    redo: handleRedo,
    save: saveFromCommand,
    copy: copySelection,
    cut: cutSelection,
    paste: pasteSelection,
    duplicate: duplicateSelection,
    selectAll: selectAllNodes,
    clearSelection,
    deleteSelection,
    fitAll: fitAllNodes,
    fitSelection: fitSelectedNodes,
    arrangeSelection,
    openCommandPalette: () => setIsCommandPaletteOpen(true),
    toggleDataLayer: () => setIsDataLayerOn((on) => !on),
    showShortcuts: () => setIsShortcutHelpOpen(true),
    testSelectedNode: () => {
      const target = editorSelection.nodes[0];
      if (!target) return;
      openInspector(target.id);
      runNodeMock(target.id, { only: true });
    },
  }), [arrangeSelection, clearSelection, copySelection, cutSelection, deleteSelection, duplicateSelection, editorSelection.nodes, fitAllNodes, fitSelectedNodes, handleRedo, handleUndo, openInspector, pasteSelection, runNodeMock, saveFromCommand, selectAllNodes]);

  const commandContext = useMemo(() => ({
    canUndo: canUndo || Boolean(pendingHistoryLabelRef.current),
    canRedo,
    hasSelection: editorSelection.count > 0,
    hasNodes: nodes.length > 0,
    selectedNodeCount: editorSelection.nodes.length,
    isOwner,
    isTextEditing: false,
  }), [canRedo, canUndo, editorSelection.count, editorSelection.nodes.length, isOwner, nodes.length]);

  const visiblePaletteCommands = useMemo(() => {
    const query = commandQuery.trim().toLocaleLowerCase('ko');
    const commands = editorCommands
      .filter((command) => command.id !== 'palette.open' && command.when(commandContext))
      .filter((command) => !query || `${command.label} ${command.category} ${command.id}`.toLocaleLowerCase('ko').includes(query));
    if (!isOwner) return commands;
    const knownNodeTypes = new Set(EDITOR_NODE_CATALOG.map((meta) => meta.type));
    const preferredTypes = [...new Set([...favoriteNodeTypes, ...recentNodeTypes])].filter((type) => knownNodeTypes.has(type));
    const nodePool = query
      ? EDITOR_NODE_CATALOG
      : preferredTypes.map((type) => getEditorNodeMeta(type)).slice(0, 8);
    const nodeCommands = nodePool
      .filter((meta) => !query || `${meta.label} ${meta.type} ${meta.categoryLabel}`.toLocaleLowerCase('ko').includes(query))
      .map((meta) => ({
        id: `node.add.${meta.type}`,
        label: `노드 추가: ${meta.label}`,
        category: `노드 · ${meta.categoryLabel}`,
        shortcuts: [],
        nodeType: meta.type,
        nodeMeta: meta,
      }));
    // Navigator(§8): 검색어가 있으면 캔버스의 기존 노드로 점프하는 항목을 함께 보여준다 —
    // 큰 그래프에서 라벨/타입으로 노드를 찾아 화면을 맞추는 용도.
    const jumpCommands = query
      ? nodes
          .map((node) => {
            const meta = getEditorNodeMeta(node.type);
            const label = node.data?.label && node.data.label !== `${node.type} node` ? node.data.label : meta.label;
            return { node, label };
          })
          .filter(({ node, label }) => `${label} ${node.type} ${node.id}`.toLocaleLowerCase('ko').includes(query))
          .slice(0, 12)
          .map(({ node, label }) => ({
            id: `node.goto.${node.id}`,
            label: `이동: ${label}`,
            category: '캔버스 노드',
            shortcuts: [],
            execute: () => focusNodeById(node.id),
          }))
      : [];
    return [...commands, ...nodeCommands, ...jumpCommands];
  }, [commandContext, commandQuery, editorCommands, favoriteNodeTypes, focusNodeById, isOwner, nodes, recentNodeTypes]);

  const executePaletteCommand = useCallback((command) => {
    if (!command) return;
    setIsCommandPaletteOpen(false);
    setCommandQuery('');
    if (command.nodeType) addNodeAtViewportCenter(command.nodeType);
    else command.execute();
  }, [addNodeAtViewportCenter]);

  const savedProjectMetadata = savedProjectMetadataRef.current;
  const isMetadataDirty = !savedProjectMetadata
    || savedProjectMetadata.title !== projectTitle
    || savedProjectMetadata.description !== projectDescription
    || savedProjectMetadata.visibility !== visibility;
  const isDirty = getEditorIsDirty(nodes, edges) || isMetadataDirty;

  useEffect(() => {
    const handleEditorShortcut = (event) => {
      if (event.isComposing || event.repeat) return;
      const isModK = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k';
      if (nodePicker) {
        if (event.key === 'Escape') {
          event.preventDefault();
          setNodePicker(null);
          setNodePickerQuery('');
        }
        return;
      }
      if (isCommandPaletteOpen) {
        if (event.key === 'Escape' || isModK) {
          event.preventDefault();
          setIsCommandPaletteOpen(false);
          setCommandQuery('');
        }
        return;
      }
      if (isShortcutHelpOpen && event.key === 'Escape') {
        event.preventDefault();
        setIsShortcutHelpOpen(false);
        return;
      }
      if ((editorContextMenu || isArrangeMenuOpen) && event.key === 'Escape') {
        event.preventDefault();
        setEditorContextMenu(null);
        setIsArrangeMenuOpen(false);
        return;
      }
      if (isTemplateModalOpen || isDeployModalOpen || isShortcutHelpOpen || pendingApproval) return;
      const context = {
        canUndo: canUndo || Boolean(pendingHistoryLabelRef.current),
        canRedo,
        hasSelection: nodesRef.current.some((node) => node.selected),
        hasNodes: nodesRef.current.length > 0,
        selectedNodeCount: nodesRef.current.filter((node) => node.selected).length,
        isOwner,
        isTextEditing: isEditableShortcutTarget(event.target),
      };
      const command = findCommandForKeyboardEvent(editorCommands, event, context);
      if (!command) return;
      event.preventDefault();
      command.execute();
    };
    document.addEventListener('keydown', handleEditorShortcut);
    return () => document.removeEventListener('keydown', handleEditorShortcut);
  }, [canRedo, canUndo, editorCommands, editorContextMenu, isArrangeMenuOpen, isCommandPaletteOpen, isDeployModalOpen, isOwner, isShortcutHelpOpen, isTemplateModalOpen, nodePicker, pendingApproval]);

  useEffect(() => {
    if (!isCommandPaletteOpen) return undefined;
    setCommandQuery('');
    setActiveCommandIndex(0);
    const frame = window.requestAnimationFrame(() => commandPaletteInputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [isCommandPaletteOpen]);

  useEffect(() => {
    if (!nodePicker) return undefined;
    setNodePickerQuery('');
    setActiveNodePickerIndex(0);
    const frame = window.requestAnimationFrame(() => nodePickerInputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [nodePicker]);

  useEffect(() => {
    setActiveNodePickerIndex(0);
  }, [nodePickerQuery]);

  useEffect(() => {
    if (activeNodePickerIndex < nodePickerCandidates.length) return;
    setActiveNodePickerIndex(Math.max(0, nodePickerCandidates.length - 1));
  }, [activeNodePickerIndex, nodePickerCandidates.length]);

  useEffect(() => {
    setActiveCommandIndex(0);
  }, [commandQuery]);

  useEffect(() => {
    if (activeCommandIndex < visiblePaletteCommands.length) return;
    setActiveCommandIndex(Math.max(0, visiblePaletteCommands.length - 1));
  }, [activeCommandIndex, visiblePaletteCommands.length]);

  useEffect(() => {
    if (!editorContextMenu) return undefined;
    const closeContextMenu = (event) => {
      if (event.type === 'pointerdown' && event.target.closest?.('.editor-context-menu')) return;
      setEditorContextMenu(null);
    };
    document.addEventListener('pointerdown', closeContextMenu);
    window.addEventListener('resize', closeContextMenu);
    window.addEventListener('scroll', closeContextMenu, true);
    return () => {
      document.removeEventListener('pointerdown', closeContextMenu);
      window.removeEventListener('resize', closeContextMenu);
      window.removeEventListener('scroll', closeContextMenu, true);
    };
  }, [editorContextMenu]);

  useEffect(() => {
    const warnAboutUnsavedChanges = (event) => {
      if (!isDirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnAboutUnsavedChanges);
    return () => window.removeEventListener('beforeunload', warnAboutUnsavedChanges);
  }, [isDirty]);

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

    // AI 하이라이트는 편집 데이터가 아니므로 새 요청 전에 지워도 통합 히스토리에는 기록되지 않는다.
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

      // 첨부한 대상이 있으면 함께 보낸다(백로그 28 POINT-1). 없으면 필드 자체를 넣지 않아
      // 예전과 똑같이 동작한다. `snapshotHash` 로 서버가 "지목 뒤 바뀌었는지" 를 판정한다.
      if (POINTING_ENABLED && pointedTargets.length > 0) {
        payload.pointing_context = {
          version: 1,
          scope: pointingScope,
          targets: await Promise.all(pointedTargets.map(async (t) => {
            const snapshot = targetSnapshot(t.kind, t.id);
            return {
              kind: t.kind, id: t.id, label: t.label,
              snapshotHash: snapshot ? await sha256Short(stableStringify(snapshot)) : undefined,
            };
          })),
        };
      }
      
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
        let finalNodes = ensureMemoNodeDefaultsForList(loadedNodes);
        let finalEdges = graph_data.edges || [];
        if (looksLikeUnlaidOutRow(finalNodes)) {
          const layouted = getLayoutedElements(finalNodes, graph_data.edges || [], 'LR');
          finalNodes = layouted.nodes;
          finalEdges = layouted.edges;
        }
        flushHistoryCommit();
        nodesRef.current = finalNodes;
        edgesRef.current = finalEdges;
        setNodesState(finalNodes);
        setEdgesState(finalEdges);
        commitEditorHistory(finalNodes, finalEdges, `AI 수정: ${userMessage}`);

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

      // 포인팅 실패는 사용자가 할 일이 정해져 있다 — 일반 오류 문구로 뭉뜽그리지 않는다.
      // 서버가 `{code, message, targets}` 를 준다(백로그 28 POINT-0).
      const pointing = error.response?.data?.detail;
      if (pointing && typeof pointing === 'object' && String(pointing.code || '').startsWith('POINTING_')) {
        if (pointing.code === 'POINTING_TARGET_NOT_FOUND') {
          // 없어진 대상만 걷어낸다. 다른 id 에 조용히 재연결하지 않는다.
          const gone = new Set(pointing.targets || []);
          setPointedTargets(prev => prev.filter(t => !gone.has(t.id)));
        }
        setChatMessages(prev => [...prev, { role: 'assistant', content: pointing.message }]);
        return;
      }

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

  const openFormatStudio = useCallback((nodeId = null, formatId = '') => {
    setFormatStudio({ isOpen: true, formatId: formatId || '', nodeId });
  }, []);

  // 포맷의 빈칸(이미지 제외)을 채우는 Structured Output llmNode 를 formatNode 앞에 삽입한다.
  // incoming 엣지가 있으면 그 사이에 끼우고(사이 삽입과 동일한 재배선), 없으면 앞에 두고 연결만 한다.
  const insertFillLLM = useCallback((formatNodeId, spec) => {
    const schema = formatFieldsSchema(spec);
    markNextHistory('빈칸 채우기 LLM 삽입');
    const targetNode = nodesRef.current.find((n) => String(n.id) === String(formatNodeId));
    if (!targetNode) return;
    const llmId = getEntityId('node');
    const llmNode = {
      id: llmId,
      type: 'llmNode',
      position: { x: (targetNode.position?.x || 0) - 470, y: targetNode.position?.y || 0 },
      data: {
        model: 'gpt-4o-mini',
        systemPrompt: `너는 문서 빈칸 채우기 도우미다. 입력 자료를 근거로 "${spec.name || '문서'}" 포맷의 빈칸을 채운 JSON 을 만든다. 자료에 없는 값은 지어내지 말고 빈 문자열로 둔다.`,
        useStructuredOutput: true,
        jsonSchema: JSON.stringify(schema, null, 2),
      },
    };
    setNodes((nds) => nds.concat(llmNode));
    setEdges((eds) => {
      const incoming = eds.find((e) => String(e.target) === String(formatNodeId) && (e.targetHandle == null || e.targetHandle === 'in'));
      let next = eds;
      if (incoming) {
        next = next.map((e) => (e === incoming ? { ...e, id: getEntityId('edge'), target: llmId, targetHandle: undefined } : e));
      }
      return next.concat({ id: getEntityId('edge'), source: llmId, target: formatNodeId, targetHandle: 'in' });
    });
  }, [markNextHistory, setEdges, setNodes]);

  // 경로 후보는 최근 실행 결과에서 뽑는다 — 실행 이력이 있으면 실제 값을 보고 고를 수 있다.
  const bindingResults = useMemo(() => {
    const map = {};
    (executionLogs || []).forEach((log) => {
      if (log?.node_id != null && log.result_data != null) map[String(log.node_id)] = log.result_data;
    });
    return map;
  }, [executionLogs]);

  const bindingContext = useMemo(() => ({
    // varName 은 변수 허브(§5-5)의 표시 이름 — 픽커·칩이 타입 라벨 대신 이 이름을 보여준다.
    nodes: nodes.map((node) => ({ id: node.id, type: node.type, varName: node.data?.varName })),
    edges: edges.map((edge) => ({ source: edge.source, target: edge.target })),
    results: bindingResults,
    onBind: applyBinding,
    dataLayer: isDataLayerOn,
  }), [nodes, edges, bindingResults, applyBinding, isDataLayerOn]);

  const enrichedNodes = useMemo(() => {
    return nodes.map(rawNode => {
      const n = ensureMemoNodeDefaults(rawNode);
      const log = executionLogs.find(l => String(l.node_id) === String(n.id));
      const visualStatus = executionNodeStates[String(n.id)] || (log?.status === 'error' ? 'error' : log ? 'success' : null);
      const pendingInputData = {};
      nodeInputCompositionRef.current.pending.forEach((change) => {
        if (String(change.id) === String(n.id)) pendingInputData[change.key] = change.value;
      });

      let nodeClass = (n.className || '').replace(/\bnode-(executing|success|error)\b/g, '').trim();
      if (visualStatus === 'running') {
        nodeClass = `${nodeClass} node-executing`.trim();
      } else if (visualStatus === 'success' && !isExecHighlightDismissed) {
        nodeClass = `${nodeClass} node-success`.trim();
      } else if (visualStatus === 'error' && !isExecHighlightDismissed) {
        nodeClass = `${nodeClass} node-error`.trim();
      }

      return {
        ...n,
        className: nodeClass,
        data: {
          ...n.data,
          ...pendingInputData,
          isTokenTrackingMode,
          predictedTokens: estimatedTokens?.node_details?.[n.id] || null,
          actualTokens: tokenUsage?.nodes?.[n.id] || null,
          tokenDisplayMode,
          costCurrency,
          isExecuting: visualStatus === 'running',
          executionStatus: visualStatus,
          // 결과 배지(§7.2) — 눌러서 Inspector 를 열고, 고정 출력이면 실행되지 않았음을 표시한다.
          isPinnedOutput: Boolean(pinnedOutputs[String(n.id)]),
          onInspect: openInspector,
          onMemoAutoResize: resizeMemoNodeToContent,
          onOpenFormatStudio: openFormatStudio,
          onInsertFillLLM: insertFillLLM,
          bindingContext,
          expandAllCommand
        }
      };
    });
  }, [nodes, isTokenTrackingMode, estimatedTokens, tokenUsage, tokenDisplayMode, costCurrency, executionLogs, executionNodeStates, isExecHighlightDismissed, expandAllCommand, openInspector, openFormatStudio, insertFillLLM, bindingContext, pinnedOutputs, resizeMemoNodeToContent]);

  // 실행 패널 탭 배지 — 로그 수, 문제 수(0이면 ✓), 평가 점수
  const executionTabBadge = (tabId) => {
    if (tabId === 'logs' && systemLogs.length > 0) return { text: systemLogs.length > 99 ? '99+' : systemLogs.length };
    if (tabId === 'problems' && problemsReport) {
      const count = (problemsReport.issues || []).length;
      return count ? { text: count, tone: 'danger' } : { text: '✓', tone: 'success' };
    }
    if (tabId === 'evaluation' && evaluationReport && typeof evaluationReport.score === 'number') {
      return { text: `${evaluationReport.score}점`, tone: scoreTone(evaluationReport.score, 80, 50) };
    }
    return null;
  };

  return (
    <div className="app-container tool-shell">
      <header className="header editor-header">
        <div className="editor-header-identity">
          <button className="editor-icon-button" onClick={() => navigate(-1)} title="뒤로가기" aria-label="뒤로가기">
            <ArrowLeft size={18} />
          </button>

          <div className="editor-project-control" ref={projectControlRef}>
            <button
              className="project-title-btn"
              onClick={() => {
                setIsDrawerOpen((open) => !open);
                setIsMobileToolsDrawerOpen(false);
              }}
              aria-expanded={isDrawerOpen}
            >
              <span className="editor-project-copy">
                <strong>{projectTitle || 'Untitled Project'}</strong>
                <small>{visibility === 'public' ? '공개' : visibility === 'friends' ? '친구 공개' : '비공개'}{isDirty ? ' · 저장 안 됨' : ' · 저장됨'}</small>
              </span>
              <Settings size={15} />
            </button>

            {isDrawerOpen && (
              <div className="editor-project-popover">
                <div className="editor-popover-heading">
                  <strong>프로젝트 설정</strong>
                  <span>이름과 설명을 관리합니다</span>
                </div>
                <label className="editor-field-label" htmlFor="editor-project-title">프로젝트 제목</label>
                <input
                  id="editor-project-title"
                  className="editor-field-input"
                  type="text"
                  value={projectTitle}
                  onChange={(e) => setProjectTitle(e.target.value)}
                  disabled={!isOwner}
                />
                <label className="editor-field-label" htmlFor="editor-project-description">프로젝트 설명</label>
                <textarea
                  id="editor-project-description"
                  className="editor-field-input editor-field-textarea"
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  disabled={!isOwner}
                  rows={4}
                  placeholder="워크플로우의 목적과 동작을 기록하세요."
                />
              </div>
            )}
          </div>
        </div>

        <div className="primary-action-container">
          {isOwner && (
            <div className="editor-history-controls">
              <button className="editor-icon-button" onClick={handleUndo} disabled={!canUndo && !pendingHistoryLabelRef.current} title={undoLabel ? `${undoLabel} 취소 (Ctrl/Cmd+Z)` : '되돌리기 (Ctrl/Cmd+Z)'} aria-label="되돌리기">
                <Undo2 size={17} />
              </button>
              <button className="editor-icon-button" onClick={handleRedo} disabled={!canRedo} title={redoLabel ? `${redoLabel} 다시 적용 (Ctrl/Cmd+Shift+Z)` : '다시 실행 (Ctrl/Cmd+Shift+Z)'} aria-label="다시 실행">
                <Redo2 size={17} />
              </button>
            </div>
          )}
          {isOwner && (
            <button
              className={`editor-icon-button ${isDirty ? 'editor-save-dirty' : ''}`}
              data-onboarding="save-workflow"
              onClick={() => { handleSave().then(s => s && alert('저장되었습니다.')); }}
              title={isDirty ? '저장되지 않은 변경사항 저장 (Ctrl/Cmd+S)' : '저장됨 (Ctrl/Cmd+S)'}
              aria-label={isDirty ? '저장되지 않은 변경사항 저장' : '저장됨'}
            >
              <Save size={17} />
            </button>
          )}
          <button
            className={`assistant-toggle-button ${isAssistantOpen ? 'active' : ''}`}
            data-tutorial="ai-assistant-btn"
            onClick={() => setIsAssistantOpen((open) => !open)}
            title="AI 워크플로우 어시스턴트"
            aria-label="AI 워크플로우 어시스턴트"
          >
            <Sparkles size={16} />
            <span className="assistant-toggle-label">AI 어시스턴트</span>
          </button>
          {/* 목업은 "실행 전에 확인하는 것"이라 실행 버튼 앞에 둔다. 예전에는 실행 패널이
              실행/평가 뒤에만 열려서, 실행을 대체하려고 만든 목업 탭에 실행 없이는 갈 수가
              없었다(ADR-0009). */}
          <button
            className="btn-mock"
            data-onboarding="run-mock"
            onClick={() => {
              setIsExecutionPanelOpen(true);
              setExecutionPanelTab('mock');
            }}
            title="API 키 없이 목업으로 실행해봅니다"
          >
            <FlaskConical size={17} />
            <span className="mock-text">목업</span>
          </button>
          <button className="btn-run" data-onboarding="run-workflow" onClick={runFlow} disabled={isLoading || isEvaluating}>
            <Play size={17} />
            <span className="run-text">{isLoading ? '실행 중...' : '실행'}</span>
          </button>

          <div className="editor-more-wrap" ref={editorToolsMenuRef}>
            <button
              className={`editor-icon-button ${isMobileToolsDrawerOpen ? 'active' : ''}`}
              data-tutorial="editor-more-btn"
              onClick={() => {
                setIsMobileToolsDrawerOpen((open) => !open);
                setIsDrawerOpen(false);
              }}
              title="더보기"
              aria-label="에디터 도구 더보기"
              aria-expanded={isMobileToolsDrawerOpen}
            >
              <MoreVertical size={19} />
            </button>

            {isMobileToolsDrawerOpen && (
              <div className="editor-more-menu" role="menu">
                <div className="editor-more-heading">
                  <div>
                    <strong>에디터 도구</strong>
                    <span>{nodes.length}개 노드 · {edges.length}개 연결</span>
                  </div>
                  <button className="editor-icon-button" onClick={() => setIsMobileToolsDrawerOpen(false)} aria-label="도구 메뉴 닫기">
                    <X size={17} />
                  </button>
                </div>

                <section className="editor-menu-section">
                  <div className="editor-menu-section-label">캔버스</div>
                  <button className="editor-menu-item" onClick={handleUndo} disabled={!canUndo && !pendingHistoryLabelRef.current}>
                    <Undo2 size={17} /><span><strong>되돌리기</strong><small>{undoLabel ? `${undoLabel} 취소` : '되돌릴 편집 없음'} · Ctrl/Cmd+Z</small></span>
                  </button>
                  <button className="editor-menu-item" onClick={handleRedo} disabled={!canRedo}>
                    <Redo2 size={17} /><span><strong>다시 실행</strong><small>{redoLabel ? `${redoLabel} 다시 적용` : '다시 적용할 편집 없음'} · Ctrl/Cmd+Shift+Z</small></span>
                  </button>
                  <button className="editor-menu-item" onClick={() => {
                    const layouted = getLayoutedElements(getNodes(), getEdges(), 'LR');
                    markNextHistory('자동 정렬');
                    setNodes([...layouted.nodes]);
                    setEdges([...layouted.edges]);
                    setIsMobileToolsDrawerOpen(false);
                  }}>
                    <Network size={17} /><span><strong>자동 정렬</strong><small>흐름을 왼쪽에서 오른쪽으로 배치</small></span>
                  </button>
                  <div className="editor-menu-inline-actions">
                    <button onClick={() => setExpandAllCommand({ action: 'expand', token: Date.now() })}><ChevronsDown size={16} /> 모두 펼치기</button>
                    <button onClick={() => setExpandAllCommand({ action: 'collapse', token: Date.now() })}><ChevronsUp size={16} /> 모두 접기</button>
                  </div>
                  <button className={`editor-menu-item ${isDataLayerOn ? 'is-active' : ''}`}
                          onClick={() => { setIsDataLayerOn((on) => !on); setIsMobileToolsDrawerOpen(false); }}>
                    <Zap size={17} /><span><strong>데이터 레이어 {isDataLayerOn ? '끄기' : '켜기'}</strong>
                      <small>필드 값 연결을 점선으로 보고 포트로 연결 · D</small></span>
                  </button>
                  <button className="editor-menu-item" onClick={() => { setIsTemplateModalOpen(true); setIsMobileToolsDrawerOpen(false); }}>
                    <Folder size={17} /><span><strong>템플릿</strong><small>준비된 워크플로우 불러오기</small></span>
                  </button>
                  <button className="editor-menu-item" onClick={() => { setIsShortcutHelpOpen(true); setIsMobileToolsDrawerOpen(false); }}>
                    <Keyboard size={17} /><span><strong>단축키</strong><small>현재 에디터 단축키 보기 · ?</small></span>
                  </button>
                  <button className="editor-menu-item" onClick={() => { setIsCommandPaletteOpen(true); setIsMobileToolsDrawerOpen(false); }}>
                    <Command size={17} /><span><strong>명령 팔레트</strong><small>사용 가능한 편집 명령 검색 · Ctrl/Cmd+K</small></span>
                  </button>
                  {currentId && (
                    <button className="editor-menu-item" onClick={() => navigate(`/project/${currentId}/runs`, { state: { fromEditor: true } })}>
                      <History size={17} /><span><strong>실행 기록</strong><small>이전 실행 결과와 상태 확인</small></span>
                    </button>
                  )}
                </section>

                <section className="editor-menu-section">
                  <div className="editor-menu-section-label">프로젝트</div>
                  {isOwner && (
                    <label className="editor-visibility-row">
                      <span><Share2 size={17} /><strong>공개 범위</strong></span>
                      <select
                        value={visibility}
                        onChange={(e) => {
                          const newVisibility = e.target.value;
                          setVisibility(newVisibility);
                          handleSave(newVisibility);
                        }}
                      >
                        <option value="private">비공개</option>
                        <option value="friends">친구 공개</option>
                        <option value="public">공개</option>
                      </select>
                    </label>
                  )}
                  {nodes.some(n => ['webhookNode', 'scheduleNode', 'discordNode'].includes(n.type)) && (
                    <button className={`editor-menu-item ${isLive ? 'danger' : ''}`} onClick={handleToggleLive}>
                      {isLive ? <Square size={17} fill="currentColor" /> : <Play size={17} />}
                      <span><strong>{isLive ? '라이브 중지' : '라이브 시작'}</strong><small>트리거 기반 자동 실행 제어</small></span>
                    </button>
                  )}
                  {isOwner && currentId && (
                    <button className="editor-menu-item" data-onboarding="deploy-workflow" onClick={() => { setIsMobileToolsDrawerOpen(false); handleOpenDeployModal(); }}>
                      <Wand2 size={17} /><span><strong>배포</strong><small>외부에서 사용할 실행 방식 설정</small></span>
                    </button>
                  )}
                </section>

                <section className="editor-menu-section" data-tutorial="quality-gate-group">
                  <div className="editor-menu-section-label">분석 및 품질</div>
                  <button className="editor-menu-item" onClick={() => { setIsMobileToolsDrawerOpen(false); openFormatStudio(); }}>
                    <LayoutTemplate size={17} /><span><strong>문서 포맷 스튜디오</strong><small>빈칸이 선언된 문서·포스터 포맷 제작</small></span>
                  </button>
                  <button className="editor-menu-item" onClick={async () => {
                    try {
                      const payload = {
                        nodes: nodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
                        edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target }))
                      };
                      const res = await axios.post('/api/estimate', payload);
                      if (res.data.status === 'success') {
                        setEstimatedTokens(res.data);
                        setIsTokenDrawerOpen(true);
                      } else {
                        alert(`${tokenDisplayMode === 'cost' ? '비용' : '토큰'} 계산 실패: ` + res.data.message);
                      }
                    } catch (error) {
                      console.error(error);
                      alert('예상 토큰 계산 중 오류가 발생했습니다.');
                    }
                  }}>
                    <BrainCircuit size={17} /><span><strong>사용량 계산</strong><small>예상 토큰과 마지막 실행 비교</small></span>
                  </button>
                  <button
                    className="editor-switch-row"
                    role="switch"
                    aria-checked={isTokenTrackingMode}
                    onClick={() => setIsTokenTrackingMode((enabled) => !enabled)}
                  >
                    <span><BrainCircuit size={17} /><strong>노드별 사용량 표시</strong></span>
                    <i className={isTokenTrackingMode ? 'active' : ''}><b /></i>
                  </button>
                  <button className="editor-menu-item" onClick={() => setIsTokenDrawerOpen((open) => !open)}>
                    <BrainCircuit size={17} /><span><strong>토큰 통계</strong><small>예상치와 실제 사용량 보기</small></span>
                  </button>
                  {isTokenDrawerOpen && (
                    <div className="editor-token-summary">
                      <div><span>1회 실행 예상</span><strong>{estimatedTokens ? `${formatTokenDisplay(estimatedTokens.total_estimated_tokens)} ~ ${formatTokenDisplay(estimatedTokens.total_max_tokens)}` : '-'}</strong></div>
                      <div><span>마지막 실제 사용량</span><strong>{tokenUsage ? formatTokenDisplay(tokenUsage.total_tokens) : '-'}</strong></div>
                    </div>
                  )}
                  <button className="editor-menu-item" onClick={evaluateFlow} disabled={isEvaluating || isLoading || isAutoImproving}>
                    <TestTube size={17} /><span><strong>{isEvaluating ? '평가 중...' : '워크플로우 평가'}</strong><small>실행 전 구성과 품질 검사</small></span>
                  </button>
                  <button className="editor-menu-item" onClick={autoImproveFlow} disabled={isEvaluating || isLoading || isAutoImproving}>
                    <Sparkles size={17} /><span><strong>{isAutoImproving ? '개선 중...' : 'AI 자동 개선'}</strong><small>평가 결과를 기준으로 흐름 보완</small></span>
                  </button>
                </section>
              </div>
            )}
          </div>
        </div>
      </header>

      <OnboardingChecklist onAction={handleOnboardingAction} />

      {isMobileToolsDrawerOpen && <div className="mobile-tools-overlay" onClick={() => setIsMobileToolsDrawerOpen(false)}></div>}

      {isShortcutHelpOpen && (
        <div className="editor-shortcut-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setIsShortcutHelpOpen(false);
        }}>
          <section className="editor-shortcut-dialog" role="dialog" aria-modal="true" aria-labelledby="editor-shortcut-title">
            <header>
              <div>
                <span className="editor-shortcut-eyebrow">EDITOR COMMANDS</span>
                <h2 id="editor-shortcut-title">에디터 단축키</h2>
                <p>입력 필드에서는 브라우저의 텍스트 편집 단축키가 우선합니다.</p>
              </div>
              <button className="editor-icon-button" onClick={() => setIsShortcutHelpOpen(false)} aria-label="단축키 도움말 닫기">
                <X size={18} />
              </button>
            </header>
            <div className="editor-shortcut-list">
              {editorCommands.filter((command) => command.shortcuts.length > 0).map((command) => (
                <div className="editor-shortcut-row" key={command.id}>
                  <span><small>{command.category}</small><strong>{command.label}</strong></span>
                  <div>{command.shortcuts.map((shortcut, index) => (
                    <span key={`${command.id}-${index}`}>
                      {index > 0 && <em>또는</em>}
                      <kbd>{formatEditorShortcut(shortcut)}</kbd>
                    </span>
                  ))}</div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {isCommandPaletteOpen && (
        <div className="editor-command-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setIsCommandPaletteOpen(false);
        }}>
          <section className="editor-command-dialog" role="dialog" aria-modal="true" aria-label="명령 팔레트">
            <div className="editor-command-search">
              <Search size={18} aria-hidden="true" />
              <input
                ref={commandPaletteInputRef}
                value={commandQuery}
                onChange={(event) => setCommandQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowDown' && visiblePaletteCommands.length) {
                    event.preventDefault();
                    setActiveCommandIndex((index) => (index + 1) % visiblePaletteCommands.length);
                  } else if (event.key === 'ArrowUp' && visiblePaletteCommands.length) {
                    event.preventDefault();
                    setActiveCommandIndex((index) => (index - 1 + visiblePaletteCommands.length) % visiblePaletteCommands.length);
                  } else if (event.key === 'Enter') {
                    event.preventDefault();
                    executePaletteCommand(visiblePaletteCommands[activeCommandIndex]);
                  } else if (event.key === 'Escape') {
                    event.preventDefault();
                    event.stopPropagation();
                    setIsCommandPaletteOpen(false);
                  }
                }}
                placeholder="명령 검색…"
                aria-label="명령 검색"
                aria-controls="editor-command-results"
              />
              <kbd>Esc</kbd>
            </div>
            <div className="editor-command-results" id="editor-command-results" role="listbox">
              {visiblePaletteCommands.length ? visiblePaletteCommands.map((command, index) => (
                <button
                  key={command.id}
                  className={index === activeCommandIndex ? 'active' : ''}
                  onMouseEnter={() => setActiveCommandIndex(index)}
                  onClick={() => executePaletteCommand(command)}
                  role="option"
                  aria-selected={index === activeCommandIndex}
                >
                  <span className="editor-command-icon" style={command.nodeMeta ? { color: command.nodeMeta.color } : undefined}>
                    {command.nodeMeta ? command.nodeMeta.label.slice(0, 1) : <Command size={16} />}
                  </span>
                  <span><strong>{command.label}</strong><small>{command.category}</small></span>
                  {command.shortcuts.length > 0 && <kbd>{formatEditorShortcut(command.shortcuts[0])}</kbd>}
                  {index === activeCommandIndex && <Check className="editor-command-check" size={15} />}
                </button>
              )) : (
                <div className="editor-command-empty">“{commandQuery}”에 해당하는 명령이 없습니다.</div>
              )}
            </div>
            <footer>↑↓ 이동 · Enter 실행 · 선택 상태에 맞는 명령만 표시됩니다.</footer>
          </section>
        </div>
      )}

      {nodePicker && (
        <div className="editor-node-picker-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setNodePicker(null);
        }}>
          <section
            className="editor-node-picker"
            style={{ left: nodePicker.x, top: nodePicker.y }}
            role="dialog"
            aria-modal="true"
            aria-label="노드 선택"
          >
            <header>
              <div>
                <strong>{nodePicker.mode === 'connect' ? '연결할 노드 추가' : nodePicker.mode === 'insert' ? '연결선에 노드 삽입' : nodePicker.mode === 'replace' ? '노드 교체' : '노드 빠른 추가'}</strong>
                <small>{nodePicker.mode === 'replace' ? '같은 역할의 노드만 표시합니다' : '검색 후 Enter로 바로 배치합니다'}</small>
              </div>
              <button onClick={() => setNodePicker(null)} aria-label="노드 선택기 닫기"><X size={16} /></button>
            </header>
            <div className="editor-node-picker-search">
              <Search size={16} />
              <input
                ref={nodePickerInputRef}
                value={nodePickerQuery}
                onChange={(event) => setNodePickerQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowDown' && nodePickerCandidates.length) {
                    event.preventDefault();
                    setActiveNodePickerIndex((index) => (index + 1) % nodePickerCandidates.length);
                  } else if (event.key === 'ArrowUp' && nodePickerCandidates.length) {
                    event.preventDefault();
                    setActiveNodePickerIndex((index) => (index - 1 + nodePickerCandidates.length) % nodePickerCandidates.length);
                  } else if (event.key === 'Enter') {
                    event.preventDefault();
                    applyNodePickerSelection(nodePickerCandidates[activeNodePickerIndex]?.type);
                  } else if (event.key === 'Escape') {
                    event.preventDefault();
                    event.stopPropagation();
                    setNodePicker(null);
                  }
                }}
                placeholder="노드 이름 또는 유형 검색…"
                aria-label="노드 검색"
              />
            </div>
            {!nodePickerQuery && (favoriteNodeTypes.length > 0 || recentNodeTypes.length > 0) && (
              <div className="editor-node-picker-hint">
                {favoriteNodeTypes.length > 0 && <span><Star size={11} fill="currentColor" /> 즐겨찾기 우선</span>}
                {recentNodeTypes.length > 0 && <span>최근 사용 순</span>}
              </div>
            )}
            <div className="editor-node-picker-results" role="listbox">
              {nodePickerCandidates.length ? nodePickerCandidates.map((meta, index) => (
                <div
                  key={meta.type}
                  className={index === activeNodePickerIndex ? 'active' : ''}
                  onMouseEnter={() => setActiveNodePickerIndex(index)}
                  role="option"
                  aria-selected={index === activeNodePickerIndex}
                >
                  <button className="editor-node-picker-choice" onClick={() => applyNodePickerSelection(meta.type)}>
                    <i style={{ '--node-color': meta.color }}>{meta.label.slice(0, 1)}</i>
                    <span><strong>{meta.label}</strong><small>{meta.categoryLabel} · {meta.type}</small></span>
                    {recentNodeTypes.includes(meta.type) && <em>최근</em>}
                  </button>
                  <button
                    className={`editor-node-favorite ${favoriteNodeTypes.includes(meta.type) ? 'active' : ''}`}
                    onClick={() => toggleFavoriteNodeType(meta.type)}
                    aria-label={`${meta.label} ${favoriteNodeTypes.includes(meta.type) ? '즐겨찾기 해제' : '즐겨찾기 추가'}`}
                    title={favoriteNodeTypes.includes(meta.type) ? '즐겨찾기 해제' : '즐겨찾기 추가'}
                  ><Star size={14} fill={favoriteNodeTypes.includes(meta.type) ? 'currentColor' : 'none'} /></button>
                </div>
              )) : (
                <div className="editor-node-picker-empty">
                  <Search size={20} />
                  <span>{nodePicker.mode === 'replace' ? '교체 가능한 같은 역할의 노드가 없습니다.' : '검색 결과가 없습니다.'}</span>
                </div>
              )}
            </div>
            <footer>↑↓ 이동 · Enter 선택 · 별표로 즐겨찾기</footer>
          </section>
        </div>
      )}

      {editorSelection.nodes.length > 0 && !isCommandPaletteOpen && !isShortcutHelpOpen && !nodePicker && (
        <div
          className="editor-selection-toolbar"
          style={selectionToolbarStyle}
          role="toolbar"
          aria-label={`${editorSelection.nodes.length}개 선택 항목 도구`}
        >
          <span className="editor-selection-count">{editorSelection.nodes.length}<small>선택</small></span>
          <i />
          <button onClick={copySelection} title="복사 (Ctrl/Cmd+C)" aria-label="선택 노드 복사"><Copy size={16} /></button>
          {isOwner && <button onClick={cutSelection} title="잘라내기 (Ctrl/Cmd+X)" aria-label="선택 노드 잘라내기"><Scissors size={16} /></button>}
          {isOwner && <button onClick={duplicateSelection} title="복제 (Ctrl/Cmd+D)" aria-label="선택 노드 복제"><ClipboardPaste size={16} /></button>}
          {editorSelection.nodes.length >= 2 && (
            <div className="editor-arrange-wrap">
              <button
                className={isArrangeMenuOpen ? 'active' : ''}
                onClick={() => setIsArrangeMenuOpen((open) => !open)}
                title="정렬 및 간격"
                aria-label="정렬 및 간격 메뉴"
                aria-expanded={isArrangeMenuOpen}
              ><AlignHorizontalDistributeCenter size={16} /></button>
              {isArrangeMenuOpen && (
                <div className="editor-arrange-popover">
                  <strong>정렬 및 간격</strong>
                  <div>
                    {ARRANGEMENT_OPTIONS.map((option) => (
                      <button
                        key={option.id}
                        disabled={editorSelection.nodes.length < (option.minimum || 2) || !isOwner}
                        onClick={() => arrangeSelection(option.id, option.label)}
                      >{option.label}</button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <button onClick={fitSelectedNodes} title="선택 영역 화면 맞춤 (Shift+2)" aria-label="선택 영역 화면 맞춤"><Maximize2 size={16} /></button>
          {/* 선택만으로 자동 첨부하지 않는다 — 속성을 보려고 클릭한 것이 AI 편집 권한이 되면 안 된다. */}
          {POINTING_ENABLED && isOwner && (
            <button
              className="editor-selection-attach"
              onClick={attachSelectionToAI}
              title="AI에 첨부 (선택한 항목만 수정하도록 지목)"
              aria-label="선택 항목을 AI에 첨부"
            ><Sparkles size={16} /></button>
          )}
          {isOwner && <><i /><button className="danger" onClick={deleteSelection} title="선택 항목 삭제" aria-label="선택 항목 삭제"><Trash2 size={16} /></button></>}
        </div>
      )}

      {editorContextMenu && (
        <div className="editor-context-menu" style={{ left: editorContextMenu.x, top: editorContextMenu.y }} role="menu">
          <div className="editor-context-heading">
            {editorContextMenu.scope === 'pane' ? '캔버스' : editorContextMenu.scope === 'edge' ? '연결선' : `${editorSelection.nodes.length}개 노드 선택`}
          </div>
          {(editorContextMenu.scope === 'node' || editorContextMenu.scope === 'selection') && (
            <>
              <button onClick={() => { copySelection(); setEditorContextMenu(null); }}><Copy size={15} /><span>복사</span><kbd>⌘/Ctrl+C</kbd></button>
              {isOwner && <button onClick={() => { cutSelection(); setEditorContextMenu(null); }}><Scissors size={15} /><span>잘라내기</span><kbd>⌘/Ctrl+X</kbd></button>}
              {isOwner && <button onClick={() => { duplicateSelection(); setEditorContextMenu(null); }}><ClipboardPaste size={15} /><span>복제</span><kbd>⌘/Ctrl+D</kbd></button>}
              {isOwner && editorContextMenu.scope === 'node' && editorSelection.nodes.length === 1 && getReplacementCandidates(editorSelection.nodes[0].type).length > 0 && (
                <button onClick={() => openNodeTypePicker({
                  mode: 'replace',
                clientX: editorContextMenu.x,
                clientY: editorContextMenu.y,
                flowPosition: editorContextMenu.flowPosition,
                node: editorSelection.nodes[0],
                })}><Replace size={15} /><span>노드 교체</span></button>
              )}
              {editorContextMenu.scope === 'node' && editorContextMenu.node && editorContextMenu.node.type !== 'memoNode' && (
                <>
                  <button onClick={() => openInspector(editorContextMenu.node.id)}><TerminalSquare size={15} /><span>노드 검사 (입출력)</span></button>
                  {/* 범위 실행(§7.4). 목업이 먼저 오는 것은 "기본은 mock" 이라는 §7.1 원칙이다. */}
                  {isOwner && <button onClick={() => runNodeMock(editorContextMenu.node.id, { only: true })}><FlaskConical size={15} /><span>이 노드만 목업 실행</span></button>}
                  {isOwner && <button onClick={() => runNodeMock(editorContextMenu.node.id, { only: false })}><FlaskConical size={15} /><span>여기부터 목업 실행</span></button>}
                  {isOwner && <button onClick={() => runUpToNode(editorContextMenu.node.id)}><Play size={15} /><span>여기까지 실제 실행</span></button>}
                  {isOwner && <button onClick={() => runFromNode(editorContextMenu.node.id)}><Play size={15} /><span>이 노드부터 실제 실행</span></button>}
                  {isOwner && <button onClick={() => toggleNodeLock(editorContextMenu.node.id)}>{editorContextMenu.node.draggable === false ? <Unlock size={15} /> : <Lock size={15} />}<span>{editorContextMenu.node.draggable === false ? '위치 잠금 해제' : '위치 잠금'}</span></button>}
                </>
              )}
              <button onClick={fitSelectedNodes}><Maximize2 size={15} /><span>선택 영역 맞춤</span><kbd>Shift+2</kbd></button>
              {/* 선택 branch 실행(§7.4) — 선택한 노드들만 목업으로 돌린다. */}
              {isOwner && editorSelection.nodes.length > 1 && (
                <button onClick={() => runSelectionMock()}><FlaskConical size={15} /><span>선택 영역만 목업 실행</span></button>
              )}
              {editorSelection.nodes.length >= 2 && (
                <div className="editor-context-arrange">
                  <small>정렬</small>
                  <div>
                    {ARRANGEMENT_OPTIONS.map((option) => (
                      <button
                        key={option.id}
                        disabled={editorSelection.nodes.length < (option.minimum || 2) || !isOwner}
                        onClick={() => arrangeSelection(option.id, option.label)}
                        title={option.label}
                      >{option.id.includes('horizontal') ? <AlignHorizontalDistributeCenter size={15} /> : option.id.includes('vertical') ? <AlignVerticalDistributeCenter size={15} /> : option.id.includes('left') || option.id.includes('right') ? <AlignStartVertical size={15} /> : <AlignStartHorizontal size={15} />}</button>
                    ))}
                  </div>
                </div>
              )}
              {isOwner && <button className="danger" onClick={deleteSelection}><Trash2 size={15} /><span>삭제</span></button>}
            </>
          )}
          {editorContextMenu.scope === 'edge' && (
            <>
              <button onClick={fitContextEdge}><Maximize2 size={15} /><span>연결 양 끝 보기</span></button>
              {isOwner && <button onClick={() => openNodeTypePicker({
                mode: 'insert',
                clientX: editorContextMenu.x,
                clientY: editorContextMenu.y,
                flowPosition: editorContextMenu.flowPosition,
                edge: editorContextMenu.edge,
              })}><CornerDownRight size={15} /><span>중간에 노드 삽입</span></button>}
              {isOwner && <button className="danger" onClick={() => {
                markNextHistory('연결 삭제');
                setEdges((currentEdges) => currentEdges.filter((edge) => String(edge.id) !== String(editorContextMenu.edge.id)));
                setEditorContextMenu(null);
              }}><Trash2 size={15} /><span>연결 삭제</span></button>}
            </>
          )}
          {editorContextMenu.scope === 'pane' && (
            <>
              {isOwner && <button onClick={() => openNodeTypePicker({
                mode: 'add',
                clientX: editorContextMenu.x,
                clientY: editorContextMenu.y,
                flowPosition: editorContextMenu.flowPosition,
              })}><Plus size={15} /><span>노드 추가</span><kbd>더블클릭</kbd></button>}
              {isOwner && <button onClick={() => addMemoAtPosition(editorContextMenu.flowPosition)}><Plus size={15} /><span>메모 추가</span></button>}
              {isOwner && <button onClick={() => { pasteSelection(); setEditorContextMenu(null); }}><ClipboardPaste size={15} /><span>붙여넣기</span><kbd>⌘/Ctrl+V</kbd></button>}
              <button onClick={() => { selectAllNodes(); setEditorContextMenu(null); }}><Copy size={15} /><span>모두 선택</span><kbd>⌘/Ctrl+A</kbd></button>
              <button onClick={fitAllNodes}><Maximize2 size={15} /><span>전체 화면 맞춤</span><kbd>Shift+1</kbd></button>
              {isOwner && <button onClick={autoLayoutGraph}><Network size={15} /><span>자동 정렬</span></button>}
              <button onClick={() => { setIsCommandPaletteOpen(true); setEditorContextMenu(null); }}><Command size={15} /><span>명령 팔레트</span><kbd>⌘/Ctrl+K</kbd></button>
              <button onClick={() => { setIsShortcutHelpOpen(true); setEditorContextMenu(null); }}><Keyboard size={15} /><span>단축키 도움말</span><kbd>?</kbd></button>
            </>
          )}
        </div>
      )}

      <main className="main-content">
        <Sidebar isMobileOpen={isPaletteOpen} onClose={() => setIsPaletteOpen(false)} onNodeTap={handleNodeTap} />
        <div
          className="flow-wrapper"
          ref={reactFlowWrapper}
          onCompositionStartCapture={handleNodeCompositionStart}
          onCompositionEndCapture={handleNodeCompositionEnd}
          onBlurCapture={handleNodeInputBlur}
          onKeyDownCapture={handleNodeInputKeyDown}
          onPasteCapture={handleNodeInputPaste}
        >
          <button className="mobile-palette-toggle" onClick={() => setIsPaletteOpen(true)} title="노드 팔레트 열기">
            <Plus size={24} />
          </button>
          <ReactFlow
            nodes={enrichedNodes}
            edges={edges.map(e => ({
              ...e,
              animated: executionNodeStates[String(e.source)] === 'running' || executionNodeStates[String(e.target)] === 'running' || e.animated,
              // 실행 중/성공 색은 토큰으로. 기본 상태는 stroke 를 주지 않고 CSS(--ts-edge)에 맡긴다 —
              // 라이트 테마에서도 연결선이 보이도록.
              style: {
                ...e.style,
                stroke: executionNodeStates[String(e.source)] === 'running' || executionNodeStates[String(e.target)] === 'running'
                  ? 'var(--ts-accent)'
                  : !isExecHighlightDismissed && executionNodeStates[String(e.source)] === 'success' && executionNodeStates[String(e.target)] === 'success'
                    ? 'var(--ts-success)'
                    : e.style?.stroke
              }
            }))}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeContextMenu={(event, node) => {
              focusContextNode(node);
              openEditorContextMenu(event, 'node', { node });
            }}
            onSelectionContextMenu={(event) => openEditorContextMenu(event, 'selection')}
            onEdgeContextMenu={(event, edge) => {
              focusContextEdge(edge);
              openEditorContextMenu(event, 'edge', { edge });
            }}
            onPaneContextMenu={(event) => {
              clearSelection();
              openEditorContextMenu(event, 'pane');
            }}
            onConnect={onConnect}
            onConnectStart={handleConnectStart}
            onConnectEnd={handleConnectEnd}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeDragStart={handleNodeDragStart}
            onNodeDragStop={onNodeDragStop}
            onPaneClick={(event) => {
              setEditorContextMenu(null);
              setIsArrangeMenuOpen(false);
              handleClearAllHighlights();
              if (event.detail === 2 && isOwner) {
                openNodeTypePicker({
                  mode: 'add',
                  clientX: event.clientX,
                  clientY: event.clientY,
                });
              }
            }}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={{
              style: { strokeWidth: 2.5 },
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
          >
            {window.innerWidth > 768 && <Controls />}
            {window.innerWidth > 768 && (
              <MiniMap
                nodeColor={(node) => getEditorNodeMeta(node.type).color}
                maskColor="var(--ts-minimap-mask)"
                bgColor="var(--ts-surface-2)"
                pannable
                zoomable
              />
            )}
            <DataLayerOverlay nodes={enrichedNodes} enabled={isDataLayerOn} />
            <Background variant="dots" gap={24} size={2} color="var(--ts-grid-dot)" />
          </ReactFlow>
        </div>

        <AIAssistantDrawer
          isOpen={isAssistantOpen}
          title="워크플로우 AI"
          description="현재 캔버스를 분석하고 수정합니다"
          contextLabel={`${nodes.length}개 노드 · ${edges.length}개 연결`}
          messages={chatMessages}
          input={chatInput}
          onInputChange={setChatInput}
          onSend={handleSendChat}
          onCancel={handleCancelChat}
          onClose={() => setIsAssistantOpen(false)}
          isLoading={isChatLoading}
          loadingLabel={chatStage}
          sendDisabled={!chatInput.trim() || isChatLoading}
          placeholder="추가하거나 수정할 워크플로우를 설명하세요..."
          suggestions={['이 흐름을 설명해줘', '오류 처리 단계를 추가해줘', '노드 구성을 더 단순하게 정리해줘']}
          onSuggestion={setChatInput}
          mentions={!POINTING_ENABLED ? [] : pointedStatus.map((t) => ({
            key: `${t.kind}:${t.id}`, label: t.label, missing: t.missing, kind: t.kind, id: t.id,
          }))}
          onRemoveMention={(m) => detachTarget(m.kind, m.id)}
          controls={(
            <>
            {/* 지목한 대상의 **핸들은 입력란 안**에 있다(mentions prop).
                여기에는 편집 범위만 둔다 — 첨부한 것이 없으면 범위도 물을 이유가 없다. */}
            {POINTING_ENABLED && pointedStatus.length > 0 && (
              <div className="assistant-pointing">
                <div className="assistant-control-row">
                  <span className="assistant-control-label">편집 범위</span>
                  <div className="assistant-segmented" role="group" aria-label="편집 범위">
                    {[
                      { id: 'target_only', label: '선택 항목만' },
                      { id: 'target_and_neighbors', label: '연결 항목 포함' },
                      { id: 'whole_canvas', label: '전체 캔버스' },
                    ].map((option) => (
                      <button
                        key={option.id}
                        type="button"
                        className={pointingScope === option.id ? 'active' : ''}
                        onClick={() => setPointingScope(option.id)}
                        aria-pressed={pointingScope === option.id}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
                {pointingScope === 'whole_canvas' && (
                  <p className="assistant-pointing-warn">
                    전체 캔버스를 열어 두면 지목하지 않은 노드도 바뀔 수 있습니다.
                  </p>
                )}
              </div>
            )}
            <div className="assistant-control-row">
              <span className="assistant-control-label">생성 깊이</span>
              <div className="assistant-segmented" role="group" aria-label="생성 깊이">
                {[
                  { id: 'low', label: '빠름' },
                  { id: 'medium', label: '확장' },
                  { id: 'high', label: '정밀' },
                ].map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={complexityLevel === option.id ? 'active' : ''}
                    onClick={() => setComplexityLevel(option.id)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            </>
          )}
        />


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

      {/* Unified Execution Panel — 탭은 중립색 + 활성 Blue, 상태는 배지로만(디자인 계획 §5.6) */}
      {isExecutionPanelOpen && (
        <section className="editor-execution-panel" style={{ height: `${executionPanelHeight}px` }} aria-label="실행 패널">
          <div
            className="editor-execution-resizer"
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
            <span />
          </div>

          <div className="editor-execution-header">
            <div className="editor-execution-tabs" role="tablist" aria-label="실행 패널 탭">
              {EXECUTION_TABS.map((tab) => {
                const TabIcon = tab.icon;
                const badge = executionTabBadge(tab.id);
                const selected = executionPanelTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    role="tab"
                    aria-selected={selected}
                    className={selected ? 'active' : ''}
                    onClick={() => {
                      setExecutionPanelTab(tab.id);
                      if (tab.id === 'problems' && !problemsReport) runProblemsCheck();
                    }}
                  >
                    <TabIcon size={15} />
                    {tab.label}
                    {badge && <span className={`exec-tab-badge ${badge.tone || ''}`}>{badge.text}</span>}
                  </button>
                );
              })}
            </div>
            <div className="editor-execution-actions">
              <button className="editor-icon-button" onClick={() => setIsExecutionPanelOpen(false)} title="닫기" aria-label="실행 패널 닫기">
                <X size={17} />
              </button>
            </div>
          </div>

          <div className="editor-execution-body">
            {executionPanelTab === 'inspect' && (() => {
              const inspected = nodes.find((node) => String(node.id) === String(inspectorNodeId))
                || editorSelection.nodes[0] || null;
              if (!inspected) {
                return <div className="exec-empty center">노드를 선택하거나, 노드 우클릭 → &quot;노드 검사&quot;로 열어주세요.</div>;
              }
              const logByNode = new Map((executionLogs || []).map((step) => [String(step.node_id), step]));
              const incomingSources = edges
                .filter((edge) => String(edge.target) === String(inspected.id))
                .map((edge) => String(edge.source));
              const fixture = readPinnedOutput(projectId, inspected.id);
              return (
                <NodeInspector
                  node={inspected}
                  meta={getEditorNodeMeta(inspected.type)}
                  ownLog={logByNode.get(String(inspected.id))}
                  inputs={incomingSources.map((sourceId) => ({ sourceId, log: logByNode.get(sourceId) }))}
                  isOwner={isOwner}
                  writesExternally={nodeWritesExternally(inspected, getNodeDefinition(inspected.type))}
                  nodeErrorV1={nodeErrorV1}
                  sampleInput={readSampleInput(inspected.id)}
                  onSampleInputChange={writeSampleInput}
                  pinnedFixture={fixture}
                  pinnedStale={isPinnedOutputStale(fixture, inspected)}
                  onPinOutput={(node) => pinOutput(node, logByNode.get(String(node.id))?.result_data || '')}
                  onUnpinOutput={unpinOutput}
                  onFocusNode={focusNodeById}
                  onFocusField={focusErrorField}
                  onNavigate={navigate}
                  onMockRun={runNodeMock}
                  onRealRun={runFromNode}
                  onRunUpTo={runUpToNode}
                  onReplayLast={replayNodeWithLastInput}
                  busy={isLoading}
                />
              );
            })()}

            {executionPanelTab === 'problems' && (() => {
              const issues = problemsReport?.issues || [];
              const riskySteps = (problemsReport?.steps || []).filter((step) => step.status !== 'simulated');
              return (
                <div className="exec-section">
                  <div className="exec-row">
                    <span className="exec-hint">실행 없이 스키마·구조·컴파일을 검사합니다. 외부 발송·결제 같은 위험 노드는 차단 표시됩니다.</span>
                    <button type="button" className="btn-secondary exec-btn" onClick={runProblemsCheck} disabled={problemsLoading}>
                      {problemsLoading ? '검사 중...' : '다시 검사'}
                    </button>
                  </div>
                  {!problemsReport && !problemsLoading && <p className="exec-empty">검사를 실행해 주세요.</p>}
                  {problemsReport && (
                    <>
                      <div className={`exec-status ${issues.length ? 'danger' : 'success'}`}>
                        {issues.length ? `문제 ${issues.length}건` : '발견된 문제 없음'}
                      </div>
                      {issues.map((issue, index) => {
                        const nodeIdMatch = String(issue).match(/^([A-Za-z0-9_-]+)\(/);
                        return (
                          <div
                            key={index}
                            className={`exec-card danger ${nodeIdMatch ? 'clickable' : ''}`}
                            onClick={() => nodeIdMatch && focusNodeById(nodeIdMatch[1])}
                            role={nodeIdMatch ? 'button' : undefined}
                            tabIndex={nodeIdMatch ? 0 : undefined}
                          >
                            {String(issue)}
                          </div>
                        );
                      })}
                      {riskySteps.length > 0 && (
                        <>
                          <div className="exec-subtitle">실행 시 주의가 필요한 노드</div>
                          {riskySteps.map((step) => (
                            <div key={step.node_id} className="exec-card clickable exec-step" onClick={() => focusNodeById(step.node_id)} role="button" tabIndex={0}>
                              <span>{step.node_id} <span className="muted">({step.node_type})</span></span>
                              <span className={`exec-badge ${step.status === 'error' ? 'danger' : 'warning'}`}>{step.detail || step.status}</span>
                            </div>
                          ))}
                        </>
                      )}
                    </>
                  )}
                </div>
              );
            })()}

            {executionPanelTab === 'mock' && (
              <MockPanel
                projectId={currentId}
                authHeaders={getAuthHeaders}
                getGraphData={getCurrentFlowData}
                onRunSucceeded={() => completeOnboardingStep('workflow_tested')}
              />
            )}

            {executionPanelTab === 'result' && (
              <div className="exec-section exec-fill">
                {isTokenTrackingMode && tokenUsage && (
                  <div className="exec-card info">
                    <strong>{tokenDisplayMode === 'cost' ? '소모 비용' : '토큰 사용량'}</strong>
                    <div className="exec-kv">
                      <span>총 {tokenDisplayMode === 'cost' ? '비용' : '소모 토큰'}: {formatTokenDisplay(tokenUsage.total_tokens)}</span>
                      <span>입력: {formatTokenDisplay(tokenUsage.total_input)} / 출력: {formatTokenDisplay(tokenUsage.total_output)}</span>
                    </div>
                  </div>
                )}
                {/* 목업 실행 결과임을 결과 탭에서 분명히 한다 — 실제 발송과 헷갈리면 안 된다(§7.1). */}
                {mockRunSummary && (
                  <div className="exec-card info">
                    <FlaskConical size={15} />
                    <span>
                      <strong>목업 실행</strong> — {mockRunSummary.nodeId} {mockRunSummary.only ? '노드만' : '부터'} 돌렸고,
                      외부로 나간 요청은 없습니다(목업 요청 {mockRunSummary.requestCount}건).
                    </span>
                  </div>
                )}
                {nodeErrorV1 && executionErrors.length > 0 && (
                  <div className="exec-error-list">
                    <div className="exec-status danger">실행 오류 {executionErrors.length}건</div>
                    {executionErrors.map((item, index) => {
                      const nodeExists = nodes.some((n) => String(n.id) === String(item.node_id));
                      return (
                        <NodeErrorCard
                          key={`${item.node_id}-${index}`}
                          error={item.error || { code: 'LEGACY_NODE_ERROR', category: 'runtime', userMessage: item.error_message || '오류' }}
                          nodeId={nodeExists ? String(item.node_id) : null}
                          nodeType={item.node_type}
                          onFocusNode={focusNodeById}
                          onFocusField={focusErrorField}
                          onRetry={isOwner ? runFromNode : undefined}
                          onNavigate={navigate}
                        />
                      );
                    })}
                  </div>
                )}
                <div className="exec-result">
                  {isCompiled ? (
                    <pre className="exec-pre grow"><code>{response || '실행하면 결과가 여기에 표시됩니다.'}</code></pre>
                  ) : (
                    (response && typeof response === 'string' && (response.startsWith('uploads/') || response.startsWith('uploads\\'))) ? (
                      <div className="exec-file">
                        <p>파일이 생성됐습니다.</p>
                        <a href={`/${response.replace(/\\/g, '/')}`} target="_blank" rel="noreferrer" className="btn-run exec-download">
                          파일 내려받기
                        </a>
                      </div>
                    ) : (
                      <div className="exec-response">{response || '대기 중...'}</div>
                    )
                  )}
                </div>
              </div>
            )}

            {executionPanelTab === 'logs' && (
              <div className="exec-log">
                {systemLogs.length === 0 ? (
                  <span className="exec-log-empty">로그가 없습니다.</span>
                ) : (
                  systemLogs.map((log, i) => (
                    <div key={i} className={`exec-log-line ${log.startsWith('>') ? 'command' : ''}`}>{log}</div>
                  ))
                )}
                <div ref={el => el?.scrollIntoView()} />
              </div>
            )}

            {executionPanelTab === 'evaluation' && (
              <div className="exec-section exec-fill">
                {isAutoImproving ? (
                  <div className="exec-center">
                    <div className="exec-spinner ai" />
                    <p>평가와 자동 수정을 반복하고 있습니다...</p>
                    <small>기준 점수를 넘기거나 최대 시도 횟수에 도달하면 종료됩니다</small>
                  </div>
                ) : isEvaluating ? (
                  <div className="exec-center">
                    <div className="exec-spinner success" />
                    <div className="exec-steps">
                      {EVALUATION_STEPS.map((stepText, idx) => {
                        const isActive = evalStep === idx;
                        const isDone = evalStep > idx;
                        return (
                          <div key={idx} className={`exec-step-item ${isActive ? 'active' : ''} ${isDone ? 'done' : ''}`}>
                            <i>{isDone ? '✓' : (idx + 1)}</i>
                            <span>
                              {stepText}
                              {isActive && <span className="exec-blink">...</span>}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : evaluationReport ? (
                  <>
                    {evaluationReport.attempts?.length > 1 && (
                      <div className="exec-card ai">
                        <Sparkles size={16} />
                        <span>자동 개선 시도:</span>
                        {evaluationReport.attempts.map((attempt, idx) => (
                          <span key={idx} className="exec-attempts">
                            {idx > 0 && ' → '}
                            <span className={`exec-score ${scoreTone(attempt.score, 70, 70)}`}>{attempt.score}점</span>
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="exec-score-card">
                      <div className={`exec-score-ring ${scoreTone(evaluationReport.score, 80, 50)}`}>{evaluationReport.score}</div>
                      <div>
                        <h3>종합 평가 리포트</h3>
                        <p>{evaluationReport.summary}</p>
                      </div>
                    </div>

                    <div>
                      <h4 className="exec-h4">테스트 케이스 상세</h4>
                      <div className="exec-testcases">
                        {evaluationReport.test_results?.map((tc, idx) => (
                          <div key={idx} className="exec-testcase">
                            <div className="exec-testcase-head">
                              <span>Test Case {idx + 1}</span>
                              <span className={`exec-score ${scoreTone(tc.score, 40, 25)}`}>Score: {tc.score}/50</span>
                            </div>
                            <div className="exec-grid-2">
                              <div>
                                <div className="exec-block-label">입력 (Input)</div>
                                <div className="exec-block">{tc.input}</div>
                              </div>
                              <div>
                                <div className="exec-block-label">예상 동작 (Expected)</div>
                                <div className="exec-block">{tc.expected}</div>
                              </div>
                            </div>
                            <div>
                              <div className="exec-block-label">실제 결과 (Actual)</div>
                              <div className={`exec-block ${tc.error ? 'danger' : ''}`}>{tc.error ? tc.error : tc.actual}</div>
                            </div>
                            <div className="exec-feedback">
                              <div className="exec-block-label">AI 심사위원 피드백</div>
                              <div className="exec-block">{tc.feedback}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {evaluationReport.suggestions?.length > 0 && (
                      <div>
                        <h4 className="exec-h4 warning">개선 제안</h4>
                        <ul className="exec-suggestions">
                          {evaluationReport.suggestions.map((sug, idx) => (
                            <li key={idx}>{sug}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="exec-empty center">더보기 메뉴의 &quot;워크플로우 평가&quot;를 눌러 워크플로우를 채점해보세요.</div>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Execution Panel Toggle Button (if closed) — 미니맵 위 우하단, 선택 툴바와 겹치지 않는 자리 */}
      {!isExecutionPanelOpen && (response || systemLogs.length > 0) && (
        <button type="button" className="editor-result-pill" onClick={() => setIsExecutionPanelOpen(true)}>
          <Play size={15} />
          실행 결과
          {systemLogs.length > 0 && <span className="sidebar-count">{systemLogs.length > 99 ? '99+' : systemLogs.length}</span>}
        </button>
      )}

      <TutorialOverlay steps={EDITOR_TUTORIAL_STEPS} storageKey="tutorial_editor_seen_v1" />
      <FormatStudio
        isOpen={formatStudio.isOpen}
        initialFormatId={formatStudio.formatId}
        onClose={() => setFormatStudio({ isOpen: false, formatId: '', nodeId: null })}
        onLibraryChanged={invalidateUserFormatsCache}
        onApplyToNode={formatStudio.nodeId ? ((formatId) => {
          markNextHistory('포맷 적용');
          setNodes((nds) => nds.map((n) => (String(n.id) === String(formatStudio.nodeId)
            ? { ...n, data: { ...n.data, formatId } } : n)));
        }) : null}
      />

      {/* 사용자 승인 대기 모달(ADR-0015) — 직전 노드의 실제 결과(견본)를 보고 결정한다.
          '나중에'를 눌러도 요청은 승인 페이지(/approvals)에 그대로 남는다. */}
      {pendingApproval && (
        <div className="editor-approval-backdrop">
          <div className="editor-approval-dialog" role="dialog" aria-modal="true" aria-labelledby="editor-approval-title">
            <header>
              <strong id="editor-approval-title"><AlertTriangle size={16} /> 사용자 승인 요청</strong>
              <button type="button" className="editor-icon-button" onClick={() => setPendingApproval(null)} aria-label="닫기">
                <X size={17} />
              </button>
            </header>
            <div className="editor-approval-body">
              <div className="editor-approval-message">{pendingApproval.message}</div>
              <div className="exec-block-label">승인 대상 미리보기 (직전 노드의 결과)</div>
              <pre className="exec-pre">{pendingApproval.payload_preview || '(내용 없음)'}</pre>
              <div className="exec-block-label exec-mt">코멘트 (선택 — 거절 사유 등)</div>
              <textarea
                className="exec-textarea"
                value={approvalComment}
                onChange={(e) => setApprovalComment(e.target.value)}
                placeholder="예: 두 번째 문단을 더 구체적으로 수정해주세요."
              />
            </div>
            <footer>
              <button type="button" className="btn-secondary" onClick={() => setPendingApproval(null)} disabled={approvalDeciding}>
                나중에 (알림함에 유지)
              </button>
              <button type="button" className="btn-secondary danger" onClick={() => decideApproval('reject')} disabled={approvalDeciding}>
                거절
              </button>
              <button type="button" className="btn-run" onClick={() => decideApproval('approve')} disabled={approvalDeciding}>
                <Play size={15} /> {approvalDeciding ? '처리 중...' : '승인하고 계속 실행'}
              </button>
            </footer>
          </div>
        </div>
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
