// 커뮤니티 Q&A (ADR-0021, 우선 백로그 23).
//
// 기본 화면은 인기 글이 아니라 **아직 답이 없는 질문**이다 — Q&A 는 답변률이 떨어지면 죽는다.
// 목록·상세·작성이 한 파일에 있는 이유는 세 화면이 같은 데이터 모양을 공유하고 아직 작아서다.
// 커지면 나눈다.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, Download, FileWarning, ImagePlus,
  MessageSquare, Paperclip, Plus, Search, Sparkles, ThumbsUp, Trash2, Users, X,
} from 'lucide-react';
import MainSidebar from '../MainSidebar';
import SectionTabs from '../components/SectionTabs';
import { COMMUNITY_SECTION_TABS } from '../navigation';
import EmptyState from '../components/EmptyState';
import { useAuth } from '../AuthContext';
import './MainPage.css';
import './CommunityQnaPage.css';

const SORTS = [
  { id: 'unanswered', label: '미해결', description: '답변을 기다리는 글' },
  { id: 'recent', label: '최신', description: '새로 올라온 글' },
  { id: 'popular', label: '인기', description: '반응이 많은 글' },
  { id: 'resolved', label: '해결됨', description: '답을 찾은 글' },
];

const KIND_LABEL = { question: '질문', showcase: '쇼케이스', tip: '팁' };

const RISK_LABEL = {
  arbitrary_code: '코드 노드 포함',
  arbitrary_url: '임의 URL 호출',
  database: '데이터베이스 접근',
  writes_files: '파일 생성',
  payment: '결제 연동',
};

const auth = (token) => (token ? { headers: { Authorization: `Bearer ${token}` } } : {});

const MAX_POST_IMAGES = 6;

function formatCommunityDate(value) {
  if (!value) return '';
  const date = new Date(value);
  const diff = Date.now() - date.getTime();
  const day = Math.floor(diff / 86400000);
  if (day === 0 && diff >= 0) return '오늘';
  if (day === 1) return '어제';
  if (day > 1 && day < 7) return `${day}일 전`;
  return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}

// 글에 붙일 이미지. 고른 즉시 올려서 artifactId 를 받아둔다 — 글을 올리는 순간에 한꺼번에
// 올리면 큰 파일에서 한참 멈춰 있다가 실패하고, 그때는 본문까지 날아간다.
function ImagePicker({ token, images, onChange }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const pick = async (event) => {
    const files = [...event.target.files].slice(0, MAX_POST_IMAGES - images.length);
    event.target.value = '';
    if (!files.length) return;
    setBusy(true);
    setError(null);
    const added = [];
    for (const file of files) {
      const form = new FormData();
      form.append('file', file);
      form.append('purpose', 'community');
      try {
        const res = await axios.post('/api/upload', form, {
          headers: { ...(auth(token).headers || {}), 'Content-Type': 'multipart/form-data' },
        });
        added.push({ artifactId: res.data.artifact_id, name: res.data.filename,
                     preview: URL.createObjectURL(file) });
      } catch (e) {
        setError(e.response?.data?.detail || `${file.name} 을(를) 올리지 못했습니다.`);
      }
    }
    if (added.length) onChange([...images, ...added]);
    setBusy(false);
  };

  return (
    <div className="qna-images">
      {images.map((img) => (
        <div key={img.artifactId} className="qna-image-thumb">
          <img src={img.preview} alt={img.name} />
          <button type="button" onClick={() => onChange(images.filter((i) => i.artifactId !== img.artifactId))}
                  aria-label={`${img.name} 빼기`}>
            <X size={12} />
          </button>
        </div>
      ))}
      {images.length < MAX_POST_IMAGES && (
        <label className="qna-image-add">
          <ImagePlus size={16} />
          <span>{busy ? '올리는 중…' : '사진 추가'}</span>
          <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple
                 onChange={pick} disabled={busy} />
        </label>
      )}
      {error && <p className="qna-error">{error}</p>}
    </div>
  );
}

