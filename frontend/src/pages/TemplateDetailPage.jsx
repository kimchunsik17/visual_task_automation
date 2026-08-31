// 커뮤니티 템플릿 소개 페이지 (ADR-0023 확장).
//
// 목록에서 곧바로 '가져오기' 를 누르던 것을 여기로 한 걸음 미뤘다. 템플릿은 남의 계정에서
// 돌아갈 로직이라, **무엇을 준비해야 하고 무엇을 건드리는지** 읽고 판단할 자리가 필요하다.
// 좋아요·댓글·신고도 여기 붙는다 — 목록 카드에 다 넣으면 어느 것도 눈에 안 들어온다.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import {
  AlertTriangle, ArrowLeft, Download, Flag, Heart, LibraryBig,
  MessageSquare, PencilLine, Send, ShieldCheck, Trash2,
} from 'lucide-react';
import MainSidebar from '../MainSidebar';
import SectionTabs from '../components/SectionTabs';
import { COMMUNITY_SECTION_TABS } from '../navigation';
import { useAuth } from '../AuthContext';
import { formatDate, timeAgo } from '../timeFormat';
import {
  CATEGORY_LABEL, RISK_LABEL, TRIGGER_LABEL, credentialLabel,
} from '../templateLabels';
import { getTemplateThumbnail } from '../officialTemplateThumbnails';
import TemplateEditDialog from '../components/TemplateEditDialog';
import ReportDialog from '../components/ReportDialog';
import TemplateFlowPreview from '../components/TemplateFlowPreview';
import './MainPage.css';
import './TemplatesPage.css';
import './TemplateDetailPage.css';

const auth = (token) => (token ? { headers: { Authorization: `Bearer ${token}` } } : {});

