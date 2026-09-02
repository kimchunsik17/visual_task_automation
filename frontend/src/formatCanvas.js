// formatCanvas.js — 디자인 포맷 캔버스 편집의 정본 모델과 직렬화기 (React 를 모른다).
//
// 캔버스 편집기의 정본은 design.elements(요소 목록)다. 렌더러(백엔드 poster_generator)는
// html/css 만 알기 때문에, 요소가 바뀔 때마다 여기 serializeElements 로 html/css 를 다시
// 만들어 design.html/design.css 에 함께 저장한다 — 저장된 포맷은 백엔드 수정 없이 그대로
// 렌더되고(validate_format_spec 은 여분 키 design.elements 를 보존한다), elements 가 없는
// 포맷(AI 생성·수기 코드)은 기존 테마/코드 편집기로 열린다.
//
// 요소 좌표는 아트보드 픽셀(design.width×height 기준)이다. 렌더는 정확히 그 크기의
// 뷰포트에서 일어나므로(page.pdf/screenshot) 캔버스에서 본 위치 = 산출물 위치가 보장된다.

// 텍스트 색은 테마 키(테마만 바꿔 분위기를 바꿀 수 있게)가 기본, 직접 지정한 hex 도 허용.
export const COLOR_KEYS = ['textColor', 'primaryColor', 'mutedColor'];

const cssColor = (color) => {
  if (!color) return 'var(--fs-textColor)';
  if (COLOR_KEYS.includes(color)) return `var(--fs-${color})`;
  return String(color);
};

const escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const round = (value) => Math.round(Number(value) || 0);

let elementSeq = 0;
export const nextElementId = () => `el_${Date.now().toString(36)}_${(elementSeq += 1)}`;

export const newTextElement = (overrides = {}) => ({
  id: nextElementId(),
  kind: 'text',
  text: '텍스트',
  x: 60, y: 60, w: 320, h: 60,
  fontSize: 20,
  bold: false,
  align: 'left',
  color: 'textColor',
  lineHeight: 1.45,
  ...overrides,
});

export const newImageElement = (field, overrides = {}) => ({
  id: nextElementId(),
  kind: 'image',
  field,
  x: 60, y: 60, w: 320, h: 220,
  radius: 12,
  ...overrides,
});

// 장식용 사각형(상장 테두리 등). 텍스트를 갖지 않는다.
export const newBoxElement = (overrides = {}) => ({
  id: nextElementId(),
  kind: 'box',
  x: 40, y: 40, w: 300, h: 200,
  borderColor: 'primaryColor',
  borderWidth: 2,
  background: '',
  radius: 0,
  ...overrides,
});

/**
 * elements → { html, css }.
 *
 * 텍스트 요소의 내용은 이스케이프한다 — 사용자가 캔버스에 적은 '<b>' 가 마크업이 되면 안 된다.
 * `{{field}}` 참조는 괄호가 이스케이프 대상이 아니라 그대로 살아남고, 실행 시 백엔드가 값을
 * (다시 이스케이프해서) 치환한다.
 */
export const serializeElements = (elements) => {
  const parts = [];
  const rules = [
    '.cv{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden;'
    + 'background:var(--fs-backgroundColor);color:var(--fs-textColor);}',
    '.cv .e{position:absolute;box-sizing:border-box;margin:0;white-space:pre-wrap;word-break:keep-all;}',
  ];
  (elements || []).forEach((el, index) => {
    const cls = `e${index + 1}`;
    const decl = [
      `left:${round(el.x)}px`, `top:${round(el.y)}px`,
      `width:${round(el.w)}px`, `height:${round(el.h)}px`,
    ];
    if (el.kind === 'image') {
      parts.push(`<img data-field="${el.field}" class="e ${cls}">`);
      decl.push('object-fit:cover');
      if (el.radius) decl.push(`border-radius:${round(el.radius)}px`);
    } else if (el.kind === 'box') {
      parts.push(`<div class="e ${cls}"></div>`);
      decl.push(`border:${round(el.borderWidth) || 1}px solid ${cssColor(el.borderColor || 'primaryColor')}`);
      if (el.background) decl.push(`background:${cssColor(el.background)}`);
      if (el.radius) decl.push(`border-radius:${round(el.radius)}px`);
    } else {
      parts.push(`<div class="e ${cls}">${escapeHtml(el.text)}</div>`);
      decl.push(`font-size:${round(el.fontSize) || 16}px`);
      decl.push(`font-weight:${el.bold ? 700 : 400}`);
      decl.push(`text-align:${el.align || 'left'}`);
      decl.push(`color:${cssColor(el.color)}`);
      decl.push(`line-height:${Number(el.lineHeight) || 1.45}`);
      if (el.letterSpacing) decl.push(`letter-spacing:${el.letterSpacing}`);
    }
    rules.push(`.cv .${cls}{${decl.join(';')};}`);
  });
  return {
    html: `<div class="cv">${parts.join('')}</div>`,
    css: rules.join('\n'),
  };
};

/** 요소가 바뀐 design 을 받아 html/css 를 재직렬화한 새 design 을 돌려준다. */
export const withSerialized = (design) => {
  const { html, css } = serializeElements(design.elements || []);
  return { ...design, html, css };
};

/** 빈 캔버스 시작점 — 제목 요소 하나를 가운데 얹는다. */
export const emptyCanvasDesign = (width = 794, height = 1123, theme = {}) => withSerialized({
  width, height, theme,
  elements: [newTextElement({
    text: '{{title}}', x: Math.round(width * 0.08), y: Math.round(height * 0.1),
    w: Math.round(width * 0.84), h: 80, fontSize: 44, bold: true, align: 'left',
  })],
});
