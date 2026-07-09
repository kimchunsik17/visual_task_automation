import { useState, useCallback, useRef } from 'react';
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
import { Play, Code, Folder } from 'lucide-react';
import Sidebar from './Sidebar';
import TemplateModal from './TemplateModal';
import { StartNode, PromptNode, LLMNode, OutputNode, ConditionNode, ValueNode, LoopNode, BreakNode, PythonNode, TokenizerNode, DistributorNode, FileModifierNode, TemplateAnalyzerNode } from './customNodes';

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
};

let id = 0;
const getId = () => `dndnode_${id++}`;

function FlowContent() {
  const reactFlowWrapper = useRef(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { screenToFlowPosition, getNodes, getEdges } = useReactFlow();
  const [response, setResponse] = useState('');
  const [isCompiled, setIsCompiled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);

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
    } catch (error) {
      console.error(error);
      setResponse('Error communicating with backend: ' + (error.response?.data?.detail || error.message));
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

  return (
    <div className="app-container">
      <header className="header">
        <h1>LangChain Visual Builder</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn-run" onClick={() => setIsTemplateModalOpen(true)} style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', color: 'white' }}>
            <Folder size={18} />
            Templates
          </button>
          <button className="btn-run" onClick={compileFlow} disabled={isLoading} style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', color: 'white' }}>
            <Code size={18} />
            {isLoading ? '...' : 'Compile Code'}
          </button>
          <button className="btn-run" onClick={runFlow} disabled={isLoading}>
            <Play size={18} />
            {isLoading ? 'Running...' : 'Run Flow'}
          </button>
        </div>
      </header>
      
      <main className="main-content">
        <Sidebar />
        <div className="flow-wrapper" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeDragStop={onNodeDragStop}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={{ 
              style: { strokeWidth: 2, stroke: '#94a3b8' },
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
                  default: return '#eee';
                }
              }}
            />
            <Background variant="dots" gap={12} size={1} color="#334155" />
          </ReactFlow>
        </div>
        
        <aside className="response-panel">
          <h2>Execution Result</h2>
          <div className="response-content">
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
                    style={{ display: 'inline-block', padding: '8px 16px', background: '#3b82f6', color: 'white', textDecoration: 'none', borderRadius: '4px', marginTop: '10px' }}
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
    </div>
  );
}

function App() {
  return (
    <ReactFlowProvider>
      <FlowContent />
    </ReactFlowProvider>
  );
}

export default App;
