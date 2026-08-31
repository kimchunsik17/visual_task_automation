import React, { useState } from 'react';
import { X, Bot, LayoutTemplate, Download, Code2 } from 'lucide-react';
import axios from 'axios';
import { customConfirm } from './CustomConfirm';
import { celebrateMilestone } from './milestoneCelebrations';

const DeployModal = ({ isOpen, onClose, project, onDeployConfigSaved, previewOnly = false }) => {
  const [deployMode, setDeployMode] = useState('apprunner');
  const [isDeploying, setIsDeploying] = useState(false);

  if (!isOpen) return null;

  const handleDeploy = async () => {
    setIsDeploying(true);
    try {
      if (previewOnly) {
        await new Promise((resolve) => window.setTimeout(resolve, 650));
        if (onDeployConfigSaved) onDeployConfigSaved(deployMode);
        onClose();
        return;
      }

      if (deployMode === 'apprunner') {
        const res = await axios.post(`/api/projects/${project.id}/deploy`, {}, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
        });
        const shareToken = res.data.share_token;
        const appUrl = `${window.location.origin}/app/${shareToken}`;
        const goApp = await customConfirm(`독립형 앱 배포가 완료되었습니다!\n링크: ${appUrl}\n\n지금 바로 접속하시겠습니까?`);
        if (goApp) {
          window.open(`/app/${shareToken}`, '_blank');
        }
        if (onDeployConfigSaved) onDeployConfigSaved(deployMode);
        celebrateMilestone('first-deploy');
        onClose();
        return;
      }

      // API call to save deploy config or generate code
      const response = await axios.post(`/api/deploy/${project.id}`, {
        mode: deployMode
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
        const goApp = await customConfirm("배포가 완료되었습니다! 지금 챗봇/폼 뷰어 페이지로 이동하시겠습니까?");
        if (goApp) {
          window.open(`/viewer/${project.id}`, '_blank');
        }
        if (onDeployConfigSaved) onDeployConfigSaved(deployMode);
        celebrateMilestone('first-deploy');
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

          {/* Integrations: 디스코드 봇은 이제 여기서 배포하는 게 아니라, 웹훅/스케줄과 동일하게
              캔버스 안의 "디스코드 봇 (시작)" 노드 + 에디터 상단의 "라이브 시작" 토글로 켠다.
              토큰을 모달에 매번 붙여넣을 필요 없이 API 센터에 등록해두면 자동으로 연결된다. */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>Integrations</h3>
            <div style={{ padding: '1rem', border: '1px dashed var(--border-color)', borderRadius: '10px', color: 'var(--text-muted)', fontSize: '0.85rem', lineHeight: '1.5' }}>
              💬 <strong style={{ color: 'var(--text-color)' }}>디스코드 봇</strong>은 여기서 배포하지 않아요 —
              캔버스에 <strong style={{ color: 'var(--text-color)' }}>"디스코드 봇 (시작)"</strong> 노드를 추가하고
              봇 토큰을 입력한 뒤(또는 API 센터 연동), 에디터 상단의 <strong style={{ color: 'var(--text-color)' }}>"라이브 시작"</strong> 토글을
              켜면 그 순간부터 봇이 메시지를 기다립니다. 스케줄/웹훅 트리거와 동일한 방식이에요.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-color)' }}>
          <button className="btn-secondary" onClick={onClose} disabled={isDeploying}>취소</button>
          <button className="btn-run" onClick={handleDeploy} disabled={isDeploying}>
            {isDeploying ? '처리 중...' : (deployMode === 'fastapi' || deployMode === 'mcp' ? '코드 다운로드' : '배포하기')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeployModal;
