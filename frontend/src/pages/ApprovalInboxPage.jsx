// 승인 알림함 (ADR-0015) — 사이트 내 알람 채널의 본체.
// 스케줄·웹훅처럼 사용자가 자리에 없을 때 멈춘 실행이 여기 쌓이고,
// 견본(직전 노드 결과)을 확인한 뒤 승인/거절하면 그 지점부터 재개된다.
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import MainSidebar from '../MainSidebar';
import { readListCache, writeListCache } from '../listCache';
import './MainPage.css';
import './SchedulerPage.css';

const STATUS_LABEL = {
  pending: '대기 중',
  approved: '승인됨',
  rejected: '거절됨',
};

export default function ApprovalInboxPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  // 재방문 첫 프레임부터 마지막 목록을 그린다(listCache.js) — 출렁임 방지.
  const cacheKey = `approvals:${user?.id ?? user?.email ?? 'anon'}`;
  const [requests, setRequests] = useState(() => readListCache(cacheKey) ?? []);
  const [loading, setLoading] = useState(() => readListCache(cacheKey) === null);
  const [expanded, setExpanded] = useState(null);
  const [detail, setDetail] = useState({});
  const [comments, setComments] = useState({});
  const [deciding, setDeciding] = useState(null);
  const [resumeResult, setResumeResult] = useState(null);

  const authHeaders = useCallback(() => ({ headers: { Authorization: `Bearer ${token}` } }), [token]);

  const load = useCallback(async () => {
    try {
      const res = await axios.get('/api/approvals', authHeaders());
      setRequests(res.data.requests || []);
      writeListCache(cacheKey, res.data.requests || []);
    } catch (e) { /* silent */ } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => { if (token) load(); }, [token, load]);

  const toggleExpand = async (request) => {
    if (expanded === request.request_id) { setExpanded(null); return; }
    setExpanded(request.request_id);
    if (!detail[request.request_id] && request.payload_truncated) {
      try {
        const res = await axios.get(`/api/approvals/${request.request_id}`, authHeaders());
        setDetail((prev) => ({ ...prev, [request.request_id]: res.data }));
      } catch (e) { /* preview fallback */ }
    }
  };

  const decide = async (request, decision) => {
    if (deciding) return;
    setDeciding(request.request_id);
    setResumeResult(null);
    try {
      const res = await axios.post(
        `/api/approvals/${request.request_id}/decide`,
        { decision, comment: comments[request.request_id] || '' },
        authHeaders(),
      );
      setResumeResult({ request_id: request.request_id, text: res.data.result });
      await load();
    } catch (error) {
      alert('처리 실패: ' + (error.response?.data?.detail || error.message));
    } finally {
      setDeciding(null);
    }
  };

  const pending = requests.filter((r) => r.status === 'pending');
  const decided = requests.filter((r) => r.status !== 'pending');

  const renderCard = (request) => {
    const isPending = request.status === 'pending';
    const full = detail[request.request_id];
    const preview = full ? full.payload_preview : request.payload_preview;
    return (
      <div key={request.request_id} style={{ border: '1px solid var(--border-color)', borderRadius: '10px', padding: '14px 16px', marginBottom: '10px', background: 'var(--panel-bg, transparent)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>
              {request.project_title || '워크플로우'}
              <span style={{
                marginLeft: '8px', fontSize: '0.7rem', padding: '2px 8px', borderRadius: '999px',
                background: isPending ? '#f59e0b22' : request.status === 'approved' ? '#10b98122' : '#ef444422',
                color: isPending ? '#f59e0b' : request.status === 'approved' ? '#10b981' : '#ef4444',
              }}>{STATUS_LABEL[request.status] || request.status}</span>
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>{request.message}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              {request.created_at ? new Date(request.created_at).toLocaleString() : ''} · 실행 출처: {request.origin || '-'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
            <button onClick={() => toggleExpand(request)} style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-color)', cursor: 'pointer', fontSize: '0.75rem' }}>
              {expanded === request.request_id ? '접기' : '견본 보기'}
            </button>
            {request.project_id && (
              <button onClick={() => navigate(`/editor/${request.project_id}`)} style={{ padding: '6px 10px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.75rem' }}>
                에디터
              </button>
            )}
          </div>
        </div>

        {expanded === request.request_id && (
          <div style={{ marginTop: '10px' }}>
            <pre style={{ background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '10px', fontSize: '0.78rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '320px', overflowY: 'auto', margin: 0 }}>
              {preview || '(내용 없음)'}
            </pre>
            {isPending ? (
              <>
                <textarea
                  value={comments[request.request_id] || ''}
                  onChange={(e) => setComments((prev) => ({ ...prev, [request.request_id]: e.target.value }))}
                  placeholder="코멘트 (선택 — 거절 사유 등)"
                  style={{ width: '100%', minHeight: '48px', marginTop: '8px', padding: '8px', borderRadius: '8px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', fontSize: '0.78rem', resize: 'vertical' }}
                />
                <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '8px' }}>
                  <button onClick={() => decide(request, 'reject')} disabled={deciding === request.request_id}
                    style={{ padding: '7px 14px', borderRadius: '8px', border: '1px solid #ef4444', background: 'transparent', color: '#ef4444', cursor: 'pointer', fontSize: '0.8rem' }}>거절</button>
                  <button onClick={() => decide(request, 'approve')} disabled={deciding === request.request_id}
                    style={{ padding: '7px 16px', borderRadius: '8px', border: 'none', background: '#10b981', color: '#fff', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600 }}>
                    {deciding === request.request_id ? '처리 중...' : '승인하고 계속 실행'}
                  </button>
                </div>
              </>
            ) : (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '8px' }}>
                {request.decided_at ? `${new Date(request.decided_at).toLocaleString()} 결정` : ''}
                {request.comment ? ` · 코멘트: ${request.comment}` : ''}
                {request.resume_outcome ? ` · 재개 결과: ${request.resume_outcome}` : ''}
              </div>
            )}
            {resumeResult && resumeResult.request_id === request.request_id && (
              <div style={{ marginTop: '8px', fontSize: '0.78rem', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '10px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                <b>재개 결과</b>
                <div style={{ marginTop: '4px' }}>{resumeResult.text}</div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="content-area" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto' }}>
          <div className="page-header">
            <div>
              <h1 className="page-title">승인 대기함</h1>
              <p className="page-subtitle">사용자 승인 노드에서 멈춘 실행들입니다. 견본을 확인하고 승인하면 멈춘 지점부터 이어서 실행됩니다.</p>
            </div>
            <button className="btn-refresh" onClick={load} disabled={loading}>새로고침</button>
          </div>
          {loading && requests.length === 0 ? <p>불러오는 중...</p> : (
            <>
              <h3 style={{ fontSize: '0.95rem' }}>대기 중 ({pending.length})</h3>
              {pending.length === 0 && <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>대기 중인 승인 요청이 없습니다.</p>}
              {pending.map(renderCard)}
              {decided.length > 0 && (
                <>
                  <h3 style={{ fontSize: '0.95rem', marginTop: '24px' }}>처리됨</h3>
                  {decided.map(renderCard)}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
