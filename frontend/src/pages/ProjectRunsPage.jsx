import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowLeft, CheckCircle2, XCircle, Clock, Database, ChevronDown, ChevronRight, Zap } from 'lucide-react';
import './ProjectRunsPage.css';

function ProjectRunsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [runDetails, setRunDetails] = useState(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState({});

  useEffect(() => {
    fetchRuns();
  }, [projectId]);

  useEffect(() => {
    if (selectedRunId) {
      fetchRunDetails(selectedRunId);
    }
  }, [selectedRunId]);

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
          <button className="back-btn" onClick={() => navigate(`/editor/${projectId}`)}>
            <ArrowLeft size={18} />
            <span>Back to Editor</span>
          </button>
          <h1>Zap History</h1>
        </div>
      </header>

      <div className="runs-content">
        <aside className="runs-sidebar">
          <div className="sidebar-header">
            <h3>Recent Runs</h3>
          </div>
          {loadingRuns ? (
            <div className="loading-state">Loading runs...</div>
          ) : runs.length === 0 ? (
            <div className="empty-state">No execution history found.</div>
          ) : (
            <ul className="runs-list">
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
          )}
        </aside>

        <main className="runs-detail-panel">
          {!selectedRunId ? (
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
          )}
        </main>
      </div>
    </div>
  );
}

export default ProjectRunsPage;
