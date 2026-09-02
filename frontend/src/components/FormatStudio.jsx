// 포맷 스튜디오 — 워크플로우 에디터의 노드 컨텍스트용 **모달** (포맷 스튜디오 계획 Phase 2 · §4.4).
//
// 가벼운 수정과 "저장하고 이 노드에 적용" 흐름을 담당한다. 포맷 탭에서 여는 풀페이지
// 편집기는 FormatStudioPage(앱 빌더 구도)가 따로 담당하며, 상태·조각은 formatStudioShared 를
// 함께 쓴다. 미리보기는 구조 확인용이다(한/글 픽셀 일치 아님).
import {
  FileUp, LayoutTemplate, Loader2, Save, Sparkles, Type, Table as TableIcon,
  Image as ImageIcon, Wand2, X,
} from 'lucide-react';
import FormatCanvasEditor from './FormatCanvasEditor';
import { customConfirm } from '../CustomConfirm';
import {
  BlocksEditor, DesignPreview, DocumentPreview, FieldsEditor,
  cloneSpec, emptySpec, useFormatDraft,
} from './formatStudioShared';
import './FormatStudio.css';

export default function FormatStudio({ isOpen, onClose, initialFormatId = '', onApplyToNode = null, onLibraryChanged = null }) {
  const draft = useFormatDraft({ isOpen, initialFormatId, onLibraryChanged });
  const {
    spec, setSpec, update, libraryId, setLibraryId, userFormats, presets,
    aiPrompt, setAiPrompt, aiLayout, setAiLayout, aiLoading, generate,
    saving, persist, importing, importFromFile,
    notice, setNotice, showCode, setShowCode,
    uploadInputRef, uploadTargetRef, importInputRef, uploadImage,
    addField, setField, removeField,
    addBlock, setBlock, moveBlock, removeBlock, isDocument,
  } = draft;

  const applyToNode = async () => {
    const id = await persist();
    if (id && onApplyToNode) { onApplyToNode(id); onClose(); }
  };

  if (!isOpen) return null;

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
            <button type="button" disabled={importing} onClick={() => importInputRef.current?.click()}
                    title="갖고 있는 서식 파일의 문단·표 구조와 {{자리표시자}}를 읽어 포맷 초안을 만듭니다">
              {importing ? <Loader2 size={13} className="fstudio-spin" /> : <FileUp size={13} />} 파일에서 가져오기<em>.hwpx·.docx</em>
            </button>
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

            <FieldsEditor spec={spec} addField={addField} setField={setField} removeField={removeField} />

            {isDocument ? (
              <BlocksEditor spec={spec} setBlock={setBlock} moveBlock={moveBlock} removeBlock={removeBlock}
                            onPickImage={(index) => { uploadTargetRef.current = index; uploadInputRef.current?.click(); }} />
            ) : (
              <div className="fstudio-design">
                <div className="fstudio-section-head"><strong>디자인 (theme)</strong>
                  {spec.design?.elements ? (
                    <button type="button" className="fstudio-code-toggle" onClick={async () => {
                      if (!(await customConfirm('코드 편집으로 전환하면 캔버스 배치(드래그 편집)가 해제됩니다. 지금까지의 배치는 HTML/CSS 로 남습니다. 전환할까요?'))) return;
                      update((s) => { delete s.design.elements; });
                      setShowCode(true);
                    }}>코드 편집으로 전환</button>
                  ) : (
                    <label className="fstudio-code-toggle"><input type="checkbox" checked={showCode} onChange={(e) => setShowCode(e.target.checked)} /> HTML/CSS 직접 편집</label>
                  )}
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
                {spec.design?.elements ? (
                  <FormatCanvasEditor design={spec.design} fields={spec.fields || []}
                                      onDesignChange={(nextDesign) => update((s) => { s.design = nextDesign; })} />
                ) : (
                  <p className="fstudio-hint">이 디자인은 코드(HTML/CSS) 기반입니다 — 위치·크기를 드래그로 편집하려면
                    "새로 만들기 → 빈 디자인 포맷"으로 캔버스에서 시작하세요.</p>
                )}
                {!spec.design?.elements && showCode && (
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
        <input ref={importInputRef} type="file" accept=".hwpx,.docx" style={{ display: 'none' }} onChange={importFromFile} />
      </div>
    </div>
  );
}
