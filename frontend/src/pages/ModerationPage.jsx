// 커뮤니티 검수 (ADR-0020·0021·0022, §4.12 COMMUNITY-4).
// 모든 조치는 되돌릴 수 있고, 되돌리기도 이력에 남는다.
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  AlertTriangle, Ban, Check, Eye, EyeOff, FileSearch, History, Inbox, Loader2,
  RefreshCw, RotateCcw, ShieldAlert, X,
} from 'lucide-react';
import MainSidebar from '../MainSidebar';
import { useAuth } from '../AuthContext';
import './MainPage.css';
import './ModerationPage.css';

const auth = (token) => ({ headers: { Authorization: `Bearer ${token}` } });

const REASON_LABEL = {
  spam: '스팸', harassment: '괴롭힘', inappropriate: '부적절',
  copyright: '저작권', other: '기타',
};
const TARGET_LABEL = {
  post: '글', answer: '답변', comment: '댓글', message: '쪽지', profile: '프로필', community: '커뮤니티',
};
const STATUS_LABEL = { open: '접수', reviewing: '검토 중', resolved: '처리됨', rejected: '반려' };
const ACTION_LABEL = { hide: '숨김', remove: '삭제', restore: '복구', suspend: '정지' };
const STATUS_TABS = [
  { id: 'open', label: '접수' },
  { id: 'reviewing', label: '검토 중' },
  { id: 'resolved', label: '처리됨' },
  { id: 'rejected', label: '반려' },
  { id: 'all', label: '전체' },
];

