import React, { useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { ReactFlow, Controls, Background, addEdge, useNodesState, useEdgesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import UIEngine from '../components/UIEngine';
import { Save, Layout, Box, Type, MousePointerClick, TextCursorInput, MousePointer2, Layers, Image as ImageIcon, Play, Database, ArrowRight, Sparkles, Code2, List, CheckSquare, Minus } from 'lucide-react';
import { logicNodeTypes } from '../logicNodes';
import './AppBuilderPage.css';

let idCounter = 1;
const getId = (type) => `${type}-${idCounter++}-${Date.now()}`;

export default function AppBuilderPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { appId } = useParams();
  const { token } = useAuth();
  const [components, setComponents] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [appTitle, setAppTitle] = useState('My Visual App');
  const [rootStyle, setRootStyle] = useState({ backgroundColor: '#f1f5f9', padding: '0px' });
  const [globalCss, setGlobalCss] = useState('');
  const [globalJs, setGlobalJs] = useState('');
  const [showDeployModal, setShowDeployModal] = useState(false);
  const [deployedUrl, setDeployedUrl] = useState('');
  const [snapLines, setSnapLines] = useState([]);
  const [workflowMappings, setWorkflowMappings] = useState({});
  const [generationMode, setGenerationMode] = useState('code'); // 'code' or 'blueprint'
  
  useEffect(() => {
    if (appId) {
      const loadApp = async () => {
        try {
          const authHeaders = token ? { headers: { Authorization: `Bearer ${token}` } } : {};
          const res = await axios.get(`/api/apps/custom/${appId}`, authHeaders);
          const data = res.data;
          
          if (data.title) setAppTitle(data.title);
          if (data.ui_graph_data) {
            if (data.ui_graph_data.components) setComponents(data.ui_graph_data.components);
            if (data.ui_graph_data.rootStyle) setRootStyle(data.ui_graph_data.rootStyle);
            if (data.ui_graph_data.globalCss) setGlobalCss(data.ui_graph_data.globalCss);
            if (data.ui_graph_data.globalJs) setGlobalJs(data.ui_graph_data.globalJs);
          }
          if (data.logic_graph) {
            if (data.logic_graph.nodes) setLogicNodes(data.logic_graph.nodes);
            if (data.logic_graph.edges) setLogicEdges(data.logic_graph.edges);
          }
          if (data.workflow_mappings) {
            setWorkflowMappings(data.workflow_mappings);
          }
        } catch (err) {
          console.error("Failed to load custom app", err);
        }
      };
      loadApp();
    } else if (location.state?.initialAppData) {
      const init = location.state.initialAppData;
      if (init.components) setComponents(init.components);
      if (init.rootStyle) setRootStyle(init.rootStyle);
      if (init.globalCss) setGlobalCss(init.globalCss);
      if (init.globalJs) setGlobalJs(init.globalJs);
      if (init.title) setAppTitle(init.title);
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
        current_state: {
          title: appTitle,
          ui_graph_data: { components, rootStyle, globalCss, globalJs },
          logic_graph: { nodes: logicNodes, edges: logicEdges },
          workflow_mappings: workflowMappings
        }
      };

      const res = await axios.post('/api/builder/generate_app', payload, {
        headers: { Authorization: `Bearer ${token}` }
      });

      const { reply, ui_graph_data, logic_graph, workflow_mappings, new_title } = res.data;
      
      if (new_title) setAppTitle(new_title);
      
      if (ui_graph_data) {
        if (ui_graph_data.components) {
          const CANVAS_WIDTH = 1024;
          let currentY = 30;

          // Type-safe default dimensions — AI-provided widths can be '100%', 'auto', etc.
          // which parseInt cannot handle. Use per-type safe pixel defaults instead.
          const TYPE_W = { text: 300, button: 180, input: 300, textarea: 300, dropdown: 300, checkbox: 200, divider: 560, image: 150 };
          const TYPE_H = { text: 36, button: 45, input: 45, textarea: 100, dropdown: 45, checkbox: 36, divider: 2, image: 150 };

          const positioned = ui_graph_data.components.map(comp => {
            if (!comp.props) comp.props = {};
            if (!comp.props.style) comp.props.style = {};

            const type = comp.type || 'text';

            // Resolve width: only trust AI value if it's a plain px number
            const aiW = parseInt(comp.props.style?.width);
            const w = (!isNaN(aiW) && aiW > 0 && aiW < CANVAS_WIDTH) ? aiW : (TYPE_W[type] || 200);

            // Resolve height: same logic
            const aiH = parseInt(comp.props.style?.height);
            const h = (!isNaN(aiH) && aiH > 0 && aiH < 2000) ? aiH : (TYPE_H[type] || 45);

            // Force safe px values so Rnd and preview render identically
            comp.props.style.width = `${w}px`;
            comp.props.style.height = `${h}px`;

            if (!comp.props.position) {
              comp.props.position = {
                x: Math.round((CANVAS_WIDTH - w) / 2),
                y: currentY
              };
              currentY += h + 16;
            }
            return comp;
          });
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
      
      if (workflow_mappings) {
        setWorkflowMappings(workflow_mappings);
      }

      setChatMessages([...newMessages, { role: 'assistant', content: reply || '요청하신 내용을 반영하여 앱 구성을 업데이트했습니다.' }]);
    } catch (err) {
      console.error('Failed to generate app:', err);
      setChatMessages([...newMessages, { role: 'assistant', content: '앱 생성 중 오류가 발생했습니다. 백엔드 에러 로그를 확인해주세요.' }]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const onLogicConnect = useCallback((params) => setLogicEdges((eds) => addEdge(params, eds)), [setLogicEdges]);

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
    
    // Simplistic coordinate calculation for React Flow
    const reactFlowBounds = e.currentTarget.getBoundingClientRect();
    const position = {
      x: e.clientX - reactFlowBounds.left,
      y: e.clientY - reactFlowBounds.top,
    };

    const newNode = {
      id: `logic-${Date.now()}`,
      type,
      position,
      data: { id: `logic-${Date.now()}` }
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
    const base = { id: getId(type), type, props: { position: { x, y }, style: {} } };
    if (type === 'container') {
      base.props.style = { padding: '1rem', border: '1px solid #cbd5e1', borderRadius: '4px', minHeight: '50px' };
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
      base.props.style = { width: '150px', height: '150px' };
    } else if (type === 'textarea') {
      base.props.label = 'Label';
      base.props.placeholder = 'Type multiline text here...';
      base.props.inputKey = 'textarea_' + Date.now();
      base.props.style = { width: '200px', height: '80px' };
    } else if (type === 'dropdown') {
      base.props.label = 'Select Option';
      base.props.options = 'Option 1, Option 2, Option 3';
      base.props.inputKey = 'dropdown_' + Date.now();
    } else if (type === 'checkbox') {
      base.props.label = 'Check me';
      base.props.inputKey = 'checkbox_' + Date.now();
    } else if (type === 'divider') {
      base.props.style = { width: '200px', height: '2px', backgroundColor: '#cbd5e1' };
    }
    return base;
  };

  const handleUpdateTransform = useCallback((id, transform, isShiftKey, isDragging) => {
    let newX = transform.x !== undefined ? transform.x : null;
    let newY = transform.y !== undefined ? transform.y : null;
    
    let activeLines = [];

    if (isShiftKey && isDragging) {
      const snapThreshold = 10;
      const canvasWidth = 800;
      const canvasHeight = 800; // estimated max height
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

    setComponents(prev => {
      let newComps = [...prev];
      const isMultiMoving = selectedIds.includes(id) && selectedIds.length > 1;

      if (isMultiMoving && transform.deltaX !== undefined && transform.deltaY !== undefined) {
        selectedIds.forEach(sid => {
          if (sid === id) return; // handled below
          newComps = updateComponent(newComps, sid, (c) => {
            c.props.position = { 
              x: (c.props.position?.x || 0) + transform.deltaX, 
              y: (c.props.position?.y || 0) + transform.deltaY 
            };
            return c;
          });
        });
      }

      newComps = updateComponent(newComps, id, (comp) => {
        if (newX !== null || newY !== null) {
          comp.props.position = { 
            x: newX !== null ? newX : (comp.props.position?.x || 0), 
            y: newY !== null ? newY : (comp.props.position?.y || 0) 
          };
        }
        if (transform.width !== undefined || transform.height !== undefined) {
          comp.props.style = comp.props.style || {};
          if (transform.width !== undefined) comp.props.style.width = transform.width;
          if (transform.height !== undefined) comp.props.style.height = transform.height;
        }
        return comp;
      });

      return newComps;
    });
  }, [components, selectedIds]);

  const updateSelectedData = (key, value, isStyle = false) => {
    if (selectedIds.length !== 1) return;
    const sId = selectedIds[0];
    setComponents(prev => updateComponent(prev, sId, (comp) => {
      if (key === 'x' || key === 'y') {
        comp.props.position = { ...comp.props.position, [key]: value };
      } else if (isStyle) {
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

  const handleReparent = useCallback((draggedId, targetContainerId) => {
    setComponents(prev => {
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

      let inserted = false;
      if (targetContainerId === 'root') {
        newTree.push(draggedComp);
        inserted = true;
      } else {
        const insertToTarget = (list) => {
          for (let i = 0; i < list.length; i++) {
            if (list[i].id === targetContainerId) {
              if (list[i].type === 'container' || list[i].type === 'form') {
                if (!list[i].children) list[i].children = [];
                list[i].children.push(draggedComp);
                inserted = true;
                return true;
              }
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
  }, []);

  const handleSaveAndDeploy = async () => {
    try {
      const workflowMappings = {};
      const extractMappings = (comps) => {
        comps.forEach(c => {
          if (c.props.workflowId) {
            workflowMappings[c.id] = { projectId: c.props.workflowId };
          }
          if (c.children) extractMappings(c.children);
        });
      };
      extractMappings(components);

      const payload = {
        app_id: appId,
        title: appTitle,
        ui_graph_data: { components, rootStyle, globalCss, globalJs },
        logic_graph: { nodes: logicNodes, edges: logicEdges },
        workflow_mappings: workflowMappings
      };

      const res = await axios.post('/api/builder/save', payload, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      
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

  return (
    <div className="builder-layout">
      {globalCss && <style>{globalCss}</style>}
      {/* Header */}
      <header className="builder-header">
        <div className="header-left">
          <MousePointer2 size={24} color="#3b82f6" />
          <input 
            className="app-title-input"
            value={appTitle}
            onChange={e => setAppTitle(e.target.value)}
            placeholder="앱 이름 입력..."
            style={{ width: '150px' }}
          />
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
            <div style={{ width: '100%', height: '100%', overflow: 'auto', padding: '20px', boxSizing: 'border-box', backgroundColor: '#f1f5f9' }}>
              <div 
                className="canvas-area"
                onDragOver={handleDragOver}
                onDrop={handleDropOnCanvas}
                onClick={() => handleSelect(null)}
                style={{ 
                  position: 'relative',
                  width: '1024px',
                  height: '768px',
                  minWidth: '1024px',
                  minHeight: '768px',
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
                  onUpdateTransform={handleUpdateTransform}
                  selectedIds={selectedIds}
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
            <div style={{ width: '100%', height: '100%', overflow: 'auto', padding: '20px', boxSizing: 'border-box', backgroundColor: '#f1f5f9' }}>
              <div 
                className="canvas-area"
                style={{ 
                  position: 'relative',
                  width: '1024px',
                  height: '768px',
                  minWidth: '1024px',
                  minHeight: '768px',
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
              
              {selectedComponent?.type === 'button' || selectedComponent?.type === 'text' ? (
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
                    <label>Flex Direction</label>
                    <select value={selectedComponent.props.style?.flexDirection || 'column'} onChange={(e) => updateSelectedData('flexDirection', e.target.value, true)}>
                      <option value="column">Column (Vertical)</option>
                      <option value="row">Row (Horizontal)</option>
                    </select>
                  </div>
                  <div className="prop-group">
                    <label>Justify Content (주축 정렬)</label>
                    <select value={selectedComponent.props.style?.justifyContent || 'flex-start'} onChange={(e) => updateSelectedData('justifyContent', e.target.value, true)}>
                      <option value="flex-start">Start</option>
                      <option value="center">Center</option>
                      <option value="flex-end">End</option>
                      <option value="space-between">Space Between</option>
                    </select>
                  </div>
                  <div className="prop-group">
                    <label>Align Items (교차축 정렬)</label>
                    <select value={selectedComponent.props.style?.alignItems || 'stretch'} onChange={(e) => updateSelectedData('alignItems', e.target.value, true)}>
                      <option value="stretch">Stretch (꽉 채우기)</option>
                      <option value="flex-start">Start</option>
                      <option value="center">Center</option>
                      <option value="flex-end">End</option>
                    </select>
                  </div>
                </>
              )}

              {selectedComponent?.type === 'button' && (
                <>
                  <div className="sidebar-title" style={{ marginTop: '1.5rem', color: '#10b981' }}>Workflow Binding</div>
                  <div className="prop-group">
                    <label>Project ID (Workflow to Run)</label>
                    <input 
                      type="text" 
                      placeholder="Enter Project ID" 
                      value={selectedComponent.props.workflowId || ''} 
                      onChange={(e) => updateSelectedData('workflowId', e.target.value)} 
                    />
                    <small style={{ color: 'var(--text-muted)' }}>* Button click will execute this workflow.</small>
                  </div>
                </>
              )}
              
              {selectedComponent?.type === 'button' && (
                <>
                  <div className="sidebar-title" style={{ marginTop: '1.5rem', color: '#f59e0b' }}>Global JS Binding</div>
                  <div className="prop-group">
                    <label>onClickHandler (JS Function Name)</label>
                    <input 
                      type="text"
                      placeholder="e.g. onSaveClick" 
                      value={selectedComponent.props.onClickHandler || ''} 
                      onChange={(e) => updateSelectedData('onClickHandler', e.target.value)} 
                      style={{ fontFamily: 'monospace', fontSize: '12px' }}
                    />
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
            <button className="btn-icon-close" onClick={() => setIsAssistantOpen(false)}>
              ✕
            </button>
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
              disabled={!chatInput.trim() || isChatLoading}
            >
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Deploy Modal */}
      {showDeployModal && (
        <div className="modal-overlay">
          <div className="deploy-modal">
            <h2>🎉 배포 완료!</h2>
            <p>커스텀 앱이 성공적으로 저장되고 배포되었습니다.</p>
            <div className="url-box">
              <input type="text" readOnly value={deployedUrl} />
              <button onClick={() => { navigator.clipboard.writeText(deployedUrl); alert('복사되었습니다!'); }}>
                복사
              </button>
            </div>
            <div className="modal-actions">
              <a href={deployedUrl} target="_blank" rel="noreferrer" className="btn-primary">
                앱 열기
              </a>
              <button className="btn-secondary" onClick={() => setShowDeployModal(false)}>
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
