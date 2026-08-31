/**
 * 커스텀 아이콘 로더.
 *
 * assets/icons/ 아래 .svg 파일이 단일 소스다. 파일을 추가하면 자동으로 등록되므로
 * 이 파일을 고칠 필요가 없다. (Vite 의 import.meta.glob — 빌드 타임에 인라인됨)
 *
 * lucide-react 와 동일한 props 시그니처(size / color)를 쓰므로 교체가 1:1로 된다.
 *   <UserCheck size={16} color="#f43f5e" />
 *   <Icon name="node-human-approval" size={16} color="#f43f5e" />
 *
 * 아이콘 사양과 생성 프롬프트: Documents/icon-generation-prompts.md
 * 품질 검증:                  python3 Documents/build-icon-qa.py
 */
const sources = import.meta.glob('../assets/icons/**/*.svg', {
  query: '?raw',
  import: 'default',
  eager: true,
});

// <svg> 래퍼를 벗기고 내부 도형만 보관한다. 래퍼는 아래 Icon 이 직접 그린다 —
// 그래야 size/color 를 React props 로 제어할 수 있다.
const shapes = {};
for (const [path, source] of Object.entries(sources)) {
  const name = path.slice(path.lastIndexOf('/') + 1, -4);
  shapes[name] = source
    .replace(/^[\s\S]*?<svg[^>]*>/, '')
    .replace(/<\/svg>\s*$/, '')
    .trim();
}

export const hasIcon = (name) => Object.prototype.hasOwnProperty.call(shapes, name);

export const iconNames = Object.keys(shapes).sort();

/**
 * @param {string} name   assets/icons 아래 파일명 (확장자 없이). 예: 'node-slack'
 * @param {number} size   픽셀. lucide 와 동일하게 width/height 에 함께 적용
 * @param {string} color  없으면 부모 CSS color 를 상속한다.
 *                        stroke="currentColor" 와 fill="currentColor"(강조 요소)가
 *                        모두 이 값으로 해석되도록 style.color 로 넘긴다.
 */
export function Icon({ name, size = 24, color, className, style, ...rest }) {
  const body = shapes[name];

  if (body === undefined) {
    if (import.meta.env.DEV) {
      console.warn(`[Icon] '${name}' 없음. 사용 가능: ${iconNames.join(', ')}`);
    }
    return null;
  }

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={color ? { color, ...style } : style}
      aria-hidden="true"
      // 빌드 타임에 인라인되는 자체 애셋이다 (외부/사용자 입력이 아님).
      dangerouslySetInnerHTML={{ __html: body }}
      {...rest}
    />
  );
}

export default Icon;
