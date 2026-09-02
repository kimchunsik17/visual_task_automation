// formatStudioShared — 포맷 스튜디오의 상태·핸들러(useFormatDraft)와 공용 부품.
//
// 같은 편집 로직을 두 셸이 쓴다: 워크플로우 에디터의 노드 컨텍스트 모달(FormatStudio)과
// 앱 빌더 구도의 풀페이지(/formats/studio, FormatStudioPage). 셸이 갈라지면서 조건부
// 렌더링이 얽히는 것을 막으려고 상태와 조각을 여기로 내렸다.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Image as ImageIcon, Plus, Trash2 } from 'lucide-react';
import axios from 'axios';
import documentFormatsBundle from '../generated/documentFormats.json';
import { emptyCanvasDesign } from '../formatCanvas';

export const BLOCK_LABELS = { heading: '제목', paragraph: '문단', table: '표', image: '이미지', page_break: '쪽 나눔' };
export const KIND_LABELS = { text: '텍스트', multiline: '긴 글', rows: '표(반복 행)', image: '이미지' };
export const OUTPUTS_BY_LAYOUT = { document: ['hwpx', 'docx', 'pdf', 'xlsx'], design: ['png', 'pdf'] };
export const DEFAULT_THEME = { primaryColor: '#4f7cff', backgroundColor: '#ffffff', textColor: '#0f172a', mutedColor: '#5b6474', fontFamily: 'Pretendard' };

export const emptySpec = (layout = 'document') => ({
  version: 1, name: '', description: '', layout,
  output: { default: OUTPUTS_BY_LAYOUT[layout][0], allowed: [...OUTPUTS_BY_LAYOUT[layout]] },
  fields: [],
  ...(layout === 'document'
    ? { blocks: [{ type: 'heading', level: 1, text: '새 문서' }] }
    : {
      // 새 디자인 포맷은 캔버스(elements)로 시작한다 — 위치·크기를 드래그로 편집한다.
      fields: [{ name: 'title', label: '제목', kind: 'text', required: false, example: '제목' }],
      design: emptyCanvasDesign(794, 1123, { ...DEFAULT_THEME }),
    }),
});

export const cloneSpec = (spec) => JSON.parse(JSON.stringify(spec));
const exampleValue = (field) => field.example || field.label || field.name;
const escapeHtml = (value) => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
export const substitute = (text, fields, { escape = false } = {}) => String(text || '').replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g, (_, name) => {
  const field = fields.find((f) => f.name === name);
  const value = field ? exampleValue(field) : `{{${name}}}`;
  return escape ? escapeHtml(value) : value;
});

// ── 미리보기 ────────────────────────────────────────────────────────────

