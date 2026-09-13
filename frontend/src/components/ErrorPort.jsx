// error 출력 포트(ENGINE-3 2단계, ADR-0030 추기) — 노드가 오류로 끝나면 이 포트의 간선으로 흐르고 보통 하류는 건너뛴다.
//
// 노드 컴포넌트 41종을 하나씩 고치지 않고 EditorPage 의 nodeTypes 등록 지점에서 감싼다. Handle 은 React Flow 노드 래퍼
// (.react-flow__node) 안에만 있으면 되므로 컴포넌트 루트의 형제로 둔다 — 위치·색은 index.css .error-port-handle.
// 어느 노드에 포트를 둘지는 errorBranch.supportsErrorPort(백엔드 graph_traversal 의 규칙과 같다)가 정한다.
import { Handle, Position } from '@xyflow/react';

export const ERROR_PORT_TITLE = '실패 시 — 이 노드가 오류로 끝나면 이 선으로 흐르고, 보통 하류는 건너뜁니다';

export function withErrorPort(Component) {
  const WithErrorPort = (props) => (
    <>
      <Component {...props} />
      <Handle type="source" position={Position.Right} id="error" className="error-port-handle" title={ERROR_PORT_TITLE} />
    </>
  );
  WithErrorPort.displayName = `WithErrorPort(${Component.displayName || Component.name || 'Node'})`;
  return WithErrorPort;
}
