import { Illustration } from '../illustrations';
import './EmptyState.css';

/**
 * 공통 빈 상태 블록 — 일러스트 + 제목 + 한 줄 설명 + Primary action 1개.
 * (DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md §7.2)
 *
 * @param {string}  [illustration] assets/illustrations 파일명. 없으면 그림 없이 렌더한다
 *                                 (검색 결과 없음처럼 "처음부터 비어 있음"이 아닌 상태용).
 * @param {node}    title          한 줄 제목
 * @param {node}    [description]  한 줄 설명
 * @param {node}    [action]       Primary action 1개. 버튼을 그대로 넘긴다 —
 *                                 onClick 은 호출부가 갖고 있고 여기서 만들지 않는다.
 * @param {number}  [artWidth=180] 일러스트 최대 폭. 모바일에서는 CSS 가 더 줄인다.
 */
export default function EmptyState({
  illustration,
  title,
  description,
  action,
  artWidth = 180,
  className = '',
}) {
  return (
    <div className={`wf-empty ${className}`.trim()}>
      {illustration && (
        // max-width 는 이 래퍼가 갖는다. <svg> 에 인라인으로 주면 인라인 스타일이
        // 미디어 쿼리를 이겨서 모바일 축소가 먹지 않는다 (실제로 그렇게 렌더됐다).
        <div className="wf-empty__art" style={{ '--wf-empty-art': `${artWidth}px` }}>
          <Illustration name={illustration} width={artWidth} />
        </div>
      )}
      <h3 className="wf-empty__title">{title}</h3>
      {description && <p className="wf-empty__desc">{description}</p>}
      {action && <div className="wf-empty__action">{action}</div>}
    </div>
  );
}
