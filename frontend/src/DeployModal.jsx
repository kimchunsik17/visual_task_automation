import React, { useState } from 'react';
import { X, Bot, LayoutTemplate, Download, Code2, MessageSquare } from 'lucide-react';
import axios from 'axios';

const DeployModal = ({ isOpen, onClose, project, onDeployConfigSaved }) => {
  const [deployMode, setDeployMode] = useState('chatbot');
  const [discordToken, setDiscordToken] = useState('');
  const [isDeploying, setIsDeploying] = useState(false);

  if (!isOpen) return null;

  const handleDeploy = async () => {
    setIsDeploying(true);
    try {
      // API call to save deploy config or generate code
      const response = await axios.post(`/api/deploy/${project.id}`, { 
        mode: deployMode,
        discord_bot_token: deployMode === 'discord' ? discordToken : undefined
      }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
      });
      
      if (deployMode === 'fastapi' || deployMode === 'mcp') {
        // Trigger download
        const blob = new Blob([response.data.code], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${project?.title || 'flow'}_${deployMode}.py`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      } else {
        const goApp = window.confirm("ë°°í¬ê°€ ?„ë£Œ?˜ì—ˆ?µë‹ˆ?? ì§€ê¸?ë°°í¬?????˜ì´ì§€ë¡??´ë™?˜ì‹œê² ìŠµ?ˆê¹Œ?");
        if (goApp) {
          window.open(`/app/${project.id}`, '_blank');
        }
        if (onDeployConfigSaved) onDeployConfigSaved(deployMode);
      }
      onClose();
    } catch (error) {
      alert("ë°°í¬ ì¤??¤ë¥˜ê°€ ë°œìƒ?ˆìŠµ?ˆë‹¤.");
      console.error(error);
    } finally {
      setIsDeploying(false);
    }
  };

  return (
    <div className="modal-overlay" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.7)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="modal-content" style={{ backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', width: '500px', maxWidth: '90vw', padding: '1.5rem', position: 'relative' }}>
        <button onClick={onClose} style={{ position: 'absolute', top: '1.5rem', right: '1.5rem', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
          <X size={20} />
        </button>
        
        <h2 style={{ margin: '0 0 1.5rem 0', color: 'var(--text-color)', fontSize: '1.3rem' }}>?Œí¬?Œë¡œ??ë°°í¬</h2>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '2rem' }}>
          <div 
            onClick={() => setDeployMode('chatbot')}
            style={{ padding: '1rem', border: `2px solid ${deployMode === 'chatbot' ? '#3b82f6' : 'var(--border-color)'}`, borderRadius: '8px', cursor: 'pointer', backgroundColor: deployMode === 'chatbot' ? 'rgba(59, 130, 246, 0.1)' : 'transparent', textAlign: 'center' }}
          >
            <Bot size={32} color={deployMode === 'chatbot' ? '#3b82f6' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
            <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', color: 'var(--text-color)' }}>Web App (Chatbot)</h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>?€?”í˜• ì±—ë´‡ ?¸í„°?˜ì´?¤ë¡œ ë°°í¬?©ë‹ˆ??</p>
          </div>
          
          <div 
            onClick={() => setDeployMode('form')}
            style={{ padding: '1rem', border: `2px solid ${deployMode === 'form' ? '#10b981' : 'var(--border-color)'}`, borderRadius: '8px', cursor: 'pointer', backgroundColor: deployMode === 'form' ? 'rgba(16, 185, 129, 0.1)' : 'transparent', textAlign: 'center' }}
          >
            <LayoutTemplate size={32} color={deployMode === 'form' ? '#10b981' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
            <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', color: 'var(--text-color)' }}>Web App (Form)</h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>?¨ìˆœ???…ë ¥ ?¼ê³¼ ë²„íŠ¼ ?•íƒœ???˜ì´ì§€ë¡?ë°°í¬?©ë‹ˆ??</p>
          </div>

          <div 
            onClick={() => setDeployMode('fastapi')}
            style={{ padding: '1rem', border: `2px solid ${deployMode === 'fastapi' ? '#eab308' : 'var(--border-color)'}`, borderRadius: '8px', cursor: 'pointer', backgroundColor: deployMode === 'fastapi' ? 'rgba(234, 179, 8, 0.1)' : 'transparent', textAlign: 'center' }}
          >
            <Code2 size={32} color={deployMode === 'fastapi' ? '#eab308' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
            <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', color: 'var(--text-color)' }}>FastAPI Server</h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>?…ë¦½?ì¸ ë°±ì—”???œë²„ ?Œì´???¤í¬ë¦½íŠ¸ë¥??¤ìš´ë¡œë“œ?©ë‹ˆ??</p>
          </div>

          <div 
            onClick={() => setDeployMode('mcp')}
            style={{ padding: '1rem', border: `2px solid ${deployMode === 'mcp' ? '#8b5cf6' : 'var(--border-color)'}`, borderRadius: '8px', cursor: 'pointer', backgroundColor: deployMode === 'mcp' ? 'rgba(139, 92, 246, 0.1)' : 'transparent', textAlign: 'center' }}
          >
            <Download size={32} color={deployMode === 'mcp' ? '#8b5cf6' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
            <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', color: 'var(--text-color)' }}>MCP Server</h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>Claude Desktop??MCP ?œë²„ ?¤í¬ë¦½íŠ¸ë¥??¤ìš´ë¡œë“œ?©ë‹ˆ??</p>
          </div>
          
          <div 
            onClick={() => setDeployMode('discord')}
            style={{ padding: '1rem', border: `2px solid ${deployMode === 'discord' ? '#ec4899' : 'var(--border-color)'}`, borderRadius: '8px', cursor: 'pointer', backgroundColor: deployMode === 'discord' ? 'rgba(236, 72, 153, 0.1)' : 'transparent', textAlign: 'center', gridColumn: '1 / -1' }}
          >
            <MessageSquare size={32} color={deployMode === 'discord' ? '#ec4899' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
            <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', color: 'var(--text-color)' }}>Discord Bot (Interactive)</h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>?”ìŠ¤ì½”ë“œ ë´‡ìœ¼ë¡??‘ë™?œì¼œ ì±„íŒ… ì±„ë„?ì„œ ?Œí¬?Œë¡œ?°ë? ?¤í–‰?©ë‹ˆ??</p>
            {deployMode === 'discord' && (
              <div style={{ marginTop: '1rem', textAlign: 'left' }} onClick={e => e.stopPropagation()}>
                <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-color)', fontSize: '0.9rem' }}>?”ìŠ¤ì½”ë“œ ë´?? í° (Discord Bot Token)</label>
                <input 
                  type="password"
                  value={discordToken}
                  onChange={(e) => setDiscordToken(e.target.value)}
                  placeholder="?”ìŠ¤ì½”ë“œ ê°œë°œ???¬í„¸?ì„œ ë°œê¸‰ë°›ì? ? í° ?…ë ¥"
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
                />
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
          <button className="btn-secondary" onClick={onClose} disabled={isDeploying}>ì·¨ì†Œ</button>
          <button className="btn-run" onClick={handleDeploy} disabled={isDeploying || (deployMode === 'discord' && !discordToken.trim())}>
            {isDeploying ? 'ë°°í¬ ì¤?..' : (deployMode === 'fastapi' || deployMode === 'mcp' ? 'ì½”ë“œ ?¤ìš´ë¡œë“œ' : 'ë°°í¬?˜ê¸°')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeployModal;
