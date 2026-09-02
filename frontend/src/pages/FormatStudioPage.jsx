// 풀페이지 포맷 스튜디오 (/formats/studio?id=…) — **앱 빌더와 같은 셸**로 그린다.
//
// AppBuilderPage 의 클래스(builder-layout tool-shell, builder-header, builder-workspace,
// builder-sidebar-left/palette, builder-canvas-toolbar/scroll, properties-panel, ab-section …)를
// 그대로 재사용해 스타일·배치를 일치시킨다. 편집 로직은 formatStudioShared.useFormatDraft 로
// 노드 컨텍스트 모달(FormatStudio)과 공유한다. 프리셋·내 포맷·파일 가져오기는 별도 창(모달)이다.
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, ChevronRight, FileUp, FolderOpen, Image as ImageIcon, LayoutTemplate, Loader2,
  Monitor, PenTool, Play, Save, Search, Settings, Sparkles, Square, Table as TableIcon,
  Type, X,
} from 'lucide-react';
import FormatCanvasEditor, { ElementPropsPanel } from '../components/FormatCanvasEditor';
import {
  BLOCK_LABELS, BlocksEditor, DesignPreview, DocumentPreview, FieldsEditor,
  cloneSpec, emptySpec, useFormatDraft,
} from '../components/formatStudioShared';
import { newBoxElement, newImageElement, newTextElement, withSerialized } from '../formatCanvas';
import { customConfirm } from '../CustomConfirm';
import './AppBuilderPage.css';
import '../components/FormatStudio.css';
import './FormatStudioPage.css';

function InspectorSection({ title, meta, open, onToggle, children }) {
  return (
    <section className={`ab-section ${open ? 'open' : ''}`}>
      <button type="button" className="ab-section-head" onClick={onToggle} aria-expanded={open}>
        <ChevronRight size={14} className="chevron" />
        <span>{title}</span>
        {meta && <span className="ab-section-meta">{meta}</span>}
      </button>
      {open && <div className="ab-section-body">{children}</div>}
    </section>
  );
}

const ELEMENT_ICONS = { text: Type, image: ImageIcon, box: Square };
const ELEMENT_NAMES = { text: '텍스트', image: '이미지 슬롯', box: '사각형' };

