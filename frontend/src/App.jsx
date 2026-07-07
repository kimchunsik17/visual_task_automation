import { useState, useCallback } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';
import { Play } from 'lucide-react';

const initialNodes = [
  { id: '1', position: { x: 100, y: 150 }, data: { label: 'Start Trigger' }, type: 'startNode' },
  { id: '2', position: { x: 400, y: 150 }, data: { label: 'Generate Summary Task' }, type: 'taskNode' },
];

const initialEdges = [];

const StartNode = ({ data }) => (
  <div className="custom-node start">
    <Handle type="source" position={Position.Right} />
    <div>{data.label}</div>
  </div>
);

const TaskNode = ({ data }) => (
  <div className="custom-node task">
    <Handle type="target" position={Position.Left} />
    <div>{data.label}</div>
    <Handle type="source" position={Position.Right} />
  </div>
);

const nodeTypes = {
  startNode: StartNode,
  taskNode: TaskNode,
};

function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [response, setResponse] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const onConnect = useCallback((params) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

  const runFlow = async () => {
    setIsLoading(true);
    setResponse('Running graph on backend...');
    
    try {
      const payload = {
        nodes: nodes.map(n => ({ id: n.id, label: n.data.label, type: n.type })),
        edges: edges.map(e => ({ source: e.source, target: e.target }))
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

  return (
    <div className="app-container">
      <header className="header">
        <h1>AutoFlow Pilot</h1>
        <button className="btn-run" onClick={runFlow} disabled={isLoading}>
          <Play size={18} />
          {isLoading ? 'Running...' : 'Run Flow'}
        </button>
      </header>
      
      <main className="main-content">
        <div className="flow-wrapper">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
            colorMode="dark"
          >
            <Controls />
            <MiniMap 
              nodeColor={(node) => {
                switch (node.type) {
                  case 'startNode': return '#10b981';
                  case 'taskNode': return '#8b5cf6';
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
            {response || 'Run the flow to see the results here.'}
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;