export default function TemplateDetailPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [data, setData] = useState(null);
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [installing, setInstalling] = useState(false);
  const [comment, setComment] = useState('');
  const [posting, setPosting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [reporting, setReporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await axios.get(`/api/community/templates/${slug}`, auth(token));
      setData(res.data.template);
      setVersions(res.data.versions || []);
    } catch (e) {
      setError(e.response?.status === 404 ? '템플릿을 찾을 수 없습니다.'
                                          : '불러오지 못했습니다.');
    } finally { setLoading(false); }
  }, [slug, token]);

  useEffect(() => { load(); }, [load]);

  const install = async () => {
    setInstalling(true); setError(null);
    try {
      const res = await axios.post(`/api/community/templates/${slug}/install`, {}, auth(token));
      navigate(`/editor/${res.data.projectId}`);
    } catch (e) {
      setError(e.response?.data?.detail || '가져오지 못했습니다.');
      setInstalling(false);
    }
  };

  const toggleLike = async () => {
    try {
      const res = await axios.post(`/api/community/templates/${slug}/like`, {}, auth(token));
      setData((prev) => ({ ...prev, likedByMe: res.data.liked, likeCount: res.data.likeCount }));
    } catch (e) {
      setError(e.response?.data?.detail || '좋아요를 반영하지 못했습니다.');
    }
  };

  const submitComment = async () => {
    if (!comment.trim()) return;
    setPosting(true); setError(null);
    try {
      const res = await axios.post(`/api/community/templates/${slug}/comments`,
                                   { body: comment }, auth(token));
      setData((prev) => ({ ...prev, comments: [...(prev.comments || []), res.data.comment],
                           commentCount: (prev.commentCount || 0) + 1 }));
      setComment('');
    } catch (e) {
      setError(e.response?.data?.detail || '댓글을 남기지 못했습니다.');
    } finally { setPosting(false); }
  };

  const removeComment = async (id) => {
    try {
      await axios.delete(`/api/community/comments/${id}`, auth(token));
      setData((prev) => ({ ...prev, comments: prev.comments.filter((c) => c.id !== id),
                           commentCount: Math.max(0, (prev.commentCount || 1) - 1) }));
    } catch (e) {
      setError(e.response?.data?.detail || '댓글을 지우지 못했습니다.');
    }
  };

  const body = () => {
    if (loading) return <p className="tpl-detail-note">불러오는 중…</p>;
    if (!data) return <p className="tpl-detail-note">{error || '템플릿을 찾을 수 없습니다.'}</p>;
    const thumbnailUrl = getTemplateThumbnail(data);

    return (
      <>
        <header className="tpl-detail-head">
          {thumbnailUrl
            ? <img className="tpl-detail-thumb" src={thumbnailUrl} alt="" />
            : <span className="tpl-detail-thumb is-empty"><LibraryBig size={26} /></span>}
          <div className="tpl-detail-headline">
            <div className="tpl-detail-badges">
              {data.isCurated && <span className="tpl-official" title="운영자가 만들고 검수한 공식 템플릿">공식</span>}
              <span className="tpl-detail-category">{CATEGORY_LABEL[data.category] || '기타'}</span>
              {data.status !== 'published' && <span className="tpl-detail-draft">{data.status}</span>}
            </div>
            <h1>{data.title}</h1>
            <p>{data.description || '한 줄 소개가 없습니다.'}</p>
            <div className="tpl-detail-byline">
              <span>{data.isCurated ? 'WorkFlow Ai' : `@${data.author?.handle || '알 수 없음'}`}</span>
              <span>v{data.latestVersion}</span>
              <span>{data.updatedAt ? `${timeAgo(data.updatedAt)} 수정` : ''}</span>
            </div>
          </div>
          <div className="tpl-detail-actions">
            <button className="management-button primary" onClick={install} disabled={installing}>
              <Download size={14} /> {installing ? '가져오는 중…' : '내 계정으로 가져오기'}
            </button>
            <div className="tpl-detail-action-row">
              <button
                type="button"
                className={`tpl-detail-like ${data.likedByMe ? 'is-on' : ''}`}
                onClick={toggleLike}
                disabled={!data.canLike}
                title={data.canLike ? '좋아요' : '자신이 올린 템플릿에는 누를 수 없어요'}
              >
                <Heart size={14} fill={data.likedByMe ? 'currentColor' : 'none'} /> {data.likeCount}
              </button>
              {data.canEdit && (
                <button type="button" className="management-button" onClick={() => setEditing(true)}>
                  <PencilLine size={14} /> 수정
                </button>
              )}
              <button type="button" className="tpl-detail-report" onClick={() => setReporting(true)}
                      title="신고하기" aria-label="신고하기">
                <Flag size={14} />
              </button>
            </div>
            {/* 고칠 수 있는 사람에게 순서를 알려 준다 — 가져와서 고친 다음 '수정' 안에서
                새 버전을 내야 반영된다. 이 단계를 모르고 소개만 저장하는 일이 있었다. */}
            {data.canEdit && (
              <p className="tpl-detail-edit-hint">
                워크플로우를 고치려면 <strong>가져오기 → 에디터에서 수정 →
                여기서 [수정] → 새 버전으로 올리기</strong> 순서로 진행하세요.
              </p>
            )}
          </div>
        </header>

        {error && <p className="tpl-error">{error}</p>}

        <section className="tpl-detail-facts" aria-label="템플릿 정보">
          <div><span>구성</span><strong>{data.nodeCount}개 노드 · {data.edgeCount}개 연결</strong></div>
          {data.memoCount > 0 && (
            <div><span>캔버스 안내</span><strong>메모 {data.memoCount}개</strong></div>
          )}
          <div><span>시작 방식</span><strong>{TRIGGER_LABEL[data.triggerType] || '수동 실행'}</strong></div>
          <div><span>AI 사용</span><strong>{data.usesAi ? '사용함' : '사용 안 함'}</strong></div>
          <div><span>가져간 횟수</span><strong>{data.signals?.installs ?? 0}회</strong></div>
          <div><span>첫 실행 성공률</span><strong>
            {data.signals?.measuredRuns
              ? `${Math.round(data.signals.firstRunSuccessRate * 100)}% (${data.signals.measuredRuns}건)`
              : '기록 없음'}
          </strong></div>
          <div><span>게시일</span><strong>{formatDate(data.publishedAt)}</strong></div>
        </section>

        {(data.requiredCredentials?.length > 0 || data.riskFlags?.length > 0) && (
          <section className="tpl-detail-prep">
            {data.requiredCredentials?.length > 0 && (
              <p className="tpl-need">
                <ShieldCheck size={13} /> 가져오기 전에 준비해야 하는 연결:{' '}
                {data.requiredCredentials.map(credentialLabel).join(', ')}
              </p>
            )}
            {data.riskFlags?.length > 0 && (
              <p className="tpl-risk">
                <AlertTriangle size={13} /> 이 템플릿이 하는 일:{' '}
                {data.riskFlags.map((f) => RISK_LABEL[f] || f).join(', ')}
              </p>
            )}
          </section>
        )}

        {/* 구조를 소개 글보다 먼저 보여준다 — 글보다 그림이 먼저 읽히고,
            "몇 단계짜리인가" 가 가져올지 말지를 가장 빨리 정해 준다. */}
        {data.graphOutline?.nodes?.length > 0 && (
          <section className="tpl-detail-flow">
            <h2>워크플로우 구조</h2>
            <p className="tpl-detail-note">
              가져오면 이 구성이 그대로 내 계정에 복사됩니다. 캔버스에는 안내 메모도 함께 붙어 있어요.
            </p>
            <TemplateFlowPreview outline={data.graphOutline} />
          </section>
        )}

        <section className="tpl-detail-intro">
          <h2>소개</h2>
          {data.introBody
            ? <div className="tpl-detail-markdown"><ReactMarkdown>{data.introBody}</ReactMarkdown></div>
            : <p className="tpl-detail-note">
                아직 제작자가 남긴 소개가 없습니다. 아래 정보와 노드 구성을 참고해주세요.
              </p>}
          {data.introImages?.length > 0 && (
            <div className="tpl-detail-gallery">
              {data.introImages.map((src) => <img key={src} src={src} alt="" loading="lazy" />)}
            </div>
          )}
        </section>

        <section className="tpl-detail-versions">
          <h2>버전 기록</h2>
          <ul>
            {versions.map((v) => (
              <li key={v.id}>
                <strong>v{v.version}</strong>
                <span>{formatDate(v.publishedAt)}</span>
                <em>{v.changelog || '변경 내용이 적혀 있지 않습니다.'}</em>
                {v.compatibility && v.compatibility.ok === false && (
                  <span className="tpl-detail-incompat">
                    <AlertTriangle size={11} /> 지금 환경과 맞지 않는 노드가 있습니다
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="tpl-detail-comments">
          <h2><MessageSquare size={15} /> 댓글 {data.commentCount || 0}</h2>
          {user ? (
            <div className="tpl-detail-commentbox">
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="써 보고 느낀 점이나 막힌 부분을 남겨주세요."
                rows={3}
              />
              <button className="management-button primary" onClick={submitComment}
                      disabled={posting || !comment.trim()}>
                <Send size={13} /> {posting ? '남기는 중…' : '댓글 남기기'}
              </button>
            </div>
          ) : (
            <p className="tpl-detail-note">댓글을 남기려면 로그인해주세요.</p>
          )}
          <ul className="tpl-detail-commentlist">
            {(data.comments || []).map((c) => (
              <li key={c.id}>
                <div>
                  <strong>@{c.author?.handle || '알 수 없음'}</strong>
                  <span>{timeAgo(c.createdAt)}</span>
                  {c.canDelete && (
                    <button type="button" onClick={() => removeComment(c.id)}
                            title="댓글 지우기" aria-label="댓글 지우기"><Trash2 size={12} /></button>
                  )}
                </div>
                <p>{c.body}</p>
              </li>
            ))}
            {(data.comments || []).length === 0 && (
              <li className="is-empty">아직 댓글이 없습니다. 첫 후기를 남겨주세요.</li>
            )}
          </ul>
        </section>
      </>
    );
  };

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <main className="main-page-content management-page">
        <SectionTabs ariaLabel="커뮤니티 섹션" tabs={COMMUNITY_SECTION_TABS} />
        <div className="management-content tpl-detail">
          <button type="button" className="tpl-detail-back"
                  onClick={() => navigate('/community/templates')}>
            <ArrowLeft size={15} /> 템플릿 목록
          </button>
          {body()}
        </div>
      </main>

      {editing && data && (
        <TemplateEditDialog
          template={data}
          token={token}
          onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); load(); }}
        />
      )}
      {reporting && data && (
        <ReportDialog
          targetType="template"
          targetId={String(data.id)}
          token={token}
          onClose={() => setReporting(false)}
        />
      )}
    </div>
  );
}
