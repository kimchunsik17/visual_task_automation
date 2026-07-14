import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { Play, Share2, Lock, Unlock, AlertTriangle } from 'lucide-react';
import './AppRunnerPage.css';

export default function AppRunnerPage() {
  const { shareToken } = useParams();
  const navigate = useNavigate();
  const [appInfo, setAppInfo] = useState(null);
  const [isLoadingInfo, setIsLoadingInfo] = useState(true);
  const [isExecuting, setIsExecuting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

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

    try {
      // POST without body, just trigger execution
      const res = await axios.post(`/api/apps/${shareToken}/execute`, {}, getAuthHeaders());
      setResult(res.data.result);
    } catch (err) {
      console.error(err);
      if (err.response?.status === 403) {
        setError("실행 권한이 없습니다. 로그인이 필요하거나 접근이 제한된 앱입니다.");
      } else {
        setError(err.response?.data?.detail || "앱 실행 중 오류가 발생했습니다.");
      }
    } finally {
      setIsExecuting(false);
    }
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
          <button className="btn-secondary" onClick={() => navigate('/')}>에디터로 이동</button>
        </header>

        <section className="app-description">
          <p>{appInfo.description || "이 앱에 대한 설명이 없습니다."}</p>
        </section>

        <section className="app-execution-area">
          <button 
            className="btn-execute-app" 
            onClick={handleExecute} 
            disabled={isExecuting}
          >
            {isExecuting ? (
              <><span className="spinner-small"></span> 실행 중...</>
            ) : (
              <><Play size={18} /> 워크플로우 실행하기</>
            )}
          </button>
        </section>

        {error && (
          <div className="app-error-box">
            <AlertTriangle size={20} />
            {error}
          </div>
        )}

        {result && (
          <section className="app-result-area">
            <h3>실행 결과</h3>
            <div className="markdown-body">
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
