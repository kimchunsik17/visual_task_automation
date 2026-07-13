import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Send, Bot, User } from 'lucide-react';
import './MainPage.css'; // Reuse existing layout classes if needed

const AppViewerPage = () => {
  const { projectId } = useParams();
  const [project, setProject] = useState(null);
  const [deployMode, setDeployMode] = useState('chatbot');
  
  // For Form mode
  const [formInputs, setFormInputs] = useState({});
  const [formResult, setFormResult] = useState('');
  // For Chatbot mode
  const [chatHistory, setChatHistory] = useState([]);
  const [currentMessage, setCurrentMessage] = useState('');
  
  const [isLoading, setIsLoading] = useState(true);
  const [isExecuting, setIsExecuting] = useState(false);
  const [dynamicNodes, setDynamicNodes] = useState([]);

  useEffect(() => {
    const fetchProject = async () => {
      try {
        // Here we ideally fetch public project info or user auth depending on visibility
        const res = await axios.get(`/api/projects/${projectId}`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
        });
        setProject(res.data);
        
        // Retrieve deploy mode from project (assuming backend sends it, fallback to 'chatbot')
        const mode = res.data.deploy_mode || 'chatbot';
        setDeployMode(mode);

        // Find all dynamic input nodes
        const nodes = res.data.graph_data?.nodes || [];
        const dynNodes = nodes.filter(n => n.type === 'dynamicInputNode');
        setDynamicNodes(dynNodes);
        
        const initialForm = {};
        dynNodes.forEach(n => {
          initialForm[n.id] = '';
        });
        setFormInputs(initialForm);

      } catch (error) {
        console.error(error);
        const errorMsg = error.response?.data?.detail || error.message;
        alert(`?ÑÎ°ú?ùÌä∏Î•?Î∂àÎü¨?§Ï? Î™ªÌñà?µÎãà?? ?êÎü¨: ${errorMsg}`);
      } finally {
        setIsLoading(false);
      }
    };
    fetchProject();
  }, [projectId]);

  const executeFlow = async (inputs) => {
    setIsExecuting(true);
    try {
      const res = await axios.post(`/api/deploy/${projectId}/execute`, { inputs }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
      });
      return res.data.result;
    } catch (error) {
      console.error(error);
      return '?§Ìñâ Ï§??§Î•òÍ∞Ä Î∞úÏÉù?àÏäµ?àÎã§.';
    } finally {
      setIsExecuting(false);
    }
  };

  const handleFormSubmit = async (e) => {
    e.preventDefault();
    setFormResult(''); // Clear previous
    const result = await executeFlow(formInputs);
    setFormResult(result);
  };

  const handleChatSubmit = async (e) => {
    e.preventDefault();
    if (!currentMessage.trim()) return;

    const userMsg = currentMessage;
    setChatHistory(prev => [...prev, { role: 'user', content: userMsg }]);
    setCurrentMessage('');

    // In chatbot mode, we assume there's one dynamic input node to feed this message to
    const targetNodeId = dynamicNodes.length > 0 ? dynamicNodes[0].id : 'default_input';
    
    const result = await executeFlow({ [targetNodeId]: userMsg });
    setChatHistory(prev => [...prev, { role: 'bot', content: result }]);
  };

  if (isLoading) return <div style={{ color: 'var(--text-color)', padding: '2rem' }}>Î°úÎî© Ï§?..</div>;
  if (!project) return <div style={{ color: 'var(--text-color)', padding: '2rem' }}>?ÑÎ°ú?ùÌä∏Î•?Ï∞æÏùÑ ???ÜÏäµ?àÎã§.</div>;

  return (
    <div style={{ backgroundColor: 'var(--bg-color)', minHeight: '100vh', display: 'flex', flexDirection: 'column', color: 'var(--text-color)' }}>
      <header style={{ padding: '1rem 2rem', borderBottom: '1px solid var(--border-color)', backgroundColor: 'var(--card-bg)' }}>
        <h1 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600 }}>{project.title}</h1>
        {project.description && <p style={{ margin: '0.5rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>{project.description}</p>}
      </header>

      <main style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: '2rem' }}>
        {deployMode === 'form' ? (
          <div style={{ width: '100%', maxWidth: '600px', backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '2rem' }}>
            <form onSubmit={handleFormSubmit}>
              {dynamicNodes.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>???åÌÅ¨?åÎ°ú?∞Ïóê???ôÏ†Å ?ÖÎ†• ?∏ÎìúÍ∞Ä ?ÜÏäµ?àÎã§. Î∞îÎ°ú ?§Ìñâ??Î≥¥ÏÑ∏??</p>
              ) : (
                dynamicNodes.map(node => (
                  <div key={node.id} style={{ marginBottom: '1.5rem' }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                      {node.data?.inputLabel || '?ÖÎ†•'}
                    </label>
                    <input
                      type="text"
                      value={formInputs[node.id] || ''}
                      onChange={(e) => setFormInputs({...formInputs, [node.id]: e.target.value})}
                      style={{ width: '100%', padding: '0.8rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'rgba(255,255,255,0.03)', color: 'var(--text-color)' }}
                      required
                    />
                  </div>
                ))
              )}
              <button 
                type="submit" 
                className="btn-run" 
                disabled={isExecuting}
                style={{ width: '100%', padding: '1rem', fontSize: '1.1rem', marginTop: '1rem' }}
              >
                {isExecuting ? '?§Ìñâ Ï§?..' : '?§Ìñâ?òÍ∏∞'}
              </button>
            </form>
            {formResult && (
              <div style={{ marginTop: '2rem', padding: '1.5rem', backgroundColor: 'rgba(59, 130, 246, 0.1)', border: '1px solid #3b82f6', borderRadius: '8px' }}>
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: '#60a5fa' }}>?§Ìñâ Í≤∞Í≥º</h3>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{formResult}</pre>
              </div>
            )}
          </div>
        ) : (
          /* Chatbot Mode */
          <div style={{ width: '100%', maxWidth: '800px', backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 150px)' }}>
            <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {chatHistory.length === 0 ? (
                <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <Bot size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                  <p>?Ä?îÎ? ?úÏûë??Î≥¥ÏÑ∏?? ?åÌÅ¨?åÎ°ú?∞Í? ?§Ìñâ?©Îãà??</p>
                </div>
              ) : (
                chatHistory.map((msg, idx) => (
                  <div key={idx} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                    <div style={{ display: 'flex', gap: '0.8rem', maxWidth: '80%', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                      <div style={{ width: '36px', height: '36px', borderRadius: '50%', backgroundColor: msg.role === 'user' ? '#3b82f6' : '#8b5cf6', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
                      </div>
                      <div style={{ padding: '1rem', borderRadius: '12px', backgroundColor: msg.role === 'user' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255, 255, 255, 0.05)', color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>
                        {msg.content}
                      </div>
                    </div>
                  </div>
                ))
              )}
              {isExecuting && (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div style={{ padding: '1rem', borderRadius: '12px', backgroundColor: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-muted)' }}>
                    ?§Ìñâ Ï§?..
                  </div>
                </div>
              )}
            </div>
            
            <div style={{ padding: '1rem', borderTop: '1px solid var(--border-color)' }}>
              <form onSubmit={handleChatSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  type="text"
                  value={currentMessage}
                  onChange={(e) => setCurrentMessage(e.target.value)}
                  placeholder="Î©îÏãúÏßÄÎ•??ÖÎ†•?òÏÑ∏??.."
                  style={{ flex: 1, padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)', backgroundColor: 'rgba(255,255,255,0.03)', color: 'var(--text-color)', outline: 'none' }}
                  disabled={isExecuting}
                />
                <button type="submit" className="btn-run" disabled={isExecuting || !currentMessage.trim()} style={{ padding: '0 1.5rem', borderRadius: '8px' }}>
                  <Send size={20} />
                </button>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default AppViewerPage;
