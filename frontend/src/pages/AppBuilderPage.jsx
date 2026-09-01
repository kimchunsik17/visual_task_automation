import React, { useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { ReactFlow, Controls, Background, addEdge, useNodesState, useEdgesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import UIEngine from '../components/UIEngine';
import {
  DEFAULT_CANVAS,
  INPUT_COMPONENT_TYPES,
  OUTPUT_COMPONENT_TYPES,
  applyWorkflowMappings,
  buildSubmitChain,
  inferButtonActionMode,
  isValidLogicConnection,
  makeGeneratedLayoutEditable,
  normalizeCanvas,
  normalizeComponents,
  normalizeWorkflowMappings,
  resolveCanvas,
  scaleDescendantGeometry,
} from '../appBuilderSchema';
import {
  FileUp, Save, ArrowLeft, Sparkles, Code2, TerminalSquare, Trash2, X, CheckCircle2, Copy, ExternalLink, Coins, Workflow,
  Undo2, Redo2, CopyPlus, Eye, EyeOff, Search, CircleDot, SlidersHorizontal, Link2, FileCode, Table2, Gauge,
  AlignStartVertical, AlignCenterVertical, AlignEndVertical, AlignStartHorizontal, AlignCenterHorizontal, AlignEndHorizontal,
  AlignHorizontalDistributeCenter, AlignVerticalDistributeCenter, StretchHorizontal, StretchVertical,
  BringToFront, SendToBack, ChevronUp, ChevronDown, ChevronRight,
  Settings, Rocket, Grid3x3, Monitor, Tablet, Smartphone, PenTool, Braces, Play, Info, Shapes, Maximize2, Scan, Check,
} from 'lucide-react';
import { Icon } from '../icons';
import { COMPONENT_CATEGORIES, catalogEntry, defaultPropsFor, defaultSizeFor, filterCatalog } from '../appBuilderCatalog';
import {
  alignComponents,
  collectIds,
  distributeComponents,
  duplicateComponents,
  findComponent,
  matchSize,
  nudgeComponents,
  pasteComponents,
  removeComponent,
  reorderComponent,
  sharedParentId,
  topLevelSelection,
  updateComponent,
} from '../appBuilderEditing';
import { useAppBuilderHistory } from '../useAppBuilderHistory';
import { logicNodeTypes } from '../logicNodes';
import AIAssistantDrawer from '../components/AIAssistantDrawer';
import EmptyState from '../components/EmptyState';
import './AppBuilderPage.css';

let idCounter = 1;
const getId = (type) => `${type}-${idCounter++}-${Date.now()}`;
const EDITOR_LAYOUT_VERSION = 2;

/**
 * X/Y 좌표 입력칸.
 *
 * 예전에는 `value={pos.x || 0}` + `parseFloat(e.target.value)` 였다. 값을 지우는 순간
 * NaN 이 저장되고 화면에는 0 이 다시 찍혀서, 숫자를 고쳐 넣으려 하면 입력이 사용자와
 * 싸웠다(지우면 0 이 되살아나고 커서가 튄다). 편집 중에는 사용자가 친 문자열을 그대로
 * 두고, 유효한 숫자일 때만 반영한다.
 */
function PositionInput({ axis, component, onCommit }) {
  const stored = Number(component?.props?.position?.[axis]) || 0;
  const [draft, setDraft] = React.useState(null);

  // 다른 컴포넌트를 고르거나 캔버스에서 드래그해 값이 바뀌면 편집 상태를 버린다.
  React.useEffect(() => { setDraft(null); }, [component?.id, stored]);

  return (
    <input
      type="number"
      value={draft ?? stored}
      onChange={(e) => {
        const text = e.target.value;
        setDraft(text);
        const numeric = Number(text);
        if (text.trim() !== '' && Number.isFinite(numeric)) onCommit(axis, numeric);
      }}
      onBlur={() => setDraft(null)}
    />
  );
}



const PLAYGROUND_PRESETS = [
  { id: 'desktop', short: 'Desktop', label: 'Desktop (1024 × 768)', width: 1024, height: 768 },
  { id: 'tablet', short: 'Tablet', label: 'Tablet (768 × 1024)', width: 768, height: 1024 },
  { id: 'mobile', short: 'Mobile', label: 'Mobile (390 × 844)', width: 390, height: 844 },
];
const PRESET_ICONS = { desktop: Monitor, tablet: Tablet, mobile: Smartphone };

// View 탭 4개는 항상 보인다. 예전에는 생성 방식(Code/Blueprint)에 따라 로직·코드 탭이 나타나고
// 사라졌다 — 생성 방식은 AI 에게 주는 옵션이라 AI 드로어로 옮겼다(디자인 계획 §5.2).
const VIEW_TABS = [
  { id: 'design', label: '디자인', icon: PenTool },
  { id: 'logic', label: '로직', icon: Workflow },
  { id: 'code', label: '코드', icon: Braces },
  { id: 'preview', label: '미리보기', icon: Play },
];
const MOBILE_CANVAS_LABELS = { design: '캔버스', logic: '로직', code: '코드', preview: '미리보기' };
const ACTION_MODE_LABELS = { auto: '자동', workflow: '워크플로우', blueprint: 'Blueprint', script: 'JS', none: '없음' };

// Blueprint 노드 팔레트. 노드 색은 CSS(.palette-tile[data-node=…])가 타일에만 칠한다.
const LOGIC_PALETTE = [
  { type: 'triggerNode', label: 'Event Trigger', icon: 'bp-event-trigger' },
  { type: 'valueNode', label: 'Get Value', icon: 'bp-get-value' },
  { type: 'actionNode', label: 'UI Action', icon: 'bp-ui-action' },
  { type: 'submitNode', label: 'Submit (전송)', icon: 'bp-workflow-execute' },
  { type: 'outputNode', label: 'Output (출력)', icon: 'bp-ui-action' },
  { type: 'workflowNode', label: 'Workflow Execute', icon: 'bp-workflow-execute' },
  { type: 'codeNode', label: 'Custom JS Code', lucide: Code2 },
];

// <input type="color"> 는 hex 값만 받는다. 값이 비어 있을 때 스와치에 보일 색.
const SWATCH_FALLBACK = { page: '#f1f5f9', background: '#ffffff', text: '#000000' };

const DEFAULT_SECTIONS = { page: true, content: true, layout: true, style: false, behavior: true, visibility: false };

const readPref = (key, fallback) => {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
};
const writePref = (key, value) => {
  try { window.localStorage.setItem(key, JSON.stringify(value)); } catch { /* 저장 불가 환경은 무시 */ }
};

/** Inspector 섹션 — 접을 수 있고, 열림 상태는 호출한 쪽이 localStorage 에 기억한다. */
function InspectorSection({ title, meta, open, onToggle, children }) {
  return (
    <section className={`ab-section ${open ? 'open' : ''}`}>
      <button type="button" className="ab-section-head" onClick={onToggle} aria-expanded={open}>
        <ChevronRight size={14} className="chevron" />
        <span>{title}</span>
        {meta && <span className="ab-section-meta">{meta}</span>}
      </button>
      {open && <div className="ab-section-body">{children}</div>}
    </section>
  );
}

/** 색 필드: 스와치 + hex 텍스트. 비워두면 컴포넌트 기본색을 쓴다는 뜻이라 빈 값을 허용한다. */
function ColorField({ label, value, fallback = SWATCH_FALLBACK.text, onChange }) {
  const isHex = /^#[0-9a-fA-F]{6}$/.test(value || '');
  return (
    <div className="prop-group">
      <label>{label}</label>
      <div className="ab-color-field">
        <input type="color" value={isHex ? value : fallback} onChange={(e) => onChange(e.target.value)} aria-label={`${label} 선택`} />
        <input type="text" value={value || ''} placeholder="기본값" onChange={(e) => onChange(e.target.value)} aria-label={`${label} hex`} />
      </div>
    </div>
  );
}

// 커스텀 아이콘(assets/icons/ui/ui-*.svg)이 아직 없는 컴포넌트 타입은 lucide 로 표시한다.
// 카탈로그의 lucide 필드가 이 표의 키다.
const LUCIDE_FALLBACKS = { FileUp, CircleDot, SlidersHorizontal, Link2, FileCode, Table2, Gauge };

function ComponentTypeIcon({ type, size = 14, color }) {
  const entry = catalogEntry(type);
  if (entry?.icon) return <Icon name={entry.icon} size={size} color={color} />;
  const Fallback = entry?.lucide ? LUCIDE_FALLBACKS[entry.lucide] : null;
  if (Fallback) return <Fallback size={size} color={color} />;
  return <Icon name="ui-text" size={size} color={color} />;
}

const hierarchyCaption = (component) => {
  const source = component.props?.text || component.props?.label;
  if (!source || typeof source !== 'string') return '';
  const firstLine = source.split('\n')[0].trim();
  return firstLine.length > 14 ? ` "${firstLine.slice(0, 14)}…"` : ` "${firstLine}"`;
};

const ARROW_DELTAS = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
};

const clampCanvasDimension = (value, minimum, maximum, fallback) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.round(parsed)));
};

const numericPixelDimension = (value) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && /^\d+(\.\d+)?px$/.test(value.trim())) return Number.parseFloat(value);
  return null;
};

const componentContains = (component, componentId) => (
  component?.children?.some((child) => child.id === componentId || componentContains(child, componentId)) || false
);

