import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { Play, Share2, Lock, Unlock, AlertTriangle, Copy, Download, Check, XCircle, Clock } from 'lucide-react';
import './AppRunnerPage.css';

export default function AppRunnerPage() {
  const { shareToken } = useParams();
  const navigate = useNavigate();
  const [appInfo, setAppInfo] = useState(null);
  const [isLoadingInfo, setIsLoadingInfo] = useState(true);
  const [isExecuting, setIsExecuting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [inputValues, setInputValues] = useState({});
  const [elapsedTime, setElapsedTime] = useState(0);
  const [isCopied, setIsCopied] = useState(false);
  const [isUrlCopied, setIsUrlCopied] = useState(false);

  const dynamicNodes = appInfo?.graph_data?.nodes?.filter(n => n.type === 'dynamicInputNode') || [];

  // Authentication logic for private apps
  const token = localStorage.getItem('token');
  const getAuthHeaders = () => token ? { headers: { Authorization: `Bearer ${token}` } } : {};

  useEffect(() => {
    const fetchAppInfo = async () => {
      try {
        const res = await axios.get(`/api/apps/${shareToken}`);
        setAppInfo(res.data);
      } catch (err) {
        console.error(err);
        if (err.response?.status === 404) {
          setError("요청하신 앱을 찾을 수 없습니다. 주소를 다시 확인해 주세요.");
        } else {
          setError("앱 정보를 불러오는 데 실패했습니다.");
        }
      } finally {
        setIsLoadingInfo(false);
      }
    };
    fetchAppInfo();
  }, [shareToken]);

  const handleExecute = async () => {
    if (!appInfo) return;
    setIsExecuting(true);
    setError(null);
    setResult(null);
    setElapsedTime(0);

    const startTime = Date.now();
    const timerInterval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      const res = await axios.post(`/api/apps/${shareToken}/execute`, { inputs: inputValues }, getAuthHeaders());
      setResult(res.data.result);
    } catch (err) {
      console.error(err);
      if (err.response?.status === 403) {
        setError("실행 권한이 없습니다. 로그인이 필요하거나 접근이 제한된 앱입니다.");
      } else {
        setError(err.response?.data?.detail || "앱 실행 중 오류가 발생했습니다.");
      }
    } finally {
      clearInterval(timerInterval);
      setIsExecuting(false);
    }
  };

  const handleCopyUrl = () => {
    navigator.clipboard.writeText(window.location.href);
    setIsUrlCopied(true);
    setTimeout(() => setIsUrlCopied(false), 2000);
  };

  const handleCopyResult = () => {
    if (result) {
      navigator.clipboard.writeText(result);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    }
  };

  const handleDownloadResult = () => {
    if (result) {
      const element = document.createElement("a");
      const file = new Blob([result], { type: 'text/plain' });
      element.href = URL.createObjectURL(file);
      element.download = `${appInfo.title || 'result'}.txt`;
      document.body.appendChild(element);
      element.click();
      document.body.removeChild(element);
    }
  };

  const clearInput = (nodeId) => {
    setInputValues(prev => ({ ...prev, [nodeId]: '' }));
  };

  if (isLoadingInfo) {
    return (
      <div className="app-runner-container loading-state">
        <div className="spinner"></div>
        <p>앱을 불러오는 중입니다...</p>
      </div>
    );
  }

  if (error && !appInfo) {
    return (
      <div className="app-runner-container error-state">
        <AlertTriangle size={48} color="#ef4444" />
        <h2>오류 발생</h2>
        <p>{error}</p>
        <button className="btn-secondary" onClick={() => navigate('/')}>홈으로 돌아가기</button>
      </div>
    );
  }

  return (
    <div className="app-runner-wrapper">
      <div className="app-runner-container">
        
        <header className="app-header">
          <div className="app-header-left">
            <h1>{appInfo.title}</h1>
            <div className="app-meta">
              <span className="owner-badge">제작자: {appInfo.owner_name}</span>
              {appInfo.is_public ? (
                <span className="status-badge public"><Unlock size={14} /> 공개 (누구나 사용 가능)</span>
              ) : (
                <span className="status-badge private"><Lock size={14} /> 비공개 (권한 필요)</span>
              )}
            </div>
          </div>
          <div className="app-header-right" style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn-secondary" onClick={handleCopyUrl}>
              {isUrlCopied ? <><Check size={16}/> 복사됨</> : <><Share2 size={16}/> URL 복사</>}
            </button>
            <button className="btn-secondary" onClick={() => navigate('/')}>에디터로 이동</button>
          </div>
        </header>

        <section className="app-description">
          <p>{appInfo.description || "이 앱에 대한 설명이 없습니다."}</p>
        </section>

        {dynamicNodes.length > 0 && (
          <section className="app-inputs-area">
            <h3>입력 정보</h3>
            <div className="inputs-wrapper">
              {dynamicNodes.map(node => (
                <div key={node.id} className="input-group">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label>{node.data?.inputLabel || '사용자 입력'}</label>
                    {inputValues[node.id] && (
                      <button className="btn-clear-input" onClick={() => clearInput(node.id)} title="입력 지우기">
                        <XCircle size={14} /> 지우기
                      </button>
                    )}
                  </div>
                  <textarea 
                    value={inputValues[node.id] || ''} 
                    onChange={(e) => setInputValues({...inputValues, [node.id]: e.target.value})}
                    placeholder="여기에 내용을 입력하세요..."
                    rows={3}
                  />
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="app-execution-area">
          <button 
            className="btn-execute-app" 
            onClick={handleExecute} 
            disabled={isExecuting}
          >
            {isExecuting ? (
              <><span className="spinner-small"></span> AI가 결과를 생성 중입니다... ({elapsedTime}초)</>
            ) : (
              <><Play size={18} /> 워크플로우 실행하기</>
            )}
          </button>
          {isExecuting && elapsedTime > 3 && (
            <div className="execution-wait-msg">
              <Clock size={16} />
              <p>모델에 따라 10~30초 가량 소요될 수 있습니다. 잠시만 기다려주세요.</p>
            </div>
          )}
        </section>

        {error && (
          <div className="app-error-box">
            <AlertTriangle size={20} />
            {error}
          </div>
        )}

        {result && (
          <section className="app-result-area">
            <div className="result-header">
              <h3>실행 결과</h3>
              <div className="result-actions">
                <button className="btn-action" onClick={handleCopyResult} title="결과 복사">
                  {isCopied ? <><Check size={16} color="#10b981"/> 복사 완료</> : <><Copy size={16} /> 복사</>}
                </button>
                <button className="btn-action" onClick={handleDownloadResult} title="텍스트로 다운로드">
                  <Download size={16} /> 다운로드
                </button>
              </div>
            </div>
            <div className="markdown-body">
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
