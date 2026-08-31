// 커뮤니티 템플릿 (ADR-0023, 우선 백로그 12).
//
// 예전 이 화면은 `/api/projects/public` 을 그대로 나열했다 — 정화도, 버전도, 계보도 없이 남의
// 프로젝트를 복사하는 경로였다. 이제 **검증된 공유의 승격**만 보여준다.
//
// 정렬 기본값이 설치 수가 아니라 **첫 실행 성공률**인 것이 이 화면의 요점이다. 설치 수와 별점은
// 조작하기 쉽고 초기 표본이 작다 — 우리는 실행 로그를 갖고 있어 더 정직한 신호를 쓸 수 있다.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  AlertTriangle, CheckCircle2, Heart, LibraryBig, MessageSquare, Search, ShieldCheck, Upload, X,
} from 'lucide-react';
import MainSidebar from '../MainSidebar';
import SectionTabs from '../components/SectionTabs';
import { COMMUNITY_SECTION_TABS } from '../navigation';
import EmptyState from '../components/EmptyState';
import { useAuth } from '../AuthContext';
import { timeAgo } from '../timeFormat';
import { CATEGORIES, CATEGORY_LABEL, RISK_LABEL, TRIGGER_LABEL, credentialLabel } from '../templateLabels';
import { getTemplateThumbnail } from '../officialTemplateThumbnails';
import './MainPage.css';
import './TemplatesPage.css';

const auth = (token) => (token ? { headers: { Authorization: `Bearer ${token}` } } : {});

const SORTS = [
  { id: 'quality', label: '첫 실행 성공률' },
  { id: 'installs', label: '많이 가져간 순' },
  { id: 'likes', label: '좋아요 순' },
  { id: 'recent', label: '최근 수정 순' },
];

function QualityBadge({ signals }) {
  if (!signals || signals.measuredRuns === 0) {
    return <span className="tpl-signal muted">아직 실행 기록 없음</span>;
  }
  const rate = Math.round(signals.firstRunSuccessRate * 100);
  return (
    <span className={`tpl-signal${rate >= 70 ? ' good' : ''}`}>
      <CheckCircle2 size={12} /> 가져간 뒤 첫 실행 성공 {rate}%
      <span className="tpl-signal-sub">({signals.measuredRuns}건 측정)</span>
    </span>
  );
}

function PublishDialog({ token, onClose, onPublished }) {
  const [projects, setProjects] = useState([]);
  const [form, setForm] = useState({ projectId: '', slug: '', title: '', description: '',
                                     category: 'automation', tags: '', version: '1.0.0' });
  const [gate, setGate] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    axios.get('/api/projects/my', auth(token)).then((r) => setProjects(r.data || [])).catch(() => {});
  }, [token]);

  const checkGate = async (projectId) => {
    setForm((f) => ({ ...f, projectId }));
    setGate(null);
    if (!projectId) return;
    const res = await axios.post('/api/community/templates/gate',
                                 { projectId: Number(projectId) }, auth(token));
    setGate(res.data);
  };

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const res = await axios.post('/api/community/templates', {
        projectId: Number(form.projectId), slug: form.slug, title: form.title,
        description: form.description, category: form.category,
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
        version: form.version,
      }, auth(token));
      onPublished(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || '올리지 못했습니다.');
    } finally { setBusy(false); }
  };

  return (
    <div className="tpl-modal-backdrop" onClick={onClose}>
      <div className="tpl-modal" onClick={(e) => e.stopPropagation()}>
        <div className="tpl-modal-head">
          <h2>템플릿으로 올리기</h2>
          <button onClick={onClose}><X size={16} /></button>
        </div>

        <label>워크플로우</label>
        <select value={form.projectId} onChange={(e) => checkGate(e.target.value)}>
          <option value="">선택하세요</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
        </select>

        {/* 게시 조건과 **왜 안 되는지**를 즉시 보여준다. */}
        {gate && (
          <ul className="tpl-gate">
            {gate.checks.map((c) => (
              <li key={c.id} className={c.ok ? 'ok' : 'bad'}>
                {c.ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                {c.label}{c.detail && <span className="tpl-gate-detail">{c.detail}</span>}
              </li>
            ))}
            {gate.needsReview && (
              <li className="review">
                <ShieldCheck size={13} /> 위험 노드가 있어 게시 전 운영 검수를 거칩니다.
              </li>
            )}
          </ul>
        )}

        <label>주소 (영문 소문자·숫자·하이픈)</label>
        <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })}
               placeholder="summary-bot" />
        <label>이름</label>
        <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <label>소개</label>
        <textarea rows={3} value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="무엇을 하는 템플릿인지, 무엇을 준비해야 하는지" />
        <div className="tpl-row">
          <div>
            <label>분류</label>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {CATEGORIES.filter((c) => c.id).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label>버전</label>
            <input value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} />
          </div>
        </div>
        <label>태그 (쉼표로 구분)</label>
        <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />

        <button className="btn-primary tpl-submit" disabled={busy || !gate?.ok || !form.slug || !form.title}
                onClick={submit}>
          {busy ? '올리는 중…' : '템플릿으로 올리기'}
        </button>
        {error && <p className="tpl-error">{error}</p>}
      </div>
    </div>
  );
}

