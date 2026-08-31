// 포맷 스튜디오 (포맷 스튜디오 계획 Phase 2 · §4.4)
//
// 포맷(FormatSpec = 빈칸 선언 + 골격)을 만드는 에디터 안 별도 창. 세 갈래로 시작한다:
// 프리셋에서 복제 · AI 생성(초안 → 편집기 로드) · 빈 포맷. 저장은 내 라이브러리(/api/formats),
// 노드 컨텍스트에서 열렸으면 "이 노드에 적용"이 formatId 를 바로 채운다.
//
// 미리보기는 **구조 확인용**이다 — 문서류는 블록을 HTML 로 그리고(한/글 픽셀 일치 아님),
// 디자인류는 sandbox iframe 에 테마 변수를 주입해 그린다. 값 자리는 example 로 채운다.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown, ArrowUp, Image as ImageIcon, LayoutTemplate, Loader2, Plus, Save,
  Sparkles, Table as TableIcon, Trash2, Type, Wand2, X,
} from 'lucide-react';
import axios from 'axios';
import documentFormatsBundle from '../generated/documentFormats.json';
import './FormatStudio.css';

const BLOCK_LABELS = { heading: '제목', paragraph: '문단', table: '표', image: '이미지', page_break: '쪽 나눔' };
const KIND_LABELS = { text: '텍스트', multiline: '긴 글', rows: '표(반복 행)', image: '이미지' };
const OUTPUTS_BY_LAYOUT = { document: ['hwpx', 'docx', 'pdf', 'xlsx'], design: ['png', 'pdf'] };
const DEFAULT_THEME = { primaryColor: '#4f7cff', backgroundColor: '#ffffff', textColor: '#0f172a', mutedColor: '#5b6474', fontFamily: 'Pretendard' };

const emptySpec = (layout = 'document') => ({
  version: 1, name: '', description: '', layout,
  output: { default: OUTPUTS_BY_LAYOUT[layout][0], allowed: [...OUTPUTS_BY_LAYOUT[layout]] },
  fields: [],
  ...(layout === 'document'
    ? { blocks: [{ type: 'heading', level: 1, text: '새 문서' }] }
    : { design: { width: 794, height: 1123, html: '<div class="page"><h1>{{title}}</h1></div>', css: '.page { width: 100%; height: 100vh; box-sizing: border-box; padding: 60px; background: var(--fs-backgroundColor); color: var(--fs-textColor); } h1 { color: var(--fs-primaryColor); }', theme: { ...DEFAULT_THEME } } }),
});

const cloneSpec = (spec) => JSON.parse(JSON.stringify(spec));
const exampleValue = (field) => field.example || field.label || field.name;
const escapeHtml = (value) => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const substitute = (text, fields, { escape = false } = {}) => String(text || '').replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g, (_, name) => {
  const field = fields.find((f) => f.name === name);
  const value = field ? exampleValue(field) : `{{${name}}}`;
  return escape ? escapeHtml(value) : value;
});

// ── 미리보기 ────────────────────────────────────────────────────────────

function DocumentPreview({ spec }) {
  const fields = spec.fields || [];
  return (
    <div className="fstudio-doc-preview">
      {(spec.blocks || []).map((block, index) => {
        if (block.type === 'heading') {
          const Tag = `h${Math.min(3, Math.max(1, block.level || 1))}`;
          return <Tag key={index}>{substitute(block.text, fields)}</Tag>;
        }
        if (block.type === 'paragraph') return <p key={index}>{substitute(block.text, fields)}</p>;
        if (block.type === 'table') {
          const field = block.fromField ? fields.find((f) => f.name === block.fromField) : null;
          const columns = field ? (field.columns || []) : (block.columns || []);
          const rows = field ? [columns.map(() => '예시')] : (block.rows || []);
          return (
            <table key={index}>
              <thead><tr>{columns.map((c, i) => <th key={i}>{substitute(c, fields)}</th>)}</tr></thead>
              <tbody>{rows.map((row, ri) => <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{substitute(cell, fields)}</td>)}</tr>)}</tbody>
            </table>
          );
        }
        if (block.type === 'image') {
          return (
            <div key={index} className="fstudio-image-slot">
              <ImageIcon size={18} />
              <span>{block.fromField ? `이미지: ${block.fromField}` : block.artifactId ? '업로드된 이미지' : '이미지'}</span>
              {block.previewUrl && <img src={block.previewUrl} alt="" />}
            </div>
          );
        }
        return <div key={index} className="fstudio-pagebreak">─ 쪽 나눔 ─</div>;
      })}
    </div>
  );
}

