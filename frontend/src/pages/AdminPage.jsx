import { useState, useEffect } from 'react';
import axios from 'axios';
import MainSidebar from '../MainSidebar';
import { useAuth } from '../AuthContext';
import { Activity, AlertTriangle, CheckCircle2, Server } from 'lucide-react';
import './AdminPage.css';

const formatNumber = (value) => Number(value ?? 0).toLocaleString();

function AdminPage() {
  const { token } = useAuth();
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [feedbacks, setFeedbacks] = useState([]);
  const [llmOperations, setLlmOperations] = useState(null);
  const [llmHealth, setLlmHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [feedbacksLoading, setFeedbacksLoading] = useState(true);
  const [errors, setErrors] = useState({});

  useEffect(() => {
    if (!token) return;

    const requestConfig = {
      headers: { Authorization: `Bearer ${token}` }
    };

    const getErrorMessage = (err, fallback) => (
      err.response?.status === 401
        ? '로그인 세션이 만료되었습니다. 다시 로그인해주세요.'
        : err.response?.data?.detail || fallback
    );

    const fetchUsers = async () => {
      try {
        const res = await axios.get('/api/admin/users', requestConfig);
        setUsers(Array.isArray(res.data) ? res.data : []);
      } catch (err) {
        console.error('Failed to fetch users:', err);
        setErrors(prev => ({
          ...prev,
          users: getErrorMessage(err, '사용자 정보를 불러오지 못했습니다.')
        }));
      } finally {
        setLoading(false);
      }
    };

    const fetchStats = async () => {
      try {
        const res = await axios.get('/api/admin/statistics', requestConfig);
        setStats(res.data);
      } catch (err) {
        console.error('Failed to fetch stats:', err);
        setErrors(prev => ({
          ...prev,
          stats: getErrorMessage(err, '통계 정보를 불러오지 못했습니다.')
        }));
      } finally {
        setStatsLoading(false);
      }
    };

    const fetchFeedbacks = async () => {
      try {
        const res = await axios.get('/api/admin/feedbacks', requestConfig);
        setFeedbacks(Array.isArray(res.data) ? res.data : []);
      } catch (err) {
        console.error('Failed to fetch feedbacks:', err);
        setErrors(prev => ({
          ...prev,
          feedbacks: getErrorMessage(err, '사용자 평가를 불러오지 못했습니다.')
        }));
      } finally {
        setFeedbacksLoading(false);
      }
    };

    const fetchLlmOperations = async () => {
      try {
        const [operationsRes, healthRes] = await Promise.all([
          axios.get('/api/admin/llm-operations', requestConfig),
          axios.get('/api/admin/llm-health', requestConfig),
        ]);
        setLlmOperations(operationsRes.data);
        setLlmHealth(healthRes.data);
      } catch (err) {
        console.error('Failed to fetch LLM operations:', err);
        setErrors(prev => ({
          ...prev,
          llm: getErrorMessage(err, 'LLM 운영 정보를 불러오지 못했습니다.')
        }));
      }
    };

    fetchUsers();
    fetchStats();
    fetchFeedbacks();
    fetchLlmOperations();
  }, [token]);

  const handleUpdateToken = async (userId, currentBalance) => {
    const newBalanceStr = prompt("새로운 토큰량을 입력하세요:", currentBalance);
    if (newBalanceStr === null) return;

    const newBalance = parseInt(newBalanceStr, 10);
    if (isNaN(newBalance) || newBalance < 0) {
      alert("유효한 숫자를 입력해주세요.");
      return;
    }

    try {
      await axios.put(`/api/admin/users/${userId}/token`, { token_balance: newBalance }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setUsers(users.map(u => u.id === userId ? { ...u, token_balance: newBalance } : u));
    } catch (err) {
      console.error('Failed to update token:', err);
      alert('토큰 변경에 실패했습니다: ' + (err.response?.data?.detail || err.message));
    }
  };

  return (
    <div className="admin-page-layout">
      <MainSidebar />
      <main className="admin-content">
        <header className="admin-header">
          <h1>Admin Dashboard</h1>
          <p>Manage system users, view statistics, and update tokens.</p>
        </header>

        <section className="admin-section stats-section">
          <h2>System Statistics</h2>
          {statsLoading ? (
            <div className="admin-loading">Loading stats...</div>
          ) : stats ? (
            <div className="stats-grid">
              <div className="stat-card">
                <h3>Total Users</h3>
                <p>{formatNumber(stats.total_users)}</p>
              </div>
              <div className="stat-card">
                <h3>Total Projects</h3>
                <p>{formatNumber(stats.total_projects)}</p>
              </div>
              <div className="stat-card">
                <h3>Total Flow Executions</h3>
                <p>{formatNumber(stats.total_executions)}</p>
              </div>
            </div>
          ) : (
            <div className="admin-error">{errors.stats || '통계 정보가 없습니다.'}</div>
          )}
        </section>

        <section className="admin-section llm-operations-section">
          <div className="admin-section-title-row">
            <div>
              <h2>LLM Operations</h2>
              <span className="admin-section-meta">
                {llmOperations?.routing_config?.mode || 'provider'} mode · {llmOperations?.routing_config?.local_traffic_percent ?? 0}% local
              </span>
            </div>
            <span className={`health-badge ${llmHealth?.healthy ? 'healthy' : 'offline'}`}>
              <Server size={15} /> {llmHealth?.healthy ? 'Local ready' : 'Local offline'}
            </span>
          </div>
          {errors.llm ? (
            <div className="admin-error">{errors.llm}</div>
          ) : llmOperations ? (
            <>
              <div className="stats-grid llm-stats-grid">
                <div className="stat-card">
                  <Activity size={18} />
                  <h3>Generation success</h3>
                  <p>{llmOperations.persistent.success_rate}%</p>
                </div>
                <div className="stat-card">
                  <CheckCircle2 size={18} />
                  <h3>User acceptance</h3>
                  <p>{llmOperations.persistent.acceptance_rate}%</p>
                </div>
                <div className="stat-card">
                  <CheckCircle2 size={18} />
                  <h3>Dry-run pass</h3>
                  <p>{llmOperations.persistent.dry_run_pass_rate}%</p>
                </div>
                <div className="stat-card">
                  <AlertTriangle size={18} />
                  <h3>Fallback rate</h3>
                  <p>{llmOperations.runtime_routing.fallback_rate}%</p>
                </div>
              </div>
              <div className="llm-detail-grid">
                <dl>
                  <div><dt>Trace samples</dt><dd>{formatNumber(llmOperations.persistent.trace_count)}</dd></div>
                  <div><dt>P95 generation</dt><dd>{formatNumber(llmOperations.persistent.p95_latency_ms)} ms</dd></div>
                  <div><dt>Training candidates</dt><dd>{formatNumber(llmOperations.persistent.training_example_count)}</dd></div>
                </dl>
                <dl>
                  <div><dt>Local attempts</dt><dd>{formatNumber(llmOperations.runtime_routing.local_attempts)}</dd></div>
                  <div><dt>Hosted attempts</dt><dd>{formatNumber(llmOperations.runtime_routing.hosted_attempts)}</dd></div>
                  <div><dt>Forced hosted</dt><dd>{formatNumber(llmOperations.runtime_routing.forced_hosted)}</dd></div>
                </dl>
              </div>
              {Object.keys(llmOperations.persistent.validation_issue_codes || {}).length > 0 && (
                <div className="issue-code-row">
                  {Object.entries(llmOperations.persistent.validation_issue_codes).map(([code, count]) => (
                    <span key={code}>{code} <strong>{count}</strong></span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="admin-loading">Loading LLM operations...</div>
          )}
        </section>

        <section className="admin-section">
          <h2>Registered Users</h2>
          {errors.users && <div className="admin-error">{errors.users}</div>}

          {loading ? (
            <div className="admin-loading">Loading users...</div>
          ) : (
            <div className="table-container">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Picture</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Token Balance</th>
                    <th>Role</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id}>
                      <td>{u.id}</td>
                      <td>
                        {u.picture ? (
                          <img src={u.picture} alt="profile" className="admin-user-pic" />
                        ) : (
                          <div className="admin-user-pic-placeholder" />
                        )}
                      </td>
                      <td>{u.name || 'Unknown'}</td>
                      <td>{u.email || 'N/A'}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span>{formatNumber(u.token_balance)}</span>
                          <button
                            className="btn-edit-token"
                            onClick={() => handleUpdateToken(u.id, u.token_balance)}
                          >
                            Edit
                          </button>
                        </div>
                      </td>
                      <td>
                        {u.is_admin ? (
                          <span className="badge-admin">Admin</span>
                        ) : (
                          <span className="badge-user">User</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {users.length === 0 && (
                    <tr>
                      <td colSpan="6" style={{ textAlign: 'center' }}>No users found.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="admin-section" style={{ marginTop: '2rem' }}>
          <h2>User Evaluations (Site Feedback)</h2>
          {errors.feedbacks && <div className="admin-error">{errors.feedbacks}</div>}
          {feedbacksLoading ? (
            <div className="admin-loading">Loading feedbacks...</div>
          ) : (
            <div className="table-container">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>User</th>
                    <th>Email</th>
                    <th>Scores</th>
                    <th>Comment</th>
                  </tr>
                </thead>
                <tbody>
                  {feedbacks.map(f => (
                    <tr key={f.id}>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {f.created_at ? new Date(f.created_at).toLocaleDateString() : '-'}
                      </td>
                      <td>{f.user_name}</td>
                      <td>{f.user_email}</td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem' }}>
                          {Object.entries(f.scores || {}).map(([k, v]) => (
                            <span key={k}><strong>{k}:</strong> {v}</span>
                          ))}
                        </div>
                      </td>
                      <td style={{ maxWidth: '300px', whiteSpace: 'pre-wrap' }}>{f.comment || '-'}</td>
                    </tr>
                  ))}
                  {feedbacks.length === 0 && (
                    <tr>
                      <td colSpan="5" style={{ textAlign: 'center' }}>No feedback found.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default AdminPage;