export default function AppBuilderPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { appId } = useParams();
  const { token } = useAuth();
  const [components, setComponents] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [activeTab, setActiveTab] = useState('design');
  const history = useAppBuilderHistory(components, setComponents);
  const clipboardRef = React.useRef({ items: [], pastes: 0 });
  const [paletteQuery, setPaletteQuery] = useState('');
  const [appTitle, setAppTitle] = useState('My Visual App');
  const [appDescription, setAppDescription] = useState('');
  const [isAppDetailsOpen, setIsAppDetailsOpen] = useState(false);
  const [rootStyle, setRootStyle] = useState({ backgroundColor: '#f1f5f9', padding: '0px' });
  const [globalCss, setGlobalCss] = useState('');
  const [globalJs, setGlobalJs] = useState('');
  const [showDeployModal, setShowDeployModal] = useState(false);
  const [deployedUrl, setDeployedUrl] = useState('');
  const [snapLines, setSnapLines] = useState([]);
  const [workflowMappings, setWorkflowMappings] = useState({});
  const [canvas, setCanvas] = useState(DEFAULT_CANVAS);
  const [canvasDimensionDraft, setCanvasDimensionDraft] = useState({
    width: String(DEFAULT_CANVAS.width),
    height: String(DEFAULT_CANVAS.height),
  });
  const reactFlowInstanceRef = React.useRef(null);
  const [generationMode, setGenerationMode] = useState('code'); // 'code' or 'blueprint'
  const [generationWorkflowMode, setGenerationWorkflowMode] = useState('auto');
  const [generationWorkflowId, setGenerationWorkflowId] = useState('');
  const [builderTokenUsage, setBuilderTokenUsage] = useState({
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    requests: 0,
  });
  const [userWorkflows, setUserWorkflows] = useState([]);
  const [executionLogs, setExecutionLogs] = useState([]);
  const [isExecutionPanelOpen, setIsExecutionPanelOpen] = useState(false);
  const [executionPanelHeight, setExecutionPanelHeight] = useState(280);
  const executionLogEndRef = React.useRef(null);
  const resizeSnapshotRef = React.useRef(null);

  const [codeSubTab, setCodeSubTab] = useState('js');
  const [mobilePane, setMobilePane] = useState('canvas');
  const [showGrid, setShowGrid] = useState(() => readPref('ab.canvas.grid', false));
  const [fitToWidth, setFitToWidth] = useState(true);
  const [canvasScale, setCanvasScale] = useState(1);
  const canvasScrollRef = React.useRef(null);
  const titleControlRef = React.useRef(null);
  const [autoOpenLogs, setAutoOpenLogs] = useState(true);
  const autoOpenLogsRef = React.useRef(true);
  const [openSections, setOpenSections] = useState(() => ({ ...DEFAULT_SECTIONS, ...readPref('ab.inspector.sections', {}) }));
  const [savedFingerprint, setSavedFingerprint] = useState(null);
  // 불러오기/저장 직후 "지금 상태 = 저장된 상태"로 표시한다. 여러 setState 가 한 렌더에 모이므로
  // 플래그를 세우고 다음 렌더에서 fingerprint 를 읽는다.
  const [pendingSavedMark, setPendingSavedMark] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);

  useEffect(() => { autoOpenLogsRef.current = autoOpenLogs; }, [autoOpenLogs]);
  useEffect(() => { writePref('ab.canvas.grid', showGrid); }, [showGrid]);
  useEffect(() => { writePref('ab.inspector.sections', openSections); }, [openSections]);
  const toggleSection = (id) => setOpenSections((current) => ({ ...current, [id]: !(current[id] !== false) }));

  useEffect(() => {
    const query = window.matchMedia('(max-width: 900px)');
    const onChange = (event) => setIsMobile(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    if (!isAppDetailsOpen) return undefined;
    const onPointerDown = (event) => {
      if (titleControlRef.current && !titleControlRef.current.contains(event.target)) setIsAppDetailsOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [isAppDetailsOpen]);

  // 코드·미리보기 탭에는 팔레트/속성 pane 이 없다 — 모바일에서 빈 화면이 남지 않게 캔버스로 돌린다.
  useEffect(() => {
    if ((activeTab === 'code' || activeTab === 'preview') && mobilePane !== 'canvas') setMobilePane('canvas');
    if (activeTab === 'logic' && mobilePane === 'inspector') setMobilePane('canvas');
  }, [activeTab, mobilePane]);

  // 아트보드를 중앙 영역 폭에 맞춰 축소한다(AI 드로어를 열면 중앙이 500px 까지 좁아진다).
  // Rnd 에 같은 배율을 넘기므로 축소된 상태에서도 드래그·리사이즈가 정확하다.
  useEffect(() => {
    const element = canvasScrollRef.current;
    if (!element) return undefined;
    const update = () => {
      if (!fitToWidth) { setCanvasScale(1); return; }
      const available = element.clientWidth - (isMobile ? 24 : 48);
      const next = Math.min(1, available / canvas.width);
      setCanvasScale(Number.isFinite(next) && next > 0.1 ? Math.round(next * 1000) / 1000 : 1);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fitToWidth, canvas.width, activeTab, isMobile, mobilePane]);

  const handleExecutionEvent = useCallback((event) => {
    setExecutionLogs((logs) => [...logs, { id: `${Date.now()}-${logs.length}`, ...event }]);
    if (autoOpenLogsRef.current || event.level === 'error') setIsExecutionPanelOpen(true);
  }, []);

  useEffect(() => {
    if (isExecutionPanelOpen) executionLogEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [executionLogs, isExecutionPanelOpen]);

  useEffect(() => {
    setCanvasDimensionDraft({
      width: String(canvas.width),
      height: String(canvas.height),
    });
  }, [canvas.width, canvas.height]);

  useEffect(() => {
    const fetchWorkflows = async () => {
      try {
        const authHeaders = token ? { headers: { Authorization: `Bearer ${token}` } } : {};
        const res = await axios.get('/api/projects/my', authHeaders);
        setUserWorkflows(res.data || []);
      } catch (err) {
        console.error('Failed to fetch user workflows', err);
      }
    };
    if (token) {
      fetchWorkflows();
    }
  }, [token]);
  
  useEffect(() => {
    if (appId) {
      const loadApp = async () => {
        try {
          const authHeaders = token ? { headers: { Authorization: `Bearer ${token}` } } : {};
          const res = await axios.get(`/api/apps/custom/${appId}`, authHeaders);
          const data = res.data;

          if (data.title) setAppTitle(data.title);
          setAppDescription(data.description || data.ui_graph_data?.description || '');
          if (data.ui_graph_data) {
            const loadedCanvas = normalizeCanvas(data.ui_graph_data.canvas);
            const loadedMappings = normalizeWorkflowMappings(data.workflow_mappings);
            if (data.ui_graph_data.components) {
              const normalizedComponents = normalizeComponents(data.ui_graph_data.components, loadedCanvas);
              const editableComponents = data.ui_graph_data.editorLayoutVersion === EDITOR_LAYOUT_VERSION
                ? normalizedComponents
                : makeGeneratedLayoutEditable(normalizedComponents);
              setComponents(applyWorkflowMappings(
                editableComponents,
                loadedMappings
              ));
            }
            setCanvas(loadedCanvas);
            history.reset();
            setPendingSavedMark(true);
            if (data.ui_graph_data.rootStyle) setRootStyle(data.ui_graph_data.rootStyle);
            if (data.ui_graph_data.globalCss) setGlobalCss(data.ui_graph_data.globalCss);
            if (data.ui_graph_data.globalJs) setGlobalJs(data.ui_graph_data.globalJs);
          }
          if (data.logic_graph) {
            if (data.logic_graph.nodes) setLogicNodes(data.logic_graph.nodes);
            if (data.logic_graph.edges) setLogicEdges(data.logic_graph.edges);
          }
          setWorkflowMappings(normalizeWorkflowMappings(data.workflow_mappings));
        } catch (err) {
          console.error("Failed to load custom app", err);
        }
      };
      loadApp();
    } else if (location.state?.initialAppData) {
      const init = location.state.initialAppData;
      const initialCanvas = normalizeCanvas(init.canvas);
      const initialMappings = normalizeWorkflowMappings(init.workflowMappings || init.workflow_mappings);
      if (init.components) {
        const normalizedComponents = normalizeComponents(init.components, initialCanvas);
        const editableComponents = init.editorLayoutVersion === EDITOR_LAYOUT_VERSION
          ? normalizedComponents
          : makeGeneratedLayoutEditable(normalizedComponents);
        setComponents(applyWorkflowMappings(editableComponents, initialMappings));
      }
      if (init.rootStyle) setRootStyle(init.rootStyle);
      if (init.globalCss) setGlobalCss(init.globalCss);
      if (init.globalJs) setGlobalJs(init.globalJs);
      if (init.title) setAppTitle(init.title);
      if (init.description) setAppDescription(init.description);
      setCanvas(initialCanvas);
      setWorkflowMappings(initialMappings);
      history.reset();
      setPendingSavedMark(true);
    }
    // history 는 매 렌더마다 새 객체지만 reset 은 안정적인 콜백이다 — 불러오기 시점에만 돌면 된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, token, location.state]);

  // 되돌리기·AI 재생성 등으로 트리가 바뀌면 사라진 컴포넌트가 선택에 남지 않게 한다.
  useEffect(() => {
    setSelectedIds((ids) => {
      const kept = ids.filter((id) => findComponent(components, id));
      return kept.length === ids.length ? ids : kept;
    });
  }, [components]);

  // Logic Blueprint State
  const [logicNodes, setLogicNodes, onLogicNodesChange] = useNodesState([]);
  const [logicEdges, setLogicEdges, onLogicEdgesChange] = useEdgesState([]);

  // AI Assistant State
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', content: '안녕하세요! AI 앱 빌더입니다. 원하시는 앱의 형태나 기능을 말씀해주시면 자동으로 만들어 드릴게요. (예: 고객 문의를 입력받아 DB에 저장하는 폼 만들어줘)' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const handleSendChatMessage = async () => {
    if (!chatInput.trim() || isChatLoading) return;
    if (generationWorkflowMode === 'existing' && !generationWorkflowId) {
      setChatMessages((messages) => [
        ...messages,
        { role: 'assistant', content: '사용할 기존 Workflow를 먼저 선택해주세요.' },
      ]);
      return;
    }
    const userMessage = chatInput.trim();
    setChatInput('');
    const newMessages = [...chatMessages, { role: 'user', content: userMessage }];
    setChatMessages(newMessages);
    setIsChatLoading(true);

    try {
      const payload = {
        app_id: appId || undefined,
        prompt: userMessage,
        generate_mode: generationMode,
        workflow_mode: generationWorkflowMode,
        existing_workflow_id: generationWorkflowMode === 'existing' ? Number(generationWorkflowId) : undefined,
        current_state: {
          title: appTitle,
          description: appDescription,
          ui_graph_data: { components, rootStyle, globalCss, globalJs, canvas, description: appDescription },
          page_settings: { canvas: normalizeCanvas(canvas), rootStyle },
          generation_options: {
            workflow_mode: generationWorkflowMode,
            existing_workflow_id: generationWorkflowMode === 'existing' ? generationWorkflowId : null,
          },
          logic_graph: { nodes: logicNodes, edges: logicEdges },
          workflow_mappings: workflowMappings
        }
      };

      const res = await axios.post('/api/builder/generate_app', payload, {
        headers: { Authorization: `Bearer ${token}` }
      });

      const { reply, ui_graph_data, logic_graph, workflow_mappings, new_title, token_usage } = res.data;
      if (token_usage) {
        setBuilderTokenUsage((current) => ({
          input_tokens: current.input_tokens + Number(token_usage.input_tokens || 0),
          output_tokens: current.output_tokens + Number(token_usage.output_tokens || 0),
          total_tokens: current.total_tokens + Number(token_usage.total_tokens || 0),
          requests: current.requests + 1,
        }));
      }
      const nextMappings = normalizeWorkflowMappings({ ...workflowMappings, ...(workflow_mappings || {}) });

      if (new_title) setAppTitle(new_title);

      let finalComponents = components;
      let finalCanvas = normalizeCanvas(canvas);

      if (ui_graph_data) {
        const generatedCanvas = normalizeCanvas({ ...canvas, ...(ui_graph_data.canvas || {}) });
        finalCanvas = generatedCanvas;
        setCanvas(generatedCanvas);
        if (ui_graph_data.components) {
          const positioned = applyWorkflowMappings(
            makeGeneratedLayoutEditable(normalizeComponents(ui_graph_data.components, generatedCanvas)),
            nextMappings
          );
          finalComponents = positioned;
          setComponents(positioned);
        }
        if (ui_graph_data.rootStyle) setRootStyle(ui_graph_data.rootStyle);
        if (ui_graph_data.globalCss) setGlobalCss(ui_graph_data.globalCss);
        if (ui_graph_data.globalJs) setGlobalJs(ui_graph_data.globalJs);
      }
      
      if (logic_graph) {
        if (logic_graph.nodes) setLogicNodes(logic_graph.nodes);
        if (logic_graph.edges) setLogicEdges(logic_graph.edges);
      }
      
      setWorkflowMappings(nextMappings);

      // Auto-save if this is a newly generated app (appId is undefined/null)
      if (!appId) {
        try {
          const autoSavePayload = {
            app_id: undefined,
            app_name: new_title || appTitle || 'Untitled App',
            ui_graph_data: {
              components: finalComponents,
              canvas: finalCanvas,
              description: appDescription,
              editorLayoutVersion: EDITOR_LAYOUT_VERSION,
              rootStyle: ui_graph_data?.rootStyle || rootStyle,
              globalCss: ui_graph_data?.globalCss || globalCss,
              globalJs: ui_graph_data?.globalJs || globalJs
            },
            logic_graph: logic_graph || { nodes: logicNodes, edges: logicEdges },
            workflow_mappings: nextMappings
          };
          const saveRes = await axios.post('/api/builder/save', autoSavePayload, {
            headers: { Authorization: `Bearer ${token}` }
          });
          const newAppId = saveRes.data.id || saveRes.data.app_id;
          if (newAppId) {
            navigate(`/app-builder/${newAppId}`, { replace: true });
          }
        } catch (saveErr) {
          console.error('Auto-save failed:', saveErr);
        }
      }

      setChatMessages([...newMessages, { role: 'assistant', content: reply || '요청하신 내용을 반영하여 앱 구성을 업데이트했습니다.' }]);
    } catch (err) {
      console.error('Failed to generate app:', err);
      const errorDetail = err.response?.data?.detail || err.message || '알 수 없는 오류';
      setChatMessages([...newMessages, {
        role: 'assistant',
        content: `앱 생성 중 오류가 발생했습니다: ${errorDetail}`
      }]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const onLogicConnect = useCallback((params) => {
    if (!isValidLogicConnection(params)) {
      alert('빨간 실행 포트끼리 또는 초록 데이터 포트끼리 연결해주세요.', 'warning');
      return;
    }
    setLogicEdges((edges) => addEdge(params, edges));
  }, [setLogicEdges]);

  // Inject components and onChange into logic nodes data
  const processedLogicNodes = logicNodes.map(node => ({
    ...node,
    data: {
      ...node.data,
      components, // Pass current UI components to populate dropdowns
      workflows: userWorkflows, // Submit 노드의 워크플로우 선택용
      onChange: (id, key, value) => {
        setLogicNodes(nds => nds.map(n => {
          if (n.id === id) {
            n.data = { ...n.data, [key]: value };
          }
          return n;
        }));
      }
    }
  }));

  const handleDragStartLogic = (e, type) => {
    e.dataTransfer.setData('application/reactflow', type);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleLogicDelete = useCallback(() => {
    setLogicNodes(nds => nds.filter(n => !n.selected));
    setLogicEdges(eds => eds.filter(e => !e.selected));
  }, [setLogicNodes, setLogicEdges]);

  const handleDeleteSelected = useCallback(() => {
    if (selectedIds.length === 0) return;
    setComponents(prev => {
      let comps = [...prev];
      selectedIds.forEach(sid => {
        comps = removeComponent(comps, sid);
      });
      return comps;
    });
    setSelectedIds([]);
  }, [selectedIds]);

  const handleDuplicateSelected = useCallback(() => {
    if (selectedIds.length === 0) return;
    const result = duplicateComponents(components, selectedIds, getId);
    setComponents(result.components);
    setSelectedIds(result.newIds);
  }, [components, selectedIds]);

  const handleCopySelected = useCallback(() => {
    if (selectedIds.length === 0) return;
    const items = topLevelSelection(components, selectedIds)
      .map((id) => findComponent(components, id))
      .filter(Boolean)
      .map((component) => JSON.parse(JSON.stringify(component)));
    clipboardRef.current = { items, pastes: 0 };
  }, [components, selectedIds]);

  const handlePaste = useCallback(() => {
    const { items, pastes } = clipboardRef.current;
    if (!items.length) return;
    // 같은 조각을 여러 번 붙이면 매번 조금씩 더 비껴 놓아 겹쳐 쌓이지 않게 한다.
    const offset = 20 * (pastes + 1);
    const result = pasteComponents(components, items, getId, { x: offset, y: offset });
    clipboardRef.current = { items, pastes: pastes + 1 };
    setComponents(result.components);
    setSelectedIds(result.newIds);
  }, [components]);

  const handleReorder = useCallback((direction) => {
    if (selectedIds.length !== 1) return;
    setComponents((prev) => reorderComponent(prev, selectedIds[0], direction));
  }, [selectedIds]);

  const handleAlign = (mode) => setComponents((prev) => alignComponents(prev, selectedIds, mode));
  const handleDistribute = (axis) => setComponents((prev) => distributeComponents(prev, selectedIds, axis));
  const handleMatchSize = (dimension) => setComponents((prev) => matchSize(prev, selectedIds, dimension));

  /**
   * 저장과 배포는 같은 API 를 부른다. 차이는 배포가 앱 URL 모달을 여는 것뿐이다 — 예전 "저장 및
   * 배포" 버튼 하나였을 때는 저장만 하고 싶어도 배포 모달을 봐야 했다(디자인 계획 §5.2).
   */
  const persistApp = useCallback(async ({ deploy = false } = {}) => {
    if (isSaving) return;
    setIsSaving(true);
    try {
      const componentMappings = {};
      const componentIds = new Set(collectIds(components));
      const walk = (comps) => {
        comps.forEach((c) => {
          if (c.props?.workflowId) componentMappings[c.id] = { projectId: c.props.workflowId };
          if (c.children) walk(c.children);
        });
      };
      walk(components);
      const normalizedMappings = Object.fromEntries(
        Object.entries(normalizeWorkflowMappings({ ...workflowMappings, ...componentMappings }))
          .filter(([componentId]) => componentIds.has(componentId))
      );
      const savedCanvas = normalizeCanvas(canvas);

      const payload = {
        app_id: appId,
        app_name: appTitle || 'Untitled App',
        ui_graph_data: {
          components,
          description: appDescription,
          rootStyle,
          globalCss,
          globalJs,
          canvas: savedCanvas,
          editorLayoutVersion: EDITOR_LAYOUT_VERSION,
        },
        logic_graph: { nodes: logicNodes, edges: logicEdges },
        workflow_mappings: normalizedMappings,
      };

      const res = await axios.post('/api/builder/save', payload, {
        headers: { Authorization: `Bearer ${token || localStorage.getItem('token')}` },
      });
      setWorkflowMappings(normalizedMappings);
      setCanvas(savedCanvas);
      setPendingSavedMark(true);

      const savedId = res.data.id || res.data.app_id || appId;
      if (!appId && savedId) navigate(`/app-builder/${savedId}`, { replace: true });

      if (deploy) {
        setDeployedUrl(`${window.location.origin}/custom-app/${savedId}`);
        setShowDeployModal(true);
      }
    } catch (err) {
      console.error(err);
      handleExecutionEvent({
        level: 'error',
        message: `저장 실패: ${err.response?.data?.detail || err.message}`,
        details: null,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setIsSaving(false);
    }
  }, [
    isSaving, components, workflowMappings, canvas, appId, appTitle, appDescription, rootStyle, globalCss, globalJs,
    logicNodes, logicEdges, token, navigate, handleExecutionEvent,
  ]);

  React.useEffect(() => {
    const handleKeyDown = (e) => {
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();

      // 저장은 입력 중이어도 동작해야 한다 — 속성 패널에서 타이핑하다 바로 Ctrl+S 를 누른다.
      if (mod && key === 's') {
        e.preventDefault();
        persistApp({ deploy: false });
        return;
      }

      const activeTag = document.activeElement?.tagName?.toUpperCase();
      if (activeTag === 'INPUT' || activeTag === 'TEXTAREA' || activeTag === 'SELECT') {
        return; // Ignore if user is typing
      }

      if (e.key === 'Delete' || e.key === 'Backspace') {
        if (activeTab === 'logic') {
          handleLogicDelete();
        } else if (activeTab === 'design' && selectedIds.length > 0) {
          e.preventDefault();
          handleDeleteSelected();
        }
        return;
      }

      if (activeTab !== 'design') return;

      if (mod && key === 'z') {
        e.preventDefault();
        if (e.shiftKey) history.redo(); else history.undo();
        return;
      }
      if (mod && key === 'y') {
        e.preventDefault();
        history.redo();
        return;
      }
      if (mod && key === 'a') {
        e.preventDefault();
        setSelectedIds(components.map((component) => component.id));
        return;
      }
      if (mod && key === 'v') {
        e.preventDefault();
        handlePaste();
        return;
      }
      if (e.key === 'Escape') {
        setSelectedIds([]);
        return;
      }
      if (selectedIds.length === 0) return;

      if (mod && key === 'd') {
        e.preventDefault();
        handleDuplicateSelected();
        return;
      }
      if (mod && key === 'c') {
        e.preventDefault();
        handleCopySelected();
        return;
      }
      if (mod && (e.key === ']' || e.key === '[')) {
        e.preventDefault();
        const forward = e.key === ']';
        handleReorder(forward ? (e.shiftKey ? 'front' : 'forward') : (e.shiftKey ? 'back' : 'backward'));
        return;
      }
      if (ARROW_DELTAS[e.key]) {
        e.preventDefault();
        const step = e.shiftKey ? 10 : 1;
        const [dx, dy] = ARROW_DELTAS[e.key];
        setComponents((prev) => nudgeComponents(prev, selectedIds, dx * step, dy * step));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    selectedIds, components, activeTab, history, persistApp,
    handleDeleteSelected, handleLogicDelete, handleDuplicateSelected, handleCopySelected, handlePaste, handleReorder,
  ]);

  const handleDropOnLogicCanvas = (e) => {
    e.preventDefault();
    const type = e.dataTransfer.getData('application/reactflow');
    if (!type) return;
    
    const position = reactFlowInstanceRef.current
      ? reactFlowInstanceRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY })
      : { x: e.clientX, y: e.clientY };

    const nodeId = `logic-${Date.now()}`;
    const defaultData = {
      triggerNode: { eventType: 'onClick' },
      valueNode: { propertyType: 'value' },
      actionNode: { actionType: 'setText' },
      workflowNode: { projectId: '' },
      codeNode: { jsCode: 'return payload;' },
      submitNode: { projectId: '', fields: [] },
      outputNode: { componentId: '', resultPath: '', format: 'text' },
    };
    const newNode = {
      id: nodeId,
      type,
      position,
      data: { id: nodeId, ...(defaultData[type] || {}) }
    };
    setLogicNodes(nds => nds.concat(newNode));
  };

  const handleTransformStart = useCallback((id, transformType) => {
    if (transformType !== 'resize') return;
    const component = findComponent(components, id);
    resizeSnapshotRef.current = component
      ? { id, component: JSON.parse(JSON.stringify(component)) }
      : null;
  }, [components]);

  const handleSelect = (comp, isMulti = false) => {
    if (!comp) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(prev => {
      if (isMulti) {
        if (prev.includes(comp.id)) return prev.filter(id => id !== comp.id);
        return [...prev, comp.id];
      }
      return [comp.id];
    });
  };

  const selectedComponent = selectedIds.length === 1 ? findComponent(components, selectedIds[0]) : null;
  const selectedButtonHasBlueprintTrigger = selectedComponent?.type === 'button'
    && logicNodes.some((node) => node.type === 'triggerNode' && node.data?.componentId === selectedComponent.id && (node.data?.eventType || 'onClick') === 'onClick');
  const selectedButtonActionMode = selectedComponent?.type === 'button'
    ? inferButtonActionMode(selectedComponent.props, selectedButtonHasBlueprintTrigger)
    : 'none';
  // Click Action 이 Blueprint/Automatic 이 아니면 연결해둔 트리거는 실행되지 않는다.
  // 이 드롭다운은 저장된 값이 아니라 "추론된 값"을 보여주기 때문에, 사용자는 자기가
  // 고르지도 않은 모드 때문에 트리거가 무시되는 걸 알아채기 어렵다.
  const selectedButtonTriggerIgnored = selectedButtonHasBlueprintTrigger
    && !['blueprint', 'auto'].includes(selectedButtonActionMode);

  const handleDragStart = (e, type) => {
    e.dataTransfer.setData('application/json', JSON.stringify({ type }));
    e.dataTransfer.effectAllowed = 'copy';
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  };

  const handleDropOnCanvas = (e) => {
    e.preventDefault();
    e.stopPropagation(); 
    const data = e.dataTransfer.getData('application/json');
    if (!data) return;
    try {
      const { type } = JSON.parse(data);
      const canvasRect = e.currentTarget.getBoundingClientRect();
      // 아트보드가 축소돼 있으면 화면 픽셀을 아트보드 좌표로 되돌린다.
      const x = (e.clientX - canvasRect.left) / canvasScale;
      const y = (e.clientY - canvasRect.top) / canvasScale;

      const newComp = createNewComponent(type, x, y);
      setComponents(prev => [...prev, newComp]);
      setSelectedIds([newComp.id]);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDropOnContainer = (parentId, type, dropX, dropY) => {
    const newComp = createNewComponent(type, dropX, dropY);
    setComponents(prev => updateComponent(prev, parentId, (parent) => {
      if (!parent.children) parent.children = [];
      parent.children.push(newComp);
      return parent;
    }));
    setSelectedIds([newComp.id]);
  };

  const createNewComponent = (type, x = 0, y = 0) => {
    const defaultSize = defaultSizeFor(type);
    const { style: defaultStyle = {}, ...defaultProps } = defaultPropsFor(type, Date.now());
    const base = {
      id: getId(type),
      type,
      props: {
        ...defaultProps,
        position: {
          x: Math.max(0, Math.min(x, canvas.width - defaultSize.width)),
          y: Math.max(0, y),
        },
        style: { width: `${defaultSize.width}px`, height: `${defaultSize.height}px`, ...defaultStyle },
      },
    };
    if (type === 'container') base.children = [];
    return base;
  };

  // 모바일에는 드래그 앤 드롭이 없다 — 팔레트 항목을 탭하면 캔버스에 놓고 캔버스 pane 으로 간다.
  const handlePaletteTap = (type) => {
    const newComp = createNewComponent(type, 24, 24 + components.length * 24);
    setComponents((prev) => [...prev, newComp]);
    setSelectedIds([newComp.id]);
    setMobilePane('canvas');
  };

  const handleUpdateTransform = useCallback((id, transform, isShiftKey, isDragging) => {
    let newX = transform.x !== undefined ? transform.x : null;
    let newY = transform.y !== undefined ? transform.y : null;
    
    let activeLines = [];

    if (isShiftKey && isDragging) {
      const snapThreshold = 10;
      const canvasWidth = canvas.width;
      const canvasHeight = canvas.height;
      const centerX = canvasWidth / 2;
      const centerY = canvasHeight / 2;

      const checkSnap = (val, target, type) => {
        if (val !== null && Math.abs(val - target) < snapThreshold) {
          activeLines.push({ type, pos: target });
          return target;
        }
        return val;
      };

      // Snap to canvas center
      newX = checkSnap(newX, centerX, 'vertical');
      newY = checkSnap(newY, centerY, 'horizontal');

      // Snap to other components (simplified, top-left based)
      const extractPositions = (comps) => {
        let pos = [];
        comps.forEach(c => {
          if (c.id !== id && c.props.position) {
            pos.push(c.props.position);
          }
          if (c.children) pos = pos.concat(extractPositions(c.children));
        });
        return pos;
      };

      const otherPositions = extractPositions(components);
      otherPositions.forEach(p => {
        newX = checkSnap(newX, p.x, 'vertical');
        newY = checkSnap(newY, p.y, 'horizontal');
      });
    }

    setSnapLines(isDragging ? activeLines : []);
    const activeResizeSnapshot = resizeSnapshotRef.current?.id === id
      ? resizeSnapshotRef.current.component
      : null;

    setComponents(prev => {
      let newComps = [...prev];
      const isMultiMoving = selectedIds.includes(id) && selectedIds.length > 1;

      if (isMultiMoving && transform.deltaX !== undefined && transform.deltaY !== undefined) {
        const draggedComponent = findComponent(newComps, id);
        selectedIds.forEach(sid => {
          if (sid === id || componentContains(draggedComponent, sid)) return;
          newComps = updateComponent(newComps, sid, (c) => {
            c.props = { ...(c.props || {}) };
            c.props.position = {
              x: (c.props.position?.x || 0) + transform.deltaX, 
              y: (c.props.position?.y || 0) + transform.deltaY 
            };
            return c;
          });
        });
      }

      newComps = updateComponent(newComps, id, (comp) => {
        comp.props = { ...(comp.props || {}) };
        if (newX !== null || newY !== null) {
          comp.props.position = { 
            x: newX !== null ? newX : (comp.props.position?.x || 0), 
            y: newY !== null ? newY : (comp.props.position?.y || 0) 
          };
        }
        if (transform.width !== undefined || transform.height !== undefined) {
          comp.props.style = { ...(comp.props.style || {}) };
          if (transform.width !== undefined) comp.props.style.width = transform.width;
          if (transform.height !== undefined) comp.props.style.height = transform.height;

          if (activeResizeSnapshot?.children?.length) {
            const originalWidth = numericPixelDimension(activeResizeSnapshot.props?.style?.width);
            const originalHeight = numericPixelDimension(activeResizeSnapshot.props?.style?.height);
            const resizedWidth = numericPixelDimension(transform.width) ?? originalWidth;
            const resizedHeight = numericPixelDimension(transform.height) ?? originalHeight;
            const scaleX = originalWidth && resizedWidth ? resizedWidth / originalWidth : 1;
            const scaleY = originalHeight && resizedHeight ? resizedHeight / originalHeight : 1;
            comp.children = scaleDescendantGeometry(activeResizeSnapshot.children, scaleX, scaleY);
          }
        }
        return comp;
      });

      return newComps;
    });
    if (!isDragging && (transform.width !== undefined || transform.height !== undefined)) {
      resizeSnapshotRef.current = null;
    }
  }, [canvas, components, selectedIds]);

  const updateSelectedData = (key, value, isStyle = false) => {
    if (selectedIds.length !== 1) return;
    const sId = selectedIds[0];
    setComponents(prev => updateComponent(prev, sId, (comp) => {
      comp.props = { ...(comp.props || {}) };
      if (key === 'x' || key === 'y') {
        // 입력칸을 비우면 parseFloat('') 이 NaN 이 된다. 그대로 저장하면 Rnd 가 위치를 잃고,
        // 다시 불러올 때 normalizeComponents 가 "좌표 없음"으로 보고 자동 배치로 되돌린다
        // — 사용자가 맞춰놓은 위치가 통째로 사라진다.
        const numeric = Number(value);
        comp.props.position = {
          ...comp.props.position,
          [key]: Number.isFinite(numeric) ? numeric : (comp.props.position?.[key] ?? 0),
        };
      } else if (isStyle) {
        if ((key === 'width' || key === 'height') && comp.children?.length) {
          const previous = numericPixelDimension(comp.props?.style?.[key]);
          const next = numericPixelDimension(value);
          if (previous && next) {
            comp.children = scaleDescendantGeometry(
              comp.children,
              key === 'width' ? next / previous : 1,
              key === 'height' ? next / previous : 1
            );
          }
        }
        comp.props.style = { ...comp.props.style, [key]: value };
      } else {
        comp.props[key] = value;
      }
      return comp;
    }));
  };

  const updateComponentProp = (id, propName, value) => {
    setComponents(prev => updateComponent(prev, id, (comp) => {
      comp.props = { ...comp.props, [propName]: value };
      return comp;
    }));
  };

  const updateSelectedWorkflow = (projectId) => {
    if (selectedIds.length !== 1) return;
    const componentId = selectedIds[0];
    updateSelectedData('workflowId', projectId);
    setWorkflowMappings((previous) => {
      const next = { ...normalizeWorkflowMappings(previous) };
      if (projectId) next[componentId] = { ...(next[componentId] || {}), projectId: String(projectId) };
      else delete next[componentId];
      return next;
    });
    // 워크플로우를 고르면 Trigger → Submit → Output 노드를 만들어준다(백로그 16). 실행은
    // Blueprint 모델 하나로 통일되고, 사용자는 Blueprint 탭에서 만들어진 노드를 그대로
    // 보고 고칠 수 있다. 이미 이 버튼의 트리거가 있으면 Submit 의 workflow 만 갱신한다.
    if (projectId) {
      const chain = buildSubmitChain(componentId, projectId, logicNodes, logicEdges);
      setLogicNodes(chain.nodes);
      setLogicEdges(chain.edges);
    }
  };

  const findAbsolutePosition = (items, componentId, parentPosition = { x: 0, y: 0 }) => {
    for (const item of items) {
      const position = item.props?.position || { x: 0, y: 0 };
      const absolute = {
        x: parentPosition.x + (Number(position.x) || 0),
        y: parentPosition.y + (Number(position.y) || 0),
      };
      if (item.id === componentId) return absolute;
      if (item.children) {
        const found = findAbsolutePosition(item.children, componentId, absolute);
        if (found) return found;
      }
    }
    return null;
  };

  const handleReparent = (draggedId, targetContainerId) => {
    setComponents(prev => {
      const draggedComponent = findComponent(prev, draggedId);
      const targetComponent = targetContainerId === 'root' ? null : findComponent(prev, targetContainerId);
      const containsTarget = (component) => component?.children?.some(
        (child) => child.id === targetContainerId || containsTarget(child)
      );
      if (!draggedComponent || containsTarget(draggedComponent)) return prev;
      if (targetContainerId !== 'root' && !['container', 'form'].includes(targetComponent?.type)) return prev;

      const draggedGlobalPosition = findAbsolutePosition(prev, draggedId);
      const targetGlobalPosition = targetContainerId === 'root'
        ? { x: 0, y: 0 }
        : findAbsolutePosition(prev, targetContainerId);
      let draggedComp = null;
      let newTree = JSON.parse(JSON.stringify(prev)); // Deep copy to avoid mutation issues
      
      const extractAndRemove = (list) => {
        for (let i = 0; i < list.length; i++) {
          if (list[i].id === draggedId) {
            draggedComp = list[i];
            list.splice(i, 1);
            return true;
          }
          if (list[i].children && extractAndRemove(list[i].children)) return true;
        }
        return false;
      };
      extractAndRemove(newTree);
      
      if (!draggedComp) return prev;

      draggedComp.props = { ...(draggedComp.props || {}) };
      draggedComp.props.position = {
        x: Math.max(0, (draggedGlobalPosition?.x || 0) - (targetGlobalPosition?.x || 0)),
        y: Math.max(0, (draggedGlobalPosition?.y || 0) - (targetGlobalPosition?.y || 0)),
      };

      let inserted = false;
      if (targetContainerId === 'root') {
        newTree.push(draggedComp);
        inserted = true;
      } else {
        const insertToTarget = (list) => {
          for (let i = 0; i < list.length; i++) {
            if (list[i].id === targetContainerId && (list[i].type === 'container' || list[i].type === 'form')) {
              if (!list[i].children) list[i].children = [];
              list[i].children.push(draggedComp);
              inserted = true;
              return true;
            }
            if (list[i].children && insertToTarget(list[i].children)) return true;
          }
          return false;
        };
        insertToTarget(newTree);
      }

      if (!inserted) newTree.push(draggedComp); // Fallback to root
      return newTree;
    });
  };

  const toggleVisibility = (component) => {
    updateComponentProp(component.id, 'visible', component.props?.visible === false);
  };

  const renderHierarchy = (comps, depth = 0) => {
    return comps.map(c => {
      const hidden = c.props?.visible === false;
      return (
      <div key={c.id}>
        <div 
          draggable
          onDragStart={(e) => {
            e.stopPropagation();
            e.dataTransfer.setData('application/hierarchy-id', c.id);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          onDrop={(e) => {
            e.stopPropagation();
            const draggedId = e.dataTransfer.getData('application/hierarchy-id');
            if (draggedId && draggedId !== c.id) {
              handleReparent(draggedId, c.id);
            }
          }}
          onClick={(e) => {
            e.stopPropagation();
            handleSelect(c, e.shiftKey || e.metaKey || e.ctrlKey);
          }} 
          className={`hierarchy-item ${selectedIds.includes(c.id) ? 'active' : ''} ${hidden ? 'hidden' : ''}`}
          style={{ paddingLeft: `${depth * 15 + 8}px` }}
        >
          <span className="hierarchy-label">
            <ComponentTypeIcon type={c.type} size={12} />
            <span>{c.type}<span className="hierarchy-caption">{hierarchyCaption(c)}</span></span>
          </span>
          <button
            type="button"
            className="hierarchy-eye"
            onClick={(e) => { e.stopPropagation(); toggleVisibility(c); }}
            title={hidden ? '표시' : '숨기기 (미리보기·배포에서 숨김)'}
            aria-label={hidden ? '표시' : '숨기기'}
          >
            {hidden ? <EyeOff size={12} /> : <Eye size={12} />}
          </button>
        </div>
        {c.children && renderHierarchy(c.children, depth + 1)}
      </div>
      );
    });
  };

  const filteredCatalog = filterCatalog(paletteQuery);
  const alignParent = selectedIds.length > 1 ? sharedParentId(components, selectedIds) : null;
  const componentCount = collectIds(components).length;
  const selectionTypeCounts = selectedIds.reduce((counts, id) => {
    const type = findComponent(components, id)?.type;
    if (type) counts[type] = (counts[type] || 0) + 1;
    return counts;
  }, {});
  const isInputLike = INPUT_COMPONENT_TYPES.includes(selectedComponent?.type);
  const isChangeBindable = ['input', 'textarea', 'dropdown', 'checkbox', 'radio', 'slider'].includes(selectedComponent?.type);
  const hasContentSection = isInputLike
    || ['button', 'text', 'terminal', 'link', 'image', 'markdown', 'table', 'progress'].includes(selectedComponent?.type);

  const copyToClipboard = (text) => {
    if (!text || !navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(text);
      window.setTimeout(() => setCopiedId((current) => (current === text ? null : current)), 1500);
    }).catch(() => {});
  };

  // 저장 여부 — 저장에 실리는 것만 fingerprint 에 넣는다. ReactFlow 가 노드에 덧붙이는
  // selected/dragging/measured 는 저장되지 않으므로 뺀다(안 그러면 노드를 클릭만 해도 "저장 안 됨").
  const appFingerprint = React.useMemo(() => JSON.stringify({
    components,
    rootStyle,
    globalCss,
    globalJs,
    canvas: normalizeCanvas(canvas),
    appTitle,
    appDescription,
    nodes: logicNodes.map((node) => ({ id: node.id, type: node.type, position: node.position, data: node.data })),
    edges: logicEdges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, sourceHandle: edge.sourceHandle, targetHandle: edge.targetHandle })),
  }), [components, rootStyle, globalCss, globalJs, canvas, appTitle, appDescription, logicNodes, logicEdges]);

  useEffect(() => {
    if (pendingSavedMark) {
      setSavedFingerprint(appFingerprint);
      setPendingSavedMark(false);
    }
  }, [pendingSavedMark, appFingerprint]);

  const isDirty = savedFingerprint !== null && appFingerprint !== savedFingerprint;

  const effectiveCanvas = resolveCanvas(components, canvas);
  const playgroundPreset = PLAYGROUND_PRESETS.find(
    (preset) => preset.width === canvas.width && preset.height === canvas.height
  )?.id || 'custom';

  const handlePlaygroundPresetChange = (presetId) => {
    const preset = PLAYGROUND_PRESETS.find((item) => item.id === presetId);
    if (preset) {
      setCanvas((current) => ({ ...current, width: preset.width, height: preset.height }));
    }
  };

  const commitCanvasDimension = (dimension) => {
    const value = dimension === 'width'
      ? clampCanvasDimension(canvasDimensionDraft[dimension], 320, 1920, canvas.width)
      : clampCanvasDimension(canvasDimensionDraft[dimension], 480, 3000, canvas.height);
    setCanvas((current) => ({ ...current, [dimension]: value }));
    setCanvasDimensionDraft((draft) => ({ ...draft, [dimension]: String(value) }));
  };

  return (
    <div className="builder-layout tool-shell">
      {globalCss && <style>{globalCss}</style>}

      {/* ── Tool Header — 워크플로우 에디터와 같은 문법(뒤로 / 정체 / View / 저장 / AI / 배포) ── */}
      <header className="header editor-header builder-header">
        <div className="editor-header-identity">
          <button className="editor-icon-button" onClick={() => navigate('/')} title="홈으로 돌아가기" aria-label="홈으로 돌아가기">
            <ArrowLeft size={18} />
          </button>

          <div className="editor-project-control" ref={titleControlRef}>
            <button
              className="project-title-btn"
              onClick={() => setIsAppDetailsOpen((open) => !open)}
              aria-expanded={isAppDetailsOpen}
              title="앱 이름과 설명"
            >
              <span className="editor-project-copy">
                <strong>{appTitle || 'Untitled App'}</strong>
                <small className={isDirty ? 'dirty' : ''}>
                  {isDirty ? '저장 안 됨' : '저장됨'} · 컴포넌트 {componentCount} · 노드 {logicNodes.length}
                </small>
              </span>
              <Settings size={15} />
            </button>

            {isAppDetailsOpen && (
              <div className="editor-project-popover">
                <div className="editor-popover-heading">
                  <strong>앱 정보</strong>
                  <span>이름과 설명을 관리합니다</span>
                </div>
                <label className="editor-field-label" htmlFor="app-details-title">앱 이름</label>
                <input
                  id="app-details-title"
                  className="editor-field-input"
                  type="text"
                  value={appTitle}
                  onChange={(e) => setAppTitle(e.target.value)}
                  placeholder="앱 이름"
                />
                <label className="editor-field-label" htmlFor="app-details-description">앱 설명</label>
                <textarea
                  id="app-details-description"
                  className="editor-field-input editor-field-textarea"
                  rows={4}
                  value={appDescription}
                  onChange={(e) => setAppDescription(e.target.value)}
                  placeholder="앱의 목적과 사용 방법을 기록하세요."
                />
              </div>
            )}
          </div>
        </div>

        <nav className="builder-view-tabs" role="tablist" aria-label="편집 화면">
          {VIEW_TABS.map((tab) => {
            const TabIcon = tab.icon;
            const selected = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={selected}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (tab.id === 'preview') setSelectedIds([]);
                }}
              >
                <TabIcon size={14} />
                {tab.label}
                {tab.id === 'logic' && logicNodes.length > 0 && <span className="builder-tab-badge">{logicNodes.length}</span>}
                {tab.id === 'code' && (globalJs.trim() || globalCss.trim()) && <span className="builder-tab-dot" aria-label="코드 있음" />}
              </button>
            );
          })}
        </nav>

        <div className="primary-action-container">
          {activeTab === 'design' && (
            <div className="builder-history-controls">
              <button className="editor-icon-button" onClick={history.undo} disabled={!history.canUndo} title="되돌리기 (Ctrl+Z)" aria-label="되돌리기">
                <Undo2 size={17} />
              </button>
              <button className="editor-icon-button" onClick={history.redo} disabled={!history.canRedo} title="다시 실행 (Ctrl+Shift+Z)" aria-label="다시 실행">
                <Redo2 size={17} />
              </button>
            </div>
          )}
          {executionLogs.length > 0 && (
            <button
              className={`editor-icon-button builder-log-toggle ${isExecutionPanelOpen ? 'active' : ''}`}
              onClick={() => setIsExecutionPanelOpen((open) => !open)}
              title="실행 로그"
              aria-label={`실행 로그 ${executionLogs.length}건`}
            >
              <TerminalSquare size={17} />
              <span className="builder-log-count">{executionLogs.length > 99 ? '99+' : executionLogs.length}</span>
            </button>
          )}
          <button
            className={`editor-icon-button ${isDirty ? 'editor-save-dirty' : ''}`}
            onClick={() => persistApp({ deploy: false })}
            disabled={isSaving}
            title={isDirty ? '저장되지 않은 변경사항 저장 (Ctrl+S)' : '저장됨 (Ctrl+S)'}
            aria-label={isDirty ? '저장되지 않은 변경사항 저장' : '저장됨'}
          >
            <Save size={17} />
          </button>
          <button
            className={`assistant-toggle-button ${isAssistantOpen ? 'active' : ''}`}
            onClick={() => setIsAssistantOpen(!isAssistantOpen)}
            title="AI 앱 빌더 어시스턴트"
            aria-label="AI 어시스턴트"
          >
            <Sparkles size={16} />
            <span className="assistant-toggle-label">AI 어시스턴트</span>
          </button>
          <button className="btn-run builder-deploy-btn" onClick={() => persistApp({ deploy: true })} disabled={isSaving} title="저장하고 앱 URL 을 받습니다">
            <Rocket size={16} />
            <span className="run-text">{isSaving ? '저장 중…' : '배포'}</span>
          </button>
        </div>
      </header>

      <div className="builder-workspace" data-mobile-pane={mobilePane}>
        {/* ── Palette (좌) ── */}
        {(activeTab === 'design' || activeTab === 'logic') && (
          <aside className="builder-sidebar-left" aria-label={activeTab === 'design' ? '컴포넌트 팔레트와 계층' : '로직 노드 팔레트'}>
            {activeTab === 'design' ? (
              <>
                <div className="builder-panel-section palette">
                  <div className="sidebar-title"><Shapes size={13} /> 컴포넌트</div>
                  <div className="palette-search">
                    <Search size={14} />
                    <input
                      value={paletteQuery}
                      onChange={(e) => setPaletteQuery(e.target.value)}
                      placeholder="컴포넌트 검색"
                      aria-label="컴포넌트 검색"
                    />
                    {paletteQuery && (
                      <button type="button" className="palette-clear" onClick={() => setPaletteQuery('')} aria-label="검색 지우기">
                        <X size={12} />
                      </button>
                    )}
                  </div>
                  <div className="builder-panel-scroll">
                    <div className="node-palette">
                      {filteredCatalog.length === 0 && <div className="palette-empty">일치하는 컴포넌트가 없습니다</div>}
                      {COMPONENT_CATEGORIES.map((category) => {
                        const entries = filteredCatalog.filter((entry) => entry.category === category.id);
                        if (entries.length === 0) return null;
                        return (
                          <React.Fragment key={category.id}>
                            <div className="palette-group-title">{category.label}</div>
                            {entries.map((entry) => (
                              <div
                                key={entry.type}
                                className="palette-item"
                                draggable
                                onDragStart={(e) => handleDragStart(e, entry.type)}
                                onClick={() => { if (isMobile) handlePaletteTap(entry.type); }}
                                role={isMobile ? 'button' : undefined}
                                title={isMobile ? `${entry.label} 추가` : `${entry.label} — 캔버스로 드래그`}
                              >
                                <span className={`palette-tile ${entry.accent ? 'accent' : ''}`}>
                                  <ComponentTypeIcon type={entry.type} size={15} />
                                </span>
                                {entry.label}
                              </div>
                            ))}
                          </React.Fragment>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="builder-panel-section grow">
                  <div className="sidebar-title">
                    <Icon name="ui-hierarchy" size={13} /> 계층
                    {componentCount > 0 && <span className="builder-tab-badge">{componentCount}</span>}
                  </div>
                  <div
                    className="builder-panel-scroll hierarchy-tree"
                    onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                    onDrop={(e) => {
                      e.stopPropagation();
                      const draggedId = e.dataTransfer.getData('application/hierarchy-id');
                      if (draggedId) handleReparent(draggedId, 'root');
                    }}
                  >
                    {components.length === 0 ? (
                      <div className="hierarchy-empty">아직 컴포넌트가 없어요</div>
                    ) : (
                      renderHierarchy(components)
                    )}
                  </div>
                </div>
              </>
            ) : (
              <div className="builder-panel-section grow">
                <div className="sidebar-title"><Workflow size={13} /> 로직 노드</div>
                <div className="builder-panel-scroll">
                  <div className="node-palette">
                    {LOGIC_PALETTE.map((entry) => (
                      <div
                        key={entry.type}
                        className="palette-item"
                        draggable
                        onDragStart={(e) => handleDragStartLogic(e, entry.type)}
                        title={`${entry.label} — 캔버스로 드래그`}
                      >
                        <span className="palette-tile" data-node-color data-node={entry.type}>
                          {entry.lucide ? <entry.lucide size={15} /> : <Icon name={entry.icon} size={15} />}
                        </span>
                        {entry.label}
                      </div>
                    ))}
                  </div>
                  <div className="builder-help-card">
                    <strong>Blueprint 사용법</strong>
                    1. <b>Event Trigger</b> 를 놓고 버튼(또는 입력)을 고릅니다.<br />
                    2. <b>Submit</b> 으로 워크플로우에 보내고 <b>Output</b> 으로 결과를 표시합니다.<br />
                    3. 빨간 포트끼리는 실행 순서, 초록 포트끼리는 데이터를 연결합니다.
                  </div>
                </div>
              </div>
            )}
          </aside>
        )}

        {/* ── Canvas (중앙) ── */}
        <main className="builder-center">
          {(activeTab === 'design' || activeTab === 'preview') && (
            <div className="builder-canvas-toolbar">
              {activeTab === 'design' ? (
                <>
                  <div className="builder-segmented" role="group" aria-label="캔버스 크기 프리셋">
                    {PLAYGROUND_PRESETS.map((preset) => {
                      const PresetIcon = PRESET_ICONS[preset.id];
                      return (
                        <button
                          key={preset.id}
                          className={playgroundPreset === preset.id ? 'active' : ''}
                          onClick={() => handlePlaygroundPresetChange(preset.id)}
                          title={preset.label}
                        >
                          {PresetIcon && <PresetIcon size={13} />}
                          <span>{preset.short}</span>
                        </button>
                      );
                    })}
                  </div>
                  <div className="builder-canvas-dims" title="캔버스 크기 (px)">
                    <input
                      type="number"
                      min="320"
                      max="1920"
                      value={canvasDimensionDraft.width}
                      onChange={(e) => setCanvasDimensionDraft((draft) => ({ ...draft, width: e.target.value }))}
                      onBlur={() => commitCanvasDimension('width')}
                      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
                      aria-label="캔버스 너비"
                    />
                    <span>×</span>
                    <input
                      type="number"
                      min="480"
                      max="3000"
                      value={canvasDimensionDraft.height}
                      onChange={(e) => setCanvasDimensionDraft((draft) => ({ ...draft, height: e.target.value }))}
                      onBlur={() => commitCanvasDimension('height')}
                      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
                      aria-label="캔버스 높이"
                      disabled={canvas.autoHeight !== false}
                    />
                  </div>
                  <button
                    className={`builder-toolbar-toggle ${canvas.autoHeight !== false ? 'active' : ''}`}
                    onClick={() => setCanvas((current) => ({ ...current, autoHeight: current.autoHeight === false }))}
                    title="컴포넌트가 아래로 넘치면 캔버스 높이를 자동으로 늘립니다"
                    aria-pressed={canvas.autoHeight !== false}
                  >
                    <Maximize2 size={13} /><span className="label">자동 높이</span>
                  </button>
                  <button
                    className={`builder-toolbar-toggle ${showGrid ? 'active' : ''}`}
                    onClick={() => setShowGrid((value) => !value)}
                    title="16px 격자 표시 (시각 보조 · 스냅은 Shift+드래그)"
                    aria-pressed={showGrid}
                  >
                    <Grid3x3 size={13} /><span className="label">격자</span>
                  </button>
                  <div className="spacer" />
                  <button
                    className={`builder-toolbar-toggle ${fitToWidth ? 'active' : ''}`}
                    onClick={() => setFitToWidth((value) => !value)}
                    title={fitToWidth ? '폭에 맞춰 축소 중 — 클릭하면 100%' : '100% — 클릭하면 폭에 맞춤'}
                    aria-pressed={fitToWidth}
                  >
                    <Scan size={13} /><span className="label">{Math.round(canvasScale * 100)}%</span>
                  </button>
                </>
              ) : (
                <>
                  <span className="builder-preview-badge"><Play size={12} /> 미리보기 · 상호작용 가능</span>
                  <span className="builder-code-hint">버튼을 눌러 Blueprint·워크플로우를 실제로 실행해 봅니다</span>
                  <div className="spacer" />
                  <button className="builder-toolbar-toggle" onClick={() => setActiveTab('design')}>
                    <PenTool size={13} /><span className="label">편집으로 돌아가기</span>
                  </button>
                </>
              )}
            </div>
          )}

          {activeTab === 'design' && (
            <div
              ref={canvasScrollRef}
              className={`builder-canvas-scroll ${showGrid ? 'grid' : ''}`}
              onClick={() => handleSelect(null)}
            >
              <div
                className="builder-artboard-frame"
                style={{ width: `${effectiveCanvas.width * canvasScale}px`, height: `${effectiveCanvas.height * canvasScale + 2}px` }}
              >
                <div
                  className={`canvas-area ${showGrid ? 'grid' : ''}`}
                  onDragOver={handleDragOver}
                  onDrop={handleDropOnCanvas}
                  style={{
                    width: `${effectiveCanvas.width}px`,
                    height: `${effectiveCanvas.height}px`,
                    transform: `scale(${canvasScale})`,
                  }}
                >
                  {snapLines.map((line, idx) => (
                    <div
                      key={idx}
                      className="builder-snap-line"
                      style={line.type === 'vertical'
                        ? { left: line.pos, top: 0, bottom: 0, width: '1px' }
                        : { top: line.pos, left: 0, right: 0, height: '1px' }}
                    />
                  ))}

                  {components.length === 0 ? (
                    <div className="builder-canvas-empty">
                      <EmptyState
                        illustration="empty-apps"
                        artWidth={150}
                        title="컴포넌트를 끌어다 놓으세요"
                        description="왼쪽 팔레트에서 드래그하거나, AI 어시스턴트에게 만들고 싶은 화면을 설명해 시작할 수 있어요."
                        action={(
                          <button type="button" className="ab-empty-action" onClick={(e) => { e.stopPropagation(); setIsAssistantOpen(true); }}>
                            <Sparkles size={15} /> AI 로 시작하기
                          </button>
                        )}
                      />
                    </div>
                  ) : (
                    <UIEngine
                      components={components}
                      globalJs={globalJs}
                      isPreview={false}
                      onSelectComponent={handleSelect}
                      onDropComponent={handleDropOnContainer}
                      onTransformStart={handleTransformStart}
                      onUpdateTransform={handleUpdateTransform}
                      selectedIds={selectedIds}
                      canvasWidth={effectiveCanvas.width}
                      canvasHeight={effectiveCanvas.height}
                      rootStyle={rootStyle}
                      editorScale={canvasScale}
                    />
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'logic' && (
            <div className="builder-flow-view" onDragOver={(e) => e.preventDefault()} onDrop={handleDropOnLogicCanvas}>
              <ReactFlow
                nodes={processedLogicNodes}
                edges={logicEdges}
                onNodesChange={onLogicNodesChange}
                onEdgesChange={onLogicEdgesChange}
                onConnect={onLogicConnect}
                nodeTypes={logicNodeTypes}
                onInit={(instance) => { reactFlowInstanceRef.current = instance; }}
                fitView
              >
                <Background color="var(--ab-border)" gap={16} />
                <Controls />
              </ReactFlow>
            </div>
          )}

          {activeTab === 'code' && (
            <div className="builder-code-view">
              <div className="builder-canvas-toolbar">
                <div className="builder-segmented" role="tablist" aria-label="코드 종류">
                  <button role="tab" aria-selected={codeSubTab === 'js'} className={codeSubTab === 'js' ? 'active' : ''} onClick={() => setCodeSubTab('js')}>
                    <Braces size={13} /> Global JS
                  </button>
                  <button role="tab" aria-selected={codeSubTab === 'css'} className={codeSubTab === 'css' ? 'active' : ''} onClick={() => setCodeSubTab('css')}>
                    <PenTool size={13} /> Global CSS
                  </button>
                </div>
                <span className="builder-code-hint">
                  {codeSubTab === 'js' ? (
                    <>핸들러 객체를 <code>return {'{ ... }'}</code> 하세요 · 사용 가능: <code>inputs</code> <code>appState</code> <code>setAppState</code> <code>runWorkflow</code></>
                  ) : (
                    <>속성 패널의 <code>CSS 클래스</code> 로 컴포넌트에 연결됩니다 · 편집 화면에도 바로 적용</>
                  )}
                </span>
              </div>
              {codeSubTab === 'js' ? (
                <textarea
                  value={globalJs}
                  onChange={(e) => setGlobalJs(e.target.value)}
                  placeholder={'return {\n  onSave: async () => {\n    const result = await runWorkflow(12, { text: inputs.message });\n    setAppState(\'result_text\', \'text\', result);\n  }\n};'}
                  spellCheck={false}
                  aria-label="Global JS"
                />
              ) : (
                <textarea
                  value={globalCss}
                  onChange={(e) => setGlobalCss(e.target.value)}
                  placeholder={'.primary-btn {\n  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);\n}'}
                  spellCheck={false}
                  aria-label="Global CSS"
                />
              )}
            </div>
          )}

          {activeTab === 'preview' && (
            <div ref={canvasScrollRef} className="builder-canvas-scroll">
              <div
                className="builder-artboard-frame"
                style={{ width: `${effectiveCanvas.width * canvasScale}px`, height: `${effectiveCanvas.height * canvasScale + 2}px` }}
              >
                <div
                  className="canvas-area preview"
                  style={{
                    width: `${effectiveCanvas.width}px`,
                    height: `${effectiveCanvas.height}px`,
                    transform: `scale(${canvasScale})`,
                  }}
                >
                  <UIEngine
                    components={components}
                    logicGraph={{ nodes: logicNodes, edges: logicEdges }}
                    globalJs={globalJs}
                    rootStyle={rootStyle}
                    isPreview={true}
                    canvasWidth={effectiveCanvas.width}
                    canvasHeight={effectiveCanvas.height}
                    onExecutionEvent={handleExecutionEvent}
                  />
                </div>
              </div>
            </div>
          )}

          {/* 다중 선택 툴바 — 에디터의 선택 툴바와 같은 모양 */}
          {activeTab === 'design' && selectedIds.length > 1 && (
            <div className="builder-selection-toolbar" role="toolbar" aria-label="선택 항목 정렬">
              <span className="builder-selection-count">{selectedIds.length}<small>개</small></span>
              <i />
              <button disabled={!alignParent} onClick={() => handleAlign('left')} title={alignParent ? '왼쪽 맞춤' : '같은 컨테이너 안에서만 정렬할 수 있어요'} aria-label="왼쪽 맞춤"><AlignStartVertical size={15} /></button>
              <button disabled={!alignParent} onClick={() => handleAlign('hcenter')} title="가로 중앙 맞춤" aria-label="가로 중앙 맞춤"><AlignCenterVertical size={15} /></button>
              <button disabled={!alignParent} onClick={() => handleAlign('right')} title="오른쪽 맞춤" aria-label="오른쪽 맞춤"><AlignEndVertical size={15} /></button>
              <i />
              <button disabled={!alignParent} onClick={() => handleAlign('top')} title="위 맞춤" aria-label="위 맞춤"><AlignStartHorizontal size={15} /></button>
              <button disabled={!alignParent} onClick={() => handleAlign('vcenter')} title="세로 중앙 맞춤" aria-label="세로 중앙 맞춤"><AlignCenterHorizontal size={15} /></button>
              <button disabled={!alignParent} onClick={() => handleAlign('bottom')} title="아래 맞춤" aria-label="아래 맞춤"><AlignEndHorizontal size={15} /></button>
              <i />
              <button disabled={!alignParent || selectedIds.length < 3} onClick={() => handleDistribute('horizontal')} title="가로 간격 균등 (3개 이상)" aria-label="가로 간격 균등"><AlignHorizontalDistributeCenter size={15} /></button>
              <button disabled={!alignParent || selectedIds.length < 3} onClick={() => handleDistribute('vertical')} title="세로 간격 균등 (3개 이상)" aria-label="세로 간격 균등"><AlignVerticalDistributeCenter size={15} /></button>
              <i />
              <button onClick={() => handleMatchSize('width')} title="너비 맞추기 (처음 선택한 것 기준)" aria-label="너비 맞추기"><StretchHorizontal size={15} /></button>
              <button onClick={() => handleMatchSize('height')} title="높이 맞추기 (처음 선택한 것 기준)" aria-label="높이 맞추기"><StretchVertical size={15} /></button>
              <i />
              <button onClick={handleDuplicateSelected} title="복제 (Ctrl+D)" aria-label="복제"><CopyPlus size={15} /></button>
              <button className="danger" onClick={handleDeleteSelected} title="삭제 (Del)" aria-label="삭제"><Trash2 size={15} /></button>
            </div>
          )}
        </main>

        {/* ── Inspector (우) ── */}
        {activeTab === 'design' && (
          <aside className="builder-sidebar-right" aria-label="속성">
            {selectedIds.length === 0 ? (
              <div className="properties-panel">
                <div className="ab-inspector-head">
                  <span className="ab-type-tile"><Monitor size={16} /></span>
                  <div className="ab-inspector-title">
                    <strong>페이지</strong>
                    <span className="ab-inspector-id"><span>{effectiveCanvas.width} × {effectiveCanvas.height}{canvas.autoHeight !== false ? ' · 자동 높이' : ''}</span></span>
                  </div>
                </div>

                <InspectorSection title="페이지 스타일" open={openSections.page !== false} onToggle={() => toggleSection('page')}>
                  <ColorField
                    label="배경색"
                    value={rootStyle.backgroundColor || ''}
                    fallback={SWATCH_FALLBACK.page}
                    onChange={(value) => setRootStyle({ ...rootStyle, backgroundColor: value })}
                  />
                  <div className="prop-group">
                    <label>안쪽 여백 (padding)</label>
                    <input type="text" value={rootStyle.padding || ''} placeholder="예: 24px" onChange={(e) => setRootStyle({ ...rootStyle, padding: e.target.value })} />
                  </div>
                  <div className="prop-hint"><Info size={13} /> 캔버스 크기와 프리셋은 캔버스 위 도구 막대에서 바꿉니다.</div>
                </InspectorSection>

                <div className="shortcut-legend">
                  <div><kbd>Ctrl</kbd>+<kbd>Z</kbd> / <kbd>Shift</kbd>+<kbd>Z</kbd> 되돌리기 · 다시 실행</div>
                  <div><kbd>Ctrl</kbd>+<kbd>S</kbd> 저장 · <kbd>Ctrl</kbd>+<kbd>D</kbd> 복제 · <kbd>Ctrl</kbd>+<kbd>C</kbd>/<kbd>V</kbd> 복사·붙여넣기</div>
                  <div><kbd>←↑→↓</kbd> 1px 이동 (<kbd>Shift</kbd> 10px) · <kbd>Shift</kbd>+드래그 스냅</div>
                  <div><kbd>Ctrl</kbd>+<kbd>]</kbd> / <kbd>[</kbd> 앞으로 · 뒤로 (<kbd>Shift</kbd> 맨 앞·맨 뒤)</div>
                  <div><kbd>Ctrl</kbd>+<kbd>A</kbd> 전체 선택 · <kbd>Esc</kbd> 선택 해제 · <kbd>Del</kbd> 삭제</div>
                </div>
              </div>
            ) : selectedIds.length > 1 ? (
              <div className="properties-panel">
                <div className="ab-inspector-summary">
                  <h3>{selectedIds.length}개 선택</h3>
                  <div className="ab-chip-row">
                    {Object.entries(selectionTypeCounts).map(([type, count]) => (
                      <span key={type} className="ab-chip">
                        <ComponentTypeIcon type={type} size={12} /> {catalogEntry(type)?.label || type}{count > 1 ? ` ×${count}` : ''}
                      </span>
                    ))}
                  </div>
                  <p>
                    정렬·간격·크기 맞추기는 캔버스 아래 선택 도구 막대에서 합니다.
                    {!alignParent && ' 지금은 서로 다른 컨테이너의 컴포넌트가 섞여 있어 정렬은 비활성입니다.'}
                  </p>
                  <div className="ab-inspector-footer inline">
                    <button type="button" className="ab-quiet-btn" onClick={handleDuplicateSelected}><CopyPlus size={14} /> 복제</button>
                    <button type="button" className="ab-quiet-btn danger" onClick={handleDeleteSelected}><Trash2 size={14} /> 선택 삭제</button>
                  </div>
                </div>
              </div>
            ) : selectedComponent ? (
              <div className="properties-panel">
                <div className="ab-inspector-head">
                  <span className="ab-type-tile"><ComponentTypeIcon type={selectedComponent.type} size={16} /></span>
                  <div className="ab-inspector-title">
                    <strong>{catalogEntry(selectedComponent.type)?.label || selectedComponent.type}</strong>
                    <button type="button" className="ab-inspector-id" onClick={() => copyToClipboard(selectedComponent.id)} title="id 복사 (Global JS 의 appState 키)">
                      <span>{selectedComponent.id}</span>
                      {copiedId === selectedComponent.id ? <Check size={11} /> : <Copy size={11} />}
                    </button>
                  </div>
                  <div className="ab-inspector-actions">
                    <button
                      type="button"
                      className={`ab-icon-btn ${selectedComponent.props?.visible === false ? 'active' : ''}`}
                      onClick={() => toggleVisibility(selectedComponent)}
                      title={selectedComponent.props?.visible === false ? '표시' : '숨기기 (미리보기·배포에서 숨김)'}
                      aria-label={selectedComponent.props?.visible === false ? '표시' : '숨기기'}
                    >
                      {selectedComponent.props?.visible === false ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                    <button type="button" className="ab-icon-btn" onClick={handleDuplicateSelected} title="복제 (Ctrl+D)" aria-label="복제"><CopyPlus size={15} /></button>
                    <button type="button" className="ab-icon-btn danger" onClick={handleDeleteSelected} title="삭제 (Del)" aria-label="삭제"><Trash2 size={15} /></button>
                  </div>
                </div>

                {/* 내용 */}
                {hasContentSection && (
                  <InspectorSection title="내용" open={openSections.content !== false} onToggle={() => toggleSection('content')}>
                    {['button', 'text', 'terminal', 'link'].includes(selectedComponent.type) && (
                      <div className="prop-group">
                        <label>텍스트</label>
                        <input type="text" value={selectedComponent.props.text || ''} onChange={(e) => updateSelectedData('text', e.target.value)} />
                      </div>
                    )}
                    {selectedComponent.type === 'text' && (
                      <label className="prop-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedComponent.props.style?.whiteSpace === 'normal'}
                          onChange={(e) => updateSelectedData('whiteSpace', e.target.checked ? 'normal' : 'nowrap', true)}
                        />
                        <span>여러 줄로 줄바꿈</span>
                      </label>
                    )}
                    {selectedComponent.type === 'link' && (
                      <>
                        <div className="prop-group">
                          <label>URL</label>
                          <input type="text" value={selectedComponent.props.href || ''} placeholder="https://..." onChange={(e) => updateSelectedData('href', e.target.value)} />
                        </div>
                        <label className="prop-checkbox">
                          <input type="checkbox" checked={selectedComponent.props.openInNewTab !== false} onChange={(e) => updateSelectedData('openInNewTab', e.target.checked)} />
                          <span>새 탭에서 열기</span>
                        </label>
                      </>
                    )}
                    {selectedComponent.type === 'image' && (
                      <div className="prop-group">
                        <label>이미지 URL</label>
                        <input type="text" value={selectedComponent.props.imageUrl || ''} placeholder="https://..." onChange={(e) => updateSelectedData('imageUrl', e.target.value)} />
                      </div>
                    )}
                    {selectedComponent.type === 'markdown' && (
                      <div className="prop-group">
                        <label>마크다운 (비우면 Output 결과만 표시)</label>
                        <textarea
                          rows="6"
                          value={selectedComponent.props.text || ''}
                          onChange={(e) => updateSelectedData('text', e.target.value)}
                          placeholder={'## 제목\n본문 **강조**\n- 항목'}
                        />
                      </div>
                    )}
                    {selectedComponent.type === 'table' && (
                      <>
                        <div className="prop-group">
                          <label>열 순서 (쉼표 구분 · 비우면 자동)</label>
                          <input type="text" value={selectedComponent.props.columns || ''} placeholder="예: 이름, 이메일, 상태" onChange={(e) => updateSelectedData('columns', e.target.value)} />
                        </div>
                        <div className="prop-group">
                          <label>데이터 없을 때 문구</label>
                          <input type="text" value={selectedComponent.props.emptyText || ''} onChange={(e) => updateSelectedData('emptyText', e.target.value)} />
                        </div>
                        <div className="prop-group">
                          <label>고정 데이터 (JSON 배열 · 비우면 Output 결과만 표시)</label>
                          <textarea
                            rows="5"
                            value={selectedComponent.props.text || ''}
                            onChange={(e) => updateSelectedData('text', e.target.value)}
                            placeholder='[{"이름": "홍길동", "점수": 90}]'
                          />
                        </div>
                      </>
                    )}
                    {selectedComponent.type === 'progress' && (
                      <>
                        <div className="prop-group">
                          <label>라벨</label>
                          <input type="text" value={selectedComponent.props.label || ''} onChange={(e) => updateSelectedData('label', e.target.value)} />
                        </div>
                        <div className="prop-row">
                          <div className="prop-group">
                            <label>초기 값</label>
                            <input type="number" value={selectedComponent.props.value ?? 0} onChange={(e) => updateSelectedData('value', Number(e.target.value))} />
                          </div>
                          <div className="prop-group">
                            <label>최대값</label>
                            <input type="number" min="1" value={selectedComponent.props.max ?? 100} onChange={(e) => updateSelectedData('max', Number(e.target.value))} />
                          </div>
                        </div>
                        <label className="prop-checkbox">
                          <input type="checkbox" checked={selectedComponent.props.showValue !== false} onChange={(e) => updateSelectedData('showValue', e.target.checked)} />
                          <span>퍼센트 표시</span>
                        </label>
                        <div className="prop-hint"><Info size={13} /> 스타일의 글자색이 막대, 배경색이 트랙 색입니다.</div>
                      </>
                    )}
                    {isInputLike && (
                      <>
                        <div className="prop-group">
                          <label>라벨</label>
                          <input type="text" value={selectedComponent.props.label || ''} onChange={(e) => updateSelectedData('label', e.target.value)} />
                        </div>
                        {selectedComponent.type === 'input' && (
                          <div className="prop-group">
                            <label>입력 종류</label>
                            <select value={selectedComponent.props.inputType || 'text'} onChange={(e) => updateSelectedData('inputType', e.target.value)}>
                              <option value="text">텍스트</option>
                              <option value="number">숫자</option>
                              <option value="email">이메일</option>
                              <option value="password">비밀번호</option>
                              <option value="date">날짜</option>
                              <option value="time">시간</option>
                              <option value="url">URL</option>
                            </select>
                          </div>
                        )}
                        {['input', 'textarea'].includes(selectedComponent.type) && (
                          <>
                            <div className="prop-group">
                              <label>안내 문구 (placeholder)</label>
                              <input type="text" value={selectedComponent.props.placeholder || ''} onChange={(e) => updateSelectedData('placeholder', e.target.value)} />
                            </div>
                            <label className="prop-checkbox">
                              <input type="checkbox" checked={!!selectedComponent.props.readOnly} onChange={(e) => updateSelectedData('readOnly', e.target.checked)} />
                              <span>읽기 전용 (결과 표시용)</span>
                            </label>
                          </>
                        )}
                        {['dropdown', 'radio'].includes(selectedComponent.type) && (
                          <div className="prop-group">
                            <label>선택지 (쉼표 구분)</label>
                            <input type="text" value={selectedComponent.props.options || ''} onChange={(e) => updateSelectedData('options', e.target.value)} />
                          </div>
                        )}
                        {selectedComponent.type === 'radio' && (
                          <div className="prop-group">
                            <label>배치</label>
                            <select value={selectedComponent.props.direction || 'column'} onChange={(e) => updateSelectedData('direction', e.target.value)}>
                              <option value="column">세로</option>
                              <option value="row">가로</option>
                            </select>
                          </div>
                        )}
                        {selectedComponent.type === 'slider' && (
                          <>
                            <div className="prop-row">
                              <div className="prop-group">
                                <label>최소</label>
                                <input type="number" value={selectedComponent.props.min ?? 0} onChange={(e) => updateSelectedData('min', Number(e.target.value))} />
                              </div>
                              <div className="prop-group">
                                <label>최대</label>
                                <input type="number" value={selectedComponent.props.max ?? 100} onChange={(e) => updateSelectedData('max', Number(e.target.value))} />
                              </div>
                            </div>
                            <div className="prop-row">
                              <div className="prop-group">
                                <label>간격</label>
                                <input type="number" min="0" step="any" value={selectedComponent.props.step ?? 1} onChange={(e) => updateSelectedData('step', Number(e.target.value))} />
                              </div>
                              <div className="prop-group">
                                <label>기본값</label>
                                <input type="number" value={selectedComponent.props.defaultValue ?? 0} onChange={(e) => updateSelectedData('defaultValue', Number(e.target.value))} />
                              </div>
                            </div>
                            <label className="prop-checkbox">
                              <input type="checkbox" checked={selectedComponent.props.showValue !== false} onChange={(e) => updateSelectedData('showValue', e.target.checked)} />
                              <span>현재 값 표시</span>
                            </label>
                          </>
                        )}
                        {selectedComponent.type === 'file' && (
                          <div className="prop-group">
                            <label>파일 종류</label>
                            <select value={selectedComponent.props.fileKind || 'document'} onChange={(e) => updateSelectedData('fileKind', e.target.value)}>
                              <option value="document">문서/이미지 (pdf, docx, xlsx, png …)</option>
                              <option value="video">영상 (mp4, mov, webm …)</option>
                            </select>
                          </div>
                        )}
                        <div className="prop-group">
                          <label>입력 키 (워크플로우 payload 필드 이름)</label>
                          <input type="text" value={selectedComponent.props.inputKey || ''} onChange={(e) => updateSelectedData('inputKey', e.target.value)} className="mono" />
                        </div>
                      </>
                    )}
                  </InspectorSection>
                )}

                {/* 배치 */}
                <InspectorSection
                  title="배치"
                  meta={`${Math.round(Number(selectedComponent.props.position?.x) || 0)}, ${Math.round(Number(selectedComponent.props.position?.y) || 0)}`}
                  open={openSections.layout !== false}
                  onToggle={() => toggleSection('layout')}
                >
                  <div className="prop-row">
                    <div className="prop-group">
                      <label>너비</label>
                      <input type="text" value={selectedComponent.props.style?.width || ''} placeholder="예: 200px" onChange={(e) => updateSelectedData('width', e.target.value, true)} />
                    </div>
                    <div className="prop-group">
                      <label>높이</label>
                      <input type="text" value={selectedComponent.props.style?.height || ''} placeholder="예: 45px" onChange={(e) => updateSelectedData('height', e.target.value, true)} />
                    </div>
                  </div>
                  <div className="prop-row">
                    <div className="prop-group">
                      <label>X</label>
                      <PositionInput axis="x" component={selectedComponent} onCommit={updateSelectedData} />
                    </div>
                    <div className="prop-group">
                      <label>Y</label>
                      <PositionInput axis="y" component={selectedComponent} onCommit={updateSelectedData} />
                    </div>
                  </div>
                  {selectedComponent.type === 'container' && (
                    <>
                      <div className="prop-group">
                        <label>자식 배치 방식</label>
                        <select value={selectedComponent.props.layoutMode || 'absolute'} onChange={(e) => updateSelectedData('layoutMode', e.target.value)}>
                          <option value="absolute">자유 배치</option>
                          <option value="column">세로 흐름</option>
                          <option value="row">가로 흐름</option>
                          <option value="grid">격자</option>
                        </select>
                      </div>
                      {selectedComponent.props.layoutMode && selectedComponent.props.layoutMode !== 'absolute' && (
                        <>
                          <div className="prop-group">
                            <label>간격 (gap)</label>
                            <input type="text" value={selectedComponent.props.style?.gap || '12px'} onChange={(e) => updateSelectedData('gap', e.target.value, true)} />
                          </div>
                          <div className="prop-row">
                            <div className="prop-group">
                              <label>주축 정렬</label>
                              <select value={selectedComponent.props.style?.justifyContent || 'flex-start'} onChange={(e) => updateSelectedData('justifyContent', e.target.value, true)}>
                                <option value="flex-start">시작</option>
                                <option value="center">가운데</option>
                                <option value="flex-end">끝</option>
                                <option value="space-between">양쪽 분배</option>
                              </select>
                            </div>
                            <div className="prop-group">
                              <label>교차축 정렬</label>
                              <select value={selectedComponent.props.style?.alignItems || 'stretch'} onChange={(e) => updateSelectedData('alignItems', e.target.value, true)}>
                                <option value="stretch">늘리기</option>
                                <option value="flex-start">시작</option>
                                <option value="center">가운데</option>
                                <option value="flex-end">끝</option>
                              </select>
                            </div>
                          </div>
                        </>
                      )}
                    </>
                  )}
                  <div className="prop-group">
                    <label>그리기 순서</label>
                    <div className="zorder-row">
                      <button type="button" onClick={() => handleReorder('back')} title="맨 뒤로 (Ctrl+Shift+[)" aria-label="맨 뒤로"><SendToBack size={14} /></button>
                      <button type="button" onClick={() => handleReorder('backward')} title="뒤로 (Ctrl+[)" aria-label="뒤로"><ChevronDown size={14} /></button>
                      <button type="button" onClick={() => handleReorder('forward')} title="앞으로 (Ctrl+])" aria-label="앞으로"><ChevronUp size={14} /></button>
                      <button type="button" onClick={() => handleReorder('front')} title="맨 앞으로 (Ctrl+Shift+])" aria-label="맨 앞으로"><BringToFront size={14} /></button>
                    </div>
                  </div>
                </InspectorSection>

                {/* 스타일 */}
                <InspectorSection title="스타일" open={openSections.style === true} onToggle={() => toggleSection('style')}>
                  <ColorField
                    label="배경색"
                    value={selectedComponent.props.style?.backgroundColor || ''}
                    fallback={SWATCH_FALLBACK.background}
                    onChange={(value) => updateSelectedData('backgroundColor', value, true)}
                  />
                  <ColorField
                    label="글자색"
                    value={selectedComponent.props.style?.color || ''}
                    fallback={SWATCH_FALLBACK.text}
                    onChange={(value) => updateSelectedData('color', value, true)}
                  />
                  <div className="prop-row">
                    <div className="prop-group">
                      <label>글꼴 크기</label>
                      <input type="text" value={selectedComponent.props.style?.fontSize || ''} placeholder="예: 1rem" onChange={(e) => updateSelectedData('fontSize', e.target.value, true)} />
                    </div>
                    <div className="prop-group">
                      <label>굵기</label>
                      <select value={selectedComponent.props.style?.fontWeight || ''} onChange={(e) => updateSelectedData('fontWeight', e.target.value, true)}>
                        <option value="">기본</option>
                        <option value="300">가늘게 300</option>
                        <option value="400">보통 400</option>
                        <option value="500">중간 500</option>
                        <option value="600">약간 굵게 600</option>
                        <option value="700">굵게 700</option>
                      </select>
                    </div>
                  </div>
                  {['text', 'button', 'link', 'markdown', 'input', 'textarea'].includes(selectedComponent.type) && (
                    <div className="prop-group">
                      <label>텍스트 정렬</label>
                      <select value={selectedComponent.props.style?.textAlign || ''} onChange={(e) => updateSelectedData('textAlign', e.target.value, true)}>
                        <option value="">기본</option>
                        <option value="left">왼쪽</option>
                        <option value="center">가운데</option>
                        <option value="right">오른쪽</option>
                      </select>
                    </div>
                  )}
                  <div className="prop-row">
                    <div className="prop-group">
                      <label>안쪽 여백</label>
                      <input type="text" value={selectedComponent.props.style?.padding || ''} placeholder="예: 12px" onChange={(e) => updateSelectedData('padding', e.target.value, true)} />
                    </div>
                    <div className="prop-group">
                      <label>모서리 둥글기</label>
                      <input type="text" value={selectedComponent.props.style?.borderRadius || ''} placeholder="예: 8px" onChange={(e) => updateSelectedData('borderRadius', e.target.value, true)} />
                    </div>
                  </div>
                  <div className="prop-group">
                    <label>테두리</label>
                    <input type="text" value={selectedComponent.props.style?.border || ''} placeholder="예: 1px solid silver" onChange={(e) => updateSelectedData('border', e.target.value, true)} />
                  </div>
                  <div className="prop-group">
                    <label>투명도 — {Math.round((selectedComponent.props.style?.opacity ?? 1) * 100)}%</label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={selectedComponent.props.style?.opacity ?? 1}
                      onChange={(e) => updateSelectedData('opacity', Number(e.target.value), true)}
                    />
                  </div>
                  <div className="prop-group">
                    <label>CSS 클래스 (Global CSS 와 연결)</label>
                    <input type="text" value={selectedComponent.props.className || ''} placeholder="예: primary-btn" onChange={(e) => updateSelectedData('className', e.target.value)} className="mono" />
                  </div>
                </InspectorSection>

                {/* 동작 */}
                {(selectedComponent.type === 'button' || isChangeBindable) && (
                  <InspectorSection
                    title="동작"
                    meta={selectedComponent.type === 'button' ? ACTION_MODE_LABELS[selectedButtonActionMode] : undefined}
                    open={openSections.behavior !== false}
                    onToggle={() => toggleSection('behavior')}
                  >
                    {selectedComponent.type === 'button' && (
                      <>
                        <div className="prop-group">
                          <label>클릭하면</label>
                          <select value={selectedButtonActionMode} onChange={(e) => updateSelectedData('actionMode', e.target.value)}>
                            <option value="auto">자동 (JS → Blueprint → 워크플로우 순)</option>
                            <option value="blueprint">Blueprint 실행</option>
                            <option value="workflow">워크플로우 바로 실행</option>
                            <option value="script">Global JS 핸들러</option>
                            <option value="none">아무것도 안 함</option>
                          </select>
                        </div>
                        {selectedButtonTriggerIgnored && (
                          <div className="prop-hint warning">
                            <Info size={13} />
                            <span>Blueprint 트리거가 연결돼 있지만 이 설정에서는 실행되지 않아요. 위에서 "Blueprint 실행"을 선택하세요.</span>
                          </div>
                        )}
                        {selectedButtonHasBlueprintTrigger && !selectedButtonTriggerIgnored && (
                          <div className="prop-hint success">
                            <Check size={13} />
                            <span>Blueprint 트리거가 연결돼 있어요. <button type="button" className="ab-link" onClick={() => setActiveTab('logic')}>로직 탭에서 보기</button></span>
                          </div>
                        )}
                        {['auto', 'workflow'].includes(selectedButtonActionMode) && (
                          <div className="prop-group">
                            <label>연결할 워크플로우</label>
                            <select value={selectedComponent.props.workflowId || ''} onChange={(e) => updateSelectedWorkflow(e.target.value)}>
                              <option value="">-- 선택 --</option>
                              {userWorkflows.map((wf) => <option key={wf.id} value={wf.id}>{wf.title || `Workflow #${wf.id}`}</option>)}
                            </select>
                            <div className="prop-hint"><Info size={13} /> 고르면 Trigger → Submit → Output 노드가 로직 탭에 만들어집니다.</div>
                          </div>
                        )}
                        {['auto', 'script'].includes(selectedButtonActionMode) && (
                          <div className="prop-group">
                            <label>Global JS 핸들러 이름 (onClick)</label>
                            <input type="text" placeholder="예: onSaveClick" value={selectedComponent.props.onClickHandler || ''} onChange={(e) => updateSelectedData('onClickHandler', e.target.value)} className="mono" />
                          </div>
                        )}
                      </>
                    )}
                    {isChangeBindable && (
                      <>
                        <div className="prop-group">
                          <label>값이 바뀌면 (Global JS 핸들러 이름)</label>
                          <input type="text" placeholder="예: onNameChange" value={selectedComponent.props.onChangeHandler || ''} onChange={(e) => updateSelectedData('onChangeHandler', e.target.value)} className="mono" />
                        </div>
                        <div className="prop-hint"><Info size={13} /> Blueprint 로 처리하려면 로직 탭에서 Event Trigger 의 이벤트를 "On Change" 로 두세요.</div>
                      </>
                    )}
                  </InspectorSection>
                )}

                {/* 표시 */}
                <InspectorSection title="표시" open={openSections.visibility === true} onToggle={() => toggleSection('visibility')}>
                  <label className="prop-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedComponent.props.visible !== false}
                      onChange={(e) => updateSelectedData('visible', e.target.checked)}
                    />
                    <span>처음부터 표시</span>
                  </label>
                  <div className="prop-hint"><Info size={13} /> 숨겨두고 Blueprint UI Action(setVisible)으로 나중에 켤 수 있어요.</div>
                  {OUTPUT_COMPONENT_TYPES.includes(selectedComponent.type) && (
                    <div className="prop-hint"><Info size={13} /> Blueprint Output 노드의 대상으로 지정하면 워크플로우 결과가 이 컴포넌트에 표시됩니다.</div>
                  )}
                </InspectorSection>

                <div className="ab-inspector-footer">
                  <button type="button" className="ab-quiet-btn danger" onClick={handleDeleteSelected}>
                    <Trash2 size={14} /> 이 컴포넌트 삭제
                  </button>
                </div>
              </div>
            ) : null}
          </aside>
        )}

        <AIAssistantDrawer
          isOpen={isAssistantOpen}
          title="앱 빌더 AI"
          description="앱 화면과 동작을 함께 구성합니다"
          contextLabel={`${componentCount}개 컴포넌트 · ${logicNodes.length}개 로직 노드`}
          messages={chatMessages}
          input={chatInput}
          onInputChange={setChatInput}
          onSend={handleSendChatMessage}
          onClose={() => setIsAssistantOpen(false)}
          isLoading={isChatLoading}
          loadingLabel="앱 구성을 업데이트하고 있어요"
          sendDisabled={!chatInput.trim() || isChatLoading || (generationWorkflowMode === 'existing' && !generationWorkflowId)}
          placeholder="만들거나 수정할 앱 화면을 설명하세요..."
          suggestions={['고객 문의 폼을 만들어줘', '결과를 표와 마크다운으로 보여줘', '버튼에 Workflow 동작을 연결해줘']}
          onSuggestion={setChatInput}
          headerMeta={(
            <span className="assistant-token-total" title={`입력 ${builderTokenUsage.input_tokens.toLocaleString()} / 출력 ${builderTokenUsage.output_tokens.toLocaleString()}`}>
              <Coins size={13} /> {builderTokenUsage.total_tokens.toLocaleString()}
            </span>
          )}
          controls={(
            <>
              <div className="builder-assistant-group">
                <div className="assistant-control-heading"><Code2 size={14} /> 로직 생성 방식</div>
                <div className="assistant-segmented" role="group" aria-label="AI 로직 생성 방식">
                  <button type="button" className={generationMode === 'blueprint' ? 'active' : ''} onClick={() => setGenerationMode('blueprint')} title="Trigger/Submit/Output 노드로 생성 — 로직 탭에서 수정">Blueprint 노드</button>
                  <button type="button" className={generationMode === 'code' ? 'active' : ''} onClick={() => setGenerationMode('code')} title="Global JS 핸들러로 생성 — 코드 탭에서 수정">Global JS</button>
                </div>
              </div>
              <div className="builder-assistant-group">
                <div className="assistant-control-heading"><Workflow size={14} /> Workflow 연결</div>
                <div className="assistant-segmented" role="group" aria-label="AI 생성 Workflow 정책">
                  <button type="button" className={generationWorkflowMode === 'auto' ? 'active' : ''} onClick={() => setGenerationWorkflowMode('auto')}>자동 생성</button>
                  <button type="button" className={generationWorkflowMode === 'existing' ? 'active' : ''} onClick={() => setGenerationWorkflowMode('existing')}>기존 사용</button>
                  <button type="button" className={generationWorkflowMode === 'none' ? 'active' : ''} onClick={() => setGenerationWorkflowMode('none')}>사용 안 함</button>
                </div>
                {generationWorkflowMode === 'existing' && (
                  <select className="assistant-control-select" value={generationWorkflowId} onChange={(e) => setGenerationWorkflowId(e.target.value)}>
                    <option value="">Workflow 선택</option>
                    {userWorkflows.map((workflow) => (
                      <option key={workflow.id} value={workflow.id}>{workflow.title || `Workflow #${workflow.id}`}</option>
                    ))}
                  </select>
                )}
              </div>
              {builderTokenUsage.requests > 0 && (
                <div className="assistant-token-breakdown">
                  <span>입력 {builderTokenUsage.input_tokens.toLocaleString()}</span>
                  <span>출력 {builderTokenUsage.output_tokens.toLocaleString()}</span>
                  <span>{builderTokenUsage.requests}회</span>
                </div>
              )}
            </>
          )}
        />

        {/* 모바일: 한 번에 pane 하나 */}
        <nav className="builder-mobile-bar" aria-label="화면 영역 전환">
          <button
            type="button"
            className={mobilePane === 'palette' ? 'active' : ''}
            onClick={() => setMobilePane('palette')}
            disabled={!(activeTab === 'design' || activeTab === 'logic')}
          >
            <Shapes size={18} />{activeTab === 'logic' ? '노드' : '컴포넌트'}
          </button>
          <button type="button" className={mobilePane === 'canvas' ? 'active' : ''} onClick={() => setMobilePane('canvas')}>
            <Monitor size={18} />{MOBILE_CANVAS_LABELS[activeTab] || '캔버스'}
          </button>
          <button
            type="button"
            className={mobilePane === 'inspector' ? 'active' : ''}
            onClick={() => setMobilePane('inspector')}
            disabled={activeTab !== 'design'}
          >
            <SlidersHorizontal size={18} />속성
            {selectedIds.length > 0 && activeTab === 'design' && <span className="builder-tab-dot" aria-hidden="true" />}
          </button>
        </nav>
      </div>

      {isExecutionPanelOpen && (
        <section className="builder-execution-panel" style={{ height: `${executionPanelHeight}px` }} aria-label="실행 로그">
          <div
            className="builder-execution-resizer"
            onMouseDown={(event) => {
              event.preventDefault();
              const startY = event.clientY;
              const startHeight = executionPanelHeight;
              const onMouseMove = (moveEvent) => {
                const nextHeight = startHeight + startY - moveEvent.clientY;
                setExecutionPanelHeight(Math.max(180, Math.min(window.innerHeight * 0.7, nextHeight)));
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
          <header className="builder-execution-header">
            <div><TerminalSquare size={16} /> 실행 로그 <span className="builder-tab-badge">{executionLogs.length}</span></div>
            <div className="builder-execution-actions">
              <button
                type="button"
                className={`builder-toolbar-toggle ${autoOpenLogs ? 'active' : ''}`}
                onClick={() => setAutoOpenLogs((value) => !value)}
                title="새 로그가 생기면 패널을 자동으로 엽니다"
                aria-pressed={autoOpenLogs}
              >
                <span className="label">자동 열기</span>
              </button>
              <button type="button" className="ab-icon-btn" onClick={() => setExecutionLogs([])} title="로그 지우기" aria-label="로그 지우기">
                <Trash2 size={15} />
              </button>
              <button type="button" className="ab-icon-btn" onClick={() => setIsExecutionPanelOpen(false)} title="닫기" aria-label="닫기">
                <X size={17} />
              </button>
            </div>
          </header>
          <div className="builder-execution-output">
            {executionLogs.length === 0 ? (
              <span className="builder-log-empty">로그가 없습니다.</span>
            ) : executionLogs.map((log) => (
              <div key={log.id} className={`builder-log-line ${log.level || 'info'}`}>
                <time>{new Date(log.timestamp).toLocaleTimeString('ko-KR', { hour12: false })}</time>
                <span>{log.message}</span>
                {log.details !== null && log.details !== undefined && (
                  <pre>{typeof log.details === 'string' ? log.details : JSON.stringify(log.details, null, 2)}</pre>
                )}
              </div>
            ))}
            <div ref={executionLogEndRef} />
          </div>
        </section>
      )}

      {/* 배포 완료 모달 — Green 은 "배포 완료" 상태에만 쓴다 */}
      {showDeployModal && (
        <div
          className="app-builder-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowDeployModal(false);
          }}
        >
          <section className="app-builder-deploy-modal" role="dialog" aria-modal="true" aria-labelledby="deploy-modal-title">
            <header className="app-builder-modal-header">
              <span className="app-builder-success-icon"><CheckCircle2 size={22} /></span>
              <div>
                <h2 id="deploy-modal-title">배포 완료</h2>
                <p>앱이 저장되고 아래 주소로 배포됐어요. 주소를 공유하면 누구나 앱을 사용할 수 있습니다.</p>
              </div>
              <button className="ab-icon-btn" onClick={() => setShowDeployModal(false)} title="닫기" aria-label="닫기">
                <X size={18} />
              </button>
            </header>
            <label className="app-builder-url-label" htmlFor="deployed-app-url">앱 주소</label>
            <div className="app-builder-url-box">
              <input id="deployed-app-url" type="text" readOnly value={deployedUrl} onFocus={(e) => e.target.select()} />
              <button className="ab-icon-btn" onClick={() => copyToClipboard(deployedUrl)} title="주소 복사" aria-label="주소 복사">
                {copiedId === deployedUrl ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
            <div className="app-builder-modal-actions">
              <button className="app-builder-modal-secondary" onClick={() => setShowDeployModal(false)}>
                닫기
              </button>
              <a href={deployedUrl} target="_blank" rel="noreferrer" className="app-builder-modal-primary">
                <ExternalLink size={16} /> 앱 열기
              </a>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
