// 템플릿 수정 창. 두 가지를 **명확히 나눠서** 보여준다.
//
//   겉면(제목·소개·분류·이미지) — 고쳐도 이미 가져간 사람의 사본은 그대로다. 바로 반영된다.
//   로직(그래프)          — 새 버전을 낸다. 예전 버전은 남는다. 공식 템플릿만 가능하다.
//
// 이 구분이 흐려지면 "오탈자 고쳤을 뿐인데 남의 워크플로우가 바뀌는" 일이 생긴다.
import { useEffect, useState } from 'react';
import axios from 'axios';
import { ImagePlus, Star, Workflow, X } from 'lucide-react';
import { CATEGORIES } from '../templateLabels';
import './TemplateEditDialog.css';

const auth = (token) => (token ? { headers: { Authorization: `Bearer ${token}` } } : {});
const MAX_IMAGES = 10;

// 다음 버전 번호를 미리 채워 준다. 고정 자리표시자(1.1.0)를 두면 이미 1.1.0 인 템플릿에서
// **올바른 버튼을 눌러도** "이미 있는 버전입니다" 로 튕긴다.
function nextVersion(current) {
  const parts = String(current || '1.0.0').split('.').map((n) => parseInt(n, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return '1.1.0';
  return `${parts[0]}.${parts[1] + 1}.0`;
}

export default function TemplateEditDialog({ template, token, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: template.title || '',
    description: template.description || '',
    category: template.category || 'etc',
    tags: (template.tags || []).join(', '),
    introBody: template.introBody || '',
  });
  // {artifactId, url} — 이미 붙어 있는 것은 서버 주소를, 방금 올린 것은 blob 미리보기를 쓴다.
  const [images, setImages] = useState(
    (template.introImageIds || []).map((id, index) => ({
      artifactId: id, url: (template.introImages || [])[index],
    })),
  );
  const [thumbnail, setThumbnail] = useState(template.thumbnailArtifactId || '');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  // ── 로직 수정(공식 템플릿 전용) ──
  const [projects, setProjects] = useState([]);
  const [revise, setRevise] = useState({
    projectId: '', version: nextVersion(template.latestVersion), changelog: '',
  });
  const canRevise = Boolean(template.isCurated);

  useEffect(() => {
    if (!canRevise) return;
    axios.get('/api/projects/my', auth(token)).then((r) => setProjects(r.data || [])).catch(() => {});
  }, [canRevise, token]);

  const pickImages = async (event) => {
    const files = [...event.target.files].slice(0, MAX_IMAGES - images.length);
    event.target.value = '';
    if (!files.length) return;
    setUploading(true); setError(null);
    const added = [];
    for (const file of files) {
      const body = new FormData();
      body.append('file', file);
      body.append('purpose', 'community');
      try {
        const res = await axios.post('/api/upload', body, {
          headers: { ...(auth(token).headers || {}), 'Content-Type': 'multipart/form-data' },
        });
        added.push({ artifactId: res.data.artifact_id, url: URL.createObjectURL(file) });
      } catch (e) {
        setError(e.response?.data?.detail || `${file.name} 을(를) 올리지 못했습니다.`);
      }
    }
    if (added.length) {
      setImages((prev) => [...prev, ...added]);
      // 섬네일이 아직 없으면 첫 그림을 자동으로 고른다 — 목록 카드가 비어 보이지 않게.
      setThumbnail((current) => current || added[0].artifactId);
    }
    setUploading(false);
  };

  const removeImage = (artifactId) => {
    setImages((prev) => prev.filter((i) => i.artifactId !== artifactId));
    setThumbnail((current) => (current === artifactId ? '' : current));
  };

  const saveSurface = async () => {
    setBusy(true); setError(null);
    try {
      await axios.patch(`/api/community/templates/${template.slug}`, {
        title: form.title,
        description: form.description,
        category: form.category,
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
        introBody: form.introBody,
        introImageIds: images.map((i) => i.artifactId),
        thumbnailArtifactId: thumbnail,
      }, auth(token));
      onSaved();
    } catch (e) {
      setError(e.response?.data?.detail || '저장하지 못했습니다.');
    } finally { setBusy(false); }
  };

  const submitRevision = async () => {
    setBusy(true); setError(null);
    try {
      await axios.post(`/api/community/templates/${template.slug}/revise`, {
        projectId: Number(revise.projectId),
        version: revise.version,
        changelog: revise.changelog,
      }, auth(token));
      onSaved();
    } catch (e) {
      setError(e.response?.data?.detail || '새 버전을 내지 못했습니다.');
    } finally { setBusy(false); }
  };

  return (
    <div className="tpledit-backdrop" onClick={onClose} role="presentation">
      <div className="tpledit-modal" onClick={(e) => e.stopPropagation()} role="dialog"
           aria-modal="true" aria-label="템플릿 수정">
        <div className="tpledit-head">
          <h2>템플릿 수정</h2>
          <button type="button" onClick={onClose} aria-label="닫기"><X size={16} /></button>
        </div>

        <div className="tpledit-body">
          {canRevise && (
            <section className="tpledit-revise">
              <h3><Workflow size={15} /> 워크플로우(노드 구성) 바꾸기</h3>
              <p className="tpledit-hint">
                <strong>노드를 고쳤다면 여기서 새 버전을 내야 반영됩니다.</strong> 아래 ‘소개만
                저장’은 글과 이미지만 저장하고 워크플로우는 건드리지 않습니다.
              </p>
              <p className="tpledit-hint">
                이 템플릿을 내 계정으로 가져와 에디터에서 고친 뒤, 그 워크플로우를 골라 새 버전으로
                냅니다. <strong>예전 버전은 지워지지 않습니다</strong> — 그걸 가져간 사람의 기록이
                거짓이 되면 안 되기 때문입니다. 게시할 때와 같은 구조 검사를 다시 통과해야 합니다.
              </p>
              <label htmlFor="tpledit-project">새 버전으로 낼 워크플로우</label>
              <select id="tpledit-project" value={revise.projectId}
                      onChange={(e) => setRevise({ ...revise, projectId: e.target.value })}>
                <option value="">선택하세요</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
              </select>
              <div className="tpledit-row">
                <div>
                  <label htmlFor="tpledit-version">새 버전 번호 (지금 v{template.latestVersion})</label>
                  <input id="tpledit-version" value={revise.version}
                         onChange={(e) => setRevise({ ...revise, version: e.target.value })} />
                </div>
                <div>
                  <label htmlFor="tpledit-changelog">무엇을 고쳤나요</label>
                  <input id="tpledit-changelog" value={revise.changelog}
                         placeholder="출력 노드를 마지막에 연결"
                         onChange={(e) => setRevise({ ...revise, changelog: e.target.value })} />
                </div>
              </div>
              <button type="button" className="management-button primary tpledit-revise-submit"
                      onClick={submitRevision}
                      disabled={busy || !revise.projectId || !revise.version}>
                <Workflow size={14} /> 워크플로우를 새 버전으로 올리기
              </button>
            </section>
          )}

          <section>
            <h3>소개 글과 겉면</h3>
            <p className="tpledit-hint">
              제목·소개·이미지는 저장하면 바로 바뀝니다. <strong>워크플로우는 바뀌지 않습니다</strong>
              — 이미 가져간 사람의 사본이 조용히 달라지면 안 되기 때문입니다.
            </p>

            <label htmlFor="tpledit-title">이름</label>
            <input id="tpledit-title" value={form.title}
                   onChange={(e) => setForm({ ...form, title: e.target.value })} />

            <label htmlFor="tpledit-desc">한 줄 소개 (목록에 보입니다)</label>
            <textarea id="tpledit-desc" rows={2} value={form.description}
                      onChange={(e) => setForm({ ...form, description: e.target.value })} />

            <div className="tpledit-row">
              <div>
                <label htmlFor="tpledit-cat">분류</label>
                <select id="tpledit-cat" value={form.category}
                        onChange={(e) => setForm({ ...form, category: e.target.value })}>
                  {CATEGORIES.filter((c) => c.id).map((c) =>
                    <option key={c.id} value={c.id}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="tpledit-tags">태그 (쉼표로 구분)</label>
                <input id="tpledit-tags" value={form.tags}
                       onChange={(e) => setForm({ ...form, tags: e.target.value })} />
              </div>
            </div>

            <label htmlFor="tpledit-intro">소개 글 (마크다운)</label>
            <textarea id="tpledit-intro" rows={10} value={form.introBody}
                      onChange={(e) => setForm({ ...form, introBody: e.target.value })}
                      placeholder={'## 무엇을 하나요\n\n## 미리 준비할 것\n\n## 가져온 뒤 바꿔야 하는 값'} />

            <label>이미지 — 별을 누르면 목록 섬네일이 됩니다</label>
            <div className="tpledit-images">
              {images.map((img) => (
                <div key={img.artifactId}
                     className={`tpledit-image ${thumbnail === img.artifactId ? 'is-thumb' : ''}`}>
                  <img src={img.url} alt="" />
                  <button type="button" className="tpledit-image-star"
                          onClick={() => setThumbnail(img.artifactId)}
                          title="목록 섬네일로 쓰기" aria-label="목록 섬네일로 쓰기">
                    <Star size={12} fill={thumbnail === img.artifactId ? 'currentColor' : 'none'} />
                  </button>
                  <button type="button" className="tpledit-image-remove"
                          onClick={() => removeImage(img.artifactId)}
                          title="빼기" aria-label="이미지 빼기"><X size={11} /></button>
                </div>
              ))}
              {images.length < MAX_IMAGES && (
                <label className="tpledit-image-add">
                  <ImagePlus size={16} />
                  <span>{uploading ? '올리는 중…' : '사진 추가'}</span>
                  <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple
                         onChange={pickImages} disabled={uploading} />
                </label>
              )}
            </div>
          </section>

        </div>

        {error && <p className="tpledit-error">{error}</p>}

        <div className="tpledit-foot">
          <button type="button" className="management-button" onClick={onClose}>취소</button>
          <button type="button" className="management-button primary" onClick={saveSurface}
                  disabled={busy || !form.title.trim()}
                  title="글과 이미지만 저장합니다. 워크플로우는 위에서 새 버전으로 올려주세요.">
            {busy ? '저장 중…' : '소개만 저장'}
          </button>
        </div>
      </div>
    </div>
  );
}
