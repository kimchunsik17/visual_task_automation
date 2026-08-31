import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import DeployModal from '../DeployModal';
import AdvancedTutorialLab from './AdvancedTutorialLab';
import {
  Box,
  Check,
  ChevronDown,
  ChevronRight,
  Command,
  CornerDownLeft,
  PlayCircle,
  MousePointer2,
  Plus,
  Rocket,
  RotateCcw,
  Save,
  Search,
  Send,
  Share2,
  Sparkles,
  TerminalSquare,
  Wand2,
  X,
} from 'lucide-react';
import { Icon } from '../icons';
import { getEditorNodeMeta } from '../editorNodeCatalog';

// 연습용 role → 실제 에디터 노드 타입. 라벨·색·아이콘·카테고리를 카탈로그에서 그대로
// 가져와, 연습 캔버스가 실제 에디터와 어긋나지 않게 한다(하드코딩 목록은 조용히 갈라진다).
const ROLE_TO_TYPE = {
  input: 'startNode',
  schedule: 'scheduleNode',
  webhook: 'webhookNode',
  dynamic: 'dynamicInputNode',
  process: 'promptNode',
  llm: 'llmNode',
  condition: 'conditionNode',
  loop: 'loopNode',
  delay: 'delayNode',
  merge: 'mergeNode',
  approval: 'humanApprovalNode',
  output: 'outputNode',
};

// custom-node 수식 클래스 — 실제 노드 CSS(customNodes)와 같은 모양을 쓰기 위한 매핑.
const ROLE_CLASSNAMES = {
  input: 'start', schedule: 'schedule', webhook: 'webhook', dynamic: 'dynamic-input',
  process: 'prompt', llm: 'llm', condition: 'condition', loop: 'loop',
  delay: 'delay', merge: 'merge', approval: 'approval', output: 'output',
};

const NODE_META = Object.fromEntries(Object.entries(ROLE_TO_TYPE).map(([role, type]) => {
  const meta = getEditorNodeMeta(type);
  return [role, {
    label: meta.label,
    color: meta.color,
    iconName: meta.icon,
    className: ROLE_CLASSNAMES[role],
    category: meta.category,
    categoryLabel: meta.categoryLabel,
  }];
}));

// 배치 과정 목표 판정용 — 팔레트가 늘어나도 "입력·처리·출력 각 1개" 기준은 유지한다.
const ROLE_FAMILIES = {
  input: 'input', schedule: 'input', webhook: 'input', dynamic: 'input',
  process: 'process', llm: 'process', condition: 'process', loop: 'process',
  delay: 'process', merge: 'process', approval: 'process',
  output: 'output',
};

// 팔레트 구성 — 실제 에디터와 같은 카테고리 순서로 묶는다.
const PALETTE_CATEGORY_ORDER = ['core', 'input', 'ai', 'logic', 'advanced'];
const PALETTE_ROLES = ['input', 'schedule', 'output', 'webhook', 'dynamic', 'process', 'llm', 'condition', 'loop', 'delay', 'merge', 'approval'];

const SPECIALS = [
  { id: 'condition', label: 'Condition', description: '조건 결과에 따라 True 또는 False 경로를 선택합니다.' },
  { id: 'loop', label: 'Loop', description: '목록이나 지정 횟수만큼 처리 노드를 반복 실행합니다.' },
  { id: 'delay', label: 'Delay', description: '다음 노드로 넘어가기 전에 정해진 시간만큼 기다립니다.' },
  { id: 'merge', label: 'Merge', description: '나뉘어 실행된 경로의 결과를 하나의 흐름으로 합칩니다.' },
  { id: 'webhook', label: 'Webhook', description: '외부 시스템의 HTTP 요청이 도착할 때 Workflow를 시작합니다.' },
  { id: 'approval', label: 'Human Approval', description: '중요한 작업 전에 사람의 승인 또는 거절을 기다립니다.' },
];

const node = (id, role, x, y, extra = {}) => ({
  id,
  type: 'tutorialNode',
  position: { x, y },
  data: {
    role,
    label: NODE_META[role]?.label || role,
    description: extra.description || '',
    userPrompt: extra.userPrompt || '',
    expanded: false,
    status: 'idle',
    ...extra,
  },
});

const edge = (id, source, target, extra = {}) => ({
  id,
  source,
  target,
  type: 'bezier',
  ...extra,
});

const baseNodes = () => [
  node('input-1', 'input', 40, 130, { description: '사용자 요청' }),
  node('process-1', 'process', 300, 130, { description: '내용 요약', userPrompt: '요청 내용을 세 문장으로 요약하세요.' }),
  node('output-1', 'output', 740, 130, { description: '결과 전달' }),
];

const baseEdges = () => [
  edge('input-process', 'input-1', 'process-1'),
  edge('process-output', 'process-1', 'output-1'),
];

