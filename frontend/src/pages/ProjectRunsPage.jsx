import { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { ArrowLeft, CheckCircle2, XCircle, Clock, Database, ChevronDown, ChevronRight, Zap, TestTube } from 'lucide-react';
import './ProjectRunsPage.css';

function ProjectRunsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  
  const [activeTab, setActiveTab] = useState('runs'); // 'runs' or 'evaluations'
  
  // Runs State
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [runDetails, setRunDetails] = useState(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState({});

  // Evaluations State
  const [evals, setEvals] = useState([]);
  const [selectedEvalId, setSelectedEvalId] = useState(null);
  const [loadingEvals, setLoadingEvals] = useState(false);

  useEffect(() => {
    fetchRuns();
    fetchEvals();
  }, [projectId]);

  useEffect(() => {
    if (activeTab === 'runs' && selectedRunId) {
      fetchRunDetails(selectedRunId);
    }
  }, [selectedRunId, activeTab]);

  const fetchRuns = async () => {
    try {
      setLoadingRuns(true);
      const res = await axios.get(`/api/projects/${projectId}/runs`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setRuns(res.data);
      if (res.data.length > 0) {
        setSelectedRunId(res.data[0].id);
      }
    } catch (error) {
      console.error("Failed to fetch runs:", error);
    } finally {
      setLoadingRuns(false);
    }
  };

  const fetchRunDetails = async (runId) => {
    try {
      setLoadingDetails(true);
      const res = await axios.get(`/api/runs/${runId}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setRunDetails(res.data);
      setExpandedNodes({}); // reset expansion on new run
    } catch (error) {
      console.error("Failed to fetch run details:", error);
    } finally {
      setLoadingDetails(false);
    }
  };

  const fetchEvals = async () => {
    try {
      setLoadingEvals(true);
      const res = await axios.get(`/api/projects/${projectId}/evaluations`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setEvals(res.data);
      if (res.data.length > 0) {
        setSelectedEvalId(res.data[0].id);
      }
    } catch (error) {
      console.error("Failed to fetch evaluations:", error);
    } finally {
      setLoadingEvals(false);
    }
  };

  const toggleNodeExpand = (nodeId) => {
    setExpandedNodes(prev => ({ ...prev, [nodeId]: !prev[nodeId] }));
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString('ko-KR', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  };

  const calculateDuration = (start, end) => {
    if (!start || !end) return 'Unknown';
    const ms = new Date(end).getTime() - new Date(start).getTime();
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  return (
    <div className="runs-page-container">
      <header className="runs-header">
        <div className="runs-header-left">
          <button className="back-btn" onClick={() => {
            if (location.state?.fromEditor) {
              navigate(-1);
            } else {
              navigate(`/editor/${projectId}`);
            }
          }}>
            <ArrowLeft size={18} />
            <span>Back to Editor</span>
          </button>
          <h1>History</h1>
        </div>
      </header>

      <div className="runs-content">
        <aside className="runs-sidebar">
          <div className="sidebar-header" style={{ paddingBottom: 0 }}>
            <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid var(--border-color)' }}>
              <button 
                onClick={() => setActiveTab('runs')}
                style={{ 
                  flex: 1, padding: '1rem 0.5rem', background: 'transparent', border: 'none', 
                  color: activeTab === 'runs' ? '#60a5fa' : 'var(--text-muted)', 
                  fontWeight: activeTab === 'runs' ? 'bold' : 'normal', 
                  borderBottom: activeTab === 'runs' ? '2px solid #60a5fa' : '2px solid transparent',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem'
                }}
              >
                <Zap size={16} /> Runs
              </button>
              <button 
                onClick={() => setActiveTab('evaluations')}
                style={{ 
                  flex: 1, padding: '1rem 0.5rem', background: 'transparent', border: 'none', 
                  color: activeTab === 'evaluations' ? '#10b981' : 'var(--text-muted)', 
                  fontWeight: activeTab === 'evaluations' ? 'bold' : 'normal', 
                  borderBottom: activeTab === 'evaluations' ? '2px solid #10b981' : '2px solid transparent',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem'
                }}
              >
                <TestTube size={16} /> Evals
              </button>
            </div>
          </div>

          <div style={{ padding: '1rem', flex: 1, overflowY: 'auto' }}>
            {activeTab === 'runs' ? (
              loadingRuns ? (
                <div className="loading-state">Loading runs...</div>
              ) : runs.length === 0 ? (
                <div className="empty-state">No execution history found.</div>
              ) : (
                <ul className="runs-list" style={{ margin: 0, padding: 0 }}>
                  {runs.map(run => (
                    <li 
                      key={run.id} 
                      className={`run-list-item ${selectedRunId === run.id ? 'active' : ''}`}
                      onClick={() => setSelectedRunId(run.id)}
                    >
                      <div className="run-status-icon">
                        {run.status === 'success' ? (
                          <CheckCircle2 size={18} className="text-success" />
                        ) : (
                          <XCircle size={18} className="text-error" />
                        )}
                      </div>
                      <div className="run-info">
                        <div className="run-date">{formatDate(run.execution_time)}</div>
                        <div className="run-meta">
                          <span>ID: #{run.id}</span>
                          {run.total_tokens > 0 && <span>• {run.total_tokens} tokens</span>}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )
            ) : (
              loadingEvals ? (
                <div className="loading-state">Loading evaluations...</div>
              ) : evals.length === 0 ? (
                <div className="empty-state">No evaluation history found.</div>
              ) : (
                <ul className="runs-list" style={{ margin: 0, padding: 0 }}>
                  {evals.map(e => (
                    <li 
                      key={e.id} 
                      className={`run-list-item ${selectedEvalId === e.id ? 'active' : ''}`}
                      onClick={() => setSelectedEvalId(e.id)}
                    >
                      <div className="run-status-icon" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: e.score >= 80 ? '#10b981' : e.score >= 50 ? '#f59e0b' : '#ef4444' }}></div>
                      </div>
                      <div className="run-info">
                        <div className="run-date">{formatDate(e.created_at)}</div>
                        <div className="run-meta">
                          <span>Score: {e.score}</span>
                          <span>• ID: #{e.id}</span>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )
            )}
          </div>
        </aside>

        <main className="runs-detail-panel" style={{ flex: 1, overflowY: 'auto' }}>
          {activeTab === 'runs' ? (
            !selectedRunId ? (
              <div className="empty-selection">Select a run from the list to view details.</div>
            ) : loadingDetails || !runDetails ? (
              <div className="loading-state">Loading details...</div>
            ) : (
              <div className="run-detail-content">
                <div className="run-detail-header">
                  <h2>Run #{runDetails.run.id} Details</h2>
                  <div className={`status-badge ${runDetails.run.status}`}>
                    {runDetails.run.status === 'success' ? 'Success' : 'Error'}
                  </div>
                </div>
                
                <div className="run-summary-card">
                  <div className="summary-item">
                    <span className="label"><Clock size={14} /> Executed At</span>
                    <span className="value">{formatDate(runDetails.run.execution_time)}</span>
                  </div>
                  <div className="summary-item">
                    <span className="label"><Database size={14} /> Tokens Used</span>
                    <span className="value">{runDetails.run.total_tokens}</span>
                  </div>
                </div>

                <h3 className="timeline-title"><Zap size={16} /> Execution Steps</h3>
                
                {runDetails.steps.length === 0 ? (
                  <div className="empty-state">No steps recorded for this run.</div>
                ) : (
                  <div className="steps-timeline">
                    {runDetails.steps.map((step, index) => (
                      <div className="step-card" key={step.id}>
                        <div className="step-card-header" onClick={() => toggleNodeExpand(step.id)}>
                          <div className="step-status">
                            {step.status === 'success' ? (
                              <CheckCircle2 size={20} className="text-success" />
                            ) : (
                              <XCircle size={20} className="text-error" />
                            )}
                          </div>
                          <div className="step-title-group">
                            <span className="step-type">{step.node_type}</span>
                            <span className="step-id">({step.node_id})</span>
                          </div>
                          <div className="step-duration">
                            {calculateDuration(step.start_time, step.end_time)}
                          </div>
                          <div className="step-expand-icon">
                            {expandedNodes[step.id] ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                          </div>
                        </div>
                        
                        {expandedNodes[step.id] && (
                          <div className="step-card-body">
                            {step.status === 'error' && step.error_message && (
                              <div className="error-box">
                                <strong>Error:</strong> {step.error_message}
                              </div>
                            )}
                            <div className="data-box">
                              <div className="data-box-title">Data Out</div>
                              <pre className="data-content">
                                {step.result_data || 'No output data.'}
                              </pre>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          ) : (
            // Evaluation details
            !selectedEvalId ? (
              <div className="empty-selection">Select an evaluation from the list to view details.</div>
            ) : (
              <div className="run-detail-content">
                {evals.filter(e => e.id === selectedEvalId).map(e => (
                  <div key={e.id} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    <div className="run-detail-header" style={{ borderBottom: 'none', paddingBottom: 0 }}>
                      <h2>Evaluation #{e.id} Details</h2>
                      <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>{formatDate(e.created_at)}</span>
                    </div>

                    <div style={{ display: 'flex', gap: '2rem', alignItems: 'center', background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minWidth: '80px', height: '80px', borderRadius: '50%', border: `6px solid ${e.score >= 80 ? '#10b981' : e.score >= 50 ? '#f59e0b' : '#ef4444'}` }}>
                        <span style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-color)' }}>{e.score}</span>
                      </div>
                      <div style={{ flex: 1 }}>
                        <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--text-color)' }}>종합 요약 (Summary)</h3>
                        <p style={{ margin: 0, color: 'var(--text-muted)', lineHeight: '1.5' }}>{e.report.summary}</p>
                      </div>
                    </div>

                    <div style={{ background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
                      <h3 style={{ margin: '0 0 1rem 0', color: 'var(--text-color)' }}>💡 개선 제안 (Suggestions)</h3>
                      <ul style={{ margin: 0, paddingLeft: '1.5rem', color: 'var(--text-muted)' }}>
                        {e.report.suggestions && e.report.suggestions.map((s, i) => <li key={i} style={{ marginBottom: '0.5rem' }}>{s}</li>)}
                      </ul>
                    </div>

                    <h3 className="timeline-title"><TestTube size={16} /> Test Case Results</h3>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      {e.report.test_results && e.report.test_results.map((tr, i) => (
                        <div key={i} style={{ background: 'var(--card-bg)', borderRadius: '8px', border: '1px solid var(--border-color)', overflow: 'hidden' }}>
                          <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-color)' }}>
                            <span style={{ fontWeight: 600 }}>Test Case {i + 1}</span>
                            <span style={{ color: tr.score >= 40 ? '#10b981' : tr.score >= 25 ? '#f59e0b' : '#ef4444', fontWeight: 'bold' }}>Score: {tr.score}/50</span>
                          </div>
                          <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.8rem', fontSize: '0.9rem' }}>
                            <div>
                              <strong style={{ color: 'var(--text-color)' }}>입력 (Input)</strong>
                              <div style={{ background: 'var(--bg-color)', padding: '0.8rem', borderRadius: '4px', marginTop: '4px', color: 'var(--text-muted)' }}>{tr.input}</div>
                            </div>
                            <div>
                              <strong style={{ color: '#10b981' }}>예상 동작 (Expected)</strong>
                              <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: '0.8rem', borderRadius: '4px', marginTop: '4px', color: '#10b981', border: '1px solid rgba(16, 185, 129, 0.2)' }}>{tr.expected}</div>
                            </div>
                            <div>
                              <strong style={{ color: '#60a5fa' }}>실제 결과 (Actual)</strong>
                              <div style={{ background: 'rgba(59, 130, 246, 0.1)', padding: '0.8rem', borderRadius: '4px', marginTop: '4px', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.2)', whiteSpace: 'pre-wrap' }}>
                                {tr.error ? tr.error : tr.actual || 'No output'}
                              </div>
                            </div>
                            <div style={{ marginTop: '0.5rem', borderTop: '1px dashed var(--border-color)', paddingTop: '0.8rem' }}>
                              <strong style={{ color: '#a78bfa' }}>AI 심사위원 피드백</strong>
                              <p style={{ margin: '4px 0 0 0', color: 'var(--text-muted)', lineHeight: '1.4' }}>{tr.feedback}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </main>
      </div>
    </div>
  );
}

export default ProjectRunsPage;