export function DocumentPreview({ spec }) {
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

export function DesignPreview({ spec, maxWidth = 330 }) {
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
  const scale = Math.min(1, maxWidth / (design.width || 794));
  return (
    <div className="fstudio-design-preview" style={{ height: (design.height || 1123) * scale + 16 }}>
      <iframe title="디자인 미리보기" sandbox="" srcDoc={srcDoc}
              style={{ width: design.width || 794, height: design.height || 1123, transform: `scale(${scale})` }} />
    </div>
  );
}

// ── 빈칸(fields) 편집 ───────────────────────────────────────────────────

export function FieldsEditor({ spec, addField, setField, removeField, showHead = true }) {
  return (
    <div className="fstudio-fields">
      {showHead && (
        <div className="fstudio-section-head">
          <strong>빈칸 (fields)</strong>
          <button type="button" onClick={addField}><Plus size={13} /> 추가</button>
        </div>
      )}
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
  );
}

// ── 골격(blocks) 편집 (문서류) ──────────────────────────────────────────

export function BlocksEditor({ spec, setBlock, moveBlock, removeBlock, onPickImage }) {
  return (
    <div className="fstudio-blocks">
      <div className="fstudio-section-head"><strong>골격 (blocks)</strong></div>
      {(spec.blocks || []).map((block, index) => (
        <div key={index} id={`fstudio-block-${index}`} className="fstudio-block">
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
                <button type="button" className="fstudio-upload" onClick={() => onPickImage(index)}>
                  <ImageIcon size={14} /> {block.artifactId ? '이미지 바꾸기' : '이미지 업로드'}
                </button>
              )}
              <input value={block.widthMm ?? ''} onChange={(e) => setBlock(index, (b) => { const v = e.target.value; if (v === '') delete b.widthMm; else b.widthMm = Number(v); })} placeholder="폭(mm)" style={{ width: 82 }} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── 상태 · 핸들러 훅 ────────────────────────────────────────────────────

export function useFormatDraft({ isOpen = true, initialFormatId = '', onLibraryChanged = null, onLoaded = null } = {}) {
  const [spec, setSpec] = useState(() => emptySpec());
  const [libraryId, setLibraryId] = useState('');       // 내 라이브러리 행 id (있으면 업데이트)
  const [userFormats, setUserFormats] = useState([]);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLayout, setAiLayout] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState(null);           // { tone: 'error'|'success', text }
  const [showCode, setShowCode] = useState(false);
  const uploadInputRef = useRef(null);
  const uploadTargetRef = useRef(null);
  const importInputRef = useRef(null);

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
      if (!initialFormatId) { setSpec(emptySpec()); setLibraryId(''); onLoaded?.(false); return; }
      const preset = presets.find((p) => p.id === initialFormatId);
      if (preset) {
        const copy = cloneSpec(preset);
        delete copy.id;
        copy.name = `${preset.name} (복제)`;
        setSpec(copy); setLibraryId('');
        onLoaded?.(true);
        return;
      }
      axios.get('/api/formats', authHeaders()).then((res) => {
        const row = (res.data.formats || []).find((f) => f.id === initialFormatId);
        if (row) { setSpec(cloneSpec({ ...row.spec, name: row.name })); setLibraryId(row.id); onLoaded?.(true); }
        else { setSpec(emptySpec()); setLibraryId(''); onLoaded?.(false); }
      }).catch(() => { setSpec(emptySpec()); setLibraryId(''); onLoaded?.(false); });
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

  // ── 파일에서 가져오기 (.hwpx/.docx → FormatSpec 초안) ──
  const importFromFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || importing) return false;
    setImporting(true);
    setNotice(null);
    const form = new FormData();
    form.append('file', file);
    form.append('use_ai', '1');
    try {
      const res = await axios.post('/api/formats/import', form, authHeaders());
      setSpec(cloneSpec(res.data.spec));
      setLibraryId('');
      const ai = res.data.ai || '';
      setNotice({
        tone: 'success',
        text: ai === 'applied'
          ? '파일 구조를 가져와 AI가 빈칸을 제안했습니다 — 확인하고 다듬은 뒤 저장하세요.'
          : `파일 구조를 가져왔습니다 (AI 다듬기 ${ai.startsWith('skipped') ? '건너뜀' : '꺼짐'}) — 실행마다 달라질 자리를 빈칸으로 선언하세요.`,
      });
      return true;
    } catch (error) {
      setNotice({ tone: 'error', text: '가져오기 실패: ' + (error.response?.data?.detail || error.message) });
      return false;
    } finally {
      setImporting(false);
    }
  };

  // ── AI 생성 ──
  const generate = async () => {
    if (!aiPrompt.trim() || aiLoading) return false;
    setAiLoading(true);
    setNotice(null);
    try {
      const res = await axios.post('/api/formats/generate', { prompt: aiPrompt, layout: aiLayout }, authHeaders());
      setSpec(cloneSpec(res.data.spec));
      setLibraryId('');
      setNotice({ tone: 'success', text: 'AI 초안이 로드되었습니다 — 다듬은 뒤 저장하세요.' });
      return true;
    } catch (error) {
      setNotice({ tone: 'error', text: error.response?.data?.detail || error.message });
      return false;
    } finally {
      setAiLoading(false);
    }
  };

  // ── 저장 ──
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
      window.dispatchEvent(new Event('formats-library-changed'));
      return res.data.id;
    } catch (error) {
      setNotice({ tone: 'error', text: error.response?.data?.detail || error.message });
      return null;
    } finally {
      setSaving(false);
    }
  };

  return {
    spec, setSpec, update, libraryId, setLibraryId, userFormats, refreshLibrary, presets,
    aiPrompt, setAiPrompt, aiLayout, setAiLayout, aiLoading, generate,
    saving, persist, importing, importFromFile,
    notice, setNotice, showCode, setShowCode,
    uploadInputRef, uploadTargetRef, importInputRef, uploadImage,
    addField, setField, removeField,
    addBlock, setBlock, moveBlock, removeBlock,
    isDocument: spec.layout === 'document',
  };
}
