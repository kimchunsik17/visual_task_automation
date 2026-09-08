import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Loader2, Mail, RefreshCw, Trash2, Users, Workflow, Youtube, Search, AlertTriangle } from 'lucide-react';
import { EDITOR_NODE_CATALOG } from '../editorNodeCatalog';
import './AdminDemoPanel.css';

// 어드민 '시연 관리' 탭 — 부스 운영 중 SSH 없이 보고 바꿔야 했던 것들을 한 화면에 모았다(2026-09-08).
//  · 게스트 현황·전체 정리 (예전: delete_demo_guests.py 를 SSH 로)
//  · 시연 플래그 즉시 전환 (예전: .env 수정 + 재기동) — 서버의 demo_settings 오버라이드 파일에 저장된다.
//    features 는 페이지가 열릴 때 읽으므로 방문자 화면은 새로고침부터 반영된다.
//  · 오늘의 실행/발송/공유키 사용 수와 외부 할당량(유튜브 이름 검색 100회, Gmail 500통)
//  · 최근 실행과 오늘의 노드 오류 — "왜 안 되지" 를 로그 없이 본다
const formatNumber = (value) => Number(value ?? 0).toLocaleString('ko-KR');
const formatTime = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`);
  return d.toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul' });
};
const SETTING_KEYS = ['DEMO_UI', 'DEMO_GUEST', 'DEMO_GUEST_TOKENS', 'DEMO_GUEST_MAX', 'HIDDEN_NODE_TYPES'];

export default function AdminDemoPanel({ token }) {
  const config = useMemo(() => ({ headers: { Authorization: `Bearer ${token}` } }), [token]);
  const [overview, setOverview] = useState(null);
  const [guests, setGuests] = useState([]);
  const [runs, setRuns] = useState([]);
  const [nodeErrors, setNodeErrors] = useState(null);
  const [draft, setDraft] = useState(null);         // 설정 편집 초안 — 저장 전까지 서버 값과 분리
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [keepActive, setKeepActive] = useState(true);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [ov, gs, rs, ne] = await Promise.all([
        axios.get('/api/admin/demo/overview', config),
        axios.get('/api/admin/demo/guests', config),
        axios.get('/api/admin/demo/runs?limit=30', config),
        axios.get('/api/admin/node-errors?days=1', config).catch(() => ({ data: null })),
      ]);
      setOverview(ov.data); setGuests(gs.data.guests || []); setRuns(rs.data.runs || []); setNodeErrors(ne.data);
      setDraft(ov.data.settings.effective);
      setMessage('');
    } catch (err) {
      setMessage(`불러오기 실패: ${err.response?.data?.detail || err.message}`);
    } finally {
      setBusy(false);
    }
  }, [config]);
  useEffect(() => { load(); }, [load]);

  const overrides = overview?.settings?.overrides || {};
  const envValues = overview?.settings?.env || {};
  const dirty = draft && overview && SETTING_KEYS.some((k) => JSON.stringify(draft[k]) !== JSON.stringify(overview.settings.effective[k]));

  const saveSettings = async () => {
    setSaving(true);
    try {
      const patch = {};
      SETTING_KEYS.forEach((k) => { if (JSON.stringify(draft[k]) !== JSON.stringify(overview.settings.effective[k])) patch[k] = draft[k]; });
      await axios.put('/api/admin/demo/settings', patch, config);
      setMessage('설정을 저장했습니다. 방문자 화면은 새로고침부터 반영됩니다.');
      await load();
    } catch (err) {
      setMessage(`저장 실패: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };
  const resetSettings = async () => {
    if (!window.confirm('패널에서 바꾼 값을 모두 지우고 .env 값으로 되돌릴까요?')) return;
    setSaving(true);
    try {
      await axios.put('/api/admin/demo/settings', { reset: SETTING_KEYS }, config);
      setMessage('.env 값으로 되돌렸습니다.');
      await load();
    } catch (err) {
      setMessage(`되돌리기 실패: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };
  const cleanupGuests = async () => {
    const note = keepActive ? ' (최근 30분 안에 실행한 게스트는 남깁니다)' : '';
    if (!window.confirm(`게스트 계정 ${guests.length}개와 그 워크플로우·앱·포맷을 모두 삭제합니다${note}. 계속할까요?`)) return;
    setSaving(true);
    try {
      const res = await axios.post('/api/admin/demo/guests/cleanup', { keep_active_minutes: keepActive ? 30 : 0 }, config);
      setMessage(`게스트 ${res.data.deleted}개를 삭제했습니다. 남은 게스트 ${res.data.remaining}개${res.data.kept_active ? ` (활동 중 ${res.data.kept_active}개 유지)` : ''}.`);
      await load();
    } catch (err) {
      setMessage(`정리 실패: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const toggleHidden = (type) => setDraft((d) => {
    const list = d.HIDDEN_NODE_TYPES || [];
    return { ...d, HIDDEN_NODE_TYPES: list.includes(type) ? list.filter((t) => t !== type) : [...list, type] };
  });
  const catalog = useMemo(() => EDITOR_NODE_CATALOG.filter((n) => !['startNode', 'outputNode', 'memoNode'].includes(n.type)), []);
  const hiddenNotInCatalog = (draft?.HIDDEN_NODE_TYPES || []).filter((t) => !catalog.some((n) => n.type === t));

  if (!overview && busy) return <div className="admin-page-loading"><Loader2 className="spin" size={22} /> 시연 현황을 불러오는 중…</div>;
  if (!overview) return <div className="admin-error">{message || '불러오지 못했습니다.'}</div>;

  const g = overview.guests; const r = overview.runs_today; const q = overview.quotas || {};
  const youtube = overview.shared_credentials_today?.youtube_data_api || 0;
  const naver = overview.shared_credentials_today?.naver_api_hub || 0;
  const emailLevel = overview.emails_today >= (q.gmail_send_per_day || 500) * 0.8 ? 'danger' : overview.emails_today >= (q.gmail_send_per_day || 500) * 0.5 ? 'warn' : '';
  const ytLevel = youtube >= (q.youtube_name_search_per_day || 100) * 0.8 ? 'danger' : youtube >= (q.youtube_name_search_per_day || 100) * 0.5 ? 'warn' : '';
  const errorCodes = Object.entries(nodeErrors?.by_code || {}).sort((a, b) => (b[1]?.count ?? b[1]) - (a[1]?.count ?? a[1])).slice(0, 8);
  const Badge = ({ k }) => (k in overrides ? <span className="demo-badge">패널 값</span> : <span className="demo-badge env">.env 값</span>);

  return (
    <div className="demo-admin">
      <section className="admin-metrics" aria-label="시연 현황">
        <article className={`admin-metric-card ${g.count >= g.cap * 0.9 ? 'warn' : ''}`}><span><Users size={15} /> 게스트</span><strong>{formatNumber(g.count)} / {formatNumber(g.cap)}</strong><small>오늘 입장 {formatNumber(g.entries_today)} · 이메일 등록 {formatNumber(g.registered_email)}</small></article>
        <article className="admin-metric-card"><span><Workflow size={15} /> 오늘 실행</span><strong>{formatNumber(r.total)}</strong><small>성공 {formatNumber(r.success)} · 실패 {formatNumber(r.failed)} · 게스트 토큰 {formatNumber(g.tokens_used_today)}</small></article>
        <article className={`admin-metric-card ${emailLevel}`}><span><Mail size={15} /> 오늘 이메일 발송</span><strong>{formatNumber(overview.emails_today)}</strong><small className="quota">Gmail 일 한도 {formatNumber(q.gmail_send_per_day)}통</small></article>
        <article className={`admin-metric-card ${ytLevel}`}><span><Youtube size={15} /> 유튜브 채널 조회</span><strong>{formatNumber(youtube)}</strong><small className="quota">이름 검색은 하루 {formatNumber(q.youtube_name_search_per_day)}회 한도(@핸들·주소는 100배 여유)</small></article>
        <article className="admin-metric-card"><span><Search size={15} /> 네이버 검색(공유 키)</span><strong>{formatNumber(naver)}</strong><small>게스트가 부스 계정 키로 검색한 횟수</small></article>
      </section>

      {message && <div className="admin-error" role="status" style={{ background: 'transparent' }}>{message}</div>}

      <div className="demo-admin-grid">
        <section className="admin-panel">
          <div className="admin-panel-head"><div><span className="admin-kicker">DEMO MODE</span><h2>시연 모드 전환</h2></div>
            <button type="button" className="admin-refresh" onClick={load} disabled={busy}><RefreshCw size={14} /> 새로고침</button></div>
          {draft && (
            <div className="demo-settings">
              <div className="demo-setting-row">
                <div><strong>시연 UI 트림 <Badge k="DEMO_UI" /></strong><small>API 센터·쪽지·패치노트를 숨기고 API 센터 진입을 안내로 바꿉니다. 관리자 준비 작업 때는 끄세요.</small></div>
                <button type="button" className={`demo-switch ${draft.DEMO_UI ? 'on' : ''}`} aria-pressed={draft.DEMO_UI} aria-label="시연 UI 트림" onClick={() => setDraft({ ...draft, DEMO_UI: !draft.DEMO_UI })} />
              </div>
              <div className="demo-setting-row">
                <div><strong>게스트 자동 입장 <Badge k="DEMO_GUEST" /></strong><small>비로그인 방문자를 게스트 계정으로 들여보내고 시연 콘텐츠를 복사합니다.</small></div>
                <button type="button" className={`demo-switch ${draft.DEMO_GUEST ? 'on' : ''}`} aria-pressed={draft.DEMO_GUEST} aria-label="게스트 자동 입장" onClick={() => setDraft({ ...draft, DEMO_GUEST: !draft.DEMO_GUEST })} />
              </div>
              <div className="demo-setting-row">
                <div><strong>게스트 토큰 상한 <Badge k="DEMO_GUEST_TOKENS" /></strong><small>게스트 1명에게 주는 토큰(1,000~2,000,000). 새 게스트부터 적용, 기존 게스트는 사용자 탭에서 충전.</small></div>
                <input type="number" min="1000" max="2000000" step="1000" value={draft.DEMO_GUEST_TOKENS ?? ''} onChange={(e) => setDraft({ ...draft, DEMO_GUEST_TOKENS: Number(e.target.value) })} />
              </div>
              <div className="demo-setting-row">
                <div><strong>게스트 정원 <Badge k="DEMO_GUEST_MAX" /></strong><small>게스트 계정 총량(1~5,000). 넘으면 입장이 429 로 막힙니다.</small></div>
                <input type="number" min="1" max="5000" value={draft.DEMO_GUEST_MAX ?? ''} onChange={(e) => setDraft({ ...draft, DEMO_GUEST_MAX: Number(e.target.value) })} />
              </div>
              <div className="demo-setting-row" style={{ gridTemplateColumns: '1fr' }}>
                <div><strong>숨길 노드 <Badge k="HIDDEN_NODE_TYPES" /></strong><small>팔레트·AI 생성 카탈로그·갤러리에서 감춥니다(실행은 허용). 빨간 칩이 숨김 상태입니다.</small></div>
                <div className="demo-chip-list">
                  {catalog.map((n) => (
                    <label key={n.type} className={`demo-chip ${draft.HIDDEN_NODE_TYPES?.includes(n.type) ? 'on' : ''}`} title={n.type}>
                      <input type="checkbox" checked={draft.HIDDEN_NODE_TYPES?.includes(n.type) || false} onChange={() => toggleHidden(n.type)} />{n.label}
                    </label>
                  ))}
                  {hiddenNotInCatalog.map((t) => (
                    <label key={t} className="demo-chip on" title="카탈로그에 없는 타입"><input type="checkbox" checked onChange={() => toggleHidden(t)} />{t}</label>
                  ))}
                </div>
              </div>
              <div className="demo-settings-actions">
                <span className="hint">.env 값: UI {String(envValues.DEMO_UI)} · 게스트 {String(envValues.DEMO_GUEST)} · 토큰 {formatNumber(envValues.DEMO_GUEST_TOKENS)} · 정원 {formatNumber(envValues.DEMO_GUEST_MAX)}</span>
                <button type="button" className="demo-btn" onClick={resetSettings} disabled={saving || Object.keys(overrides).length === 0}>.env 값으로 되돌리기</button>
                <button type="button" className="demo-btn primary" onClick={saveSettings} disabled={saving || !dirty}>{saving ? '저장 중…' : '저장'}</button>
              </div>
            </div>
          )}
        </section>

        <section className="admin-panel">
          <div className="admin-panel-head"><div><span className="admin-kicker">NODE ERRORS · TODAY</span><h2>오늘 노드 오류</h2></div>
            <span className="admin-status-ok"><AlertTriangle size={12} /> {formatNumber(nodeErrors?.error_steps)} / {formatNumber(nodeErrors?.total_steps)} 단계</span></div>
          {errorCodes.length ? (
            <div className="demo-error-list">
              {errorCodes.map(([code, value]) => (
                <div key={code}><code>{code}</code><strong>{formatNumber(value?.count ?? value)}</strong></div>
              ))}
            </div>
          ) : <p className="demo-note">오늘 기록된 노드 오류가 없습니다.</p>}
          {nodeErrors?.by_node_type && Object.keys(nodeErrors.by_node_type).length > 0 && (
            <p className="demo-note">노드별: {Object.entries(nodeErrors.by_node_type).slice(0, 6).map(([t, v]) => `${t} ${v?.count ?? v}`).join(' · ')}</p>
          )}
        </section>
      </div>

      <section className="admin-panel admin-users-panel">
        <div className="admin-panel-head admin-users-head">
          <div><span className="admin-kicker">GUESTS</span><h2>게스트 계정 <em>{guests.length}</em></h2></div>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <label className="demo-inline-check"><input type="checkbox" checked={keepActive} onChange={(e) => setKeepActive(e.target.checked)} /> 최근 30분 실행자 유지</label>
            <button type="button" className="demo-btn danger" onClick={cleanupGuests} disabled={saving || guests.length === 0}><Trash2 size={14} /> 게스트 전체 정리</button>
          </div>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>이름</th><th>등록 이메일</th><th>토큰 잔액</th><th>실행</th><th>마지막 실행</th></tr></thead>
            <tbody>
              {guests.map((item) => (
                <tr key={item.id}>
                  <td>{item.name} <small style={{ color: 'var(--text-muted)' }}>#{item.id}</small></td>
                  <td className="admin-user-email">{item.registered ? item.email : <span style={{ color: 'var(--text-muted)' }}>미등록</span>}</td>
                  <td>{formatNumber(item.token_balance)}</td>
                  <td>{formatNumber(item.runs)}</td>
                  <td>{formatTime(item.last_run_at)}</td>
                </tr>
              ))}
              {guests.length === 0 && <tr><td colSpan="5"><div className="admin-table-empty"><Users size={18} /> 게스트가 없습니다.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-panel admin-users-panel">
        <div className="admin-panel-head"><div><span className="admin-kicker">RECENT RUNS</span><h2>최근 실행 <em>{runs.length}</em></h2></div></div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>시간</th><th>사용자</th><th>워크플로우</th><th>상태</th><th>토큰</th><th>경로</th></tr></thead>
            <tbody>
              {runs.map((row) => (
                <tr key={row.id} title={row.error || ''}>
                  <td>{formatTime(row.time)}</td>
                  <td>{row.user_name || (row.user_id ? `#${row.user_id}` : '—')}{row.is_guest && <span className="demo-guest-tag">게스트</span>}</td>
                  <td>{row.project_title || (row.project_id ? `#${row.project_id}` : '저장 전 그래프')}</td>
                  <td><span className={`demo-status-pill ${row.status === 'success' ? 'success' : 'error'}`}>{row.status === 'success' ? '성공' : '실패'}</span></td>
                  <td>{formatNumber(row.total_tokens)}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{row.trigger_type || '—'}</td>
                </tr>
              ))}
              {runs.length === 0 && <tr><td colSpan="6"><div className="admin-table-empty"><Workflow size={18} /> 실행 기록이 없습니다.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