function formatDateTime(value) {
  if (!value) return '-';
  return new Date(value).toLocaleString('ko-KR', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function ModerationPanel({ embedded = false, onSummaryChange }) {
  const { token } = useAuth();
  const [status, setStatus] = useState('open');
  const [reports, setReports] = useState([]);
  const [actions, setActions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [reportResponse, actionResponse, statusResponse] = await Promise.all([
        axios.get('/api/community/moderation/reports', { ...auth(token), params: { status_filter: status } }),
        axios.get('/api/community/moderation/actions', auth(token)),
        axios.get('/api/community/moderation/status', auth(token)),
      ]);
      setReports(reportResponse.data.reports || []);
      setActions(actionResponse.data.actions || []);
      setSummary(statusResponse.data);
      onSummaryChange?.(statusResponse.data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '검수 정보를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [token, status, onSummaryChange]);

  useEffect(() => { load(); }, [load]);

  const run = async (operation) => {
    setBusy(true);
    setError(null);
    try {
      await operation();
      await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '처리하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const setReportStatus = (id, next) => run(() =>
    axios.post(`/api/community/moderation/reports/${id}`, { status: next }, auth(token)));

  const moderate = (report, action) => run(() =>
    axios.post('/api/community/moderation/content', {
      targetType: report.targetType,
      targetId: report.targetId,
      action,
      reason: `신고 #${report.id} 처리`,
    }, auth(token)));

  const suspend = (handle) => {
    if (!window.confirm(`@${handle} 사용자의 커뮤니티 쓰기를 7일 동안 정지할까요?`)) return;
    run(() => axios.post('/api/community/moderation/suspend', {
      handle, days: 7, reason: '신고 처리',
    }, auth(token)));
  };

  const toggleWrites = () => {
    const enabling = !summary?.writesEnabled;
    if (!enabling && !window.confirm('커뮤니티 쓰기를 전체 중지할까요? 읽기는 계속 가능합니다.')) return;
    run(() => axios.post('/api/community/moderation/writes', {
      enabled: enabling, reason: '운영 판단',
    }, auth(token)));
  };

  return (
    <div className={`mod-panel${embedded ? ' embedded' : ''}`}>
      <div className="mod-panel-head">
        <div>
          <span className="mod-eyebrow"><ShieldAlert size={13} /> TRUST &amp; SAFETY</span>
          <h2>커뮤니티 검수</h2>
          <p>신고된 콘텐츠를 확인하고 조치 이력까지 한곳에서 관리합니다.</p>
        </div>
        <div className="mod-head-actions">
          <button type="button" className="mod-refresh" onClick={load} disabled={loading || busy}>
            <RefreshCw size={14} /> 새로고침
          </button>
          <button type="button" className={`mod-switch${summary?.writesEnabled ? '' : ' off'}`}
                  onClick={toggleWrites} disabled={busy || !summary}>
            {summary?.writesEnabled
              ? <><Ban size={14} /> 쓰기 중지</>
              : <><RotateCcw size={14} /> 쓰기 다시 열기</>}
          </button>
        </div>
      </div>

      {summary && !summary.writesEnabled && (
        <div className="mod-banner" role="status">
          <AlertTriangle size={15} />
          <div><strong>커뮤니티 쓰기가 중지되었습니다.</strong><span>기존 콘텐츠 읽기는 계속 동작합니다.</span></div>
        </div>
      )}
      {error && <p className="mod-error" role="alert"><AlertTriangle size={14} /> {error}</p>}

      <div className="mod-summary-grid">
        <div className="mod-summary-card urgent"><span><Inbox size={15} /> 접수 대기</span><strong>{summary?.openReports ?? '—'}</strong><small>확인이 필요한 신고</small></div>
        <div className="mod-summary-card"><span><FileSearch size={15} /> 검토 중</span><strong>{summary?.reviewing ?? '—'}</strong><small>운영자가 확인 중</small></div>
        <div className={`mod-summary-card ${summary?.writesEnabled ? 'healthy' : 'paused'}`}><span>{summary?.writesEnabled ? <Check size={15} /> : <Ban size={15} />} 쓰기 상태</span><strong>{summary?.writesEnabled ? '정상' : '중지'}</strong><small>읽기는 항상 유지</small></div>
        <div className="mod-summary-card"><span><History size={15} /> 최근 조치</span><strong>{actions.length}</strong><small>현재 불러온 이력</small></div>
      </div>

      <div className="mod-workspace">
        <section className="mod-queue" aria-label="신고 검수 큐">
          <div className="mod-queue-head">
            <div><h3>신고 큐</h3><span>{loading ? '불러오는 중' : `${reports.length}건`}</span></div>
            <div className="mod-tabs" role="tablist" aria-label="신고 상태">
              {STATUS_TABS.map((tab) => (
                <button key={tab.id} type="button" role="tab" aria-selected={status === tab.id}
                        className={status === tab.id ? 'active' : ''} onClick={() => setStatus(tab.id)}>
                  {tab.label}
                  {tab.id === 'open' && summary?.openReports > 0 && <span>{summary.openReports}</span>}
                  {tab.id === 'reviewing' && summary?.reviewing > 0 && <span>{summary.reviewing}</span>}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div className="mod-loading"><Loader2 size={19} /> 신고 목록을 불러오는 중</div>
          ) : reports.length === 0 ? (
            <div className="mod-empty"><Check size={20} /><strong>{STATUS_LABEL[status] || '해당 상태'} 신고가 없습니다.</strong><span>새 신고가 접수되면 이곳에 표시됩니다.</span></div>
          ) : reports.map((report) => (
            <article key={report.id} className="mod-report">
              <header>
                <div className="mod-report-labels">
                  <span className="mod-ticket">#{report.id}</span>
                  <span className="mod-kind">{TARGET_LABEL[report.targetType] || report.targetType}</span>
                  <span className="mod-reason">{REASON_LABEL[report.reason] || report.reason}</span>
                </div>
                <div className="mod-report-state">
                  <time dateTime={report.createdAt}>{formatDateTime(report.createdAt)}</time>
                  <span className={`mod-status ${report.status}`}>{STATUS_LABEL[report.status] || report.status}</span>
                </div>
              </header>

              <div className="mod-target">
                {report.target?.found ? (
                  <>
                    <div className="mod-target-head">
                      <strong>{report.target.title || `${TARGET_LABEL[report.targetType] || '콘텐츠'} #${report.targetId}`}</strong>
                      {report.target.hidden && <span><EyeOff size={11} /> 숨김 상태</span>}
                    </div>
                    <p>{report.target.excerpt || '(내용 없음)'}</p>
                    <span className="mod-meta">작성자 @{report.target.author?.handle || '알 수 없음'}</span>
                  </>
                ) : <p className="mod-gone">대상이 이미 삭제됐거나 찾을 수 없습니다.</p>}
              </div>

              {report.detail && <div className="mod-detail"><strong>신고자 메모</strong><p>{report.detail}</p></div>}

              <div className="mod-actions">
                <div className="mod-actions-group">
                  {['post', 'answer', 'comment', 'message'].includes(report.targetType) && report.target?.found && !report.target.hidden && (
                    <button type="button" onClick={() => moderate(report, 'hide')} disabled={busy}><EyeOff size={13} /> {report.targetType === 'message' ? '쪽지 삭제' : '콘텐츠 숨기기'}</button>
                  )}
                  {['post', 'answer', 'comment'].includes(report.targetType) && report.target?.found && report.target.hidden && (
                    <button type="button" onClick={() => moderate(report, 'restore')} disabled={busy}><Eye size={13} /> 콘텐츠 복구</button>
                  )}
                  {report.target?.author?.handle && (
                    <button type="button" className="danger" onClick={() => suspend(report.target.author.handle)} disabled={busy}><Ban size={13} /> 7일 정지</button>
                  )}
                </div>
                <div className="mod-actions-group resolution">
                  {report.status !== 'reviewing' && <button type="button" onClick={() => setReportStatus(report.id, 'reviewing')} disabled={busy}>검토 중</button>}
                  <button type="button" className="success" onClick={() => setReportStatus(report.id, 'resolved')} disabled={busy}><Check size={13} /> 처리 완료</button>
                  <button type="button" onClick={() => setReportStatus(report.id, 'rejected')} disabled={busy}><X size={13} /> 반려</button>
                </div>
              </div>
            </article>
          ))}
        </section>

        <aside className="mod-history-panel" aria-label="최근 검수 조치">
          <div className="mod-history-head"><div><History size={15} /><h3>최근 조치</h3></div><span>{actions.length}</span></div>
          {actions.length === 0 ? (
            <p className="mod-history-empty">아직 조치 이력이 없습니다.</p>
          ) : (
            <ol className="mod-history">
              {actions.map((action) => (
                <li key={action.id}>
                  <span className={`mod-action ${action.action}`}>{ACTION_LABEL[action.action] || action.action}</span>
                  <div>
                    <strong>{TARGET_LABEL[action.targetType] || action.targetType} #{action.targetId}</strong>
                    <span>@{action.admin?.handle || '알 수 없음'} · {formatDateTime(action.createdAt)}</span>
                    {action.reason && <p>{action.reason}</p>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </aside>
      </div>
    </div>
  );
}

export default function ModerationPage() {
  return (
    <div className="main-page-layout">
      <MainSidebar />
      <main className="main-page-content mod-standalone" style={{ justifyContent: 'flex-start' }}>
        <ModerationPanel />
      </main>
    </div>
  );
}