function DesignPreview({ spec }) {
  const design = spec.design || {};
  const fields = spec.fields || [];
  const srcDoc = useMemo(() => {
    const theme = design.theme || {};
    const vars = Object.entries(theme).map(([k, v]) => `--fs-${k}: ${v};`).join(' ');
    let body = substitute(design.html || '', fields, { escape: true });
    // 이미지 슬롯 → 자리 표시 상자 (실행 시 artifact 가 들어온다)
    body = body.replace(/<img\b[^>]*data-field=["']([A-Za-z_][A-Za-z0-9_]*)["'][^>]*>/gi,
      (_, name) => `<div style="min-height:120px;border:2px dashed rgba(127,127,127,.55);border-radius:12px;display:flex;align-items:center;justify-content:center;color:rgba(127,127,127,.9);font-size:14px;">이미지: ${name}</div>`);
    const font = theme.fontFamily ? `body{font-family:'${theme.fontFamily}',Pretendard,sans-serif;}` : '';
    return `<html><head><meta charset="utf-8"><style>:root{${vars}} *{box-sizing:border-box} body{margin:0} ${font} ${design.css || ''}</style></head><body>${body}</body></html>`;
  }, [design, fields]);
  const scale = Math.min(1, 330 / (design.width || 794));
  return (
    <div className="fstudio-design-preview" style={{ height: (design.height || 1123) * scale + 16 }}>
      <iframe title="디자인 미리보기" sandbox="" srcDoc={srcDoc}
              style={{ width: design.width || 794, height: design.height || 1123, transform: `scale(${scale})` }} />
    </div>
  );
}

// ── 본체 ────────────────────────────────────────────────────────────────

export default function FormatStudio({ isOpen, onClose, initialFormatId = '', onApplyToNode = null, onLibraryChanged = null }) {
  const [spec, setSpec] = useState(() => emptySpec());
  const [libraryId, setLibraryId] = useState('');       // 내 라이브러리 행 id (있으면 업데이트)
  const [userFormats, setUserFormats] = useState([]);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLayout, setAiLayout] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);           // { tone: 'error'|'success', text }
  const [showCode, setShowCode] = useState(false);
  const uploadInputRef = useRef(null);
  const uploadTargetRef = useRef(null);

  const authHeaders = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
  const presets = documentFormatsBundle.formats || [];

  const refreshLibrary = useCallback(async () => {
    try {
      const res = await axios.get('/api/formats', authHeaders());
      setUserFormats(res.data.formats || []);
    } catch { setUserFormats([]); }
  }, []);

  // 열릴 때: 컨텍스트 formatId 가 프리셋이면 복제본으로, 내 포맷이면 그대로 편집.
  useEffect(() => {
    if (!isOpen) return;
    setNotice(null);
    refreshLibrary().then(() => {
      if (!initialFormatId) { setSpec(emptySpec()); setLibraryId(''); return; }
      const preset = presets.find((p) => p.id === initialFormatId);
      if (preset) {
        const copy = cloneSpec(preset);
        delete copy.id;
        copy.name = `${preset.name} (복제)`;
        setSpec(copy); setLibraryId('');
        return;
      }
      axios.get('/api/formats', authHeaders()).then((res) => {
        const row = (res.data.formats || []).find((f) => f.id === initialFormatId);
        if (row) { setSpec(cloneSpec({ ...row.spec, name: row.name })); setLibraryId(row.id); }
        else { setSpec(emptySpec()); setLibraryId(''); }
      }).catch(() => { setSpec(emptySpec()); setLibraryId(''); });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, initialFormatId]);

  const update = (mutator) => setSpec((current) => { const next = cloneSpec(current); mutator(next); return next; });

  // ── fields 편집 ──
  const addField = () => update((s) => {
    let n = 1; while (s.fields.some((f) => f.name === `field${n}`)) n += 1;
    s.fields.push({ name: `field${n}`, label: `빈칸 ${n}`, kind: 'text', required: false });
  });
  const setField = (index, key, value) => update((s) => {
    const field = s.fields[index];
    if (key === 'columns') field.columns = value.split(',').map((c) => c.trim()).filter(Boolean);
    else if (key === 'required') field.required = value;
    else field[key] = value;
    if (key === 'kind' && value === 'rows' && !field.columns) field.columns = ['항목', '내용'];
  });
  const removeField = (index) => update((s) => { s.fields.splice(index, 1); });

  // ── blocks 편집 (document) ──
  const addBlock = (type) => update((s) => {
    const block = { type };
    if (type === 'heading') { block.level = 2; block.text = '새 제목'; }
    if (type === 'paragraph') block.text = '';
    if (type === 'table') { block.columns = ['항목', '내용']; block.rows = [['', '']]; }
    s.blocks.push(block);
  });
  const setBlock = (index, mutator) => update((s) => mutator(s.blocks[index]));
  const moveBlock = (index, delta) => update((s) => {
    const to = index + delta;
    if (to < 0 || to >= s.blocks.length) return;
    const [b] = s.blocks.splice(index, 1);
    s.blocks.splice(to, 0, b);
  });
  const removeBlock = (index) => update((s) => { s.blocks.splice(index, 1); });

  const uploadImage = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    const index = uploadTargetRef.current;
    if (!file || index == null) return;
    const form = new FormData();
    form.append('file', file);
    form.append('purpose', 'community'); // 이미지 전용 업로드 경로(ADR-0010) 재사용
    try {
      const res = await axios.post('/api/upload', form, authHeaders());
      setBlock(index, (block) => {
        block.artifactId = res.data.artifact_id;
        delete block.fromField;
        block.previewUrl = `/${res.data.file_path}`;
      });
    } catch (error) {
      setNotice({ tone: 'error', text: '이미지 업로드 실패: ' + (error.response?.data?.detail || error.message) });
    }
  };

  // ── AI 생성 ──
  const generate = async () => {
    if (!aiPrompt.trim() || aiLoading) return;
    setAiLoading(true);
    setNotice(null);
    try {
      const res = await axios.post('/api/formats/generate', { prompt: aiPrompt, layout: aiLayout }, authHeaders());
      const generated = res.data.spec;
      setSpec(cloneSpec(generated));
      setLibraryId('');
      setNotice({ tone: 'success', text: 'AI 초안이 로드되었습니다 — 다듬은 뒤 저장하세요.' });
    } catch (error) {
      setNotice({ tone: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setAiLoading(false);
    }
  };

  // ── 저장·적용 ──
  const persist = async () => {
    if (!spec.name?.trim()) { setNotice({ tone: 'error', text: '포맷 이름을 입력하세요.' }); return null; }
    setSaving(true);
    setNotice(null);
    try {
      const body = { name: spec.name.trim(), spec };
      const res = libraryId
        ? await axios.put(`/api/formats/${libraryId}`, body, authHeaders())
        : await axios.post('/api/formats', body, authHeaders());
      setLibraryId(res.data.id);
      setNotice({ tone: 'success', text: '내 라이브러리에 저장되었습니다.' });
      refreshLibrary();
      onLibraryChanged?.();
      return res.data.id;
    } catch (error) {
      setNotice({ tone: 'error', text: error.response?.data?.detail || error.message });
      return null;
    } finally {
      setSaving(false);
    }
  };

  const applyToNode = async () => {
    const id = await persist();
    if (id && onApplyToNode) { onApplyToNode(id); onClose(); }
  };

  if (!isOpen) return null;
  const isDocument = spec.layout === 'document';

  return (
    <div className="fstudio-backdrop" onClick={onClose}>
      <div className="fstudio" role="dialog" aria-label="포맷 스튜디오" onClick={(e) => e.stopPropagation()}>
        <header className="fstudio-head">
          <div className="fstudio-title"><LayoutTemplate size={18} /> 포맷 스튜디오</div>
          <div className="fstudio-ai">
            <select value={aiLayout} onChange={(e) => setAiLayout(e.target.value)} aria-label="생성 종류">
              <option value="">자동</option><option value="document">문서</option><option value="design">포스터·팜플렛</option>
            </select>
            <input value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)}
                   onKeyDown={(e) => { if (e.key === 'Enter') generate(); }}
                   placeholder='AI에게 포맷 요청 — 예: "주간 업무 보고서 양식"' />
            <button type="button" onClick={generate} disabled={aiLoading}>
              {aiLoading ? <Loader2 size={15} className="fstudio-spin" /> : <Sparkles size={15} />} 생성
            </button>
          </div>
          <button type="button" className="fstudio-close" onClick={onClose} aria-label="닫기"><X size={18} /></button>
        </header>

        <div className="fstudio-body">
          {/* ── 좌: 시작점 ── */}
          <aside className="fstudio-side">
            <span className="fstudio-side-label">프리셋에서 시작</span>
            {presets.map((p) => (
              <button key={p.id} type="button" onClick={() => { const c = cloneSpec(p); delete c.id; c.name = `${p.name} (복제)`; setSpec(c); setLibraryId(''); setNotice(null); }}>
                {p.name}<em>{p.layout === 'design' ? '디자인' : '문서'}</em>
              </button>
            ))}
            {userFormats.length > 0 && <span className="fstudio-side-label">내 포맷 열기</span>}
            {userFormats.map((f) => (
              <button key={f.id} type="button" onClick={() => { setSpec(cloneSpec({ ...f.spec, name: f.name })); setLibraryId(f.id); setNotice(null); }}>
                {f.name}<em>편집</em>
              </button>
            ))}
            <span className="fstudio-side-label">새로 만들기</span>
            <button type="button" onClick={() => { setSpec(emptySpec('document')); setLibraryId(''); }}>빈 문서 포맷</button>
            <button type="button" onClick={() => { setSpec(emptySpec('design')); setLibraryId(''); }}>빈 디자인 포맷</button>
            {isDocument && (
              <>
                <span className="fstudio-side-label">블록 추가</span>
                <div className="fstudio-block-palette">
                  <button type="button" onClick={() => addBlock('heading')}><Type size={14} /> 제목</button>
                  <button type="button" onClick={() => addBlock('paragraph')}><Type size={14} /> 문단</button>
                  <button type="button" onClick={() => addBlock('table')}><TableIcon size={14} /> 표</button>
                  <button type="button" onClick={() => addBlock('image')}><ImageIcon size={14} /> 이미지</button>
                  <button type="button" onClick={() => addBlock('page_break')}>쪽 나눔</button>
                </div>
              </>
            )}
          </aside>

          {/* ── 중: 편집기 ── */}
          <section className="fstudio-editor">
            <div className="fstudio-name-row">
              <input value={spec.name} onChange={(e) => update((s) => { s.name = e.target.value; })} placeholder="포맷 이름" />
              <span className={`fstudio-layout-badge ${spec.layout}`}>{isDocument ? '문서' : '디자인'}</span>
            </div>

            <div className="fstudio-fields">
              <div className="fstudio-section-head">
                <strong>빈칸 (fields)</strong>
                <button type="button" onClick={addField}><Plus size={13} /> 추가</button>
              </div>
              {(spec.fields || []).length === 0 && <p className="fstudio-hint">실행마다 달라질 내용을 빈칸으로 선언하세요. 골격에서 {'{{이름}}'} 으로 참조합니다.</p>}
              {(spec.fields || []).map((field, index) => (
                <div key={index} className="fstudio-field-row">
                  <input className="mono" value={field.name} onChange={(e) => setField(index, 'name', e.target.value)} placeholder="name" title="영문 이름" />
                  <input value={field.label || ''} onChange={(e) => setField(index, 'label', e.target.value)} placeholder="라벨" />
                  <select value={field.kind || 'text'} onChange={(e) => setField(index, 'kind', e.target.value)}>
                    {Object.entries(KIND_LABELS).map(([v, l]) => (
                      (spec.layout === 'design' && v === 'rows') ? null : <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                  <label className="fstudio-req"><input type="checkbox" checked={!!field.required} onChange={(e) => setField(index, 'required', e.target.checked)} />필수</label>
                  {field.kind === 'rows'
                    ? <input value={(field.columns || []).join(', ')} onChange={(e) => setField(index, 'columns', e.target.value)} placeholder="열 이름 (쉼표)" />
                    : <input value={field.example || ''} onChange={(e) => setField(index, 'example', e.target.value)} placeholder="예시값 (미리보기)" />}
                  <button type="button" className="fstudio-icon-btn" onClick={() => removeField(index)} aria-label="빈칸 삭제"><Trash2 size={14} /></button>
                </div>
              ))}
            </div>

            {isDocument ? (
              <div className="fstudio-blocks">
                <div className="fstudio-section-head"><strong>골격 (blocks)</strong></div>
                {(spec.blocks || []).map((block, index) => (
                  <div key={index} className="fstudio-block">
                    <div className="fstudio-block-head">
                      <span>{BLOCK_LABELS[block.type]}</span>
                      <div>
                        <button type="button" className="fstudio-icon-btn" onClick={() => moveBlock(index, -1)} aria-label="위로"><ArrowUp size={13} /></button>
                        <button type="button" className="fstudio-icon-btn" onClick={() => moveBlock(index, 1)} aria-label="아래로"><ArrowDown size={13} /></button>
                        <button type="button" className="fstudio-icon-btn" onClick={() => removeBlock(index)} aria-label="삭제"><Trash2 size={13} /></button>
                      </div>
                    </div>
                    {block.type === 'heading' && (
                      <div className="fstudio-block-body">
                        <select value={block.level || 1} onChange={(e) => setBlock(index, (b) => { b.level = Number(e.target.value); })}>
                          <option value={1}>제목 1</option><option value={2}>제목 2</option><option value={3}>제목 3</option>
                        </select>
                        <input value={block.text || ''} onChange={(e) => setBlock(index, (b) => { b.text = e.target.value; })} placeholder="제목 — {{빈칸}} 참조 가능" />
                      </div>
                    )}
                    {block.type === 'paragraph' && (
                      <textarea rows={2} value={block.text || ''} onChange={(e) => setBlock(index, (b) => { b.text = e.target.value; })} placeholder="문단 내용 — {{빈칸}} 참조 가능" />
                    )}
                    {block.type === 'table' && (
                      <div className="fstudio-block-body fstudio-table-edit">
                        <select value={block.fromField || ''} onChange={(e) => setBlock(index, (b) => {
                          if (e.target.value) { b.fromField = e.target.value; delete b.columns; delete b.rows; }
                          else { delete b.fromField; b.columns = b.columns || ['항목', '내용']; b.rows = b.rows || [['', '']]; }
                        })}>
                          <option value="">직접 입력 표</option>
                          {(spec.fields || []).filter((f) => f.kind === 'rows').map((f) => <option key={f.name} value={f.name}>반복 행: {f.label || f.name}</option>)}
                        </select>
                        {!block.fromField && (
                          <div className="fstudio-grid">
                            <div className="fstudio-grid-row">
                              {(block.columns || []).map((col, ci) => (
                                <input key={ci} className="head" value={col} onChange={(e) => setBlock(index, (b) => { b.columns[ci] = e.target.value; })} />
                              ))}
                              <button type="button" className="fstudio-icon-btn" title="열 추가" onClick={() => setBlock(index, (b) => { b.columns.push(''); b.rows.forEach((r) => r.push('')); })}><Plus size={13} /></button>
                            </div>
                            {(block.rows || []).map((row, ri) => (
                              <div key={ri} className="fstudio-grid-row">
                                {row.map((cell, ci) => (
                                  <input key={ci} value={cell} onChange={(e) => setBlock(index, (b) => { b.rows[ri][ci] = e.target.value; })} placeholder="{{빈칸}}" />
                                ))}
                                <button type="button" className="fstudio-icon-btn" title="행 삭제" onClick={() => setBlock(index, (b) => { b.rows.splice(ri, 1); })}><Trash2 size={13} /></button>
                              </div>
                            ))}
                            <button type="button" className="fstudio-add-row" onClick={() => setBlock(index, (b) => { b.rows.push(b.columns.map(() => '')); })}><Plus size={12} /> 행 추가</button>
                          </div>
                        )}
                      </div>
                    )}
                    {block.type === 'image' && (
                      <div className="fstudio-block-body">
                        <select value={block.fromField || ''} onChange={(e) => setBlock(index, (b) => {
                          if (e.target.value) { b.fromField = e.target.value; delete b.artifactId; delete b.previewUrl; }
                          else delete b.fromField;
                        })}>
                          <option value="">고정 이미지 (업로드)</option>
                          {(spec.fields || []).filter((f) => f.kind === 'image').map((f) => <option key={f.name} value={f.name}>빈칸: {f.label || f.name}</option>)}
                        </select>
                        {!block.fromField && (
                          <button type="button" className="fstudio-upload" onClick={() => { uploadTargetRef.current = index; uploadInputRef.current?.click(); }}>
                            <ImageIcon size={14} /> {block.artifactId ? '이미지 바꾸기' : '이미지 업로드'}
                          </button>
                        )}
                        <input value={block.widthMm ?? ''} onChange={(e) => setBlock(index, (b) => { const v = e.target.value; if (v === '') delete b.widthMm; else b.widthMm = Number(v); })} placeholder="폭(mm)" style={{ width: 82 }} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="fstudio-design">
                <div className="fstudio-section-head"><strong>디자인 (theme)</strong>
                  <label className="fstudio-code-toggle"><input type="checkbox" checked={showCode} onChange={(e) => setShowCode(e.target.checked)} /> HTML/CSS 직접 편집</label>
                </div>
                <div className="fstudio-theme-grid">
                  {['primaryColor', 'backgroundColor', 'textColor', 'mutedColor'].map((key) => (
                    <label key={key}>
                      <span>{{ primaryColor: '주 색', backgroundColor: '배경', textColor: '글자', mutedColor: '보조 글자' }[key]}</span>
                      <input type="color" value={spec.design?.theme?.[key] || '#888888'}
                             onChange={(e) => update((s) => { s.design.theme = { ...(s.design.theme || {}), [key]: e.target.value }; })} />
                    </label>
                  ))}
                  <label><span>글꼴</span>
                    <input type="text" value={spec.design?.theme?.fontFamily || ''} placeholder="Pretendard"
                           onChange={(e) => update((s) => { s.design.theme = { ...(s.design.theme || {}), fontFamily: e.target.value }; })} />
                  </label>
                  <label><span>크기(px)</span>
                    <span className="fstudio-size">
                      <input type="number" value={spec.design?.width || 794} onChange={(e) => update((s) => { s.design.width = Number(e.target.value) || 794; })} />
                      ×
                      <input type="number" value={spec.design?.height || 1123} onChange={(e) => update((s) => { s.design.height = Number(e.target.value) || 1123; })} />
                    </span>
                  </label>
                </div>
                {showCode && (
                  <>
                    <label className="fstudio-code-label">HTML — 텍스트 자리 {'{{빈칸}}'}, 이미지 자리 &lt;img data-field="빈칸"&gt;</label>
                    <textarea className="mono" rows={8} value={spec.design?.html || ''} onChange={(e) => update((s) => { s.design.html = e.target.value; })} spellCheck={false} />
                    <label className="fstudio-code-label">CSS — 색은 var(--fs-primaryColor) 형태의 테마 변수로</label>
                    <textarea className="mono" rows={8} value={spec.design?.css || ''} onChange={(e) => update((s) => { s.design.css = e.target.value; })} spellCheck={false} />
                  </>
                )}
              </div>
            )}
          </section>

          {/* ── 우: 미리보기 ── */}
          <aside className="fstudio-preview">
            <span className="fstudio-side-label">구조 미리보기 <em>예시값 기준 · 실제 문서와 다를 수 있음</em></span>
            {isDocument ? <DocumentPreview spec={spec} /> : <DesignPreview spec={spec} />}
          </aside>
        </div>

        <footer className="fstudio-foot">
          {notice && <span className={`fstudio-notice ${notice.tone}`}>{notice.text}</span>}
          <div className="fstudio-actions">
            <button type="button" className="fstudio-save" onClick={persist} disabled={saving}>
              <Save size={15} /> {libraryId ? '업데이트' : '내 라이브러리에 저장'}
            </button>
            {onApplyToNode && (
              <button type="button" className="fstudio-apply" onClick={applyToNode} disabled={saving}>
                <Wand2 size={15} /> 저장하고 이 노드에 적용
              </button>
            )}
          </div>
        </footer>
        <input ref={uploadInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={uploadImage} />
      </div>
    </div>
  );
}
