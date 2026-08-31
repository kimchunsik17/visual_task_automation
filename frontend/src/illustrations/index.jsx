/**
 * 빈 상태 일러스트 로더.
 *
 * assets/illustrations/ 아래 .svg 가 단일 소스다. 파일을 추가하면 자동 등록되므로
 * 이 파일을 고칠 필요가 없다. (icons/index.jsx 와 같은 import.meta.glob 방식)
 *
 * icons/index.jsx 를 재사용하지 않고 따로 둔 이유:
 *   - 아이콘 로더는 viewBox="0 0 24 24" / stroke-width="2" 를 <svg> 래퍼에 하드코딩한다.
 *     일러스트는 4:3(320×240) 그리드에 stroke-width 3.2 라 그 래퍼에 담기지 않는다.
 *   - 아이콘은 size(px) 정사각 고정, 일러스트는 폭 100% + max-width 로 반응형 축소된다.
 *   - glob 경로도 assets/icons/** 밖이라 아이콘 세트의 QA 스크립트 대상과 섞이지 않는다.
 *
 * 사양과 생성 근거: Documents/icon-empty-states.md
 */
const sources = import.meta.glob('../assets/illustrations/*.svg', {
  query: '?raw',
  import: 'default',
  eager: true,
});

// <svg> 래퍼를 벗기고 내부 도형만 보관한다. 래퍼는 아래 Illustration 이 직접 그린다 —
// 그래야 폭과 색을 React/CSS 로 제어할 수 있다.
const arts = {};
for (const [path, source] of Object.entries(sources)) {
  const name = path.slice(path.lastIndexOf('/') + 1, -4);
  arts[name] = {
    viewBox: /viewBox="([^"]+)"/.exec(source)?.[1] ?? '0 0 320 240',
    body: source
      .replace(/^[\s\S]*?<svg[^>]*>/, '')
      .replace(/<\/svg>\s*$/, '')
      .trim(),
  };
}

export const illustrationNames = Object.keys(arts).sort();

/**
 * 세트 공통 획 굵기. viewBox 320 폭을 200px 로 표시할 때 화면에서 2px 로 보이는 값이다
 * (2 ÷ (200/320) = 3.2). 세 일러스트가 같은 굵기로 보이도록 여기 한 곳에서만 정한다.
 */
export const ILLUSTRATION_STROKE = 3.2;

/**
 * @param {string} name   assets/illustrations 아래 파일명 (확장자 없이). 예: 'empty-workflows'
 * @param {number} width  최대 표시 폭(px). 부모가 좁으면 그만큼 함께 줄어든다.
 *                        본체는 currentColor 라 부모 CSS color 를 상속하고,
 *                        액센트(파랑/보라/에메랄드)만 SVG 안에서 HEX 로 고정돼 있다.
 */
export function Illustration({ name, width = 200, className, style, ...rest }) {
  const art = arts[name];

  if (art === undefined) {
    if (import.meta.env.DEV) {
      console.warn(`[Illustration] '${name}' 없음. 사용 가능: ${illustrationNames.join(', ')}`);
    }
    return null;
  }

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={art.viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth={ILLUSTRATION_STROKE}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ display: 'block', width: '100%', maxWidth: `${width}px`, height: 'auto', ...style }}
      aria-hidden="true"
      // 빌드 타임에 인라인되는 자체 애셋이다 (외부/사용자 입력이 아님).
      dangerouslySetInnerHTML={{ __html: art.body }}
      {...rest}
    />
  );
}

export default Illustration;