export default function TemplatesPage() {
  const navigate = useNavigate();
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [category, setCategory] = useState('');
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('quality');
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [message, setMessage] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/community/templates',
                                  { params: { category: category || undefined,
                                              q: query || undefined, sort } });
      setItems(res.data.templates || []);
    } finally { setLoading(false); }
  }, [category, query, sort]);

  useEffect(() => { load(); }, [load]);

  // 목록에서 곧바로 가져오지 않는다 — 제작자가 남긴 소개를 먼저 읽을 자리를 준다.
  const open = (template) => navigate(`/community/templates/${template.slug}`);

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <main className="main-page-content management-page">
        <SectionTabs ariaLabel="커뮤니티 섹션" tabs={COMMUNITY_SECTION_TABS} />
        <div className="management-content">
          <header className="management-header">
            <div className="management-heading">
              <span className="management-kicker">COMMUNITY TEMPLATES</span>
              <h1>커뮤니티 템플릿</h1>
              <p>검증을 통과한 워크플로우만 올라옵니다. 소개를 읽고 가져오면 내 계정에 사본이 생기고, 자동으로 실행되지는 않아요.</p>
            </div>
            <div className="management-header-side" aria-label="템플릿 요약">
              <div className="management-stat"><span>표시 중</span><strong>{items.length}</strong></div>
              <button className="management-button primary" onClick={() => setPublishing(true)}>
                <Upload size={15} /> 템플릿으로 올리기
              </button>
            </div>
          </header>

          <div className="tpl-filters">
            {CATEGORIES.map((c) => (
              <button key={c.id} className={category === c.id ? 'active' : ''}
                      onClick={() => setCategory(c.id)}>{c.label}</button>
            ))}
            <div className="tpl-search">
              <Search size={14} />
              <input value={query} onChange={(e) => setQuery(e.target.value)}
                     onKeyDown={(e) => e.key === 'Enter' && load()} placeholder="이름·소개 검색" />
            </div>
          </div>

          <div className="management-toolbar">
            <span className="management-toolbar-label">
              정렬 기준은 설치 수가 아니라 <strong>가져간 뒤 첫 실행이 성공했는지</strong>가 기본입니다.
            </span>
            <div className="management-toolbar-actions tpl-sorts">
              {SORTS.map((s) => (
                <button key={s.id} type="button" className={sort === s.id ? 'active' : ''}
                        onClick={() => setSort(s.id)}>{s.label}</button>
              ))}
            </div>
          </div>

          {message && <p className="tpl-error">{message}</p>}

          {loading ? (
            <div className="management-loading" aria-label="템플릿을 불러오는 중">
              {[0, 1, 2, 3].map((item) => <span key={item} />)}
            </div>
          ) : items.length === 0 ? (
            <EmptyState illustration="empty-templates" title="아직 템플릿이 없습니다"
                        description="직접 만든 워크플로우를 첫 템플릿으로 올려보세요. 한 번 실행에 성공한 워크플로우만 올릴 수 있어요(공식 템플릿은 운영자가 검수해 올립니다)." />
          ) : (
            <div className="management-grid">
              {items.map((t) => {
                const thumbnailUrl = getTemplateThumbnail(t);
                return (
                <article key={t.id} className="management-card tpl-row" onClick={() => open(t)}
                         role="link" tabIndex={0}
                         onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(t); } }}>
                  {thumbnailUrl
                    ? <img className="tpl-row-thumb" src={thumbnailUrl} alt="" loading="lazy" />
                    : <span className="tpl-row-thumb is-empty"><LibraryBig size={20} /></span>}

                  <div className="management-card-body">
                    <div className="management-card-top">
                      <span className="management-resource">
                        <span className="management-resource-icon"><LibraryBig size={14} /></span>
                        {CATEGORY_LABEL[t.category] || '기타'}
                      </span>
                      <div className="management-card-tools">
                        {/* 공식 템플릿은 실행 이력 대신 사람이 검수했다 — 그 차이를 감추지 않는다. */}
                        {t.isCurated && <span className="tpl-official" title="운영자가 만들고 검수한 공식 템플릿">공식</span>}
                        <QualityBadge signals={t.signals} />
                      </div>
                    </div>

                    <h2 title={t.title}>{t.title}</h2>
                    <p className="management-card-description">{t.description || '소개가 없습니다.'}</p>

                    <div className="management-meta-grid">
                      <span className="management-meta-item"><span>구성</span>
                        <strong>{t.nodeCount ?? 0}개 노드 · {t.edgeCount ?? 0}개 연결</strong></span>
                      <span className="management-meta-item"><span>시작 방식</span>
                        <strong>{TRIGGER_LABEL[t.triggerType] || '수동 실행'}</strong></span>
                      <span className="management-meta-item"><span>버전</span><strong>v{t.latestVersion}</strong></span>
                      <span className="management-meta-item"><span>가져간 횟수</span>
                        <strong>{t.signals?.installs ?? 0}회</strong></span>
                      <span className="management-meta-item"><span>반응</span><strong>
                        <Heart size={10} /> {t.likeCount ?? 0} · <MessageSquare size={10} /> {t.commentCount ?? 0}
                      </strong></span>
                      <span className="management-meta-item"><span>최근 수정</span>
                        <strong>{timeAgo(t.updatedAt) || '기록 없음'}</strong></span>
                      <span className="management-meta-item"><span>만든이</span>
                        <strong>{t.isCurated ? 'WorkFlow Ai' : `@${t.author?.handle || '알 수 없음'}`}</strong></span>
                      {t.requiredCredentials?.length > 0 && (
                        <span className="management-meta-item"><span>필요한 연결</span>
                          <strong title={t.requiredCredentials.map(credentialLabel).join(', ')}>
                            {t.requiredCredentials.map(credentialLabel).join(', ')}
                          </strong></span>
                      )}
                    </div>

                    {t.riskFlags?.length > 0 && (
                      <p className="tpl-risk">
                        <AlertTriangle size={11} /> {t.riskFlags.map((f) => RISK_LABEL[f] || f).join(', ')}
                      </p>
                    )}
                  </div>

                  <footer className="management-card-actions">
                    <button className="management-button primary" onClick={(e) => { e.stopPropagation(); open(t); }}>
                      소개 보기
                    </button>
                  </footer>
                </article>
                );
              })}
            </div>
          )}
        </div>
      </main>

      {publishing && (
        <PublishDialog token={token} onClose={() => setPublishing(false)}
                       onPublished={(d) => { setPublishing(false); load();
                         setMessage(d.templateStatus === 'in_review'
                           ? '검수 대기 상태로 접수됐습니다. 승인되면 목록에 나타납니다.'
                           : '템플릿이 등록됐습니다.'); }} />
      )}
    </div>
  );
}
