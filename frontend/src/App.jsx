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
import { Play, Code } from 'lucide-react';
import Sidebar from './Sidebar';
import { PromptNode, LLMNode, OutputNode, ConditionNode, ValueNode, LoopNode, BreakNode, PythonNode, TokenizerNode, DistributorNode } from './customNodes';

const nodeTypes = {
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
};

let id = 0;
const getId = () => `dndnode_${id++}`;

function FlowContent() {
  const reactFlowWrapper = useRef(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { screenToFlowPosition } = useReactFlow();
  const [response, setResponse] = useState('');
  const [isCompiled, setIsCompiled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

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
                newNode.zIndex = 10; // Ensure child nodes render above
                break;
            }
          }
        }
        return nds.concat(newNode);
      });
    },
    [screenToFlowPosition, onNodeDataChange, deleteNode, setNodes],
  );

  const { getIntersectingNodes } = useReactFlow();

  const onNodeDragStop = useCallback((event, node) => {
    if (node.type === 'loopNode') return;

    const intersections = getIntersectingNodes(node).filter((n) => n.type === 'loopNode');
    const targetParentId = intersections.length > 0 ? intersections[0].id : undefined;

    if (node.parentNode === targetParentId) return;

    setNodes((nds) => {
      const parentObj = targetParentId ? nds.find(n => n.id === targetParentId) : null;
      
      return nds.map((n) => {
        if (n.id === node.id) {
          if (targetParentId && parentObj) {
             const absX = node.positionAbsolute ? node.positionAbsolute.x : node.position.x;
             const absY = node.positionAbsolute ? node.positionAbsolute.y : node.position.y;
             
             return {
               ...n,
               parentNode: targetParentId,
               zIndex: 10,
               position: {
                 x: absX - parentObj.position.x,
                 y: absY - parentObj.position.y,
               }
             };
          } else if (n.parentNode) {
             const { parentNode, ...rest } = n;
             const absX = node.positionAbsolute ? node.positionAbsolute.x : node.position.x;
             const absY = node.positionAbsolute ? node.positionAbsolute.y : node.position.y;
             return {
               ...rest,
               zIndex: 1,
               position: { x: absX, y: absY }
             };
          }
        }
        
        // Also ensure all loop nodes stay at zIndex -1
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
      // Pass the entire node data including prompts/model selections to backend
      const payload = {
        nodes: nodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
        edges: edges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle }))
      };

      const res = await axios.post('http://localhost:8000/api/execute', payload);
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
        edges: edges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle }))
      };

      const res = await axios.post('http://localhost:8000/api/compile', payload);
      setResponse(res.data.code || 'No code generated.');
    } catch (error) {
      console.error(error);
      setResponse('Error communicating with backend: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>LangChain Visual Builder</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
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
                  case 'promptNode': return '#10b981';
                  case 'llmNode': return '#8b5cf6';
                  case 'outputNode': return '#f59e0b';
                  case 'loopNode': return '#eab308';
                  case 'breakNode': return '#ef4444';
                  case 'pythonNode': return '#3b82f6';
                  case 'tokenizerNode': return '#10b981';
                  case 'distributorNode': return '#8b5cf6';
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
              response || 'Run or Compile the flow to see the results here.'
            )}
          </div>
        </aside>
      </main>
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