const getSpecialGraph = (specialId) => {
  if (specialId === 'condition') {
    return {
      nodes: [
        node('input-special', 'input', 10, 145, { description: '주문 금액' }),
        node('special-main', 'condition', 250, 145, { description: '10만원 이상?' }),
        node('true-output', 'output', 510, 50, { label: '승인 경로', description: 'True' }),
        node('false-output', 'output', 510, 240, { label: '일반 경로', description: 'False' }),
      ],
      edges: [
        edge('special-in', 'input-special', 'special-main'),
        edge('special-true', 'special-main', 'true-output', { sourceHandle: 'true' }),
        edge('special-false', 'special-main', 'false-output', { sourceHandle: 'false' }),
      ],
      sequence: ['input-special', 'special-main', 'true-output'],
    };
  }
  if (specialId === 'loop') {
    return {
      nodes: [
        node('input-special', 'input', 10, 145, { description: '항목 3개' }),
        node('special-main', 'loop', 245, 145, { description: '3회 반복' }),
        node('loop-process', 'process', 480, 60, { description: '항목 처리' }),
        node('true-output', 'output', 480, 235, { label: '반복 완료' }),
      ],
      edges: [
        edge('special-in', 'input-special', 'special-main'),
        edge('loop-body', 'special-main', 'loop-process'),
        edge('loop-back', 'loop-process', 'special-main'),
        edge('loop-done', 'special-main', 'true-output'),
      ],
      sequence: ['input-special', 'special-main', 'loop-process', 'special-main', 'loop-process', 'special-main', 'true-output'],
    };
  }
  if (specialId === 'delay') {
    return {
      nodes: [
        node('input-special', 'input', 10, 145, { description: '보고서 초안' }),
        node('special-main', 'delay', 250, 145, { description: '30분 대기' }),
        node('true-output', 'output', 510, 145, { description: '검토 후 발송' }),
      ],
      edges: [
        edge('special-in', 'input-special', 'special-main'),
        edge('special-out', 'special-main', 'true-output'),
      ],
      sequence: ['input-special', 'special-main', 'true-output'],
    };
  }
  if (specialId === 'merge') {
    return {
      nodes: [
        node('branch-a', 'process', 10, 50, { label: '뉴스 요약', description: '경로 A' }),
        node('branch-b', 'process', 10, 240, { label: '일정 정리', description: '경로 B' }),
        node('special-main', 'merge', 300, 145, { description: '결과 합치기' }),
        node('true-output', 'output', 560, 145, { description: '하나의 브리핑' }),
      ],
      edges: [
        edge('merge-a', 'branch-a', 'special-main'),
        edge('merge-b', 'branch-b', 'special-main'),
        edge('merge-out', 'special-main', 'true-output'),
      ],
      sequence: ['branch-a', 'branch-b', 'special-main', 'true-output'],
    };
  }
  if (specialId === 'webhook') {
    return {
      nodes: [
        node('special-main', 'webhook', 70, 145, { description: '요청 대기' }),
        node('loop-process', 'process', 325, 145, { description: 'Payload 처리' }),
        node('true-output', 'output', 570, 145, { description: '200 응답' }),
      ],
      edges: [edge('webhook-process', 'special-main', 'loop-process'), edge('webhook-output', 'loop-process', 'true-output')],
      sequence: ['special-main', 'loop-process', 'true-output'],
    };
  }
  return {
    nodes: [
      node('input-special', 'input', 10, 145, { description: '결제 요청' }),
      node('special-main', 'approval', 250, 145, { description: '승인 대기' }),
      node('true-output', 'output', 510, 50, { label: '승인됨', description: '작업 진행' }),
      node('false-output', 'output', 510, 240, { label: '거절됨', description: '작업 중단' }),
    ],
    edges: [
      edge('approval-in', 'input-special', 'special-main'),
      edge('approval-yes', 'special-main', 'true-output'),
      edge('approval-no', 'special-main', 'false-output'),
    ],
    sequence: ['input-special', 'special-main', 'true-output'],
  };
};