function Author({ profile, at }) {
  const handle = profile?.handle || '알 수 없는 사용자';
  return (
    <span className="qna-author">
      <span className="qna-avatar" aria-hidden="true">{handle.slice(0, 1).toUpperCase()}</span>
      <span className="qna-author-name">{profile?.handle ? `@${profile.handle}` : handle}</span>
      {at && (
        <time dateTime={at} title={new Date(at).toLocaleString('ko-KR')}>
          {formatCommunityDate(at)}
        </time>
      )}
    </span>
  );
}

/** 가져오기 전에 보여줄 것 — 무엇이 필요하고 무엇을 채워야 하는가. */
function WorkflowCard({ share, token, onImported }) {
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  if (!share) return null;

  const load = async () => {
    const res = await axios.get(`/api/community/shares/${share.id}`, auth(token));
    setDetail(res.data);
  };

  const doImport = async () => {
    setBusy(true);
    try {
      const res = await axios.post(`/api/community/shares/${share.id}/import`, {}, auth(token));
      onImported?.(res.data);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="qna-workflow">
      <div className="qna-workflow-head">
        <Paperclip size={14} /> 워크플로우 {share.nodeCount}개 노드
        {(share.riskFlags || []).map((flag) => (
          <span key={flag} className="qna-risk"><AlertTriangle size={11} /> {RISK_LABEL[flag] || flag}</span>
        ))}
      </div>
      <p className="qna-workflow-meta">
        노드: {(share.nodeTypes || []).join(', ')}
        {share.requiredCredentials?.length > 0 && ` · 필요한 자격증명: ${share.requiredCredentials.join(', ')}`}
        {share.importCount > 0 && ` · ${share.importCount}명이 가져감`}
      </p>
      <div className="qna-workflow-actions">
        {!detail && <button onClick={load}>가져오기 전에 확인</button>}
        {detail && (
          <button className="btn-primary" onClick={doImport} disabled={busy}>
            <Download size={13} /> {busy ? '가져오는 중…' : '내 워크플로우로 가져오기'}
          </button>
        )}
      </div>
      {detail && (
        <div className="qna-import-preview">
          {detail.preview.needsInput?.length > 0 && (
            <p>채워야 하는 칸: {detail.preview.needsInput.map((n) => `${n.nodeId}.${n.field}`).join(', ')}</p>
          )}
          {detail.preview.pythonCode?.length > 0 && (
            // 코드 전문을 접지 않고 보여준다 — 보안이 아니라 "무엇을 가져오는지 알고 가져간다"의 문제다.
            <div className="qna-code">
              <strong>포함된 코드 노드</strong>
              {detail.preview.pythonCode.map((c) => <pre key={c.nodeId}>{c.code}</pre>)}
            </div>
          )}
          <p className="qna-note">가져오면 사본이 만들어집니다. 자동으로 실행되지 않아요.</p>
        </div>
      )}
    </div>
  );
}

function PostList() {
  const navigate = useNavigate();
  const { token } = useAuth();
  const [params, setParams] = useSearchParams();
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(params.get('q') || '');
  const sort = params.get('sort') || 'unanswered';
  const errorCode = params.get('error_code') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/community/posts', {
        ...auth(token),
        params: { sort, q: params.get('q') || undefined, error_code: errorCode || undefined },
      });
      setPosts(res.data.posts || []);
    } finally {
      setLoading(false);
    }
  }, [token, sort, params, errorCode]);

  useEffect(() => { load(); }, [load]);

  const setParam = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next);
  };

  const activeSort = SORTS.find((item) => item.id === sort) || SORTS[0];
  const activeQuery = params.get('q') || '';

  return (
    <div className="qna-wrap qna-list-view">
      <header className="qna-head">
        <div className="qna-head-copy">
          <span className="qna-eyebrow"><Sparkles size={13} /> COMMUNITY</span>
          <h1>함께 만들고, 함께 해결해요.</h1>
          <p className="qna-sub">막힌 지점을 질문하고 실제 워크플로우까지 공유하세요. 답을 찾으면 다음 사람의 출발점이 됩니다.</p>
          <div className="qna-head-points" aria-label="커뮤니티 특징">
            <span><MessageSquare size={13} /> 실전 Q&amp;A</span>
            <span><Paperclip size={13} /> 워크플로우 공유</span>
            <span><Users size={13} /> 친구 공개 지원</span>
          </div>
        </div>
        <button className="btn-primary" onClick={() => navigate('/community/qna/new')}>
          <Plus size={15} /> 질문하기
        </button>
      </header>

      <div className="qna-toolbar">
        <div className="qna-filters" role="tablist" aria-label="게시글 정렬">
          {SORTS.map((s) => (
            <button key={s.id} type="button" role="tab" aria-selected={sort === s.id}
                    className={sort === s.id ? 'active' : ''} onClick={() => setParam('sort', s.id)}>
              {s.label}
            </button>
          ))}
        </div>
        <form className="qna-search" onSubmit={(e) => { e.preventDefault(); setParam('q', query.trim()); }}>
          <Search size={14} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="제목·본문 검색"
            aria-label="커뮤니티 검색"
          />
          {query && <button type="button" className="qna-search-clear" onClick={() => { setQuery(''); setParam('q', ''); }} aria-label="검색어 지우기"><X size={13} /></button>}
          <button type="submit" className="qna-search-submit">검색</button>
        </form>
      </div>

      {errorCode && (
        <p className="qna-error-filter">
          <FileWarning size={14} /> 오류 코드 <code>{errorCode}</code> 로 묶인 질문
          <button onClick={() => setParam('error_code', '')}>필터 해제</button>
        </p>
      )}

      <div className="qna-result-head" aria-live="polite">
        <div>
          <strong>{activeSort.label}</strong>
          <span>{activeQuery ? `“${activeQuery}” 검색 결과` : activeSort.description}</span>
        </div>
        {!loading && <span className="qna-result-count">{posts.length}개 글</span>}
      </div>

      {loading ? (
        <div className="qna-skeleton-list" aria-label="게시글을 불러오는 중">
          {[0, 1, 2].map((item) => <div key={item} className="qna-skeleton-card"><span /><span /><span /></div>)}
        </div>
      ) : posts.length === 0 ? (
        <EmptyState
          className="qna-empty-state"
          illustration="empty-templates"
          title={sort === 'unanswered' ? '미해결 질문이 없습니다' : '아직 글이 없습니다'}
          description="첫 질문을 올려보세요. 워크플로우를 붙이면 답하기 훨씬 쉬워집니다."
          action={<button className="btn-primary" onClick={() => navigate('/community/qna/new')}><Plus size={14} /> 질문하기</button>}
        />
      ) : (
        <ul className="qna-list">
          {posts.map((p) => (
            <li key={p.id}>
              <button type="button" className="qna-card" onClick={() => navigate(`/community/qna/${p.id}`)}>
                <div className={`qna-status${p.resolved ? ' resolved' : p.answerCount > 0 ? ' discussing' : ''}`}>
                  {p.resolved ? <CheckCircle2 size={13} /> : <MessageSquare size={13} />}
                  {p.resolved ? '해결됨' : p.answerCount > 0 ? '논의 중' : '답변 대기'}
                </div>
                <div className="qna-item-main">
                  <span className="qna-kind">{KIND_LABEL[p.kind] || '커뮤니티'}</span>
                  <h3>{p.title}</h3>
                  <div className="qna-item-meta">
                    <Author profile={p.author} at={p.createdAt} />
                    {p.visibility === 'friends' && <span className="qna-chip"><Users size={10} /> 친구 공개</span>}
                    {p.hasWorkflow && <span className="qna-chip"><Paperclip size={10} /> 워크플로우</span>}
                    {(p.tags || []).map((t) => <span key={t} className="qna-tag">#{t}</span>)}
                  </div>
                </div>
                <div className="qna-item-stats" aria-label={`답변 ${p.answerCount}개, 좋아요 ${p.likeCount}개`}>
                  <span className={p.answerCount === 0 ? 'zero' : ''}><strong>{p.answerCount}</strong> 답변</span>
                  <span><ThumbsUp size={12} /> {p.likeCount}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PostDetail() {
  const { postId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const [post, setPost] = useState(null);
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`/api/community/posts/${postId}`, auth(token));
      setPost(res.data.post);
    } catch {
      setPost(false);
    }
  }, [postId, token]);

  useEffect(() => { load(); }, [load]);

  if (post === false) return <div className="qna-wrap"><p className="qna-empty">글을 찾을 수 없습니다.</p></div>;
  if (!post) return <div className="qna-wrap"><p className="qna-empty">불러오는 중…</p></div>;

  const submitAnswer = async () => {
    if (!answer.trim()) return;
    setBusy(true);
    try {
      await axios.post(`/api/community/posts/${postId}/answers`, { body: answer }, auth(token));
      setAnswer('');
      load();
    } catch (e) {
      setMessage(e.response?.data?.detail || '답변을 올리지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const accept = async (answerId) => {
    await axios.post(`/api/community/posts/${postId}/accept/${answerId}`, {}, auth(token));
    load();
  };

  // 삭제는 되돌릴 수 없게 보이므로 반드시 한 번 묻는다. 운영자가 남의 글을 지우는 경우는
  // 문구를 달리해, 자기 글을 지우는 것과 헷갈리지 않게 한다.
  const removePost = async () => {
    const mine = post?.isAuthor;
    const ok = window.confirm(mine
      ? '이 글을 삭제할까요? 답변도 함께 보이지 않게 됩니다.'
      : '운영 권한으로 이 글을 삭제할까요? 신고 검토를 위해 기록은 남습니다.');
    if (!ok) return;
    try {
      await axios.delete(`/api/community/posts/${postId}`, auth(token));
      navigate('/community/qna');
    } catch (e) {
      setMessage(e.response?.data?.detail || '삭제하지 못했습니다.');
    }
  };

  const like = async (targetType, targetId) => {
    try {
      await axios.post('/api/community/likes', { targetType, targetId }, auth(token));
      load();
    } catch (e) {
      setMessage(e.response?.data?.detail || '좋아요를 누르지 못했습니다.');
    }
  };

  return (
    <div className="qna-wrap qna-detail-view">
      <button className="qna-back" onClick={() => navigate('/community/qna')}>
        <ArrowLeft size={14} /> 목록으로
      </button>

      <article className="qna-post">
        <header className="qna-post-head">
          <div className={`qna-status${post.resolved ? ' resolved' : ''}`}>
            {post.resolved ? <CheckCircle2 size={13} /> : <MessageSquare size={13} />}
            {post.resolved ? '해결된 글' : '답변을 기다리는 글'}
          </div>
          <span className="qna-kind">{KIND_LABEL[post.kind] || '커뮤니티'}</span>
          <h1>{post.title}</h1>
          <div className="qna-item-meta qna-post-meta">
            <Author profile={post.author} at={post.createdAt} />
            {post.visibility === 'friends' && <span className="qna-chip"><Users size={10} /> 친구 공개</span>}
            {(post.tags || []).map((t) => <span key={t} className="qna-tag">#{t}</span>)}
          </div>
        </header>
        <div className="qna-post-content">
          <div className="qna-body">{post.body}</div>
        </div>

        {(post.images || []).length > 0 && (
          <div className="qna-image-grid">
            {post.images.map((src) => (
              <a key={src} href={src} target="_blank" rel="noreferrer">
                <img src={src} alt="첨부 사진" loading="lazy" />
              </a>
            ))}
          </div>
        )}

        {/* 실행 오류 발췌 — NodeError 의 공개 payload 만 담긴다(요청 id·원문은 없다). */}
        {(post.excerpts || []).map((e, i) => (
          <div key={i} className="qna-excerpt">
            <FileWarning size={14} />
            <div>
              <code>{e.errorCode}</code> {e.nodeType && `· ${e.nodeType}`}
              <p>{e.userMessage}</p>
              <button onClick={() => navigate(`/community/qna?error_code=${e.errorCode}`)}>
                같은 오류의 다른 질문 보기
              </button>
            </div>
          </div>
        ))}

        <WorkflowCard share={post.workflow} token={token}
                      onImported={(d) => navigate(`/editor/${d.projectId}`)} />

        <div className="qna-actions">
          <button onClick={() => like('post', post.id)}><ThumbsUp size={13} /> 도움됐어요 · {post.likeCount}</button>
          {/* 삭제 권한은 서버가 canDelete 로 알려준다 — 본인 글이거나 운영자일 때다. */}
          {post.canDelete && (
            <button className="qna-danger" onClick={removePost}>
              <Trash2 size={13} /> {post.isAuthor ? '삭제' : '운영 삭제'}
            </button>
          )}
        </div>
      </article>

      <div className="qna-answers-head">
        <div>
          <span className="qna-eyebrow">DISCUSSION</span>
          <h2>답변 {post.answers.length}</h2>
        </div>
        <p>실제로 해결에 도움이 된 답변을 채택할 수 있어요.</p>
      </div>
      {post.answers.length === 0 && (
        <div className="qna-inline-empty">
          <MessageSquare size={18} />
          <div><strong>첫 답변을 기다리고 있어요.</strong><span>아는 해결 방법이 있다면 아래에 남겨주세요.</span></div>
        </div>
      )}

      {post.answers.map((a) => (
        <article key={a.id} className={`qna-answer${a.isAccepted ? ' accepted' : ''}`}>
          {a.isAccepted && <div className="qna-accepted-badge"><Check size={13} /> 채택된 답변</div>}
          <div className="qna-item-meta"><Author profile={a.author} at={a.createdAt} /></div>
          <div className="qna-body">{a.body}</div>
          <WorkflowCard share={a.workflow} token={token}
                        onImported={(d) => navigate(`/editor/${d.projectId}`)} />
          <div className="qna-actions">
            <button onClick={() => like('answer', a.id)}><ThumbsUp size={13} /> {a.likeCount}</button>
            {/* 채택은 질문자만 — 무엇이 자기 문제를 풀었는지는 질문자만 안다. */}
            {post.isAuthor && !a.isAccepted && (
              <button onClick={() => accept(a.id)}><Check size={13} /> 이 답변 채택</button>
            )}
          </div>
        </article>
      ))}

      <HandleGate>
      <div className="qna-answer-form">
        <div className="qna-answer-form-head">
          <div>
            <span className="qna-eyebrow">YOUR ANSWER</span>
            <h3>해결 방법을 공유해주세요.</h3>
          </div>
          <span>{answer.length.toLocaleString()}자</span>
        </div>
        <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={6}
                  placeholder="어떻게 해결하는지 알려주세요. 워크플로우를 함께 붙이려면 편집기에서 공유하세요." />
        <div className="qna-answer-form-foot">
          <span>구체적인 설정값과 확인 방법을 함께 적으면 더 유용해요.</span>
          <button className="btn-primary" onClick={submitAnswer} disabled={busy || !answer.trim()}>
            {busy ? '올리는 중…' : '답변 올리기'}
          </button>
        </div>
        {message && <p className="qna-error">{message}</p>}
      </div>
      </HandleGate>
    </div>
  );
}

// 핸들이 없으면 커뮤니티 쓰기가 409 로 막힌다(ADR-0020 SAFE-1). 설정 페이지까지 보내지 않고
// 막힌 그 자리에서 만들게 한다 — 첫 글이 첫 좌절이 되면 두 번째 글은 없다.
// 읽기는 이 관문을 지나지 않는다. 쓰기 화면만 감싼다.
function HandleGate({ children }) {
  const { token } = useAuth();
  const [me, setMe] = useState(null); // null = 확인 중
  const [handle, setHandle] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    axios.get('/api/community/me', auth(token))
      .then((r) => {
        setMe(r.data);
        if (r.data.needsProfile) setHandle((h) => h || r.data.suggestedHandle || '');
      })
      // 확인에 실패하면 막지 않는다 — 서버가 다시 판단하고, 그때 사유를 알려준다.
      .catch(() => setMe({ needsProfile: false }));
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    const value = handle.trim().replace(/^@/, '');
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    try {
      await axios.post('/api/community/profile', { handle: value }, auth(token));
      load();
    } catch (e) {
      setError(e.response?.data?.detail || '핸들을 만들지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  if (me === null) return null;
  if (!me.needsProfile) return children;

  return (
    <div className="qna-handle-gate">
      <h3>먼저 핸들을 만들어주세요</h3>
      <p>
        핸들은 커뮤니티에서 쓰이는 공개 이름입니다. 이메일은 공개되지 않습니다.
        소문자·숫자·하이픈으로 3~20자.
      </p>
      <div className="qna-handle-row">
        <input value={handle} onChange={(e) => setHandle(e.target.value)}
               placeholder="예: minsu-kim" autoFocus
               onKeyDown={(e) => e.key === 'Enter' && create()} />
        <button className="btn-primary" onClick={create} disabled={busy || !handle.trim()}>
          {busy ? '만드는 중…' : '핸들 만들기'}
        </button>
      </div>
      {error && <p className="qna-error">{error}</p>}
    </div>
  );
}

function PostCompose() {
  const navigate = useNavigate();
  const { token } = useAuth();
  const [params] = useSearchParams();
  const [form, setForm] = useState({
    kind: 'question', visibility: 'public', title: '', body: '', tags: '', projectId: '',
  });
  const [projects, setProjects] = useState([]);
  const [images, setImages] = useState([]);
  const [preview, setPreview] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  // 편집기 오류 카드에서 넘어오면 오류 정보를 함께 싣는다 — 막힌 그 자리가 질문이 시작되는 자리다.
  const nodeError = useMemo(() => {
    try { return params.get('error') ? JSON.parse(decodeURIComponent(params.get('error'))) : null; }
    catch { return null; }
  }, [params]);

  useEffect(() => {
    axios.get('/api/projects/my', auth(token)).then((r) => setProjects(r.data || [])).catch(() => {});
    if (nodeError?.code) {
      setForm((f) => ({ ...f, title: f.title || `${nodeError.code} 오류가 납니다`,
                        body: f.body || `${nodeError.userMessage || ''}\n\n` }));
    }
  }, [token, nodeError]);

  // 게시 **전에** 무엇이 지워지는지 보여준다. 사용자가 모른 채 누르게 하지 않는다.
  const checkShare = async (projectId) => {
    setForm((f) => ({ ...f, projectId }));
    setPreview(null);
    if (!projectId) return;
    try {
      const res = await axios.post('/api/community/shares/preview', { projectId: Number(projectId) }, auth(token));
      setPreview(res.data);
    } catch (e) {
      setPreview({ ok: false, message: e.response?.data?.detail || '확인하지 못했습니다.' });
    }
  };

  const submit = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const res = await axios.post('/api/community/posts', {
        kind: form.kind, visibility: form.visibility, title: form.title, body: form.body,
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
        projectId: form.projectId ? Number(form.projectId) : null,
        nodeError: nodeError || null, nodeType: params.get('node_type') || null,
        imageArtifactIds: images.map((i) => i.artifactId),
      }, auth(token));
      navigate(`/community/qna/${res.data.postId}`);
    } catch (e) {
      setMessage(e.response?.data?.detail || '올리지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="qna-wrap qna-compose-view">
      <button className="qna-back" onClick={() => navigate('/community/qna')}>
        <ArrowLeft size={14} /> 목록으로
      </button>
      <header className="qna-compose-head">
        <span className="qna-eyebrow"><Sparkles size={13} /> NEW POST</span>
        <h1>커뮤니티에 이야기 올리기</h1>
        <p>맥락과 시도한 방법을 함께 적으면 더 정확한 답을 받을 수 있어요.</p>
      </header>

      <div className="qna-form-section">
        <div className="qna-form-section-title"><span>01</span><div><h2>글의 성격</h2><p>사람들이 글을 빠르게 이해할 수 있게 분류해주세요.</p></div></div>
        <div className="qna-form-grid">
          <label className="qna-field">
            <span>종류</span>
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              <option value="question">질문 — 막힌 것을 묻습니다</option>
              <option value="showcase">쇼케이스 — 만든 것을 보여줍니다</option>
              <option value="tip">팁 — 알게 된 것을 공유합니다</option>
            </select>
          </label>
          <label className="qna-field">
            <span>공개 범위</span>
            <select value={form.visibility} onChange={(e) => setForm({ ...form, visibility: e.target.value })}>
              <option value="public">전체 공개</option>
              <option value="friends">친구 공개</option>
            </select>
          </label>
        </div>
      </div>

      <div className="qna-form-section">
        <div className="qna-form-section-title"><span>02</span><div><h2>내용과 맥락</h2><p>무엇을 만들고 있었는지부터 설명해주세요.</p></div></div>
        <label className="qna-field">
          <span>제목 <em>필수</em></span>
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                 placeholder="무엇이 막혔는지 한 줄로" autoFocus />
          <small>{form.title.length.toLocaleString()}자</small>
        </label>
        <label className="qna-field">
          <span>내용</span>
          <textarea rows={10} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })}
                    placeholder={'하려던 작업\n현재 결과 또는 오류\n이미 시도해본 방법을 순서대로 적어주세요.'} />
          <small>{form.body.length.toLocaleString()}자</small>
        </label>
        <div className="qna-field">
          <span>사진 <em>선택 · 최대 6장</em></span>
          <ImagePicker token={token} images={images} onChange={setImages} />
        </div>
        <label className="qna-field">
          <span>태그 <em>쉼표로 구분 · 최대 5개</em></span>
          <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })}
                 placeholder="예: discord, 파일전송" />
        </label>
      </div>

      <div className="qna-form-section">
        <div className="qna-form-section-title"><span>03</span><div><h2>워크플로우 공유</h2><p>선택한 워크플로우는 민감한 값을 제거한 사본으로 공유됩니다.</p></div></div>
        <label className="qna-field">
          <span>워크플로우 <em>선택</em></span>
          <select value={form.projectId} onChange={(e) => checkShare(e.target.value)}>
            <option value="">붙이지 않음</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
          </select>
        </label>

        {preview && (
          <div className={`qna-preview${preview.ok ? '' : ' bad'}`}>
            {preview.ok ? (
              <>
                <strong>게시하면 이렇게 정리됩니다</strong>
                {preview.cleared?.length > 0 && <p>지워지는 값: {preview.cleared.map((c) => `${c.nodeId}.${c.field}`).join(', ')}</p>}
                {preview.requiredCredentials?.length > 0 && <p>가져가는 사람이 준비할 자격증명: {preview.requiredCredentials.join(', ')}</p>}
                {preview.riskFlags?.length > 0 && <p>위험 표시: {preview.riskFlags.map((f) => RISK_LABEL[f] || f).join(', ')}</p>}
                <p className="qna-note">비밀번호·토큰·서버 경로는 공개되지 않습니다.</p>
              </>
            ) : <p>{preview.message}</p>}
          </div>
        )}

        {nodeError?.code && (
          <p className="qna-note qna-attached-error">
            <FileWarning size={14} /> 실행 오류 <code>{nodeError.code}</code>가 함께 첨부됩니다. 요청 ID와 내부 기록은 제외됩니다.
          </p>
        )}
      </div>

      <div className="qna-compose-actions">
        <div><strong>게시할 준비가 되었나요?</strong><span>게시 후에도 민감한 값은 공개되지 않습니다.</span></div>
        <button className="btn-primary qna-submit" onClick={submit} disabled={busy || !form.title.trim()}>
          {busy ? '올리는 중…' : '커뮤니티에 올리기'}
        </button>
      </div>
      {message && <p className="qna-error" role="alert">{message}</p>}
    </div>
  );
}

export default function CommunityQnaPage({ view = 'list' }) {
  return (
    // main-page-layout/main-page-content 가 목록형 페이지의 래퍼다. main-content 는 에디터
    // 캔버스용이라 overflow:hidden 이고, 그 안에 넣으면 페이지가 스크롤되지 않는다.
    <div className="main-page-layout">
      <MainSidebar />
      <main className="main-page-content qna-page" style={{ justifyContent: 'flex-start' }}>
        <SectionTabs ariaLabel="커뮤니티 섹션" tabs={COMMUNITY_SECTION_TABS} />
        {view === 'detail' ? <PostDetail /> : view === 'new' ? <HandleGate><PostCompose /></HandleGate> : <PostList />}
      </main>
    </div>
  );
}
