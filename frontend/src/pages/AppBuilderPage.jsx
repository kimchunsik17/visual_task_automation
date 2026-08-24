import React, { useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { ReactFlow, Controls, Background, addEdge, useNodesState, useEdgesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import UIEngine from '../components/UIEngine';
import {
  COMPONENT_DEFAULT_SIZES,
  DEFAULT_CANVAS,
  applyWorkflowMappings,
  inferButtonActionMode,
  isValidLogicConnection,
  makeGeneratedLayoutEditable,
  normalizeCanvas,
  normalizeComponents,
  normalizeWorkflowMappings,
  resolveCanvas,
  scaleDescendantGeometry,
} from '../appBuilderSchema';
import { Save, Layout, Box, Type, MousePointerClick, TextCursorInput, MousePointer2, Layers, Image as ImageIcon, Play, Database, ArrowRight, ArrowLeft, Sparkles, Code2, List, CheckSquare, Minus, TerminalSquare, Trash2, X, CheckCircle2, Copy, ExternalLink, FileText, Coins, Workflow } from 'lucide-react';
import { logicNodeTypes } from '../logicNodes';
import './AppBuilderPage.css';

let idCounter = 1;
const getId = (type) => `${type}-${idCounter++}-${Date.now()}`;
const EDITOR_LAYOUT_VERSION = 2;

const PLAYGROUND_PRESETS = [
  { id: 'desktop', label: 'Desktop (1024 x 768)', width: 1024, height: 768 },
  { id: 'tablet', label: 'Tablet (768 x 1024)', width: 768, height: 1024 },
  { id: 'mobile', label: 'Mobile (390 x 844)', width: 390, height: 844 },
];

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

  const handleExecutionEvent = useCallback((event) => {
    setExecutionLogs((logs) => [...logs, { id: `${Date.now()}-${logs.length}`, ...event }]);
    setIsExecutionPanelOpen(true);
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
    }
  }, [appId, token, location.state]);

  // Logic Blueprint State
  const [activeTab, setActiveTab] = useState('design');
  const [logicNodes, setLogicNodes, onLogicNodesChange] = useNodesState([]);
  const [logicEdges, setLogicEdges, onLogicEdgesChange] = useEdgesState([]);

  // AI Assistant State
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', content: '안녕하세요! AI 앱 빌더입니다. 원하시는 앱의 형태나 기능을 말씀해주시면 자동으로 만들어 드릴게요. (예: 고객 문의를 입력받아 DB에 저장하는 폼 만들어줘)' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const chatMessagesEndRef = React.useRef(null);
  
  useEffect(() => {
    chatMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isChatLoading, isAssistantOpen]);

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
      alert('빨간 실행 포트끼리 또는 초록 데이터 포트끼리 연결해주세요.');
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

  React.useEffect(() => {
    const handleKeyDown = (e) => {
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
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedIds, handleDeleteSelected, handleLogicDelete, activeTab]);

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
    };
    const newNode = {
      id: nodeId,
      type,
      position,
      data: { id: nodeId, ...(defaultData[type] || {}) }
    };
    setLogicNodes(nds => nds.concat(newNode));
  };

  const findComponent = (comps, id) => {
    for (let c of comps) {
      if (c.id === id) return c;
      if (c.children) {
        let found = findComponent(c.children, id);
        if (found) return found;
      }
    }
    return null;
  };

  const handleTransformStart = useCallback((id, transformType) => {
    if (transformType !== 'resize') return;
    const component = findComponent(components, id);
    resizeSnapshotRef.current = component
      ? { id, component: JSON.parse(JSON.stringify(component)) }
      : null;
  }, [components]);

  const updateComponent = (comps, id, updater) => {
    return comps.map(c => {
      if (c.id === id) return updater({ ...c });
      if (c.children) return { ...c, children: updateComponent(c.children, id, updater) };
      return c;
    });
  };

  const removeComponent = (comps, id) => {
    return comps.filter(c => c.id !== id).map(c => {
      if (c.children) return { ...c, children: removeComponent(c.children, id) };
      return c;
    });
  };

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
  const selectedButtonActionMode = selectedComponent?.type === 'button'
    ? inferButtonActionMode(
        selectedComponent.props,
        logicNodes.some((node) => node.type === 'triggerNode' && node.data?.componentId === selectedComponent.id && (node.data?.eventType || 'onClick') === 'onClick')
      )
    : 'none';

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
      const x = e.clientX - canvasRect.left;
      const y = e.clientY - canvasRect.top;

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
    const defaultSize = COMPONENT_DEFAULT_SIZES[type] || { width: 200, height: 45 };
    const base = {
      id: getId(type),
      type,
      props: {
        position: {
          x: Math.max(0, Math.min(x, canvas.width - defaultSize.width)),
          y: Math.max(0, y),
        },
        style: { width: `${defaultSize.width}px`, height: `${defaultSize.height}px` },
      },
    };
    if (type === 'container') {
      base.props.layoutMode = 'absolute';
      base.props.style = { ...base.props.style, padding: '1rem', border: '1px solid #cbd5e1', borderRadius: '4px' };
      base.children = [];
    } else if (type === 'text') {
      base.props.text = 'New Text';
    } else if (type === 'button') {
      base.props.text = 'Click Me';
    } else if (type === 'input') {
      base.props.label = 'Label';
      base.props.placeholder = 'Type here...';
      base.props.inputKey = 'input_' + Date.now();
    } else if (type === 'image') {
      base.props.imageUrl = 'https://via.placeholder.com/150';
      base.props.style = { ...base.props.style };
    } else if (type === 'textarea') {
      base.props.label = 'Label';
      base.props.placeholder = 'Type multiline text here...';
      base.props.inputKey = 'textarea_' + Date.now();
      base.props.style = { ...base.props.style };
    } else if (type === 'dropdown') {
      base.props.label = 'Select Option';
      base.props.options = 'Option 1, Option 2, Option 3';
      base.props.inputKey = 'dropdown_' + Date.now();
    } else if (type === 'checkbox') {
      base.props.label = 'Check me';
      base.props.inputKey = 'checkbox_' + Date.now();
    } else if (type === 'divider') {
      base.props.style = { ...base.props.style, backgroundColor: '#cbd5e1' };
    }
    return base;
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
        comp.props.position = { ...comp.props.position, [key]: value };
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

  const handleSaveAndDeploy = async () => {
    try {
      const componentMappings = {};
      const componentIds = new Set();
      const extractMappings = (comps) => {
        comps.forEach(c => {
          componentIds.add(c.id);
          if (c.props.workflowId) {
            componentMappings[c.id] = { projectId: c.props.workflowId };
          }
          if (c.children) extractMappings(c.children);
        });
      };
      extractMappings(components);
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
        workflow_mappings: normalizedMappings
      };

      const res = await axios.post('/api/builder/save', payload, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setWorkflowMappings(normalizedMappings);
      setCanvas(savedCanvas);
      
      const appUrl = `${window.location.origin}/custom-app/${res.data.id}`;
      setDeployedUrl(appUrl);
      setShowDeployModal(true);
    } catch (err) {
      console.error(err);
      alert('저장 중 오류가 발생했습니다.');
    }
  };

  const renderHierarchy = (comps, depth = 0) => {
    return comps.map(c => (
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
          className={`hierarchy-item ${selectedIds.includes(c.id) ? 'active' : ''}`}
          style={{ paddingLeft: `${depth * 15 + 8}px` }}
        >
          {c.type === 'container' && <Box size={12} />}
          {c.type === 'text' && <Type size={12} />}
          {c.type === 'input' && <TextCursorInput size={12} />}
          {c.type === 'button' && <MousePointerClick size={12} />}
          {c.type === 'image' && <ImageIcon size={12} />}
          <span>{c.type} {c.props.text ? `"${c.props.text.substring(0, 8)}..."` : ''}</span>
        </div>
        {c.children && renderHierarchy(c.children, depth + 1)}
      </div>
    ));
  };

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
    <div className="builder-layout">
      {globalCss && <style>{globalCss}</style>}
      {/* Header */}
      <header className="builder-header">
        <div className="header-left">
          <button
            onClick={() => navigate('/')}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', marginRight: '0.5rem' }}
            title="홈으로 돌아가기"
          >
            <ArrowLeft size={20} />
          </button>
          <MousePointer2 size={24} color="#3b82f6" />
          <input 
            className="app-title-input"
            value={appTitle}
            onChange={e => setAppTitle(e.target.value)}
            placeholder="앱 이름 입력..."
            style={{ width: '150px' }}
          />
          <div className="app-details-control">
            <button
              className={`builder-icon-button ${isAppDetailsOpen ? 'active' : ''}`}
              onClick={() => setIsAppDetailsOpen((open) => !open)}
              title="앱 정보"
              aria-label="앱 정보"
            >
              <FileText size={17} />
            </button>
            {isAppDetailsOpen && (
              <div className="app-details-popover">
                <div className="prop-group">
                  <label htmlFor="app-details-title">앱 제목</label>
                  <input id="app-details-title" type="text" value={appTitle} onChange={(e) => setAppTitle(e.target.value)} />
                </div>
                <div className="prop-group">
                  <label htmlFor="app-details-description">앱 설명</label>
                  <textarea
                    id="app-details-description"
                    rows="5"
                    value={appDescription}
                    onChange={(e) => setAppDescription(e.target.value)}
                    placeholder="앱의 목적과 사용 방법을 기록하세요."
                  />
                </div>
              </div>
            )}
          </div>
          <div style={{ marginLeft: '1rem', display: 'flex', background: '#0f172a', padding: '4px', borderRadius: '6px' }}>
            <button
              onClick={() => {
                setGenerationMode('code');
                if (activeTab === 'logic') setActiveTab('code');
              }}
              style={{ fontSize: '0.8rem', padding: '4px 12px', borderRadius: '4px', border: 'none', background: generationMode === 'code' ? '#f59e0b' : 'transparent', color: 'white', cursor: 'pointer', fontWeight: generationMode === 'code' ? 'bold' : 'normal' }}
            >
              Code Native
            </button>
            <button
              onClick={() => {
                setGenerationMode('blueprint');
                if (activeTab === 'code') setActiveTab('logic');
              }}
              style={{ fontSize: '0.8rem', padding: '4px 12px', borderRadius: '4px', border: 'none', background: generationMode === 'blueprint' ? '#8b5cf6' : 'transparent', color: 'white', cursor: 'pointer', fontWeight: generationMode === 'blueprint' ? 'bold' : 'normal' }}
            >
              Blueprint
            </button>
          </div>
        </div>
        
        <div style={{ display: 'flex', background: '#1e293b', padding: '4px', borderRadius: '8px', gap: '4px' }}>
          <button 
            onClick={() => setActiveTab('design')}
            style={{ padding: '6px 16px', borderRadius: '6px', border: 'none', background: activeTab === 'design' ? '#3b82f6' : 'transparent', color: 'white', cursor: 'pointer', fontWeight: activeTab === 'design' ? 'bold' : 'normal' }}
          >
            Design
          </button>
          {generationMode === 'blueprint' && (
            <button 
              onClick={() => setActiveTab('logic')}
              style={{ padding: '6px 16px', borderRadius: '6px', border: 'none', background: activeTab === 'logic' ? '#8b5cf6' : 'transparent', color: 'white', cursor: 'pointer', fontWeight: activeTab === 'logic' ? 'bold' : 'normal' }}
            >
              Blueprint
            </button>
          )}
          <button 
            onClick={() => {
              setActiveTab('preview');
              setSelectedIds([]); // clear selection when going to preview
            }}
            style={{ padding: '6px 16px', borderRadius: '6px', border: 'none', background: activeTab === 'preview' ? '#10b981' : 'transparent', color: 'white', cursor: 'pointer', fontWeight: activeTab === 'preview' ? 'bold' : 'normal' }}
          >
            Preview
          </button>
          {generationMode === 'code' && (
            <button 
              onClick={() => setActiveTab('code')}
              style={{ padding: '6px 16px', borderRadius: '6px', border: 'none', background: activeTab === 'code' ? '#ec4899' : 'transparent', color: 'white', cursor: 'pointer', fontWeight: activeTab === 'code' ? 'bold' : 'normal' }}
            >
              Code
            </button>
          )}
          <button 
            onClick={() => setActiveTab('css')}
            style={{ padding: '6px 16px', borderRadius: '6px', border: 'none', background: activeTab === 'css' ? '#f59e0b' : 'transparent', color: 'white', cursor: 'pointer', fontWeight: activeTab === 'css' ? 'bold' : 'normal' }}
          >
            Global CSS
          </button>
        </div>

        <div className="header-right">
          {executionLogs.length > 0 && (
            <button
              className="builder-icon-button builder-log-toggle"
              onClick={() => setIsExecutionPanelOpen((open) => !open)}
              title="실행 로그"
              aria-label="실행 로그"
            >
              <TerminalSquare size={18} />
              <span>{executionLogs.length}</span>
            </button>
          )}
          <button className="btn-ai-assistant" onClick={() => setIsAssistantOpen(!isAssistantOpen)}>
            <Sparkles size={16} /> AI 어시스턴트
          </button>
          <button className="btn-deploy" onClick={handleSaveAndDeploy}>
            <Save size={16} /> 저장 및 배포
          </button>
        </div>
      </header>

      <div className="builder-workspace">
        {/* Left Sidebar */}
        {(activeTab === 'design' || activeTab === 'logic') && (
        <aside className="builder-sidebar-left">
          {activeTab === 'design' ? (
            <>
              <div className="sidebar-title">UI Components</div>
              <div className="node-palette">
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'container')}>
                  <Box size={16} /> Container (Div)
                </div>
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'text')}>
                  <Type size={16} /> Text
                </div>
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'input')}>
                  <TextCursorInput size={16} /> Input Field
                </div>
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'button')}>
                  <MousePointerClick size={16} /> Button
                </div>
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'image')}>
                  <ImageIcon size={16} /> Image
                </div>
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'textarea')}>
                  <TextCursorInput size={16} /> Text Area
                </div>
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'dropdown')}>
                  <List size={16} /> Dropdown
                </div>
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'checkbox')}>
                  <CheckSquare size={16} /> Checkbox
                </div>
                <div className="palette-item" draggable onDragStart={(e) => handleDragStart(e, 'divider')}>
                  <Minus size={16} /> Divider
                </div>
              </div>

              <div className="sidebar-title" style={{ marginTop: '2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Layers size={14} /> Hierarchy
              </div>
              <div 
                className="hierarchy-tree"
                onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onDrop={(e) => {
                  e.stopPropagation();
                  const draggedId = e.dataTransfer.getData('application/hierarchy-id');
                  if (draggedId) handleReparent(draggedId, 'root');
                }}
                style={{ paddingBottom: '20px', minHeight: '50px' }}
              >
                {components.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontStyle: 'italic' }}>No components</div>
                ) : (
                  renderHierarchy(components)
                )}
              </div>
            </>
          ) : (
            <>
              <div className="sidebar-title">Logic Nodes</div>
              <div className="node-palette">
                <div className="palette-item" style={{ borderColor: '#ef4444' }} draggable onDragStart={(e) => handleDragStartLogic(e, 'triggerNode')}>
                  <Play size={16} color="#ef4444" /> Event Trigger
                </div>
                <div className="palette-item" style={{ borderColor: '#10b981' }} draggable onDragStart={(e) => handleDragStartLogic(e, 'valueNode')}>
                  <Database size={16} color="#10b981" /> Get Value
                </div>
                <div className="palette-item" style={{ borderColor: '#3b82f6' }} draggable onDragStart={(e) => handleDragStartLogic(e, 'actionNode')}>
                  <ArrowRight size={16} color="#3b82f6" /> UI Action
                </div>
                <div 
                  className="palette-item" 
                  draggable 
                  onDragStart={(e) => handleDragStartLogic(e, 'workflowNode')}
                >
                  <Sparkles size={16} /> Workflow Execute
                </div>
                <div 
                  className="palette-item" 
                  draggable 
                  onDragStart={(e) => handleDragStartLogic(e, 'codeNode')}
                  style={{ borderColor: '#f59e0b', color: '#f59e0b' }}
                >
                  <Code2 size={16} /> Custom JS Code
                </div>
              </div>
              <div style={{ marginTop: '2rem', padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', fontSize: '0.8rem', color: '#94a3b8' }}>
                <p style={{ margin: '0 0 8px 0', color: 'white', fontWeight: 'bold' }}>How to use Blueprint:</p>
                1. Drag <b>Event Trigger</b> to detect clicks.<br/>
                2. Drag <b>UI Action</b> to change a component.<br/>
                3. Connect red handles (Triggers) to control execution flow.<br/>
                4. Connect green handles (Data) to pass values.
              </div>
            </>
          )}
        </aside>
        )}

        {/* Center - Canvas or Blueprint or Preview */}
        <main 
          className="builder-center" 
          onClick={(e) => {
            if (activeTab === 'design' && (e.target === e.currentTarget || e.target.className === 'canvas-area')) {
              handleSelect(null);
            }
          }}
          style={activeTab === 'logic' || activeTab === 'preview' ? { padding: 0 } : {}}
        >
          {activeTab === 'design' ? (
            <div style={{ width: '100%', height: '100%', overflow: 'auto', padding: '20px', boxSizing: 'border-box', backgroundColor: '#0f172a' }}>
              <div 
                className="canvas-area"
                onDragOver={handleDragOver}
                onDrop={handleDropOnCanvas}
                onClick={() => handleSelect(null)}
                style={{ 
                  position: 'relative',
                  width: `${effectiveCanvas.width}px`,
                  height: `${effectiveCanvas.height}px`,
                  minWidth: `${effectiveCanvas.width}px`,
                  minHeight: `${effectiveCanvas.height}px`,
                  backgroundColor: 'white',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                  margin: '0 auto',
                }}
              >
              {snapLines.map((line, idx) => (
                <div 
                  key={idx}
                  style={{
                    position: 'absolute',
                    backgroundColor: 'red',
                    zIndex: 9999,
                    ...(line.type === 'vertical' 
                      ? { left: line.pos, top: 0, bottom: 0, width: '1px' } 
                      : { top: line.pos, left: 0, right: 0, height: '1px' })
                  }}
                />
              ))}

              {components.length === 0 ? (
                <div className="canvas-placeholder">
                  좌측 패널에서 컴포넌트를 드래그하여 이곳에 놓으세요
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
                />
              )}
              </div>
            </div>
          ) : activeTab === 'logic' ? (
            <div style={{ width: '100%', height: '100%' }} onDragOver={(e) => e.preventDefault()} onDrop={handleDropOnLogicCanvas}>
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
                <Background color="#334155" gap={16} />
                <Controls />
              </ReactFlow>
            </div>
          ) : activeTab === 'css' ? (
            <div style={{ width: '100%', height: '100%', padding: '1rem', backgroundColor: '#1e293b', boxSizing: 'border-box' }}>
              <div style={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '0.9rem' }}>Global CSS (적용 시 자동으로 화면에 렌더링됩니다)</div>
              <textarea 
                value={globalCss}
                onChange={(e) => setGlobalCss(e.target.value)}
                placeholder=".my-btn {\n  box-shadow: 0 4px 6px rgba(0,0,0,0.1);\n}"
                style={{ width: '100%', height: 'calc(100% - 2rem)', backgroundColor: '#0f172a', color: '#10b981', border: '1px solid #475569', borderRadius: '6px', padding: '1rem', fontFamily: 'monospace', fontSize: '14px', resize: 'none' }}
              />
            </div>
          ) : activeTab === 'code' ? (
            <div style={{ width: '100%', height: '100%', padding: '1rem', backgroundColor: '#1e293b', boxSizing: 'border-box' }}>
              <div style={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '0.9rem' }}>Global JS (Export an object with handler functions)</div>
              <textarea 
                value={globalJs}
                onChange={(e) => setGlobalJs(e.target.value)}
                placeholder="return {\n  onSave: async () => {\n    // logic\n  }\n};"
                style={{ width: '100%', height: 'calc(100% - 2rem)', backgroundColor: '#0f172a', color: '#fcd34d', border: '1px solid #475569', borderRadius: '6px', padding: '1rem', fontFamily: 'monospace', fontSize: '14px', resize: 'none' }}
              />
            </div>
          ) : (
            <div style={{ width: '100%', height: '100%', overflow: 'auto', padding: '20px', boxSizing: 'border-box', backgroundColor: '#0f172a' }}>
              <div 
                className="canvas-area"
                style={{ 
                  position: 'relative',
                  width: `${effectiveCanvas.width}px`,
                  height: `${effectiveCanvas.height}px`,
                  minWidth: `${effectiveCanvas.width}px`,
                  minHeight: `${effectiveCanvas.height}px`,
                  backgroundColor: 'white',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                  margin: '0 auto',
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
          )}
        </main>

        {/* Right Sidebar - Properties (Only in Design Mode) */}
        {activeTab === 'design' && (
          <aside className="builder-sidebar-right">
          {selectedIds.length === 0 ? (
            <div className="properties-panel">
            <div className="sidebar-title">Page (Root) Settings</div>
              <div className="prop-group">
                <label>Background Color</label>
                <input type="color" value={rootStyle.backgroundColor || '#f1f5f9'} onChange={(e) => setRootStyle({...rootStyle, backgroundColor: e.target.value})} />
              </div>
              <div className="prop-group">
                <label>Padding</label>
                <input type="text" value={rootStyle.padding || '2rem'} onChange={(e) => setRootStyle({...rootStyle, padding: e.target.value})} />
              </div>
              <div className="prop-group">
                <label>Playground Size</label>
                <select value={playgroundPreset} onChange={(e) => handlePlaygroundPresetChange(e.target.value)}>
                  {PLAYGROUND_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>{preset.label}</option>
                  ))}
                  <option value="custom">Custom</option>
                </select>
              </div>
              <div className="playground-dimensions">
                <div className="prop-group">
                  <label htmlFor="playground-width">Width</label>
                  <input
                    id="playground-width"
                    type="number"
                    min="320"
                    max="1920"
                    step="1"
                    value={canvasDimensionDraft.width}
                    onChange={(e) => setCanvasDimensionDraft((draft) => ({ ...draft, width: e.target.value }))}
                    onBlur={() => commitCanvasDimension('width')}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') e.currentTarget.blur();
                    }}
                  />
                </div>
                <div className="prop-group">
                  <label htmlFor="playground-height">Height</label>
                  <input
                    id="playground-height"
                    type="number"
                    min="480"
                    max="3000"
                    step="1"
                    value={canvasDimensionDraft.height}
                    onChange={(e) => setCanvasDimensionDraft((draft) => ({ ...draft, height: e.target.value }))}
                    onBlur={() => commitCanvasDimension('height')}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') e.currentTarget.blur();
                    }}
                  />
                </div>
              </div>
              <label className="playground-auto-height">
                <input
                  type="checkbox"
                  checked={canvas.autoHeight !== false}
                  onChange={(e) => setCanvas((current) => ({ ...current, autoHeight: e.target.checked }))}
                />
                <span>Auto Height</span>
              </label>
            </div>
          ) : selectedIds.length > 1 ? (
            <div className="properties-panel">
              <div className="sidebar-title">{selectedIds.length} components selected</div>
              <button className="btn-danger" onClick={handleDeleteSelected}>
                Delete Selected
              </button>
            </div>
          ) : (
            <div className="properties-panel">
              <div className="sidebar-title">Properties - {selectedComponent?.type}</div>
              
              {selectedComponent?.type === 'button' || selectedComponent?.type === 'text' || selectedComponent?.type === 'terminal' ? (
                <div className="prop-group">
                  <label>Text Content</label>
                  <input 
                    type="text" 
                    value={selectedComponent.props.text || ''} 
                    onChange={(e) => updateSelectedData('text', e.target.value)} 
                  />
                </div>
              ) : null}

              {['input', 'textarea', 'dropdown', 'checkbox'].includes(selectedComponent?.type) && (
                <>
                  <div className="prop-group">
                    <label>Label</label>
                    <input type="text" value={selectedComponent.props.label || ''} onChange={(e) => updateSelectedData('label', e.target.value)} />
                  </div>
                  {['input', 'textarea'].includes(selectedComponent?.type) && (
                  <div className="prop-group">
                    <label>Placeholder</label>
                    <input type="text" value={selectedComponent.props.placeholder || ''} onChange={(e) => updateSelectedData('placeholder', e.target.value)} />
                  </div>
                  )}
                  {selectedComponent?.type === 'dropdown' && (
                  <div className="prop-group">
                    <label>Options (comma separated)</label>
                    <input type="text" value={selectedComponent.props.options || ''} onChange={(e) => updateSelectedData('options', e.target.value)} />
                  </div>
                  )}
                  <div className="prop-group">
                    <label>Input Key (Variable name)</label>
                    <input type="text" value={selectedComponent.props.inputKey || ''} onChange={(e) => updateSelectedData('inputKey', e.target.value)} />
                  </div>
                </>
              )}

              {selectedComponent?.type === 'image' && (
                <div className="prop-group">
                  <label>Image URL</label>
                  <input type="text" value={selectedComponent.props.imageUrl || ''} onChange={(e) => updateSelectedData('imageUrl', e.target.value)} placeholder="https://..." />
                </div>
              )}

              <div className="sidebar-title" style={{ marginTop: '1.5rem' }}>Layout & Size</div>
              <div className="prop-group">
                <label>Width</label>
                <input type="text" value={selectedComponent?.props.style?.width || ''} placeholder="e.g. 100%, 200px" onChange={(e) => updateSelectedData('width', e.target.value, true)} />
              </div>
              <div className="prop-group">
                <label>Height</label>
                <input type="text" value={selectedComponent?.props.style?.height || ''} placeholder="e.g. auto, 100px" onChange={(e) => updateSelectedData('height', e.target.value, true)} />
              </div>
              <div className="prop-group">
                <label>X Position</label>
                <input type="number" value={selectedComponent?.props.position?.x || 0} onChange={(e) => updateSelectedData('x', parseFloat(e.target.value))} />
              </div>
              <div className="prop-group">
                <label>Y Position</label>
                <input type="number" value={selectedComponent?.props.position?.y || 0} onChange={(e) => updateSelectedData('y', parseFloat(e.target.value))} />
              </div>

              <div className="sidebar-title" style={{ marginTop: '1.5rem' }}>Design</div>
              <div className="prop-group">
                <label>CSS Class Name</label>
                <input type="text" value={selectedComponent?.props.className || ''} placeholder="e.g. custom-style" onChange={(e) => updateSelectedData('className', e.target.value)} />
              </div>
              <div className="prop-group">
                <label>Background Color</label>
                <input type="color" value={selectedComponent?.props.style?.backgroundColor || '#ffffff'} onChange={(e) => updateSelectedData('backgroundColor', e.target.value, true)} />
              </div>
              <div className="prop-group">
                <label>Text Color</label>
                <input type="color" value={selectedComponent?.props.style?.color || '#000000'} onChange={(e) => updateSelectedData('color', e.target.value, true)} />
              </div>
              <div className="prop-group">
                <label>Font Size</label>
                <input type="text" value={selectedComponent?.props.style?.fontSize || ''} placeholder="e.g. 1.2rem" onChange={(e) => updateSelectedData('fontSize', e.target.value, true)} />
              </div>
              <div className="prop-group">
                <label>Padding</label>
                <input type="text" value={selectedComponent?.props.style?.padding || ''} placeholder="e.g. 1rem" onChange={(e) => updateSelectedData('padding', e.target.value, true)} />
              </div>
              <div className="prop-group">
                <label>Border Radius</label>
                <input type="text" value={selectedComponent?.props.style?.borderRadius || ''} placeholder="e.g. 8px" onChange={(e) => updateSelectedData('borderRadius', e.target.value, true)} />
              </div>

              {selectedComponent?.type === 'container' && (
                <>
                  <div className="prop-group">
                    <label>Layout Mode</label>
                    <select value={selectedComponent.props.layoutMode || 'absolute'} onChange={(e) => updateSelectedData('layoutMode', e.target.value)}>
                      <option value="absolute">Free Position</option>
                      <option value="column">Column</option>
                      <option value="row">Row</option>
                      <option value="grid">Grid</option>
                    </select>
                  </div>
                  {selectedComponent.props.layoutMode !== 'absolute' && (
                    <>
                      <div className="prop-group">
                        <label>Gap</label>
                        <input type="text" value={selectedComponent.props.style?.gap || '12px'} onChange={(e) => updateSelectedData('gap', e.target.value, true)} />
                      </div>
                      <div className="prop-group">
                        <label>Justify Content</label>
                        <select value={selectedComponent.props.style?.justifyContent || 'flex-start'} onChange={(e) => updateSelectedData('justifyContent', e.target.value, true)}>
                          <option value="flex-start">Start</option>
                          <option value="center">Center</option>
                          <option value="flex-end">End</option>
                          <option value="space-between">Space Between</option>
                        </select>
                      </div>
                      <div className="prop-group">
                        <label>Align Items</label>
                        <select value={selectedComponent.props.style?.alignItems || 'stretch'} onChange={(e) => updateSelectedData('alignItems', e.target.value, true)}>
                          <option value="stretch">Stretch</option>
                          <option value="flex-start">Start</option>
                          <option value="center">Center</option>
                          <option value="flex-end">End</option>
                        </select>
                      </div>
                    </>
                  )}
                </>
              )}

              {selectedComponent?.type === 'button' && (
                <>
                  <div className="prop-group">
                    <label>Click Action</label>
                    <select value={selectedButtonActionMode} onChange={(e) => updateSelectedData('actionMode', e.target.value)}>
                      <option value="auto">Automatic (Legacy)</option>
                      <option value="workflow">Workflow</option>
                      <option value="blueprint">Blueprint</option>
                      <option value="script">JavaScript</option>
                      <option value="none">None</option>
                    </select>
                  </div>
                </>
              )}

              {selectedComponent?.type === 'button' && ['auto', 'workflow'].includes(selectedButtonActionMode) && (
                <>
                  <div className="sidebar-title" style={{ marginTop: '1.5rem', color: '#10b981' }}>Workflow Binding</div>
                  <div className="prop-group">
                    <label>Project ID</label>
                    <select value={selectedComponent.props.workflowId || ''} onChange={(e) => updateSelectedWorkflow(e.target.value)}>
                      <option value="">-- 워크플로우 선택 --</option>
                      {userWorkflows.map(wf => <option key={wf.id} value={wf.id}>{wf.title || `Workflow #${wf.id}`}</option>)}
                    </select>
                  </div>
                </>
              )}

              {selectedComponent?.type === 'button' && ['auto', 'script'].includes(selectedButtonActionMode) && (
                <>
                  <div className="sidebar-title" style={{ marginTop: '1.5rem', color: '#f59e0b' }}>Global JS Binding</div>
                  <div className="prop-group">
                    <label>onClickHandler</label>
                    <input type="text" placeholder="e.g. onSaveClick" value={selectedComponent.props.onClickHandler || ''} onChange={(e) => updateSelectedData('onClickHandler', e.target.value)} style={{ fontFamily: 'monospace', fontSize: '12px' }} />
                  </div>
                </>
              )}

              {['input', 'textarea', 'dropdown', 'checkbox'].includes(selectedComponent?.type) && (
                <>
                  <div className="sidebar-title" style={{ marginTop: '1.5rem', color: '#f59e0b' }}>Global JS Binding</div>
                  <div className="prop-group">
                    <label>onChangeHandler (JS Function Name)</label>
                    <input 
                      type="text"
                      placeholder="e.g. onNameChange" 
                      value={selectedComponent.props.onChangeHandler || ''} 
                      onChange={(e) => updateSelectedData('onChangeHandler', e.target.value)} 
                      style={{ fontFamily: 'monospace', fontSize: '12px' }}
                    />
                  </div>
                </>
              )}
              
              <button className="btn-danger" onClick={handleDeleteSelected}>
                Delete Component
              </button>
            </div>
          )}
          </aside>
        )}
        
        {/* AI Assistant Drawer */}
        <div className={`ai-assistant-drawer ${isAssistantOpen ? 'open' : ''}`}>
          <div className="ai-drawer-header">
            <h3><Sparkles size={18} color="#3b82f6" /> AI 앱 빌더</h3>
            <div className="ai-drawer-header-actions">
              <span className="builder-token-total" title={`입력 ${builderTokenUsage.input_tokens.toLocaleString()} / 출력 ${builderTokenUsage.output_tokens.toLocaleString()}`}>
                <Coins size={14} /> {builderTokenUsage.total_tokens.toLocaleString()}
              </span>
              <button className="btn-icon-close" onClick={() => setIsAssistantOpen(false)} title="닫기" aria-label="닫기">
                <X size={18} />
              </button>
            </div>
          </div>

          <div className="ai-generation-options">
            <div className="ai-generation-options-title">
              <Workflow size={15} /> Workflow
            </div>
            <div className="ai-workflow-mode" role="group" aria-label="AI 생성 Workflow 정책">
              <button className={generationWorkflowMode === 'auto' ? 'active' : ''} onClick={() => setGenerationWorkflowMode('auto')}>자동 생성</button>
              <button className={generationWorkflowMode === 'existing' ? 'active' : ''} onClick={() => setGenerationWorkflowMode('existing')}>기존 사용</button>
              <button className={generationWorkflowMode === 'none' ? 'active' : ''} onClick={() => setGenerationWorkflowMode('none')}>사용 안 함</button>
            </div>
            {generationWorkflowMode === 'existing' && (
              <select value={generationWorkflowId} onChange={(e) => setGenerationWorkflowId(e.target.value)}>
                <option value="">Workflow 선택</option>
                {userWorkflows.map((workflow) => (
                  <option key={workflow.id} value={workflow.id}>{workflow.title || `Workflow #${workflow.id}`}</option>
                ))}
              </select>
            )}
            {builderTokenUsage.requests > 0 && (
              <div className="builder-token-breakdown">
                <span>입력 {builderTokenUsage.input_tokens.toLocaleString()}</span>
                <span>출력 {builderTokenUsage.output_tokens.toLocaleString()}</span>
                <span>{builderTokenUsage.requests}회</span>
              </div>
            )}
          </div>
          
          <div className="ai-drawer-messages">
            {chatMessages.map((msg, idx) => (
              <div key={idx} className={`ai-message ${msg.role}`}>
                <div className="ai-bubble">
                  {msg.content}
                </div>
              </div>
            ))}
            {isChatLoading && (
              <div className="ai-message assistant">
                <div className="ai-bubble" style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  <span className="typing-dot">.</span><span className="typing-dot">.</span><span className="typing-dot">.</span>
                </div>
              </div>
            )}
            <div ref={chatMessagesEndRef} />
          </div>
          
          <div className="ai-drawer-input">
            <textarea 
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendChatMessage();
                }
              }}
              placeholder="앱 요구사항을 입력하세요..."
              disabled={isChatLoading}
            />
            <button 
              className="btn-send"
              onClick={handleSendChatMessage}
              disabled={!chatInput.trim() || isChatLoading || (generationWorkflowMode === 'existing' && !generationWorkflowId)}
            >
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </div>

      {isExecutionPanelOpen && (
        <section className="builder-execution-panel" style={{ height: `${executionPanelHeight}px` }}>
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
            <div><TerminalSquare size={16} /> 실행 로그</div>
            <div className="builder-execution-actions">
              <button onClick={() => setExecutionLogs([])} title="로그 지우기" aria-label="로그 지우기">
                <Trash2 size={16} />
              </button>
              <button onClick={() => setIsExecutionPanelOpen(false)} title="닫기" aria-label="닫기">
                <X size={18} />
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

      {/* Deploy Modal */}
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
                <p>커스텀 앱이 성공적으로 저장되고 배포되었습니다.</p>
              </div>
              <button className="app-builder-modal-close" onClick={() => setShowDeployModal(false)} title="닫기" aria-label="닫기">
                <X size={18} />
              </button>
            </header>
            <label className="app-builder-url-label" htmlFor="deployed-app-url">App URL</label>
            <div className="app-builder-url-box">
              <input id="deployed-app-url" type="text" readOnly value={deployedUrl} />
              <button onClick={() => navigator.clipboard.writeText(deployedUrl)} title="URL 복사" aria-label="URL 복사">
                <Copy size={17} />
              </button>
            </div>
            <div className="app-builder-modal-actions">
              <a href={deployedUrl} target="_blank" rel="noreferrer" className="app-builder-modal-primary">
                <ExternalLink size={16} /> 앱 열기
              </a>
              <button className="app-builder-modal-secondary" onClick={() => setShowDeployModal(false)}>
                닫기
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
