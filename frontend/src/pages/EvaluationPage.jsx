import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Activity, CheckCircle, XCircle, Clock, Zap, ArrowLeft, RefreshCw, BarChart3 } from 'lucide-react';
import './EvaluationPage.css';

export default function EvaluationPage() {
  const navigate = useNavigate();
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [totalTests, setTotalTests] = useState(0);
  const [results, setResults] = useState([]);
  const [summary, setSummary] = useState(null);
  
  const [availableCases, setAvailableCases] = useState([]);
  const [selectedCaseIds, setSelectedCaseIds] = useState(new Set());
  const [isLoadingCases, setIsLoadingCases] = useState(true);

  useEffect(() => {
    const fetchCases = async () => {
      try {
        const res = await fetch('/api/evaluate/cases');
        const data = await res.json();
        setAvailableCases(data.cases);
        setSelectedCaseIds(new Set(data.cases.map(c => c.id)));
      } catch (e) {
        console.error("Failed to fetch evaluation cases", e);
      } finally {
        setIsLoadingCases(false);
      }
    };
    fetchCases();
  }, []);

  const toggleCaseSelection = (id) => {
    setSelectedCaseIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllCases = (select) => {
    if (select) {
      setSelectedCaseIds(new Set(availableCases.map(c => c.id)));
    } else {
      setSelectedCaseIds(new Set());
    }
  };

  const startEvaluation = () => {
    if (selectedCaseIds.size === 0) {
      alert("평가할 프롬프트를 최소 1개 이상 선택해주세요.");
      return;
    }

    setIsRunning(true);
    setResults([]);
    setSummary(null);
    setProgress(0);

    const idsParam = Array.from(selectedCaseIds).join(',');
    const eventSource = new EventSource(`/api/evaluate/run?ids=${idsParam}`);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'start') {
        setTotalTests(data.total);
      } else if (data.type === 'progress') {
        setProgress((data.current / data.total) * 100);
        setResults((prev) => [...prev, data.result]);
      } else if (data.type === 'complete') {
        setSummary(data.summary);
        setResults(data.results);
        setIsRunning(false);
        eventSource.close();
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE Error:', error);
      setIsRunning(false);
      eventSource.close();
    };
  };

  return (
    <div className="eval-container">
      <header className="eval-header">
        <button className="back-btn" onClick={() => navigate('/')}>
          <ArrowLeft size={20} />
          <span>뒤로 가기</span>
        </button>
        <div className="eval-title">
          <Activity size={28} className="eval-icon" />
          <h1>에이전트 성능 평가 <span>(Benchmark)</span></h1>
        </div>
      </header>

      <main className="eval-main">
        <section className="eval-hero">
          <div className="hero-content">
            <h2>AI 에이전트 워크플로우 생성 능력 테스트</h2>
            <p>다양한 시나리오 프롬프트를 통해 에이전트가 올바른 노드 조합을 생성하는지 실시간으로 검증합니다.</p>
            
            {!isRunning && !summary && !isLoadingCases && (
              <div className="case-selection-panel">
                <div className="case-selection-header">
                  <h3>평가할 프롬프트 선택</h3>
                  <div className="case-actions">
                    <button onClick={() => selectAllCases(true)}>전체 선택</button>
                    <button onClick={() => selectAllCases(false)}>전체 해제</button>
                  </div>
                </div>
                <div className="case-list">
                  {availableCases.map(c => (
                    <label key={c.id} className={`case-option ${selectedCaseIds.has(c.id) ? 'selected' : ''}`}>
                      <input 
                        type="checkbox" 
                        checked={selectedCaseIds.has(c.id)}
                        onChange={() => toggleCaseSelection(c.id)}
                      />
                      <span className="case-category">{c.category}</span>
                      <span className="case-prompt">{c.prompt}</span>
                    </label>
                  ))}
                </div>
                <button className="run-eval-btn" onClick={startEvaluation}>
                  <Play size={20} />
                  <span>평가 시작하기 ({selectedCaseIds.size}개)</span>
                </button>
              </div>
            )}

            {isLoadingCases && !isRunning && !summary && (
              <div className="progress-info" style={{justifyContent: 'center'}}>
                <span>테스트 케이스 불러오는 중...</span>
              </div>
            )}

            {isRunning && (
              <div className="progress-container">
                <div className="progress-info">
                  <span>평가 진행 중...</span>
                  <span>{Math.round(progress)}%</span>
                </div>
                <div className="progress-bar-bg">
                  <div className="progress-bar-fill" style={{ width: `${progress}%` }}></div>
                </div>
              </div>
            )}

            {summary && !isRunning && (
              <div className="summary-cards">
                <div className="summary-card">
                  <BarChart3 size={24} className="card-icon text-blue" />
                  <span className="card-label">정확도 (Accuracy)</span>
                  <span className="card-value">{summary.average_score}%</span>
                </div>
                <div className="summary-card">
                  <CheckCircle size={24} className="card-icon text-green" />
                  <span className="card-label">통과 (Pass)</span>
                  <span className="card-value">{summary.pass_count} / {summary.total_tests}</span>
                </div>
                <div className="summary-card">
                  <Clock size={24} className="card-icon text-purple" />
                  <span className="card-label">평균 응답 속도</span>
                  <span className="card-value">{summary.average_latency_sec}s</span>
                </div>
                <button className="re-run-btn" onClick={startEvaluation}>
                  <RefreshCw size={18} />
                </button>
              </div>
            )}
          </div>
        </section>

        <section className="eval-results">
          <h3 className="section-title">테스트 케이스 결과</h3>
          {results.length === 0 && !isRunning && (
            <div className="empty-state">평가를 시작하여 결과를 확인하세요.</div>
          )}
          
          <div className="result-list">
            {results.map((res, idx) => (
              <div key={idx} className={`result-item ${res.passed ? 'passed' : 'failed'} slide-up`} style={{ animationDelay: `${idx * 0.1}s` }}>
                <div className="result-header">
                  <span className="category-badge">{res.category}</span>
                  <div className="result-status">
                    {res.passed ? (
                      <span className="status pass"><CheckCircle size={16} /> PASS</span>
                    ) : (
                      <span className="status fail"><XCircle size={16} /> FAIL</span>
                    )}
                  </div>
                </div>
                <div className="result-prompt">
                  "{res.prompt}"
                </div>
                <div className="result-details">
                  <div className="detail-col">
                    <span className="detail-label">생성된 노드</span>
                    <div className="node-tags">
                      {res.generated_nodes?.length > 0 ? (
                        res.generated_nodes.map((n, i) => <span key={i} className="node-tag">{n}</span>)
                      ) : (
                        <span className="text-muted">없음</span>
                      )}
                    </div>
                  </div>
                  {!res.passed && res.missing_nodes?.length > 0 && (
                    <div className="detail-col missing">
                      <span className="detail-label text-red">누락된 필수 노드</span>
                      <div className="node-tags">
                        {res.missing_nodes.map((n, i) => <span key={i} className="node-tag missing">{n}</span>)}
                      </div>
                    </div>
                  )}
                  <div className="detail-metrics">
                    <span className="metric"><Clock size={14} /> {res.latency_sec}s</span>
                    <span className="metric"><Zap size={14} /> Score: {res.score}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
