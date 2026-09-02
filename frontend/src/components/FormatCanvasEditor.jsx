// FormatCanvasEditor — 디자인 포맷(포스터·팜플렛·카드뉴스·상장)의 위치·크기 시각 편집기.
//
// 정본은 design.elements(formatCanvas.js)다. 드래그 이동·모서리 크기 조절·속성 패널 편집이
// 일어날 때마다 withSerialized 로 html/css 를 재직렬화해 부모(FormatStudio)의 spec 에 싣는다.
// 렌더러(Chromium)는 그 html/css 를 그대로 그리므로 캔버스에서 본 배치 = 산출물 배치다.
//
// 두 배치를 지원한다: 모달(기본) 은 도구줄·캔버스·속성 패널을 세로로 쌓고,
// 풀페이지 스튜디오는 selectedId/onSelect 로 선택을 밖에서 들고 hideProps 로 속성 패널을
// 우측 인스펙터(ElementPropsPanel)에 따로 그린다.
import { useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  AlignCenter, AlignLeft, AlignRight, ArrowDown, ArrowUp, Bold, Copy, Image as ImageIcon,
  Square, Trash2, Type,
} from 'lucide-react';
import {
  COLOR_KEYS, newBoxElement, newImageElement, newTextElement, nextElementId, withSerialized,
} from '../formatCanvas';
import './FormatCanvasEditor.css';

const COLOR_LABELS = { textColor: '글자색', primaryColor: '주 색', mutedColor: '보조색' };
const SNAP = 2;
const snap = (v) => Math.round(v / SNAP) * SNAP;

// 캔버스 표시용 예시값 치환 (FormatStudio 미리보기와 같은 규칙)
const substituteExamples = (text, fields) => String(text || '').replace(
  /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g,
  (raw, name) => {
    const field = (fields || []).find((f) => f.name === name);
    return field ? (field.example || field.label || field.name) : raw;
  });

const cssColorOf = (color, theme) => {
  if (!color) return theme?.textColor || '#222';
  if (COLOR_KEYS.includes(color)) return theme?.[color] || '#222';
  return color;
};

/** 선택 요소 속성 패널 — 모달에서는 캔버스 아래, 풀페이지에서는 우측 인스펙터에 그린다. */
export function ElementPropsPanel({ element, fields, theme, onPatch, onReorder, onDuplicate, onRemove }) {
  if (!element) {
    return <p className="fcv-empty-hint">요소를 클릭해 선택하면 위치·크기·글자 속성을 편집할 수 있습니다.</p>;
  }
  const imageFields = (fields || []).filter((f) => f.kind === 'image');
  const patch = (patchValues) => onPatch(element.id, patchValues);
  return (
    <div className="fcv-props">
      <div className="fcv-props-row">
        <label>X<input type="number" value={Math.round(element.x)} onChange={(e) => patch({ x: Number(e.target.value) })} /></label>
        <label>Y<input type="number" value={Math.round(element.y)} onChange={(e) => patch({ y: Number(e.target.value) })} /></label>
        <label>W<input type="number" value={Math.round(element.w)} onChange={(e) => patch({ w: Number(e.target.value) })} /></label>
        <label>H<input type="number" value={Math.round(element.h)} onChange={(e) => patch({ h: Number(e.target.value) })} /></label>
        <div className="fcv-props-actions">
          <button type="button" title="앞으로" onClick={() => onReorder(1)}><ArrowUp size={13} /></button>
          <button type="button" title="뒤로" onClick={() => onReorder(-1)}><ArrowDown size={13} /></button>
          <button type="button" title="복제" onClick={onDuplicate}><Copy size={13} /></button>
          <button type="button" title="삭제" className="danger" onClick={onRemove}><Trash2 size={13} /></button>
        </div>
      </div>

      {element.kind === 'text' && (
        <>
          <div className="fcv-props-row">
            <label>크기<input type="number" value={element.fontSize || 16}
                            onChange={(e) => patch({ fontSize: Number(e.target.value) })} /></label>
            <button type="button" className={element.bold ? 'active' : ''} title="굵게"
                    onClick={() => patch({ bold: !element.bold })}><Bold size={13} /></button>
            {[['left', AlignLeft], ['center', AlignCenter], ['right', AlignRight]].map(([align, AlignIcon]) => (
              <button key={align} type="button" className={element.align === align ? 'active' : ''} title={`정렬: ${align}`}
                      onClick={() => patch({ align })}><AlignIcon size={13} /></button>
            ))}
            <select value={COLOR_KEYS.includes(element.color) ? element.color : 'custom'}
                    onChange={(e) => patch({ color: e.target.value === 'custom' ? (theme?.textColor || '#222222') : e.target.value })}>
              {COLOR_KEYS.map((key) => <option key={key} value={key}>{COLOR_LABELS[key]}</option>)}
              <option value="custom">직접 지정</option>
            </select>
            {!COLOR_KEYS.includes(element.color) && (
              <input type="color" value={element.color || '#222222'}
                     onChange={(e) => patch({ color: e.target.value })} />
            )}
          </div>
          <textarea rows={2} value={element.text || ''} placeholder="내용 — {{빈칸}} 참조 가능"
                    onChange={(e) => patch({ text: e.target.value })} />
          <div className="fcv-props-row">
            <select className="fcv-add-select" value=""
                    onChange={(e) => { if (e.target.value) patch({ text: `${element.text || ''}{{${e.target.value}}}` }); }}>
              <option value="">내용에 빈칸 삽입…</option>
              {(fields || []).filter((f) => f.kind !== 'image' && f.kind !== 'rows').map((f) => (
                <option key={f.name} value={f.name}>{f.label || f.name}</option>
              ))}
            </select>
          </div>
        </>
      )}

      {element.kind === 'image' && (
        <div className="fcv-props-row">
          <label>빈칸
            <select value={element.field || ''} onChange={(e) => patch({ field: e.target.value })}>
              {imageFields.map((f) => <option key={f.name} value={f.name}>{f.label || f.name}</option>)}
            </select>
          </label>
          <label>둥글기<input type="number" value={element.radius || 0}
                           onChange={(e) => patch({ radius: Number(e.target.value) })} /></label>
        </div>
      )}

      {element.kind === 'box' && (
        <div className="fcv-props-row">
          <label>선 굵기<input type="number" value={element.borderWidth || 1}
                           onChange={(e) => patch({ borderWidth: Number(e.target.value) })} /></label>
          <select value={COLOR_KEYS.includes(element.borderColor) ? element.borderColor : 'primaryColor'}
                  onChange={(e) => patch({ borderColor: e.target.value })}>
            {COLOR_KEYS.map((key) => <option key={key} value={key}>{COLOR_LABELS[key]}</option>)}
          </select>
          <label>둥글기<input type="number" value={element.radius || 0}
                           onChange={(e) => patch({ radius: Number(e.target.value) })} /></label>
        </div>
      )}
    </div>
  );
}

