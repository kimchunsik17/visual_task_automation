import { COMPONENT_DEFAULT_SIZES } from './appBuilderSchema.js';

/**
 * 앱 빌더 컴포넌트 카탈로그 — 팔레트, 계층 트리 아이콘, 새 컴포넌트의 기본 props 가 모두
 * 이 목록 하나에서 나온다. 예전에는 팔레트(JSX 10줄), 계층 아이콘(if 9개), createNewComponent
 * (else-if 사슬) 세 곳에 같은 목록이 흩어져 있어서, 컴포넌트 하나를 더하려면 세 곳을 같이
 * 고쳐야 했고 하나를 빼먹으면 계층 트리에 아이콘 없는 항목이 생겼다(file 이 그랬다).
 *
 * icon 은 커스텀 아이콘 이름(assets/icons/ui/ui-*.svg)이고, 커스텀 아이콘이 아직 없는 타입은
 * lucide 로 표시한다 — AppBuilderPage 의 LUCIDE_FALLBACKS 가 이름을 컴포넌트로 바꾼다.
 */
export const COMPONENT_CATEGORIES = Object.freeze([
  { id: 'layout', label: '레이아웃' },
  { id: 'input', label: '입력' },
  { id: 'action', label: '동작' },
  { id: 'display', label: '표시 · 출력' },
]);

export const COMPONENT_CATALOG = Object.freeze([
  { type: 'container', label: 'Container (Div)', category: 'layout', icon: 'ui-container',
    keywords: ['div', '박스', '그룹', 'layout'] },
  { type: 'divider', label: 'Divider', category: 'layout', icon: 'ui-divider',
    keywords: ['구분선', 'line', 'hr'] },

  { type: 'input', label: 'Input Field', category: 'input', icon: 'ui-input',
    keywords: ['텍스트', '입력', 'number', 'email', 'password', 'date'] },
  { type: 'textarea', label: 'Text Area', category: 'input', icon: 'ui-textarea',
    keywords: ['여러 줄', '입력', '결과'] },
  { type: 'dropdown', label: 'Dropdown', category: 'input', icon: 'ui-dropdown',
    keywords: ['select', '선택', '목록'] },
  { type: 'checkbox', label: 'Checkbox', category: 'input', icon: 'ui-checkbox',
    keywords: ['체크', '토글', 'boolean'] },
  { type: 'radio', label: 'Radio Group', category: 'input', lucide: 'CircleDot',
    keywords: ['라디오', '단일 선택', 'option'] },
  { type: 'slider', label: 'Slider', category: 'input', lucide: 'SlidersHorizontal',
    keywords: ['범위', 'range', '숫자', '슬라이더'] },
  { type: 'file', label: '파일 업로드', category: 'input', lucide: 'FileUp', accent: '#0ea5e9',
    keywords: ['upload', '문서', '영상', '첨부'] },

  { type: 'button', label: 'Button', category: 'action', icon: 'ui-button',
    keywords: ['버튼', '실행', '클릭', 'submit'] },
  { type: 'link', label: 'Link', category: 'action', lucide: 'Link2',
    keywords: ['링크', 'url', 'anchor', '바로가기'] },

  { type: 'text', label: 'Text', category: 'display', icon: 'ui-text',
    keywords: ['제목', '문구', 'heading', 'label'] },
  { type: 'image', label: 'Image', category: 'display', icon: 'ui-image',
    keywords: ['이미지', '사진', 'img'] },
  { type: 'markdown', label: 'Markdown', category: 'display', lucide: 'FileCode',
    keywords: ['마크다운', '결과', 'LLM', '서식', 'output'] },
  { type: 'table', label: 'Table', category: 'display', lucide: 'Table2',
    keywords: ['표', '테이블', 'json', '목록', 'output'] },
  { type: 'progress', label: 'Progress Bar', category: 'display', lucide: 'Gauge',
    keywords: ['진행', '퍼센트', '게이지', 'output'] },
]);

const CATALOG_BY_TYPE = Object.fromEntries(COMPONENT_CATALOG.map((entry) => [entry.type, entry]));

export const catalogEntry = (type) => CATALOG_BY_TYPE[type] || null;

export const filterCatalog = (query = '') => {
  const needle = String(query || '').trim().toLowerCase();
  if (!needle) return COMPONENT_CATALOG;
  return COMPONENT_CATALOG.filter((entry) => (
    entry.type.includes(needle)
      || entry.label.toLowerCase().includes(needle)
      || (entry.keywords || []).some((keyword) => keyword.toLowerCase().includes(needle))
  ));
};

/**
 * 타입별 기본 props. position 과 style.width/height 는 호출한 쪽(createNewComponent)이 채운다.
 * stamp 는 inputKey 가 서로 겹치지 않게 하는 접미사다.
 */
export const defaultPropsFor = (type, stamp = Date.now()) => {
  switch (type) {
    case 'container':
      return { layoutMode: 'absolute', style: { padding: '1rem', border: '1px solid #cbd5e1', borderRadius: '4px' } };
    case 'text':
      return { text: 'New Text' };
    case 'button':
      return { text: 'Click Me' };
    case 'input':
      return { label: 'Label', placeholder: 'Type here...', inputType: 'text', inputKey: `input_${stamp}` };
    case 'textarea':
      return { label: 'Label', placeholder: 'Type multiline text here...', inputKey: `textarea_${stamp}` };
    case 'dropdown':
      return { label: 'Select Option', options: 'Option 1, Option 2, Option 3', inputKey: `dropdown_${stamp}` };
    case 'checkbox':
      return { label: 'Check me', inputKey: `checkbox_${stamp}` };
    case 'radio':
      return { label: '하나를 선택하세요', options: 'Option A, Option B, Option C', direction: 'column', inputKey: `radio_${stamp}` };
    case 'slider':
      return { label: '값', min: 0, max: 100, step: 1, defaultValue: 50, showValue: true, inputKey: `slider_${stamp}` };
    case 'file':
      // 'document' | 'video' — 서버의 용도별 허용 목록(purpose)과 짝이다(ADR-0010).
      return { label: '파일 업로드', fileKind: 'document', inputKey: `file_${stamp}` };
    case 'image':
      return { imageUrl: 'https://via.placeholder.com/150' };
    case 'link':
      return { text: '자세히 보기', href: 'https://', openInNewTab: true };
    // markdown/table 은 기본 내용을 비워 둔다 — 배포된 앱에 예시 문구가 남지 않도록. 편집
    // 화면에서는 UIEngine 이 안내 문구/예시 행을 대신 그린다.
    case 'markdown':
      return { text: '' };
    case 'table':
      return { text: '', columns: '', emptyText: '표시할 데이터가 없습니다.' };
    case 'progress':
      return { label: '진행률', value: 40, max: 100, showValue: true, style: { color: '#3b82f6' } };
    case 'divider':
      return { style: { backgroundColor: '#cbd5e1' } };
    default:
      return {};
  }
};

export const defaultSizeFor = (type) => COMPONENT_DEFAULT_SIZES[type] || { width: 200, height: 45 };
