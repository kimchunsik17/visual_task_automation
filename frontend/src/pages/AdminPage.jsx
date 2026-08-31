import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  Activity, ArrowRight, BarChart3, BrainCircuit, Check, Coins, FolderKanban,
  LayoutDashboard, Loader2, MessageSquareText, RefreshCw, Search, Server,
  ShieldCheck, Sparkles, Users, Workflow, X,
} from 'lucide-react';
import MainSidebar from '../MainSidebar';
import { useAuth } from '../AuthContext';
import { ModerationPanel } from './ModerationPage';
import './AdminPage.css';

const formatNumber = (value) => Number(value ?? 0).toLocaleString('ko-KR');

const ADMIN_SECTIONS = [
  { id: 'overview', label: '개요', path: '/admin', icon: LayoutDashboard, adminOnly: true },
  { id: 'moderation', label: '커뮤니티 검수', path: '/admin/moderation', icon: ShieldCheck },
  { id: 'users', label: '사용자', path: '/admin/users', icon: Users, adminOnly: true },
  { id: 'llm', label: 'LLM 운영', path: '/admin/llm', icon: BrainCircuit, adminOnly: true },
  { id: 'feedback', label: '피드백', path: '/admin/feedback', icon: MessageSquareText, adminOnly: true },
];

const VIEW_COPY = {
  overview: ['운영 개요', '서비스의 핵심 상태와 즉시 확인할 운영 항목을 모았습니다.'],
  moderation: ['커뮤니티 검수', '신고 큐와 콘텐츠 조치 이력을 관리합니다.'],
  users: ['사용자 관리', '계정 정보와 토큰 잔액을 확인하고 조정합니다.'],
  llm: ['LLM 운영', '생성 품질, 라우팅, 로컬 모델 상태를 확인합니다.'],
  feedback: ['사용자 피드백', '사이트 평가 점수와 정성 의견을 함께 검토합니다.'],
};