export default function FormatCanvasEditor({
  design, fields, onDesignChange,
  selectedId: controlledSelectedId, onSelect,   // 풀페이지: 선택을 부모가 든다
  propsContainer = null,                        // 풀페이지: 속성 패널을 이 DOM 노드(우측 인스펙터)에 포털로 그린다
  maxWidth = 620,
}) {
  const [internalSelectedId, setInternalSelectedId] = useState(null);
  const isControlled = onSelect !== undefined;
  const selectedId = isControlled ? controlledSelectedId : internalSelectedId;
  const setSelectedId = (id) => (isControlled ? onSelect(id) : setInternalSelectedId(id));

  const dragRef = useRef(null); // { mode: 'move'|'resize', id, startX, startY, orig }
  const width = design.width || 794;
  const height = design.height || 1123;
  const theme = design.theme || {};
  const elements = useMemo(() => design.elements || [], [design.elements]);
  const selected = elements.find((el) => el.id === selectedId) || null;
  const imageFields = (fields || []).filter((f) => f.kind === 'image');
  const scale = Math.min(1, maxWidth / width);

  const commit = (nextElements) => onDesignChange(withSerialized({ ...design, elements: nextElements }));
  const patchElement = (id, patch) => commit(elements.map((el) => (el.id === id ? { ...el, ...patch } : el)));

  // ── 드래그 이동 / 크기 조절 ──
  const beginDrag = (event, el, mode) => {
    event.preventDefault();
    event.stopPropagation();
    setSelectedId(el.id);
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      mode, id: el.id, startX: event.clientX, startY: event.clientY,
      orig: { x: el.x, y: el.y, w: el.w, h: el.h },
    };
  };
  const onDragMove = (event) => {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = (event.clientX - drag.startX) / scale;
    const dy = (event.clientY - drag.startY) / scale;
    if (drag.mode === 'move') {
      patchElement(drag.id, {
        x: Math.max(0, Math.min(width - 12, snap(drag.orig.x + dx))),
        y: Math.max(0, Math.min(height - 12, snap(drag.orig.y + dy))),
      });
    } else {
      patchElement(drag.id, {
        w: Math.max(16, snap(drag.orig.w + dx)),
        h: Math.max(16, snap(drag.orig.h + dy)),
      });
    }
  };
  const endDrag = () => { dragRef.current = null; };

  // ── 요소 추가·정렬·삭제 (풀페이지 인스펙터도 이 핸들러를 그대로 받아 쓴다) ──
  const addElement = (el) => { commit([...elements, el]); setSelectedId(el.id); };
  const removeSelected = () => { if (selected) { commit(elements.filter((el) => el.id !== selected.id)); setSelectedId(null); } };
  const duplicateSelected = () => {
    if (!selected) return;
    addElement({ ...selected, id: nextElementId(), x: selected.x + 16, y: selected.y + 16 });
  };
  const reorderSelected = (delta) => {
    if (!selected) return;
    const index = elements.findIndex((el) => el.id === selected.id);
    const to = index + delta;
    if (to < 0 || to >= elements.length) return;
    const next = [...elements];
    const [moved] = next.splice(index, 1);
    next.splice(to, 0, moved);
    commit(next);
  };
  const onKeyDown = (event) => {
    if (!selected) return;
    const step = event.shiftKey ? 10 : 2;
    if (event.key === 'Delete' || event.key === 'Backspace') {
      if (event.target.tagName === 'TEXTAREA' || event.target.tagName === 'INPUT') return;
      event.preventDefault(); removeSelected();
    } else if (event.key.startsWith('Arrow')) {
      if (event.target.tagName === 'TEXTAREA' || event.target.tagName === 'INPUT') return;
      event.preventDefault();
      patchElement(selected.id, {
        x: selected.x + (event.key === 'ArrowRight' ? step : event.key === 'ArrowLeft' ? -step : 0),
        y: selected.y + (event.key === 'ArrowDown' ? step : event.key === 'ArrowUp' ? -step : 0),
      });
    }
  };

  const renderElement = (el) => {
    const isSelected = el.id === selectedId;
    const style = {
      left: el.x * scale, top: el.y * scale,
      width: el.w * scale, height: el.h * scale,
    };
    let body = null;
    if (el.kind === 'image') {
      body = <span className="fcv-image-slot"><ImageIcon size={14} /> {el.field}</span>;
      if (el.radius) style.borderRadius = el.radius * scale;
    } else if (el.kind === 'box') {
      style.border = `${Math.max(1, (el.borderWidth || 1) * scale)}px solid ${cssColorOf(el.borderColor || 'primaryColor', theme)}`;
      if (el.background) style.background = cssColorOf(el.background, theme);
      if (el.radius) style.borderRadius = el.radius * scale;
    } else {
      body = substituteExamples(el.text, fields);
      style.fontSize = (el.fontSize || 16) * scale;
      style.fontWeight = el.bold ? 700 : 400;
      style.textAlign = el.align || 'left';
      style.color = cssColorOf(el.color, theme);
      style.lineHeight = el.lineHeight || 1.45;
    }
    return (
      <div key={el.id}
           className={`fcv-el fcv-${el.kind} ${isSelected ? 'selected' : ''}`}
           style={style}
           onPointerDown={(e) => beginDrag(e, el, 'move')}
           onPointerMove={onDragMove}
           onPointerUp={endDrag}>
        {body}
        {isSelected && (
          <span className="fcv-resize"
                onPointerDown={(e) => beginDrag(e, el, 'resize')}
                onPointerMove={onDragMove}
                onPointerUp={endDrag} />
        )}
      </div>
    );
  };

  return (
    <div className="fcv" tabIndex={0} onKeyDown={onKeyDown}>
      <div className="fcv-toolbar">
        <button type="button" onClick={() => addElement(newTextElement({ x: 60, y: 60 }))}><Type size={13} /> 텍스트</button>
        <select className="fcv-add-select" value=""
                onChange={(e) => { if (e.target.value) addElement(newTextElement({ text: `{{${e.target.value}}}`, x: 60, y: 120 })); }}>
          <option value="">+ 빈칸 텍스트…</option>
          {(fields || []).filter((f) => f.kind !== 'image' && f.kind !== 'rows').map((f) => (
            <option key={f.name} value={f.name}>{f.label || f.name}</option>
          ))}
        </select>
        <select className="fcv-add-select" value=""
                onChange={(e) => { if (e.target.value) addElement(newImageElement(e.target.value, { x: 60, y: 200 })); }}>
          <option value="">+ 이미지 슬롯…</option>
          {imageFields.map((f) => <option key={f.name} value={f.name}>{f.label || f.name}</option>)}
        </select>
        <button type="button" onClick={() => addElement(newBoxElement({ x: 40, y: 40 }))}><Square size={13} /> 사각형</button>
        <span className="fcv-hint">드래그로 이동 · 오른쪽 아래 모서리로 크기 · 방향키 미세 이동(Shift=10px)</span>
      </div>

      <div className="fcv-stage" style={{ height: height * scale + 20 }}>
        <div className="fcv-artboard"
             style={{ width: width * scale, height: height * scale, background: theme.backgroundColor || '#fff' }}
             onPointerDown={() => setSelectedId(null)}>
          {elements.map(renderElement)}
        </div>
      </div>

      {(() => {
        const panel = (
          <ElementPropsPanel element={selected} fields={fields} theme={theme}
                             onPatch={patchElement} onReorder={reorderSelected}
                             onDuplicate={duplicateSelected} onRemove={removeSelected} />
        );
        return propsContainer ? createPortal(panel, propsContainer) : panel;
      })()}
    </div>
  );
}
