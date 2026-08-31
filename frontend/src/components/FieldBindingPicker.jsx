// 필드 데이터 바인딩 UI (계획 DATA_FLOW_SEPARATION_PLAN §5-1·5-3).
//
// 기본은 **무선**이다 — 캔버스에 선을 긋지 않고, 필드 옆 ⚡ 로 상류 노드와 경로를 고른다.
// 바인딩이 걸린 필드는 입력창 대신 소스 칩으로 바뀌어 "이 값이 어디서 오는지"를 보여준다.
import { useMemo, useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { X, Zap } from 'lucide-react';
import { getEditorNodeMeta } from '../editorNodeCatalog';
import { bindingOf, isBindableField, pathCandidates, upstreamIds, variableName } from '../nodeBindings';
import './FieldBindingPicker.css';

/** 소스 노드 표시 이름 — 변수 허브(§5-5)는 타입 라벨보다 붙인 이름이 유용하다. */
const sourceLabel = (node, meta) => {
  const name = variableName(node);
  return name ? `변수 · ${name}` : meta.label;
};

/**
 * data.bindingContext 는 EditorPage 가 주입한다:
 *   { edges, nodes, results, onBind(nodeId, field, spec|null) }
 * 컨텍스트가 없으면(앱 빌더 미리보기 등) 바인딩 UI 를 아예 그리지 않는다.
 */
export function FieldBindingControl({ id, data, nodeType, field, label }) {
  const [open, setOpen] = useState(false);
  const context = data?.bindingContext;
  const binding = bindingOf(data, field);
  // 선택 연결(required: false) — 계약에는 처음부터 있었지만 UI 가 없어서 만들 방법이 없었다.
  // 조건 분기의 한쪽에서만 값이 오는 흐름에 필요하다: 없으면 실행을 멈추지 말고 원래 값으로 둔다.
  const [optional, setOptional] = useState(binding ? binding.required === false : false);

  const upstream = useMemo(() => {
    if (!context) return [];
    const ids = upstreamIds(id, context.edges);
    return (context.nodes || [])
      .filter((node) => ids.has(String(node.id)))
      .map((node) => ({ id: String(node.id), node, meta: getEditorNodeMeta(node.type) }));
  }, [context, id]);

  if (!context || !isBindableField(nodeType, field)) return null;

  const bind = (source, path) => {
    context.onBind(id, field, optional ? { source, path, required: false } : { source, path });
    setOpen(false);
  };

  return (
    <>
      {context.dataLayer && (
        <Handle type="target" position={Position.Left} id={`bind:${field}`} className="fbind-port"
                title={`${label || field} 에 값 연결`} />
      )}
      <button
        type="button"
        className={`fbind-toggle nodrag ${binding ? 'is-bound' : ''}`}
        title={binding ? '연결된 값 바꾸기' : '앞 노드의 값과 연결'}
        onClick={(event) => { event.stopPropagation(); setOpen((v) => !v); }}
      >
        <Zap size={12} />
      </button>
      {open && (
        <div className="fbind-popover nodrag" onClick={(event) => event.stopPropagation()}>
          <div className="fbind-head">
            <strong>{label || field}</strong>에 넣을 값
            <button type="button" onClick={() => setOpen(false)} aria-label="닫기"><X size={13} /></button>
          </div>
          {upstream.length === 0 && (
            <p className="fbind-empty">앞에 연결된 노드가 없습니다. 실행 순서로 먼저 연결하세요.</p>
          )}
          {upstream.length > 0 && (
            <label className="fbind-optional" title="조건 분기로 그 노드를 지나지 않았을 때 실행을 멈추지 않습니다">
              <input type="checkbox" checked={optional} onChange={(event) => setOptional(event.target.checked)} />
              값이 없으면 비워 두고 계속
            </label>
          )}
          <div className="fbind-sources">
            {upstream.map((node) => {
              const candidates = pathCandidates(context.results?.[node.id]);
              return (
                <div key={node.id} className="fbind-source">
                  <div className="fbind-source-head">
                    <span className="fbind-dot" style={{ background: node.meta.color }} />
                    {sourceLabel(node.node, node.meta)}
                    <button type="button" onClick={() => bind(node.id, '')}>출력 전체</button>
                  </div>
                  {candidates.length > 0 ? (
                    <div className="fbind-paths">
                      {candidates.map((candidate) => (
                        <button key={candidate.path} type="button" onClick={() => bind(node.id, candidate.path)}>
                          <code>{candidate.path}</code><small>{candidate.preview}</small>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="fbind-hint">
                      한 번 실행하면 이 노드의 결과에서 경로를 골라 쓸 수 있습니다.
                      지금은 <em>출력 전체</em>만 연결할 수 있어요.
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}

/** 바인딩이 걸린 필드가 입력창 대신 보여주는 칩. */
export function FieldBindingChip({ id, data, field }) {
  const context = data?.bindingContext;
  const binding = bindingOf(data, field);
  if (!binding) return null;
  const sourceNode = (context?.nodes || []).find((node) => String(node.id) === binding.source);
  const meta = sourceNode ? getEditorNodeMeta(sourceNode.type) : null;
  return (
    <div className="fbind-chip nodrag" data-fbind-anchor={`${id}:${field}`}
         title={`${binding.source}${binding.path ? ` → ${binding.path}` : ' (출력 전체)'}`}>
      <span className="fbind-dot" style={{ background: meta?.color || 'var(--text-muted)' }} />
      <span className="fbind-chip-label">
        {(sourceNode && meta && sourceLabel(sourceNode, meta)) || binding.source}
        {binding.path && <code>{binding.path}</code>}
        {binding.required === false && <em title="값이 없으면 비워 두고 계속합니다">선택</em>}
      </span>
      {context && (
        <button type="button" aria-label="연결 해제"
                onClick={(event) => { event.stopPropagation(); context.onBind(id, field, null); }}>
          <X size={12} />
        </button>
      )}
    </div>
  );
}

/** 접힌 노드의 바인딩 개수 배지 — 포트를 그리지 않는 대신 개수만 알린다(§5-4). */
export function BindingCountBadge({ count }) {
  if (!count) return null;
  return <span className="fbind-badge" title={`연결된 값 ${count}개`}>⇣{count}</span>;
}