function averageScore(scores) {
  const values = Object.values(scores || {}).map(Number).filter(Number.isFinite);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function AdminPage({ view = 'overview' }) {
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [feedbacks, setFeedbacks] = useState([]);
  const [llmOperations, setLlmOperations] = useState(null);
  const [llmHealth, setLlmHealth] = useState(null);
  const [moderationSummary, setModerationSummary] = useState(null);
  const [loading, setLoading] = useState(view !== 'moderation');
  const [error, setError] = useState(null);
  const [userQuery, setUserQuery] = useState('');
  const [editingUserId, setEditingUserId] = useState(null);
  const [tokenDraft, setTokenDraft] = useState('');
  const [savingUserId, setSavingUserId] = useState(null);

  const load = useCallback(async () => {
    if (!token || view === 'moderation') {
      setLoading(false);
      return;
    }
    const config = { headers: { Authorization: `Bearer ${token}` } };
    const messageFor = (requestError) => requestError.response?.status === 401
      ? '로그인 세션이 만료되었습니다. 다시 로그인해주세요.'
      : requestError.response?.data?.detail || '운영 정보를 불러오지 못했습니다.';
    setLoading(true);
    setError(null);
    try {
      if (view === 'overview') {
        const [statsResponse, healthResponse, operationsResponse, moderationResponse] = await Promise.all([
          axios.get('/api/admin/statistics', config),
          axios.get('/api/admin/llm-health', config),
          axios.get('/api/admin/llm-operations', config),
          axios.get('/api/community/moderation/status', config),
        ]);
        setStats(statsResponse.data);
        setLlmHealth(healthResponse.data);
        setLlmOperations(operationsResponse.data);
        setModerationSummary(moderationResponse.data);
      } else if (view === 'users') {
        const response = await axios.get('/api/admin/users', config);
        setUsers(Array.isArray(response.data) ? response.data : []);
      } else if (view === 'llm') {
        const [operationsResponse, healthResponse] = await Promise.all([
          axios.get('/api/admin/llm-operations', config),
          axios.get('/api/admin/llm-health', config),
        ]);
        setLlmOperations(operationsResponse.data);
        setLlmHealth(healthResponse.data);
      } else if (view === 'feedback') {
        const response = await axios.get('/api/admin/feedbacks', config);
        setFeedbacks(Array.isArray(response.data) ? response.data : []);
      }
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setLoading(false);
    }
  }, [token, view]);

  useEffect(() => { load(); }, [load]);

  const filteredUsers = useMemo(() => {
    const query = userQuery.trim().toLowerCase();
    if (!query) return users;
    return users.filter((item) => `${item.name || ''} ${item.email || ''} ${item.id}`.toLowerCase().includes(query));
  }, [users, userQuery]);

  const beginTokenEdit = (item) => {
    setEditingUserId(item.id);
    setTokenDraft(String(item.token_balance ?? 0));
  };

  const saveToken = async (userId) => {
    const newBalance = Number.parseInt(tokenDraft, 10);
    if (!Number.isFinite(newBalance) || newBalance < 0) {
      setError('토큰 잔액은 0 이상의 숫자로 입력해주세요.');
      return;
    }
    setSavingUserId(userId);
    setError(null);
    try {
      await axios.put(`/api/admin/users/${userId}/token`, { token_balance: newBalance }, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setUsers((current) => current.map((item) => (
        item.id === userId ? { ...item, token_balance: newBalance } : item
      )));
      setEditingUserId(null);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '토큰 잔액을 변경하지 못했습니다.');
    } finally {
      setSavingUserId(null);
    }
  };

  const availableSections = ADMIN_SECTIONS.filter((section) => !section.adminOnly || user?.is_admin);
  const [viewTitle, viewDescription] = VIEW_COPY[view] || VIEW_COPY.overview;

  return (
    <div className="admin-page-layout">
      <MainSidebar />
      <main className="admin-content">
        <header className="admin-header">
          <div className="admin-header-copy">
            <span className="admin-eyebrow"><Sparkles size={13} /> OPERATIONS CONSOLE</span>
            <div className="admin-title-row">
              <div><h1>{viewTitle}</h1><p>{viewDescription}</p></div>
              <span className="admin-role-badge"><ShieldCheck size={13} /> {user?.is_admin ? 'Administrator' : 'Moderator'}</span>
            </div>
          </div>
          {view !== 'moderation' && (
            <button type="button" className="admin-refresh" onClick={load} disabled={loading}>
              <RefreshCw size={14} /> 새로고침
            </button>
          )}
        </header>

        <nav className="admin-nav" aria-label="어드민 섹션">
          {availableSections.map((section) => {
            const SectionIcon = section.icon;
            const active = view === section.id;
            return (
              <button key={section.id} type="button" className={active ? 'active' : ''}
                      aria-current={active ? 'page' : undefined} onClick={() => !active && navigate(section.path)}>
                <SectionIcon size={14} /> {section.label}
                {section.id === 'moderation' && moderationSummary?.openReports > 0 && <span>{moderationSummary.openReports}</span>}
              </button>
            );
          })}
        </nav>

        {error && <div className="admin-error" role="alert"><Activity size={14} /> {error}</div>}

        {view === 'moderation' ? (
          <ModerationPanel embedded onSummaryChange={setModerationSummary} />
        ) : loading ? (
          <div className="admin-page-loading"><Loader2 size={21} /> 운영 데이터를 불러오는 중</div>
        ) : view === 'overview' ? (
          <div className="admin-overview">
            <section className="admin-metrics" aria-label="서비스 주요 지표">
              <article className="admin-metric-card"><span><Users size={15} /> 전체 사용자</span><strong>{formatNumber(stats?.total_users)}</strong><small>등록 계정</small></article>
              <article className="admin-metric-card"><span><FolderKanban size={15} /> 프로젝트</span><strong>{formatNumber(stats?.total_projects)}</strong><small>전체 워크플로우 프로젝트</small></article>
              <article className="admin-metric-card"><span><Workflow size={15} /> 누적 실행</span><strong>{formatNumber(stats?.total_executions)}</strong><small>플로우 실행 기록</small></article>
              <article className="admin-metric-card attention"><span><ShieldCheck size={15} /> 검수 대기</span><strong>{formatNumber(moderationSummary?.openReports)}</strong><small>접수 상태 신고</small></article>
            </section>

            <div className="admin-overview-grid">
              <section className="admin-panel admin-status-panel">
                <div className="admin-panel-head"><div><span className="admin-kicker">SYSTEM STATUS</span><h2>운영 상태</h2></div><span className="admin-status-ok"><Check size={12} /> 모니터링 중</span></div>
                <div className="admin-status-list">
                  <div><span className={`admin-status-dot ${llmHealth?.healthy ? 'on' : 'warn'}`} /><div><strong>로컬 LLM</strong><small>{llmHealth?.healthy ? '요청 처리 준비됨' : '오프라인 또는 확인 필요'}</small></div><em>{llmHealth?.healthy ? 'Ready' : 'Offline'}</em></div>
                  <div><span className={`admin-status-dot ${moderationSummary?.writesEnabled ? 'on' : 'danger'}`} /><div><strong>커뮤니티 쓰기</strong><small>읽기는 상태와 관계없이 유지</small></div><em>{moderationSummary?.writesEnabled ? 'Enabled' : 'Paused'}</em></div>
                  <div><span className="admin-status-dot on" /><div><strong>LLM 라우팅</strong><small>로컬 트래픽 {llmOperations?.routing_config?.local_traffic_percent ?? 0}%</small></div><em>{llmOperations?.routing_config?.mode || 'provider'}</em></div>
                </div>
              </section>

              <section className="admin-panel admin-quality-panel">
                <div className="admin-panel-head"><div><span className="admin-kicker">GENERATION QUALITY</span><h2>LLM 품질 스냅샷</h2></div><button type="button" onClick={() => navigate('/admin/llm')}>자세히 <ArrowRight size={13} /></button></div>
                <div className="admin-quality-grid">
                  <div><span>생성 성공률</span><strong>{llmOperations?.persistent?.success_rate ?? 0}%</strong></div>
                  <div><span>사용자 수락률</span><strong>{llmOperations?.persistent?.acceptance_rate ?? 0}%</strong></div>
                  <div><span>드라이런 통과</span><strong>{llmOperations?.persistent?.dry_run_pass_rate ?? 0}%</strong></div>
                  <div><span>폴백 비율</span><strong>{llmOperations?.runtime_routing?.fallback_rate ?? 0}%</strong></div>
                </div>
              </section>
            </div>

            <section className="admin-quick-actions">
              <div className="admin-section-copy"><span className="admin-kicker">QUICK ACTIONS</span><h2>바로 관리하기</h2><p>자주 확인하는 운영 영역으로 이동합니다.</p></div>
              <div className="admin-action-grid">
                <button type="button" onClick={() => navigate('/admin/moderation')}><span className="amber"><ShieldCheck size={17} /></span><div><strong>신고 검수</strong><small>{moderationSummary?.openReports ?? 0}건의 접수 신고 확인</small></div><ArrowRight size={15} /></button>
                <button type="button" onClick={() => navigate('/admin/users')}><span><Users size={17} /></span><div><strong>사용자 관리</strong><small>계정과 토큰 잔액 관리</small></div><ArrowRight size={15} /></button>
                <button type="button" onClick={() => navigate('/admin/llm')}><span className="violet"><BrainCircuit size={17} /></span><div><strong>LLM 운영</strong><small>품질과 라우팅 상태 확인</small></div><ArrowRight size={15} /></button>
              </div>
            </section>
          </div>
        ) : view === 'users' ? (
          <section className="admin-panel admin-users-panel">
            <div className="admin-panel-head admin-users-head">
              <div><span className="admin-kicker">ACCOUNTS</span><h2>등록 사용자 <em>{users.length}</em></h2></div>
              <label className="admin-search"><Search size={14} /><input value={userQuery} onChange={(event) => setUserQuery(event.target.value)} placeholder="이름, 이메일 또는 ID 검색" />{userQuery && <button type="button" onClick={() => setUserQuery('')} aria-label="검색어 지우기"><X size={13} /></button>}</label>
            </div>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead><tr><th>사용자</th><th>이메일</th><th>토큰 잔액</th><th>권한</th><th><span className="sr-only">작업</span></th></tr></thead>
                <tbody>
                  {filteredUsers.map((item) => (
                    <tr key={item.id}>
                      <td><div className="admin-user-cell">{item.picture ? <img src={item.picture} alt="" /> : <span>{(item.name || '?').slice(0, 1).toUpperCase()}</span>}<div><strong>{item.name || '이름 없음'}</strong><small>ID {item.id}</small></div></div></td>
                      <td className="admin-user-email">{item.email || '—'}</td>
                      <td>
                        {editingUserId === item.id ? (
                          <div className="admin-token-editor"><input type="number" min="0" value={tokenDraft} onChange={(event) => setTokenDraft(event.target.value)} autoFocus onKeyDown={(event) => { if (event.key === 'Enter') saveToken(item.id); if (event.key === 'Escape') setEditingUserId(null); }} /><button type="button" onClick={() => saveToken(item.id)} disabled={savingUserId === item.id}>{savingUserId === item.id ? <Loader2 size={13} /> : <Check size={13} />}</button><button type="button" onClick={() => setEditingUserId(null)} aria-label="편집 취소"><X size={13} /></button></div>
                        ) : <span className="admin-token"><Coins size={13} /> {formatNumber(item.token_balance)}</span>}
                      </td>
                      <td><span className={`admin-role ${item.is_admin ? 'admin' : ''}`}>{item.is_admin ? 'Admin' : 'User'}</span></td>
                      <td><button type="button" className="admin-row-action" onClick={() => beginTokenEdit(item)} disabled={editingUserId === item.id}>토큰 편집</button></td>
                    </tr>
                  ))}
                  {filteredUsers.length === 0 && <tr><td colSpan="5"><div className="admin-table-empty"><Users size={18} /> 검색 결과가 없습니다.</div></td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        ) : view === 'llm' ? (
          <div className="admin-llm-view">
            <section className="admin-metrics llm">
              <article className="admin-metric-card"><span><Activity size={15} /> 생성 성공률</span><strong>{llmOperations?.persistent?.success_rate ?? 0}%</strong><small>{formatNumber(llmOperations?.persistent?.trace_count)}개 트레이스</small></article>
              <article className="admin-metric-card"><span><Check size={15} /> 사용자 수락률</span><strong>{llmOperations?.persistent?.acceptance_rate ?? 0}%</strong><small>생성 결과 수락</small></article>
              <article className="admin-metric-card"><span><BarChart3 size={15} /> 드라이런 통과</span><strong>{llmOperations?.persistent?.dry_run_pass_rate ?? 0}%</strong><small>실행 전 검증</small></article>
              <article className="admin-metric-card"><span><RefreshCw size={15} /> 폴백 비율</span><strong>{llmOperations?.runtime_routing?.fallback_rate ?? 0}%</strong><small>호스티드 전환</small></article>
            </section>
            <div className="admin-overview-grid">
              <section className="admin-panel">
                <div className="admin-panel-head"><div><span className="admin-kicker">PROVIDER</span><h2>모델 상태</h2></div><span className={`admin-health ${llmHealth?.healthy ? 'healthy' : 'offline'}`}><Server size={13} /> {llmHealth?.healthy ? 'Local ready' : 'Local offline'}</span></div>
                <dl className="admin-detail-list"><div><dt>라우팅 모드</dt><dd>{llmOperations?.routing_config?.mode || 'provider'}</dd></div><div><dt>로컬 트래픽</dt><dd>{llmOperations?.routing_config?.local_traffic_percent ?? 0}%</dd></div><div><dt>P95 생성 시간</dt><dd>{formatNumber(llmOperations?.persistent?.p95_latency_ms)} ms</dd></div><div><dt>학습 후보</dt><dd>{formatNumber(llmOperations?.persistent?.training_example_count)}</dd></div></dl>
              </section>
              <section className="admin-panel">
                <div className="admin-panel-head"><div><span className="admin-kicker">ROUTING</span><h2>요청 분배</h2></div></div>
                <dl className="admin-detail-list"><div><dt>로컬 시도</dt><dd>{formatNumber(llmOperations?.runtime_routing?.local_attempts)}</dd></div><div><dt>호스티드 시도</dt><dd>{formatNumber(llmOperations?.runtime_routing?.hosted_attempts)}</dd></div><div><dt>강제 호스티드</dt><dd>{formatNumber(llmOperations?.runtime_routing?.forced_hosted)}</dd></div><div><dt>폴백 비율</dt><dd>{llmOperations?.runtime_routing?.fallback_rate ?? 0}%</dd></div></dl>
              </section>
            </div>
            {Object.keys(llmOperations?.persistent?.validation_issue_codes || {}).length > 0 && <section className="admin-panel admin-issues"><div className="admin-panel-head"><div><span className="admin-kicker">VALIDATION</span><h2>검증 이슈 코드</h2></div></div><div>{Object.entries(llmOperations.persistent.validation_issue_codes).map(([code, count]) => <span key={code}>{code}<strong>{count}</strong></span>)}</div></section>}
          </div>
        ) : (
          <section className="admin-feedback-view">
            <div className="admin-section-copy"><span className="admin-kicker">SITE EVALUATIONS</span><h2>피드백 {feedbacks.length}건</h2><p>평가 점수와 사용자가 남긴 의견입니다.</p></div>
            {feedbacks.length === 0 ? <div className="admin-empty"><MessageSquareText size={20} /><strong>아직 피드백이 없습니다.</strong></div> : <div className="admin-feedback-grid">{feedbacks.map((item) => { const average = averageScore(item.scores); return <article key={item.id} className="admin-feedback-card"><header><div className="admin-user-cell"><span>{(item.user_name || '?').slice(0, 1).toUpperCase()}</span><div><strong>{item.user_name || '익명'}</strong><small>{item.user_email}</small></div></div>{average !== null && <span className="admin-score">{average.toFixed(1)}</span>}</header><div className="admin-score-list">{Object.entries(item.scores || {}).map(([key, value]) => <span key={key}><em>{key}</em><strong>{value}</strong></span>)}</div><p>{item.comment || '별도의 코멘트가 없습니다.'}</p><time>{item.created_at ? new Date(item.created_at).toLocaleDateString('ko-KR') : '—'}</time></article>; })}</div>}
          </section>
        )}
      </main>
    </div>
  );
}

export default AdminPage;