function TutorialNode({ data, selected }) {
  const meta = NODE_META[data.role] || NODE_META.process;
  const hasTarget = !['input', 'webhook', 'schedule'].includes(data.role);
  const hasSource = data.role !== 'output';
  const statusClass = data.status === 'running'
    ? 'node-executing'
    : data.status === 'success' ? 'node-success' : '';

  return (
    <div
      className={`custom-node ${data.expanded ? 'expanded' : 'collapsed'} ${meta.className} ${statusClass} ${selected ? 'selected' : ''}`}
      data-tutorial-role={data.role}
    >
      {hasTarget && <Handle type="target" position={Position.Left} id="in" />}
      <div className="node-header" onClick={() => data.onToggleExpand?.()} style={{ cursor: 'pointer' }}>
        {data.expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Icon name={meta.iconName} size={16} color={meta.color} /> {data.label || meta.label}
        </div>
        <button
          type="button"
          className="btn-delete"
          aria-label={`${data.label || meta.label} 삭제`}
          onClick={(event) => {
            event.stopPropagation();
            data.onDelete?.();
          }}
        >x</button>
      </div>
      {data.expanded && data.role === 'process' && (
        <div className="node-body">
          <label htmlFor={`tutorial-prompt-${data.nodeId}`}>사용자 프롬프트</label>
          <textarea
            id={`tutorial-prompt-${data.nodeId}`}
            className="nodrag tutorial-inline-prompt"
            value={data.userPrompt || ''}
            onChange={(event) => data.onPromptChange?.(event.target.value)}
            placeholder="프롬프트를 입력하세요..."
          />
        </div>
      )}
      {data.expanded && data.role !== 'process' && (
        <div className="node-body">
          <div className="node-collapsed-badge">{data.description || `${meta.label} 설정`}</div>
        </div>
      )}
      {hasSource && data.role === 'condition' ? (
        <>
          <Handle type="source" position={Position.Right} id="true" style={{ top: '32%' }} />
          <Handle type="source" position={Position.Right} id="false" style={{ top: '70%' }} />
        </>
      ) : hasSource ? <Handle type="source" position={Position.Right} id="out" /> : null}
    </div>
  );
}

const nodeTypes = { tutorialNode: TutorialNode };

const lessonGraph = (lessonId) => {
  if (lessonId === 'placement' || lessonId === 'assist') return { nodes: [], edges: [] };
  if (lessonId === 'connection') return { nodes: baseNodes(), edges: [] };
  return { nodes: baseNodes(), edges: baseEdges() };
};

const sleep = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function TutorialSandboxContent({ lesson, onComplete }) {
  const initial = useMemo(() => lessonGraph(lesson.id), [lesson.id]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const [feedback, setFeedback] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState([]);
  const [specialId, setSpecialId] = useState('condition');
  const [visitedSpecials, setVisitedSpecials] = useState([]);
  const [deploymentVisibility, setDeploymentVisibility] = useState('private');
  const [isTutorialSaved, setIsTutorialSaved] = useState(false);
  const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
  const [isDemoPlaying, setIsDemoPlaying] = useState(false);
  const [isPaletteOpen, setIsPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState('');
  // AI 생성·어시스턴트 과정 — 프롬프트는 draft 패턴(로컬 상태만, 액션 시점에 사용).
  const [assistDraft, setAssistDraft] = useState('');
  const [assistStage, setAssistStage] = useState('idle'); // idle → generating → generated → modifying → modified
  // 편의 기능 과정
  const [featureId, setFeatureId] = useState('command-palette');
  const [visitedFeatures, setVisitedFeatures] = useState([]);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [quickAdd, setQuickAdd] = useState(null); // { x, y, flow: {x, y} }
  const [demoCursor, setDemoCursor] = useState({ visible: false, x: 28, y: 28, pressing: false, label: '' });
  const runTokenRef = useRef(0);
  const demoTokenRef = useRef(0);
  const placedCounterRef = useRef(0);
  const paletteDragRef = useRef(false);
  const flowAreaRef = useRef(null);
  const hasUserInteractedRef = useRef(false);
  const { screenToFlowPosition, fitView } = useReactFlow();

  const setNodeStatus = useCallback((nodeId, status) => {
    setNodes((current) => current.map((item) => (
      item.id === nodeId ? { ...item, data: { ...item.data, status } } : item
    )));
  }, [setNodes]);

  const resetLesson = useCallback(() => {
    runTokenRef.current += 1;
    demoTokenRef.current += 1;
    const next = lesson.id === 'special' ? getSpecialGraph('condition') : lessonGraph(lesson.id);
    setNodes(next.nodes);
    setEdges(next.edges);
    setFeedback('');
    setIsRunning(false);
    setLogs([]);
    setSpecialId('condition');
    setVisitedSpecials([]);
    setDeploymentVisibility('private');
    setIsTutorialSaved(false);
    setIsDeployModalOpen(false);
    setIsDemoPlaying(false);
    setIsPaletteOpen(false);
    setPaletteQuery('');
    setAssistDraft('');
    setAssistStage('idle');
    setFeatureId('command-palette');
    setVisitedFeatures([]);
    setIsCommandPaletteOpen(false);
    setQuickAdd(null);
    hasUserInteractedRef.current = false;
    placedCounterRef.current = 0;
    window.setTimeout(() => fitView({ padding: 0.22, duration: 250 }), 60);
  }, [fitView, lesson.id, setEdges, setNodes]);

  useEffect(() => {
    resetLesson();
    return () => { runTokenRef.current += 1; };
  }, [resetLesson]);

  const animateSequence = async (sequence, onFinished, logEnabled = false) => {
    if (isRunning) return;
    const token = ++runTokenRef.current;
    setIsRunning(true);
    setFeedback('데이터가 노드를 따라 이동하고 있습니다.');
    setNodes((current) => current.map((item) => ({ ...item, data: { ...item.data, status: 'idle' } })));
    if (logEnabled) setLogs([{ tone: 'info', text: 'Workflow 실행을 시작했습니다.' }]);

    for (let index = 0; index < sequence.length; index += 1) {
      if (runTokenRef.current !== token) return;
      const nodeId = sequence[index];
      setNodeStatus(nodeId, 'running');
      if (logEnabled) setLogs((current) => [...current, { tone: 'running', text: `${nodeId} 실행 중` }]);
      await sleep(650);
      if (runTokenRef.current !== token) return;
      setNodeStatus(nodeId, 'success');
      if (logEnabled) setLogs((current) => [...current, { tone: 'success', text: `${nodeId} 완료` }]);
      await sleep(220);
    }

    if (runTokenRef.current !== token) return;
    setIsRunning(false);
    setFeedback('실행이 성공적으로 완료되었습니다.');
    if (logEnabled) setLogs((current) => [...current, { tone: 'success', text: '결과가 출력 노드에 전달되었습니다.' }]);
    onFinished?.();
  };

  const runCurrentLesson = () => {
    if (lesson.id === 'structure') {
      animateSequence(['input-1', 'process-1', 'output-1'], onComplete);
    } else if (lesson.id === 'execution') {
      animateSequence(['input-1', 'process-1', 'output-1'], onComplete, true);
    }
  };

  const addPaletteNode = useCallback((role, position, isDemonstration = false) => {
    if (!isDemonstration) {
      hasUserInteractedRef.current = true;
      demoTokenRef.current += 1;
      setIsDemoPlaying(false);
      setDemoCursor((current) => ({ ...current, visible: false }));
    }
    placedCounterRef.current += 1;
    const id = `${role}-placed-${placedCounterRef.current}`;
    const fallbackPositions = [
      { x: 55, y: 80 }, { x: 300, y: 170 }, { x: 540, y: 80 },
      { x: 180, y: 280 }, { x: 440, y: 290 },
    ];
    const nextNode = node(id, role, position?.x ?? fallbackPositions[(placedCounterRef.current - 1) % fallbackPositions.length].x, position?.y ?? fallbackPositions[(placedCounterRef.current - 1) % fallbackPositions.length].y);
    setNodes((current) => {
      const next = [...current, nextNode];
      const families = new Set(next.map((item) => ROLE_FAMILIES[item.data.role]));
      if (!isDemonstration && ['input', 'process', 'output'].every((required) => families.has(required))) {
        setFeedback('입력·처리·출력 역할의 노드를 모두 배치했습니다.');
        onComplete();
      }
      return next;
    });
  }, [onComplete, setNodes]);

  const handleDrop = useCallback((event) => {
    event.preventDefault();
    const role = event.dataTransfer.getData('application/tutorial-node');
    if (!role) return;
    paletteDragRef.current = true;
    addPaletteNode(role, screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  }, [addPaletteNode, screenToFlowPosition]);

  const handlePaletteDragStart = useCallback((event, role) => {
    paletteDragRef.current = true;
    event.dataTransfer.setData('application/tutorial-node', role);
    event.dataTransfer.setData('application/reactflow', role);
    event.dataTransfer.effectAllowed = 'move';
  }, []);

  const handlePaletteDragEnd = useCallback(() => {
    window.setTimeout(() => {
      paletteDragRef.current = false;
    }, 0);
  }, []);

  const handlePaletteClick = useCallback((role) => {
    if (paletteDragRef.current) return;
    addPaletteNode(role);
  }, [addPaletteNode]);

  const handleConnect = useCallback((params) => {
    hasUserInteractedRef.current = true;
    demoTokenRef.current += 1;
    setIsDemoPlaying(false);
    setIsPaletteOpen(false);
    setDemoCursor((current) => ({ ...current, visible: false }));
    const validPairs = new Set(['input-1:process-1', 'process-1:output-1']);
    const pair = `${params.source}:${params.target}`;
    if (!validPairs.has(pair)) {
      setFeedback('입력 → 처리 → 출력 방향으로 연결해보세요.');
      return;
    }
    setEdges((current) => {
      if (current.some((item) => item.source === params.source && item.target === params.target)) return current;
      const next = addEdge({ ...params, type: 'bezier' }, current);
      if (validPairs.size === next.length && [...validPairs].every((valid) => {
        const [source, target] = valid.split(':');
        return next.some((item) => item.source === source && item.target === target);
      })) {
        setFeedback('실행 순서가 올바르게 연결되었습니다.');
        onComplete();
      } else {
        setFeedback('좋아요. 이제 다음 노드까지 연결하세요.');
      }
      return next;
    });
  }, [onComplete, setEdges]);

  const updateProcessPrompt = useCallback((value, completeLesson = true) => {
    setNodes((current) => current.map((item) => (
      item.id === 'process-1' ? { ...item, data: { ...item.data, userPrompt: value, description: value || '내용 요약' } } : item
    )));
    if (completeLesson && value.trim() && value.trim() !== '요청 내용을 세 문장으로 요약하세요.') {
      hasUserInteractedRef.current = true;
      setFeedback('처리 노드의 입력값을 직접 수정했습니다.');
      onComplete();
    }
  }, [onComplete, setNodes]);

  const toggleNodeExpanded = useCallback((nodeId, fromDemo = false) => {
    if (!fromDemo) {
      hasUserInteractedRef.current = true;
      demoTokenRef.current += 1;
      setIsDemoPlaying(false);
      setDemoCursor((current) => ({ ...current, visible: false }));
    }
    setNodes((current) => current.map((item) => (
      item.id === nodeId
        ? { ...item, data: { ...item.data, expanded: !item.data.expanded } }
        : item
    )));
  }, [setNodes]);

  const deleteTutorialNode = useCallback((nodeId) => {
    hasUserInteractedRef.current = true;
    setNodes((current) => current.filter((item) => item.id !== nodeId));
    setEdges((current) => current.filter((item) => item.source !== nodeId && item.target !== nodeId));
  }, [setEdges, setNodes]);

  const moveDemoCursor = useCallback(async (selector, token, options = {}) => {
    await sleep(options.before || 80);
    if (demoTokenRef.current !== token) return false;
    const area = flowAreaRef.current;
    const target = area?.querySelector(selector);
    if (!area || !target) return false;
    const areaRect = area.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const anchorX = options.anchorX ?? 0.5;
    const anchorY = options.anchorY ?? 0.5;
    setDemoCursor({
      visible: true,
      x: targetRect.left - areaRect.left + (targetRect.width * anchorX),
      y: targetRect.top - areaRect.top + (targetRect.height * anchorY),
      pressing: Boolean(options.pressing),
      label: options.label || '',
    });
    await sleep(options.duration || 720);
    return demoTokenRef.current === token;
  }, []);

  const finishDemonstration = useCallback(async (token, message) => {
    if (demoTokenRef.current !== token) return;
    setDemoCursor((current) => ({ ...current, pressing: false, label: '이제 직접 해보세요' }));
    await sleep(900);
    if (demoTokenRef.current !== token) return;
    const restored = lessonGraph(lesson.id);
    setNodes(restored.nodes);
    setEdges(restored.edges);
    placedCounterRef.current = 0;
    setFeedback(message);
    setIsDemoPlaying(false);
    setIsPaletteOpen(false);
    setDemoCursor((current) => ({ ...current, visible: false, label: '' }));
    window.setTimeout(() => fitView({ padding: 0.22, duration: 250 }), 40);
  }, [fitView, lesson.id, setEdges, setNodes]);

  const playInteractionDemo = useCallback(async (manual = true) => {
    if (!['placement', 'connection', 'configuration'].includes(lesson.id) || isDemoPlaying) return;
    if (!manual && hasUserInteractedRef.current) return;

    const token = ++demoTokenRef.current;
    const startGraph = lessonGraph(lesson.id);
    placedCounterRef.current = 0;
    setNodes(startGraph.nodes);
    setEdges(startGraph.edges);
    setFeedback('마우스 커서의 움직임을 따라가세요.');
    setIsDemoPlaying(true);
    setDemoCursor({ visible: true, x: 30, y: 34, pressing: false, label: '동작 시연' });
    await sleep(300);

    if (lesson.id === 'placement') {
      setIsPaletteOpen(true);
      const roles = ['input', 'process', 'output'];
      for (const role of roles) {
        if (!await moveDemoCursor(`[data-palette-role="${role}"]`, token, { label: '노드를 잡습니다' })) return;
        setDemoCursor((current) => ({ ...current, pressing: true, label: '캔버스로 드래그' }));
        await sleep(240);
        if (!await moveDemoCursor('.tutorial-flow-canvas', token, {
          anchorX: role === 'input' ? 0.2 : role === 'process' ? 0.5 : 0.8,
          anchorY: role === 'process' ? 0.58 : 0.42,
          pressing: true,
          label: '여기에 놓기',
          duration: 850,
        })) return;
        addPaletteNode(role, undefined, true);
        setDemoCursor((current) => ({ ...current, pressing: false, label: '배치 완료' }));
        await sleep(420);
      }
      await finishDemonstration(token, '시연이 끝났습니다. 왼쪽 노드 목록에서 세 노드를 직접 배치하세요.');
      return;
    }

    if (lesson.id === 'connection') {
      await sleep(350);
      const pairs = [
        ['input-1', 'process-1'],
        ['process-1', 'output-1'],
      ];
      for (const [source, target] of pairs) {
        if (!await moveDemoCursor(`.react-flow__node[data-id="${source}"] .react-flow__handle-right`, token, { label: '출력 Handle 선택' })) return;
        setDemoCursor((current) => ({ ...current, pressing: true, label: '연결선을 드래그' }));
        if (!await moveDemoCursor(`.react-flow__node[data-id="${target}"] .react-flow__handle-left`, token, {
          pressing: true,
          label: '입력 Handle에 놓기',
          duration: 950,
        })) return;
        setEdges((current) => [...current, edge(`demo-${source}-${target}`, source, target)]);
        setDemoCursor((current) => ({ ...current, pressing: false, label: '연결 완료' }));
        await sleep(480);
      }
      await finishDemonstration(token, '시연이 끝났습니다. 오른쪽 Handle에서 다음 노드의 왼쪽 Handle로 직접 연결하세요.');
      return;
    }

    await sleep(350);
    if (!await moveDemoCursor('.react-flow__node[data-id="process-1"] .node-header', token, { label: '프롬프트 노드 선택' })) return;
    setDemoCursor((current) => ({ ...current, pressing: true, label: '클릭해서 펼치기' }));
    await sleep(220);
    toggleNodeExpanded('process-1', true);
    setDemoCursor((current) => ({ ...current, pressing: false, label: '노드 내부 설정 열림' }));
    await sleep(520);
    if (!await moveDemoCursor('#tutorial-prompt-process-1', token, { label: '입력 필드 선택', duration: 680 })) return;
    setDemoCursor((current) => ({ ...current, pressing: true, label: '프롬프트 수정' }));
    const sample = '고객 요청의 핵심을 세 문장으로 요약하세요.';
    for (let index = 1; index <= sample.length; index += 1) {
      if (demoTokenRef.current !== token) return;
      updateProcessPrompt(sample.slice(0, index), false);
      await sleep(45);
    }
    setDemoCursor((current) => ({ ...current, pressing: false, label: '수정 완료' }));
    await finishDemonstration(token, '시연이 끝났습니다. 프롬프트 노드를 펼쳐 내용을 직접 수정하세요.');
  }, [addPaletteNode, finishDemonstration, isDemoPlaying, lesson.id, moveDemoCursor, setEdges, setNodes, toggleNodeExpanded, updateProcessPrompt]);

  const selectSpecial = (nextSpecialId) => {
    if (isRunning) return;
    runTokenRef.current += 1;
    setSpecialId(nextSpecialId);
    const graph = getSpecialGraph(nextSpecialId);
    setNodes(graph.nodes);
    setEdges(graph.edges);
    setFeedback(SPECIALS.find((item) => item.id === nextSpecialId)?.description || '');
    window.setTimeout(() => fitView({ padding: 0.2, duration: 250 }), 50);
  };

  const runSpecial = () => {
    const graph = getSpecialGraph(specialId);
    animateSequence(graph.sequence, () => {
      setVisitedSpecials((current) => {
        const next = current.includes(specialId) ? current : [...current, specialId];
        if (next.length === SPECIALS.length) onComplete();
        return next;
      });
    });
  };

  // ── AI 생성·어시스턴트 과정 ──────────────────────────────────────────────
  const runAssistGeneration = async () => {
    if (assistStage === 'generating' || assistStage === 'modifying') return;
    if (!assistDraft.trim()) {
      setFeedback('만들고 싶은 자동화를 한 문장으로 먼저 적어주세요. 아래 예시를 눌러도 됩니다.');
      return;
    }
    const token = ++runTokenRef.current;
    setAssistStage('generating');
    setNodes([]);
    setEdges([]);
    setFeedback('AI가 요청을 분석해 Workflow 초안을 만들고 있습니다…');
    const draft = [
      node('assist-input', 'input', 20, 150, { description: '요청 접수' }),
      node('assist-prompt', 'process', 250, 150, { description: '요청 정리', userPrompt: assistDraft.trim() }),
      node('assist-llm', 'llm', 500, 150, { description: '내용 생성' }),
      node('assist-output', 'output', 740, 150, { description: '결과 전달' }),
    ];
    const draftEdges = [
      edge('assist-e1', 'assist-input', 'assist-prompt'),
      edge('assist-e2', 'assist-prompt', 'assist-llm'),
      edge('assist-e3', 'assist-llm', 'assist-output'),
    ];
    for (let index = 0; index < draft.length; index += 1) {
      if (runTokenRef.current !== token) return;
      const draftNode = draft[index];
      setNodes((current) => [...current, { ...draftNode, data: { ...draftNode.data, status: 'running' } }]);
      if (index > 0) setEdges((current) => [...current, draftEdges[index - 1]]);
      await sleep(430);
      if (runTokenRef.current !== token) return;
      setNodeStatus(draftNode.id, 'success');
    }
    await sleep(300);
    if (runTokenRef.current !== token) return;
    setNodes((current) => current.map((item) => ({ ...item, data: { ...item.data, status: 'idle' } })));
    setAssistStage('generated');
    setFeedback('초안이 생성되었습니다. 이제 어시스턴트에게 수정을 요청해보세요.');
    window.setTimeout(() => fitView({ padding: 0.22, duration: 250 }), 60);
  };

  const runAssistModification = async () => {
    if (assistStage !== 'generated') return;
    const token = ++runTokenRef.current;
    setAssistStage('modifying');
    setFeedback('어시스턴트가 기존 노드를 유지한 채 출력 단계만 바꾸고 있습니다…');
    setNodeStatus('assist-output', 'running');
    await sleep(700);
    if (runTokenRef.current !== token) return;
    setNodes((current) => current.map((item) => (
      item.id === 'assist-output'
        ? { ...item, data: { ...item.data, label: '디스코드 발송', description: '#알림 채널로 전송', status: 'success' } }
        : item
    )));
    await sleep(450);
    if (runTokenRef.current !== token) return;
    setNodeStatus('assist-output', 'idle');
    setAssistStage('modified');
    setFeedback('수정 요청이 반영되었습니다. 실제 에디터에서는 이 과정을 AI 어시스턴트 패널에서 진행합니다.');
    onComplete();
  };

  // ── 편의 기능 과정 ──────────────────────────────────────────────────────
  const FEATURES = [
    { id: 'command-palette', label: '명령 팔레트', hint: '명령 팔레트를 열어 "선택 항목 정렬"을 실행하세요.' },
    { id: 'quick-add', label: '캔버스 빠른 추가', hint: '캔버스의 빈 곳을 더블 클릭해 노드를 추가하세요.' },
    { id: 'insert-between', label: '노드 사이 삽입', hint: '아래 버튼으로 프롬프트와 결과 출력 사이에 LLM을 삽입하세요.' },
  ];

  const markFeatureVisited = (id) => {
    setVisitedFeatures((current) => {
      const next = current.includes(id) ? current : [...current, id];
      if (next.length === FEATURES.length) onComplete();
      return next;
    });
  };

  const runPaletteCommand = (commandId) => {
    setIsCommandPaletteOpen(false);
    if (commandId === 'arrange') {
      setNodes((current) => current.map((item, index) => ({
        ...item,
        position: { x: 40 + index * 250, y: 150 },
      })));
      setFeedback('선택 항목 정렬 명령이 실행되어 노드가 한 줄로 정돈되었습니다.');
    } else if (commandId === 'inspect') {
      setFeedback('문제 검사 결과: 연결되지 않은 노드가 없습니다.');
    } else {
      setFeedback('프로젝트가 저장되었다고 가정합니다. 연습 캔버스는 실제로 저장되지 않습니다.');
    }
    markFeatureVisited('command-palette');
    window.setTimeout(() => fitView({ padding: 0.22, duration: 250 }), 80);
  };

  const handleCanvasDoubleClick = (event) => {
    if (lesson.id !== 'convenience' || featureId !== 'quick-add') return;
    if (event.target.closest('.react-flow__node') || event.target.closest('.react-flow__edge')) return;
    const area = flowAreaRef.current;
    if (!area) return;
    const areaRect = area.getBoundingClientRect();
    setQuickAdd({
      x: Math.min(event.clientX - areaRect.left, areaRect.width - 190),
      y: Math.min(event.clientY - areaRect.top, areaRect.height - 170),
      flow: screenToFlowPosition({ x: event.clientX, y: event.clientY }),
    });
  };

  const addQuickNode = (role) => {
    if (!quickAdd) return;
    addPaletteNode(role, quickAdd.flow, true);
    setQuickAdd(null);
    setFeedback(`${NODE_META[role].label} 노드가 더블 클릭한 위치에 추가되었습니다.`);
    markFeatureVisited('quick-add');
  };

  const runInsertBetween = async () => {
    if (visitedFeatures.includes('insert-between')) return;
    const token = ++runTokenRef.current;
    setFeedback('프롬프트 → 결과 출력 연결선 위에 LLM 노드를 삽입합니다…');
    setEdges((current) => current.filter((item) => !(item.source === 'process-1' && item.target === 'output-1')));
    const inserted = node('llm-inserted', 'llm', 520, 150, { description: '내용 생성' });
    setNodes((current) => [...current.map((item) => (
      item.id === 'output-1' ? { ...item, position: { x: 760, y: 130 } } : item
    )), { ...inserted, data: { ...inserted.data, status: 'running' } }]);
    await sleep(500);
    if (runTokenRef.current !== token) return;
    setEdges((current) => [
      ...current,
      edge('insert-e1', 'process-1', 'llm-inserted'),
      edge('insert-e2', 'llm-inserted', 'output-1'),
    ]);
    setNodeStatus('llm-inserted', 'success');
    await sleep(400);
    if (runTokenRef.current !== token) return;
    setNodeStatus('llm-inserted', 'idle');
    setFeedback('연결을 끊지 않고 중간 단계가 추가되었습니다. 실제 에디터에서는 노드를 연결선 위로 드래그하면 됩니다.');
    markFeatureVisited('insert-between');
    window.setTimeout(() => fitView({ padding: 0.22, duration: 250 }), 80);
  };

  const saveTutorialWorkflow = () => {
    setIsTutorialSaved(true);
    setFeedback('연습 Workflow가 저장되었습니다. 이제 배포 버튼을 눌러 배포 방식을 선택하세요.');
  };

  const openTutorialDeployModal = () => {
    if (!isTutorialSaved) {
      setFeedback('에디터와 동일하게 배포 전에 Workflow를 먼저 저장해야 합니다.');
      return;
    }
    setIsDeployModalOpen(true);
  };

  const completeTutorialDeployment = (mode) => {
    setFeedback(`${mode} 배포 설정을 확인했습니다. 연습 모드에서는 실제 배포 요청을 보내지 않습니다.`);
    onComplete();
  };

  const selectedSpecial = SPECIALS.find((item) => item.id === specialId);
  const displayNodes = nodes.map((item) => ({
    ...item,
    data: {
      ...item.data,
      nodeId: item.id,
      onToggleExpand: () => toggleNodeExpanded(item.id),
      onPromptChange: (value) => updateProcessPrompt(value),
      onDelete: () => deleteTutorialNode(item.id),
    },
  }));

  if (lesson.id === 'deployment') {
    return (
      <section className="tutorial-lab tutorial-deploy-lab tool-shell">
        <header className="tutorial-editor-toolbar">
          <div className="tutorial-editor-project">
            <span className="tutorial-editor-project-icon"><Rocket size={16} /></span>
            <div><strong>튜토리얼 Workflow</strong><span>{isTutorialSaved ? '저장됨' : '저장되지 않음'}</span></div>
          </div>
          <div className="tutorial-editor-deploy-tools">
            <label className="tutorial-visibility-control">
              <Share2 size={15} />
              <select value={deploymentVisibility} onChange={(event) => setDeploymentVisibility(event.target.value)} aria-label="공개 범위">
                <option value="private">비공개</option>
                <option value="friends">친구공개</option>
                <option value="public">공개</option>
              </select>
            </label>
            <button type="button" className={`btn-secondary tutorial-save-button ${isTutorialSaved ? 'is-saved' : ''}`} onClick={saveTutorialWorkflow} title="저장" aria-label="Workflow 저장">
              {isTutorialSaved ? <Check size={16} /> : <Save size={16} />}
            </button>
            <button type="button" className="btn-secondary tutorial-deploy-button" onClick={openTutorialDeployModal} disabled={!isTutorialSaved} title="배포">
              <Wand2 size={16} /><span>배포</span>
            </button>
            <button type="button" className="tutorial-icon-button" onClick={resetLesson} title="과정 초기화" aria-label="과정 초기화"><RotateCcw size={16} /></button>
          </div>
        </header>
        <div className="tutorial-deploy-editor-canvas">
          <ReactFlow
            nodes={displayNodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodesDraggable
            elementsSelectable
            fitView
            fitViewOptions={{ padding: 0.24 }}
            defaultEdgeOptions={{ type: 'bezier', style: { strokeWidth: 2, stroke: 'var(--text-muted)' } }}
            colorMode={document.documentElement.getAttribute('data-theme') || 'dark'}
          >
            <Controls />
            <MiniMap nodeColor={(item) => NODE_META[item.data.role]?.color || '#94a3b8'} />
            <Background variant="dots" gap={24} size={2} color={document.documentElement.getAttribute('data-theme') === 'light' ? '#94a3b8' : '#64748b'} />
          </ReactFlow>
        </div>
        <footer className="tutorial-lab-feedback">{feedback || '공개 범위를 정하고 Workflow를 저장한 뒤 배포 버튼을 누르세요.'}</footer>
        <DeployModal
          isOpen={isDeployModalOpen}
          onClose={() => setIsDeployModalOpen(false)}
          project={{ id: 'tutorial-preview', title: '튜토리얼 Workflow' }}
          onDeployConfigSaved={completeTutorialDeployment}
          previewOnly
        />
      </section>
    );
  }

  return (
    <section className="tutorial-lab tool-shell">
      <header className="tutorial-lab-header">
        <div><Box size={17} /><strong>연습 캔버스</strong><span>이곳의 작업은 실제 프로젝트에 저장되지 않습니다.</span></div>
        <div className="tutorial-lab-actions">
          {(lesson.id === 'structure' || lesson.id === 'execution') && (
            <button type="button" className="tutorial-run-button" onClick={runCurrentLesson} disabled={isRunning}>
              <PlayCircle size={16} /> {isRunning ? '실행 중' : lesson.id === 'structure' ? '흐름 재생' : 'Workflow 실행'}
            </button>
          )}
          {lesson.id === 'special' && (
            <button type="button" className="tutorial-run-button" onClick={runSpecial} disabled={isRunning}>
              <PlayCircle size={16} /> 시뮬레이션 재생
            </button>
          )}
          {['placement', 'connection', 'configuration'].includes(lesson.id) && (
            <button type="button" className="tutorial-demo-button" onClick={() => playInteractionDemo(true)} disabled={isDemoPlaying}>
              <MousePointer2 size={15} /> {isDemoPlaying ? '시연 중' : '동작 보기'}
            </button>
          )}
          <button type="button" className="tutorial-icon-button" onClick={resetLesson} title="과정 초기화" aria-label="과정 초기화"><RotateCcw size={16} /></button>
        </div>
      </header>

      {lesson.id === 'special' && (
        <div className="tutorial-special-tabs">
          {SPECIALS.map((special) => (
            <button key={special.id} type="button" className={specialId === special.id ? 'active' : ''} onClick={() => selectSpecial(special.id)}>
              {visitedSpecials.includes(special.id) && <Check size={12} />}{special.label}
            </button>
          ))}
          <span>{selectedSpecial?.description}</span>
        </div>
      )}

      {lesson.id === 'assist' && (
        <div className="tutorial-assist-bar">
          <div className="tutorial-assist-input">
            <Sparkles size={16} />
            <input
              type="text"
              value={assistDraft}
              onChange={(event) => setAssistDraft(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') runAssistGeneration(); }}
              placeholder="만들고 싶은 자동화를 설명해보세요"
              aria-label="AI 생성 요청"
              disabled={assistStage === 'generating' || assistStage === 'modifying'}
            />
            <button type="button" onClick={runAssistGeneration} disabled={assistStage === 'generating' || assistStage === 'modifying'}>
              <Send size={14} /> {assistStage === 'generating' ? '생성 중' : '생성'}
            </button>
          </div>
          {assistStage === 'idle' && (
            <div className="tutorial-assist-chips">
              {['고객 문의가 오면 요약해서 알려줘', '매일 아침 뉴스 브리핑을 만들어줘'].map((sample) => (
                <button key={sample} type="button" onClick={() => setAssistDraft(sample)}>{sample}</button>
              ))}
            </div>
          )}
          {(assistStage === 'generated' || assistStage === 'modifying' || assistStage === 'modified') && (
            <div className="tutorial-assist-chips">
              <button
                type="button"
                className={`tutorial-assist-modify ${assistStage === 'modified' ? 'is-done' : ''}`}
                onClick={runAssistModification}
                disabled={assistStage !== 'generated'}
              >
                {assistStage === 'modified' ? <Check size={14} /> : <Wand2 size={14} />}
                수정 요청: 결과를 디스코드로 보내줘
              </button>
            </div>
          )}
        </div>
      )}

      {lesson.id === 'convenience' && (
        <div className="tutorial-special-tabs">
          {FEATURES.map((feature) => (
            <button key={feature.id} type="button" className={featureId === feature.id ? 'active' : ''} onClick={() => { setFeatureId(feature.id); setQuickAdd(null); setFeedback(feature.hint); }}>
              {visitedFeatures.includes(feature.id) && <Check size={12} />}{feature.label}
            </button>
          ))}
          {featureId === 'command-palette' && (
            <button type="button" className="tutorial-feature-action" onClick={() => setIsCommandPaletteOpen(true)}>
              <Command size={13} /> 명령 팔레트 열기 <kbd>Ctrl K</kbd>
            </button>
          )}
          {featureId === 'insert-between' && (
            <button type="button" className="tutorial-feature-action" onClick={runInsertBetween} disabled={visitedFeatures.includes('insert-between')}>
              <Plus size={13} /> 사이에 LLM 삽입
            </button>
          )}
          {featureId === 'quick-add' && <span>{FEATURES[1].hint}</span>}
        </div>
      )}

      <div className="tutorial-flow-area" ref={flowAreaRef}>
        {isPaletteOpen && <button type="button" className="tutorial-palette-overlay" onClick={() => setIsPaletteOpen(false)} aria-label="노드 목록 닫기" />}
        <button type="button" className="tutorial-mobile-palette-toggle" onClick={() => setIsPaletteOpen(true)} title="노드 목록 열기" aria-label="노드 목록 열기">
          <Plus size={20} />
        </button>
        <aside className={`tutorial-node-palette ${isPaletteOpen ? 'mobile-open' : ''}`} aria-label="연습용 노드 목록">
          <div className="sidebar-header">
            <h3 className="sidebar-title">노드 <span className="sidebar-count">{PALETTE_ROLES.length}</span></h3>
            <button type="button" className="tutorial-palette-close" onClick={() => setIsPaletteOpen(false)} aria-label="노드 목록 닫기"><X size={17} /></button>
          </div>
          <div className="sidebar-search">
            <Search size={14} />
            <input
              type="text"
              value={paletteQuery}
              onChange={(event) => setPaletteQuery(event.target.value)}
              placeholder="노드 검색"
              aria-label="노드 검색"
            />
          </div>
          <div className="node-list">
            {(() => {
              const isPlacementLesson = lesson.id === 'placement';
              const needle = paletteQuery.trim().toLocaleLowerCase('ko');
              const matches = (role) => !needle || NODE_META[role].label.toLocaleLowerCase('ko').includes(needle);
              const renderRole = (role, showCategory = false) => {
                const meta = NODE_META[role];
                return (
                  <button
                    key={role}
                    type="button"
                    className={`dnd-node tutorial-palette-node ${isPlacementLesson ? '' : 'is-disabled'}`}
                    data-palette-role={role}
                    draggable={isPlacementLesson && !isDemoPlaying}
                    onPointerDown={() => { paletteDragRef.current = false; }}
                    onDragStart={(event) => handlePaletteDragStart(event, role)}
                    onDragEnd={handlePaletteDragEnd}
                    onClick={() => isPlacementLesson && !isDemoPlaying && handlePaletteClick(role)}
                    aria-disabled={!isPlacementLesson}
                    title={isPlacementLesson ? `${meta.label} — 캔버스로 드래그` : `${meta.label} — 배치는 '노드 배치' 과정에서`}
                  >
                    <span className="dnd-node-icon" style={{ '--node-color': meta.color }}><Icon name={meta.iconName} size={15} /></span>
                    <span className="dnd-node-label">{meta.label}</span>
                    {showCategory && <span className="dnd-node-category">{meta.categoryLabel}</span>}
                    {!showCategory && isPlacementLesson && <Plus size={13} />}
                  </button>
                );
              };
              if (needle) {
                const found = PALETTE_ROLES.filter(matches);
                return found.length === 0
                  ? <div className="node-list-empty">일치하는 노드가 없습니다</div>
                  : found.map((role) => renderRole(role, true));
              }
              return PALETTE_CATEGORY_ORDER.map((categoryId) => {
                const categoryRoles = PALETTE_ROLES.filter((role) => NODE_META[role].category === categoryId);
                if (categoryRoles.length === 0) return null;
                return (
                  <div key={categoryId} className="sidebar-category">
                    <div className="sidebar-category-header" aria-expanded="true">
                      <ChevronRight size={13} className="chevron" />
                      {NODE_META[categoryRoles[0]].categoryLabel}
                      <span className="sidebar-count">{categoryRoles.length}</span>
                    </div>
                    <div className="sidebar-category-nodes">
                      {categoryRoles.map((role) => renderRole(role))}
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        </aside>
        <div className="tutorial-flow-canvas" onDrop={handleDrop} onDragOver={(event) => event.preventDefault()} onDoubleClickCapture={handleCanvasDoubleClick}>
          <ReactFlow
            nodes={displayNodes}
            edges={edges.map((item) => ({ ...item, animated: isRunning }))}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={handleConnect}
            nodesDraggable={!isDemoPlaying}
            nodesConnectable={lesson.id === 'connection' && !isDemoPlaying}
            connectOnClick
            connectionRadius={24}
            nodeDragThreshold={1}
            elementsSelectable
            fitView
            fitViewOptions={{ padding: 0.22 }}
            deleteKeyCode={['Backspace', 'Delete']}
            defaultEdgeOptions={{ type: 'bezier', style: { strokeWidth: 2, stroke: 'var(--text-muted)' } }}
            colorMode={document.documentElement.getAttribute('data-theme') || 'dark'}
            panOnDrag={[1, 2]}
            selectionOnDrag
            selectionMode="partial"
            panOnScroll
            zoomOnScroll
            zoomOnDoubleClick={lesson.id !== 'convenience'}
          >
            <Controls />
            <MiniMap
              nodeColor={(item) => NODE_META[item.data.role]?.color || '#94a3b8'}
              pannable
              zoomable
            />
            <Background variant="dots" gap={24} size={2} color={document.documentElement.getAttribute('data-theme') === 'light' ? '#94a3b8' : '#64748b'} />
          </ReactFlow>
          {nodes.length === 0 && lesson.id !== 'assist' && (
            <div className="tutorial-empty-canvas"><MousePointer2 size={28} /><strong>노드를 배치해보세요</strong><span>왼쪽 팔레트에서 입력 노드부터 추가하세요.</span></div>
          )}
          {nodes.length === 0 && lesson.id === 'assist' && (
            <div className="tutorial-empty-canvas"><Sparkles size={28} /><strong>AI로 초안을 만들어보세요</strong><span>위 입력창에 요청을 적고 생성을 누르면 노드가 자동으로 배치됩니다.</span></div>
          )}
          {quickAdd && (
            <div className="tutorial-quick-add" style={{ left: quickAdd.x, top: quickAdd.y }}>
              <span>노드 빠른 추가</span>
              {['llm', 'condition', 'delay'].map((role) => (
                <button key={role} type="button" onClick={() => addQuickNode(role)}>
                  <span className="dnd-node-icon" style={{ '--node-color': NODE_META[role].color }}><Icon name={NODE_META[role].iconName} size={14} /></span>
                  {NODE_META[role].label}
                </button>
              ))}
            </div>
          )}
        </div>
        {isCommandPaletteOpen && (
          <div className="tutorial-command-palette-backdrop" onClick={() => setIsCommandPaletteOpen(false)}>
            <div className="tutorial-command-palette" role="dialog" aria-label="명령 팔레트" onClick={(event) => event.stopPropagation()}>
              <div className="tutorial-command-search"><Search size={14} /><span>명령 검색…</span><kbd>Esc</kbd></div>
              {[
                { id: 'arrange', category: '정렬', label: '선택 항목 정렬' },
                { id: 'inspect', category: '진단', label: '문제 검사' },
                { id: 'save', category: '프로젝트', label: '프로젝트 저장' },
              ].map((command) => (
                <button key={command.id} type="button" onClick={() => runPaletteCommand(command.id)}>
                  <span><small>{command.category}</small><strong>{command.label}</strong></span>
                  <CornerDownLeft size={13} />
                </button>
              ))}
            </div>
          </div>
        )}
        <div
          className={`tutorial-demo-cursor ${demoCursor.visible ? 'is-visible' : ''} ${demoCursor.pressing ? 'is-pressing' : ''}`}
          style={{ transform: `translate3d(${demoCursor.x}px, ${demoCursor.y}px, 0)` }}
          aria-hidden="true"
        >
          <MousePointer2 size={26} fill="currentColor" />
          {demoCursor.label && <span>{demoCursor.label}</span>}
        </div>
      </div>

      {lesson.id === 'execution' && (
        <div className="tutorial-log-panel">
          <div><TerminalSquare size={15} /><strong>실행 로그</strong></div>
          <pre>{logs.length > 0 ? logs.map((log, index) => `[${String(index + 1).padStart(2, '0')}] ${log.text}`).join('\n') : '실행 버튼을 누르면 노드별 로그가 표시됩니다.'}</pre>
        </div>
      )}

      <footer className="tutorial-lab-feedback">
        {lesson.id === 'special' && <span>{visitedSpecials.length}/{SPECIALS.length} 확인</span>}
        {lesson.id === 'convenience' && <span>{visitedFeatures.length}/{FEATURES.length} 완료</span>}
        {feedback || lesson.objective}
      </footer>
    </section>
  );
}

function TutorialSandbox(props) {
  if (props.lesson.labType === 'guided') {
    return <AdvancedTutorialLab {...props} />;
  }
  return (
    <ReactFlowProvider>
      <TutorialSandboxContent {...props} />
    </ReactFlowProvider>
  );
}

export default TutorialSandbox;
