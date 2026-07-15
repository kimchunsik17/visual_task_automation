import React, { useState } from 'react';
import { X, Bot, LayoutTemplate, Download, Code2, MessageSquare } from 'lucide-react';
import axios from 'axios';

const DeployModal = ({ isOpen, onClose, project, onDeployConfigSaved }) => {
  const [deployMode, setDeployMode] = useState('apprunner');
  const [discordToken, setDiscordToken] = useState('');
  const [isDeploying, setIsDeploying] = useState(false);

  if (!isOpen) return null;

  const handleDeploy = async () => {
    setIsDeploying(true);
    try {
      if (deployMode === 'apprunner') {
        const res = await axios.post(`/api/projects/${project.id}/deploy`, {}, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
        });
        const shareToken = res.data.share_token;
        const appUrl = `${window.location.origin}/app/${shareToken}`;
        const goApp = window.confirm(`독립형 앱 배포가 완료되었습니다!\n링크: ${appUrl}\n\n지금 바로 접속하시겠습니까?`);
        if (goApp) {
          window.open(`/app/${shareToken}`, '_blank');
        }
        if (onDeployConfigSaved) onDeployConfigSaved(deployMode);
        onClose();
        return;
      }

      // API call to save deploy config or generate code
      const response = await axios.post(`/api/deploy/${project.id}`, { 
        mode: deployMode,
        discord_bot_token: deployMode === 'discord' ? discordToken : undefined
      }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
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
        const goApp = window.confirm("배포가 완료되었습니다! 지금 챗봇/폼 뷰어 페이지로 이동하시겠습니까?");
        if (goApp) {
          window.open(`/viewer/${project.id}`, '_blank');
        }
        if (onDeployConfigSaved) onDeployConfigSaved(deployMode);
      }
      onClose();
    } catch (error) {
      alert("배포 중 오류가 발생했습니다.");
      console.error(error);
    } finally {
      setIsDeploying(false);
    }
  };

  return (
    <div className="modal-overlay" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.7)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="modal-content" style={{ backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', width: '650px', maxWidth: '90vw', padding: '1.5rem', position: 'relative', display: 'flex', flexDirection: 'column', maxHeight: '85vh' }}>
        <button onClick={onClose} style={{ position: 'absolute', top: '1.5rem', right: '1.5rem', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
          <X size={20} />
        </button>
        
        <h2 style={{ margin: '0 0 1.5rem 0', color: 'var(--text-color)', fontSize: '1.3rem' }}>🚀 워크플로우 배포</h2>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto', paddingRight: '0.5rem', flex: 1 }}>
          
          {/* Category 1: Web Apps */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>Web Applications</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
              <div 
                onClick={() => setDeployMode('apprunner')}
                style={{ padding: '1rem', border: `2px solid ${deployMode === 'apprunner' ? '#3b82f6' : 'var(--border-color)'}`, borderRadius: '10px', cursor: 'pointer', backgroundColor: deployMode === 'apprunner' ? 'rgba(59, 130, 246, 0.1)' : 'var(--bg-color)', textAlign: 'center', transition: 'all 0.2s', boxShadow: deployMode === 'apprunner' ? '0 0 12px rgba(59, 130, 246, 0.3)' : 'none' }}
              >
                <LayoutTemplate size={28} color={deployMode === 'apprunner' ? '#3b82f6' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
                <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-color)' }}>App Runner</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>독립형 실행 웹사이트</p>
              </div>

              <div 
                onClick={() => setDeployMode('chatbot')}
                style={{ padding: '1rem', border: `2px solid ${deployMode === 'chatbot' ? '#10b981' : 'var(--border-color)'}`, borderRadius: '10px', cursor: 'pointer', backgroundColor: deployMode === 'chatbot' ? 'rgba(16, 185, 129, 0.1)' : 'var(--bg-color)', textAlign: 'center', transition: 'all 0.2s', boxShadow: deployMode === 'chatbot' ? '0 0 12px rgba(16, 185, 129, 0.3)' : 'none' }}
              >
                <Bot size={28} color={deployMode === 'chatbot' ? '#10b981' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
                <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-color)' }}>Chatbot</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>대화형 챗봇 인터페이스</p>
              </div>
              
              <div 
                onClick={() => setDeployMode('form')}
                style={{ padding: '1rem', border: `2px solid ${deployMode === 'form' ? '#10b981' : 'var(--border-color)'}`, borderRadius: '10px', cursor: 'pointer', backgroundColor: deployMode === 'form' ? 'rgba(16, 185, 129, 0.1)' : 'var(--bg-color)', textAlign: 'center', transition: 'all 0.2s', boxShadow: deployMode === 'form' ? '0 0 12px rgba(16, 185, 129, 0.3)' : 'none' }}
              >
                <LayoutTemplate size={28} color={deployMode === 'form' ? '#10b981' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
                <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-color)' }}>Form</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>단순 입력 폼 인터페이스</p>
              </div>
            </div>
          </div>

          {/* Category 2: API & Code */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>APIs & Code</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div 
                onClick={() => setDeployMode('fastapi')}
                style={{ padding: '1rem', border: `2px solid ${deployMode === 'fastapi' ? '#eab308' : 'var(--border-color)'}`, borderRadius: '10px', cursor: 'pointer', backgroundColor: deployMode === 'fastapi' ? 'rgba(234, 179, 8, 0.1)' : 'var(--bg-color)', textAlign: 'center', transition: 'all 0.2s', boxShadow: deployMode === 'fastapi' ? '0 0 12px rgba(234, 179, 8, 0.3)' : 'none' }}
              >
                <Code2 size={28} color={deployMode === 'fastapi' ? '#eab308' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
                <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-color)' }}>FastAPI Server</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>독립 백엔드 코드 다운로드</p>
              </div>

              <div 
                onClick={() => setDeployMode('mcp')}
                style={{ padding: '1rem', border: `2px solid ${deployMode === 'mcp' ? '#8b5cf6' : 'var(--border-color)'}`, borderRadius: '10px', cursor: 'pointer', backgroundColor: deployMode === 'mcp' ? 'rgba(139, 92, 246, 0.1)' : 'var(--bg-color)', textAlign: 'center', transition: 'all 0.2s', boxShadow: deployMode === 'mcp' ? '0 0 12px rgba(139, 92, 246, 0.3)' : 'none' }}
              >
                <Download size={28} color={deployMode === 'mcp' ? '#8b5cf6' : 'var(--text-muted)'} style={{ margin: '0 auto 0.5rem' }} />
                <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-color)' }}>MCP Server</h4>
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>Claude Desktop용 연동 서버</p>
              </div>
            </div>
          </div>

          {/* Category 3: Integrations */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>Integrations</h3>
            <div 
              onClick={() => setDeployMode('discord')}
              style={{ padding: '1.25rem', border: `2px solid ${deployMode === 'discord' ? '#ec4899' : 'var(--border-color)'}`, borderRadius: '10px', cursor: 'pointer', backgroundColor: deployMode === 'discord' ? 'rgba(236, 72, 153, 0.1)' : 'var(--bg-color)', transition: 'all 0.2s', boxShadow: deployMode === 'discord' ? '0 0 12px rgba(236, 72, 153, 0.3)' : 'none', display: 'flex', flexDirection: 'column' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <MessageSquare size={32} color={deployMode === 'discord' ? '#ec4899' : 'var(--text-muted)'} />
                <div style={{ flex: 1 }}>
                  <h4 style={{ margin: '0 0 0.25rem', fontSize: '1rem', color: 'var(--text-color)' }}>Discord Bot (Interactive)</h4>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>디스코드 채팅 채널에서 봇을 통해 워크플로우를 실행합니다.</p>
                </div>
              </div>
              
              {deployMode === 'discord' && (
                <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px dashed var(--border-color)', textAlign: 'left' }} onClick={e => e.stopPropagation()}>
                  <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-color)', fontSize: '0.85rem' }}>Discord Bot Token</label>
                  <input 
                    type="password"
                    value={discordToken}
                    onChange={(e) => setDiscordToken(e.target.value)}
                    placeholder="디스코드 개발자 포털에서 발급받은 토큰 입력"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: '6px', background: 'var(--btn-active-bg)', color: 'var(--text-color)', border: '1px solid var(--border-color)', outline: 'none' }}
                  />
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-color)' }}>
          <button className="btn-secondary" onClick={onClose} disabled={isDeploying}>취소</button>
          <button className="btn-run" onClick={handleDeploy} disabled={isDeploying || (deployMode === 'discord' && !discordToken.trim())}>
            {isDeploying ? '처리 중...' : (deployMode === 'fastapi' || deployMode === 'mcp' ? '코드 다운로드' : '배포하기')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeployModal;