export default function FormatStudioPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const initialFormatId = params.get('id') || '';

  const [pickerOpen, setPickerOpen] = useState(false);
  const draft = useFormatDraft({
    isOpen: true, initialFormatId,
    onLoaded: (loaded) => setPickerOpen(!loaded),   // 빈 진입이면 열기 창부터
  });
  const {
    spec, setSpec, update, libraryId, setLibraryId, userFormats, presets,
    aiPrompt, setAiPrompt, aiLayout, setAiLayout, aiLoading, generate,
    saving, persist, importing, importFromFile,
    notice, setNotice, showCode, setShowCode,
    uploadInputRef, uploadTargetRef, importInputRef, uploadImage,
    addField, setField, removeField,
    addBlock, setBlock, moveBlock, removeBlock, isDocument,
  } = draft;

  const [activeTab, setActiveTab] = useState('design');       // 'design' | 'preview'
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);  // 포맷 이름·설명 팝오버
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);
  const [canvasSel, setCanvasSel] = useState(null);
  const [propsEl, setPropsEl] = useState(null);               // 우측 "요소 속성" 섹션 (포털 대상)
  const [paletteQuery, setPaletteQuery] = useState('');
  const [openSections, setOpenSections] = useState({ element: true, format: true, fields: false, preview: false });
  const toggleSection = (key) => setOpenSections((s) => ({ ...s, [key]: !s[key] }));

  const design = spec.design || {};
  const hasCanvas = !isDocument && Array.isArray(design.elements);
  const elements = hasCanvas ? design.elements : [];
  const selectedElement = elements.find((el) => el.id === canvasSel) || null;

  const addCanvasElement = (make) => {
    const el = make();
    update((s) => { s.design = withSerialized({ ...s.design, elements: [...(s.design.elements || []), el] }); });
    setCanvasSel(el.id);
  };

  // Ctrl+S 저장 — 앱 빌더와 같은 손맛
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); persist(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, libraryId]);

  const needle = paletteQuery.trim().toLowerCase();
  const matches = (label) => !needle || label.toLowerCase().includes(needle);
  const textFields = (spec.fields || []).filter((f) => f.kind !== 'image' && f.kind !== 'rows');
  const imageFields = (spec.fields || []).filter((f) => f.kind === 'image');

  const openFormat = (mutate) => { mutate(); setCanvasSel(null); setNotice(null); setPickerOpen(false); setActiveTab('design'); };

  const statusLine = `${libraryId ? '내 라이브러리' : '저장 안 됨'} · 빈칸 ${(spec.fields || []).length} · ${isDocument ? `블록 ${(spec.blocks || []).length}` : `요소 ${elements.length}`}`;

  return (
    <div className="builder-layout tool-shell fsp">
      {/* ── Tool Header — 앱 빌더와 같은 문법(뒤로 / 정체 / View / 저장 / AI) ── */}
      <header className="header editor-header builder-header">
        <div className="editor-header-identity">
          <button className="editor-icon-button" onClick={() => navigate('/formats')} title="포맷 탭으로 돌아가기" aria-label="포맷 탭으로 돌아가기">
            <ArrowLeft size={18} />
          </button>
          <div className="editor-project-control">
            <button className="project-title-btn" onClick={() => setIsDetailsOpen((open) => !open)}
                    aria-expanded={isDetailsOpen} title="포맷 이름과 설명">
              <span className="editor-project-copy">
                <strong>{spec.name || '이름 없는 포맷'}</strong>
                <small className={libraryId ? '' : 'dirty'}>{statusLine}</small>
              </span>
              <Settings size={15} />
            </button>
            {isDetailsOpen && (
              <div className="editor-project-popover">
                <div className="editor-popover-heading">
                  <strong>포맷 정보</strong>
                  <span>이름과 설명을 관리합니다</span>
                </div>
                <label className="editor-field-label" htmlFor="fsp-title">포맷 이름</label>
                <input id="fsp-title" className="editor-field-input" type="text" value={spec.name}
                       onChange={(e) => update((s) => { s.name = e.target.value; })} placeholder="포맷 이름" />
                <label className="editor-field-label" htmlFor="fsp-desc">설명</label>
                <textarea id="fsp-desc" className="editor-field-input editor-field-textarea" rows={4}
                          value={spec.description || ''}
                          onChange={(e) => update((s) => { s.description = e.target.value; })}
                          placeholder="이 포맷의 용도를 기록하세요." />
              </div>
            )}
          </div>
        </div>

        <nav className="builder-view-tabs" role="tablist" aria-label="편집 화면">
          <button role="tab" aria-selected={activeTab === 'design'} onClick={() => setActiveTab('design')}>
            <PenTool size={14} /> 디자인
          </button>
          <button role="tab" aria-selected={activeTab === 'preview'} onClick={() => setActiveTab('preview')}>
            <Play size={14} /> 미리보기
          </button>
        </nav>

        <div className="primary-action-container">
          <button className="editor-icon-button" onClick={() => setPickerOpen(true)} title="열기 · 프리셋" aria-label="열기 · 프리셋">
            <FolderOpen size={17} />
          </button>
          <button className={`assistant-toggle-button ${isAssistantOpen ? 'active' : ''}`}
                  onClick={() => setIsAssistantOpen((open) => !open)} title="AI 포맷 어시스턴트" aria-label="AI 어시스턴트">
            <Sparkles size={16} />
            <span className="assistant-toggle-label">AI 어시스턴트</span>
          </button>
          <button className="btn-run builder-deploy-btn" onClick={persist} disabled={saving}
                  title="내 라이브러리에 저장 (Ctrl+S)">
            <Save size={16} />
            <span className="run-text">{saving ? '저장 중…' : libraryId ? '업데이트' : '저장'}</span>
          </button>
        </div>
      </header>

      <div className="builder-workspace">
        {/* ── Palette + 계층 (좌) ── */}
        <aside className="builder-sidebar-left" aria-label="요소 팔레트와 계층">
          <div className="builder-panel-section palette">
            <div className="sidebar-title"><LayoutTemplate size={13} /> {isDocument ? '블록' : '요소'}</div>
            <div className="palette-search">
              <Search size={14} />
              <input placeholder={isDocument ? '블록 검색' : '요소·빈칸 검색'} value={paletteQuery}
                     onChange={(e) => setPaletteQuery(e.target.value)} />
              {paletteQuery && (
                <button type="button" className="palette-clear" onClick={() => setPaletteQuery('')} aria-label="검색 지우기">
                  <X size={12} />
                </button>
              )}
            </div>
            <div className="builder-panel-scroll">
              <div className="node-palette">
                {isDocument ? (
                  <>
                    <div className="palette-group-title">골격 블록</div>
                    {Object.entries(BLOCK_LABELS).filter(([, label]) => matches(label)).map(([type, label]) => (
                      <button key={type} type="button" className="palette-item" onClick={() => addBlock(type)}>
                        <span className="palette-tile">{type === 'table' ? <TableIcon size={15} /> : type === 'image' ? <ImageIcon size={15} /> : <Type size={15} />}</span>
                        <span>{label}</span>
                      </button>
                    ))}
                  </>
                ) : hasCanvas ? (
                  <>
                    <div className="palette-group-title">기본 요소</div>
                    {matches('텍스트') && (
                      <button type="button" className="palette-item" onClick={() => addCanvasElement(() => newTextElement({ x: 60, y: 60 }))}>
                        <span className="palette-tile"><Type size={15} /></span><span>텍스트</span>
                      </button>
                    )}
                    {matches('사각형') && (
                      <button type="button" className="palette-item" onClick={() => addCanvasElement(() => newBoxElement({ x: 40, y: 40 }))}>
                        <span className="palette-tile"><Square size={15} /></span><span>사각형</span>
                      </button>
                    )}
                    {textFields.some((f) => matches(f.label || f.name)) && <div className="palette-group-title">빈칸 텍스트</div>}
                    {textFields.filter((f) => matches(f.label || f.name)).map((f) => (
                      <button key={f.name} type="button" className="palette-item"
                              onClick={() => addCanvasElement(() => newTextElement({ text: `{{${f.name}}}`, x: 60, y: 120 }))}>
                        <span className="palette-tile accent"><Type size={15} /></span><span>{f.label || f.name}</span>
                      </button>
                    ))}
                    {imageFields.some((f) => matches(f.label || f.name)) && <div className="palette-group-title">이미지 슬롯</div>}
                    {imageFields.filter((f) => matches(f.label || f.name)).map((f) => (
                      <button key={f.name} type="button" className="palette-item"
                              onClick={() => addCanvasElement(() => newImageElement(f.name, { x: 60, y: 200 }))}>
                        <span className="palette-tile accent"><ImageIcon size={15} /></span><span>{f.label || f.name}</span>
                      </button>
                    ))}
                    {(spec.fields || []).length === 0 && <div className="palette-empty">빈칸을 먼저 선언하면 여기서 바로 배치할 수 있어요 (우측 "빈칸" 섹션)</div>}
                  </>
                ) : (
                  <div className="palette-empty">코드(HTML/CSS) 기반 디자인입니다 — 캔버스 요소 팔레트는 캔버스 기반 포맷에서 쓸 수 있어요.</div>
                )}
              </div>
            </div>
          </div>

          <div className="builder-panel-section grow">
            <div className="sidebar-title">계층</div>
            <div className="builder-panel-scroll hierarchy-tree">
              {isDocument ? (
                (spec.blocks || []).length === 0 ? <div className="palette-empty">아직 블록이 없어요</div>
                  : (spec.blocks || []).map((block, index) => (
                    <div key={index} className="hierarchy-item"
                         onClick={() => document.getElementById(`fstudio-block-${index}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>
                      <span className="hierarchy-label">
                        <Type size={12} />
                        <span>{BLOCK_LABELS[block.type]}<span className="hierarchy-caption">{block.text ? ` ${String(block.text).slice(0, 14)}` : ''}</span></span>
                      </span>
                    </div>
                  ))
              ) : elements.length === 0 ? (
                <div className="palette-empty">아직 요소가 없어요</div>
              ) : (
                elements.map((el) => {
                  const ElIcon = ELEMENT_ICONS[el.kind] || Type;
                  const caption = el.kind === 'image' ? el.field
                    : el.kind === 'box' ? `${Math.round(el.w)}×${Math.round(el.h)}`
                      : String(el.text || '').replace(/\s+/g, ' ').slice(0, 16);
                  return (
                    <div key={el.id} className={`hierarchy-item ${canvasSel === el.id ? 'active' : ''}`}
                         onClick={() => setCanvasSel(el.id)}>
                      <span className="hierarchy-label">
                        <ElIcon size={12} />
                        <span>{ELEMENT_NAMES[el.kind]}<span className="hierarchy-caption"> {caption}</span></span>
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </aside>

        {/* ── Canvas (중앙) ── */}
        <main className="builder-center">
          <div className="builder-canvas-toolbar">
            {activeTab === 'design' ? (
              <>
                {!isDocument && (
                  <div className="builder-canvas-dims" title="아트보드 크기 (px)">
                    <input type="number" min="200" max="3000" value={design.width || 794}
                           onChange={(e) => update((s) => { s.design.width = Number(e.target.value) || 794; })} aria-label="너비" />
                    <span>×</span>
                    <input type="number" min="200" max="3000" value={design.height || 1123}
                           onChange={(e) => update((s) => { s.design.height = Number(e.target.value) || 1123; })} aria-label="높이" />
                  </div>
                )}
                <span className="builder-code-hint">
                  {isDocument
                    ? '문서 골격 — 블록을 위에서 아래로 편집합니다 (렌더 시 hwpx·docx·pdf 로 흐름 배치)'
                    : hasCanvas ? '드래그로 이동 · 모서리로 크기 · 방향키 미세 이동 (Shift=10px)' : '코드 기반 디자인'}
                </span>
                <div className="spacer" />
                {!isDocument && hasCanvas && (
                  <button className="builder-toolbar-toggle" onClick={async () => {
                    if (!(await customConfirm('코드 편집으로 전환하면 캔버스 배치(드래그 편집)가 해제됩니다. 지금까지의 배치는 HTML/CSS 로 남습니다. 전환할까요?'))) return;
                    update((s) => { delete s.design.elements; });
                    setShowCode(true);
                  }} title="캔버스 배치를 해제하고 HTML/CSS 를 직접 편집합니다">
                    <PenTool size={13} /><span className="label">코드로 전환</span>
                  </button>
                )}
              </>
            ) : (
              <>
                <span className="builder-preview-badge"><Play size={12} /> 구조 미리보기 · 예시값 기준</span>
                <span className="builder-code-hint">실제 문서(hwpx·pdf)와 세부 모양은 다를 수 있습니다 — 확정은 실행 결과로 확인하세요</span>
                <div className="spacer" />
                <button className="builder-toolbar-toggle" onClick={() => setActiveTab('design')}>
                  <PenTool size={13} /><span className="label">편집으로 돌아가기</span>
                </button>
              </>
            )}
          </div>

          <div className="builder-canvas-scroll" onClick={() => setCanvasSel(null)}>
            {activeTab === 'preview' ? (
              <div className="fsp-preview-frame" onClick={(e) => e.stopPropagation()}>
                {isDocument ? <DocumentPreview spec={spec} /> : <DesignPreview spec={spec} maxWidth={720} />}
              </div>
            ) : isDocument ? (
              <div className="fsp-doc-wrap" onClick={(e) => e.stopPropagation()}>
                <BlocksEditor spec={spec} setBlock={setBlock} moveBlock={moveBlock} removeBlock={removeBlock}
                              onPickImage={(index) => { uploadTargetRef.current = index; uploadInputRef.current?.click(); }} />
              </div>
            ) : hasCanvas ? (
              <div className="fsp-canvas-wrap" onClick={(e) => e.stopPropagation()}>
                <FormatCanvasEditor design={design} fields={spec.fields || []}
                                    hideToolbar hideProps
                                    selectedId={canvasSel} onSelect={setCanvasSel}
                                    propsContainer={propsEl}
                                    maxWidth={1100}
                                    onDesignChange={(nextDesign) => update((s) => { s.design = nextDesign; })} />
              </div>
            ) : (
              <div className="fsp-doc-wrap" onClick={(e) => e.stopPropagation()}>
                <div className="fstudio-design">
                  <label className="fstudio-code-toggle"><input type="checkbox" checked={showCode} onChange={(e) => setShowCode(e.target.checked)} /> HTML/CSS 직접 편집</label>
                  {showCode && (
                    <>
                      <label className="fstudio-code-label">HTML — 텍스트 자리 {'{{빈칸}}'}, 이미지 자리 &lt;img data-field="빈칸"&gt;</label>
                      <textarea className="mono" rows={12} value={design.html || ''} onChange={(e) => update((s) => { s.design.html = e.target.value; })} spellCheck={false} />
                      <label className="fstudio-code-label">CSS — 색은 var(--fs-primaryColor) 형태의 테마 변수로</label>
                      <textarea className="mono" rows={12} value={design.css || ''} onChange={(e) => update((s) => { s.design.css = e.target.value; })} spellCheck={false} />
                    </>
                  )}
                  {!showCode && <p className="fstudio-hint">코드(HTML/CSS) 기반 디자인입니다 — 위 체크박스로 코드를 열거나, 새 캔버스 포맷은 "열기 · 프리셋 → 빈 디자인 포맷"으로 시작하세요.</p>}
                </div>
              </div>
            )}
          </div>
        </main>

        {/* ── Inspector (우) ── */}
        <aside className="properties-panel" aria-label="속성">
          {isAssistantOpen && (
            <div className="fsp-ai-panel">
              <div className="fsp-ai-head"><Sparkles size={14} /> AI 포맷 생성 <button type="button" className="fstudio-close" onClick={() => setIsAssistantOpen(false)} aria-label="닫기"><X size={14} /></button></div>
              <div className="fstudio-ai">
                <select value={aiLayout} onChange={(e) => setAiLayout(e.target.value)} aria-label="생성 종류">
                  <option value="">자동</option><option value="document">문서</option><option value="design">포스터·팜플렛</option>
                </select>
                <input value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)}
                       onKeyDown={(e) => { if (e.key === 'Enter') generate(); }}
                       placeholder='예: "주간 업무 보고서 양식"' />
                <button type="button" onClick={generate} disabled={aiLoading}>
                  {aiLoading ? <Loader2 size={15} className="fstudio-spin" /> : <Sparkles size={15} />} 생성
                </button>
              </div>
              <p className="fstudio-hint">생성된 골격이 초안으로 로드됩니다 — 지금 작업을 대체합니다.</p>
            </div>
          )}

          <div className="ab-inspector-head">
            <span className="ab-type-tile">
              {selectedElement ? ((ELEMENT_ICONS[selectedElement.kind] || Type) && (() => { const HeadIcon = ELEMENT_ICONS[selectedElement.kind] || Type; return <HeadIcon size={16} />; })()) : <Monitor size={16} />}
            </span>
            <div className="ab-inspector-title">
              <strong>{selectedElement ? ELEMENT_NAMES[selectedElement.kind] : (spec.name || '포맷')}</strong>
              <span className="ab-inspector-id">
                <span>
                  {selectedElement
                    ? `${Math.round(selectedElement.x)}, ${Math.round(selectedElement.y)} · ${Math.round(selectedElement.w)}×${Math.round(selectedElement.h)}`
                    : isDocument ? `문서 · 블록 ${(spec.blocks || []).length}` : `${design.width || 794} × ${design.height || 1123}`}
                </span>
              </span>
            </div>
          </div>

          {hasCanvas && (
            <InspectorSection title="요소 속성" meta={selectedElement ? ELEMENT_NAMES[selectedElement.kind] : '선택 없음'}
                              open={openSections.element !== false} onToggle={() => toggleSection('element')}>
              <div ref={setPropsEl} />
            </InspectorSection>
          )}

          <InspectorSection title={isDocument ? '포맷' : '포맷 · 테마'} open={openSections.format !== false} onToggle={() => toggleSection('format')}>
            <div className="fstudio-name-row">
              <input value={spec.name} onChange={(e) => update((s) => { s.name = e.target.value; })} placeholder="포맷 이름" />
              <span className={`fstudio-layout-badge ${spec.layout}`}>{isDocument ? '문서' : '디자인'}</span>
            </div>
            {!isDocument && (
              <div className="fstudio-theme-grid">
                {['primaryColor', 'backgroundColor', 'textColor', 'mutedColor'].map((key) => (
                  <label key={key}>
                    <span>{{ primaryColor: '주 색', backgroundColor: '배경', textColor: '글자', mutedColor: '보조 글자' }[key]}</span>
                    <input type="color" value={design.theme?.[key] || '#888888'}
                           onChange={(e) => update((s) => { s.design.theme = { ...(s.design.theme || {}), [key]: e.target.value }; })} />
                  </label>
                ))}
                <label><span>글꼴</span>
                  <input type="text" value={design.theme?.fontFamily || ''} placeholder="Pretendard"
                         onChange={(e) => update((s) => { s.design.theme = { ...(s.design.theme || {}), fontFamily: e.target.value }; })} />
                </label>
              </div>
            )}
          </InspectorSection>

          <InspectorSection title="빈칸 (fields)" meta={`${(spec.fields || []).length}개`}
                            open={openSections.fields !== false} onToggle={() => toggleSection('fields')}>
            <FieldsEditor spec={spec} addField={addField} setField={setField} removeField={removeField} />
          </InspectorSection>

          <InspectorSection title="구조 미리보기" meta="예시값"
                            open={openSections.preview !== false} onToggle={() => toggleSection('preview')}>
            {isDocument ? <DocumentPreview spec={spec} /> : <DesignPreview spec={spec} maxWidth={300} />}
          </InspectorSection>
        </aside>
      </div>

      {notice && <div className={`fsp-toast ${notice.tone}`} role="status">{notice.text}</div>}

      {pickerOpen && (
        <div className="fstudio-picker-backdrop" onClick={() => setPickerOpen(false)}>
          <div className="fstudio-picker" role="dialog" aria-label="열기·프리셋" onClick={(e) => e.stopPropagation()}>
            <div className="fstudio-picker-head">
              <strong><FolderOpen size={15} /> 열기 · 프리셋</strong>
              <button type="button" className="fstudio-close" onClick={() => setPickerOpen(false)} aria-label="닫기"><X size={16} /></button>
            </div>
            <div className="fstudio-picker-body">
              <span className="fstudio-side-label">새로 만들기</span>
              <div className="fstudio-picker-grid">
                <button type="button" onClick={() => openFormat(() => { setSpec(emptySpec('document')); setLibraryId(''); })}>빈 문서 포맷</button>
                <button type="button" onClick={() => openFormat(() => { setSpec(emptySpec('design')); setLibraryId(''); })}>빈 디자인 포맷</button>
                <button type="button" disabled={importing} onClick={() => importInputRef.current?.click()}>
                  {importing ? <Loader2 size={13} className="fstudio-spin" /> : <FileUp size={13} />} 파일에서 가져오기<em>.hwpx·.docx</em>
                </button>
              </div>
              {userFormats.length > 0 && (
                <>
                  <span className="fstudio-side-label">내 포맷</span>
                  <div className="fstudio-picker-grid">
                    {userFormats.map((f) => (
                      <button key={f.id} type="button"
                              onClick={() => openFormat(() => { setSpec(cloneSpec({ ...f.spec, name: f.name })); setLibraryId(f.id); })}>
                        {f.name}<em>{f.layout === 'design' ? '디자인' : '문서'}</em>
                      </button>
                    ))}
                  </div>
                </>
              )}
              <span className="fstudio-side-label">프리셋 {presets.length}종 — 복제해서 시작</span>
              <div className="fstudio-picker-grid">
                {presets.map((p) => (
                  <button key={p.id} type="button"
                          onClick={() => openFormat(() => { const c = cloneSpec(p); delete c.id; c.name = `${p.name} (복제)`; setSpec(c); setLibraryId(''); })}>
                    {p.name}<em>{p.layout === 'design' ? '디자인' : '문서'}</em>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <input ref={uploadInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={uploadImage} />
      <input ref={importInputRef} type="file" accept=".hwpx,.docx" style={{ display: 'none' }}
             onChange={async (e) => { if (await importFromFile(e)) { setPickerOpen(false); setActiveTab('design'); } }} />
    </div>
  );
}
