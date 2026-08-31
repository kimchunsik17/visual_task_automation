// 데이터 레이어 오버레이 (계획 DATA_FLOW_SEPARATION_PLAN §5-2·5-3).
//
// 바인딩의 정본은 노드 data 이므로 **선을 그리지 않는 것이 기본**이다. 이 컴포넌트는
// 필요할 때만 켜는 렌즈다 — 전체 토글(D)이거나, 선택한 노드가 주고받는 것만 보는 로컬 렌즈.
//
// 실행 엣지(굵은 실선)와 시각 언어를 분리한다: 얇은 점선 + 소스 노드 색.
import { useEffect, useMemo, useState } from 'react';
import { ViewportPortal, useStore } from '@xyflow/react';
import { getEditorNodeMeta } from '../editorNodeCatalog';
import { bindingLinks } from '../nodeBindings';
import './DataLayerOverlay.css';

// 흐름 방향을 보여주는 점선 애니메이션은 선이 몇 개일 때만 켠다.
// 측정(2026-08-31, 노드 51개·바인딩 100개): 100개 전부 애니메이션하면 노드 드래그가
// 13.4초/15fps 였고, 애니메이션만 끄면 8.0초/38fps 로 레이어를 끈 상태와 거의 같아졌다.
// 비용은 rect 측정이나 리렌더가 아니라 SVG 100개의 무한 애니메이션 자체였다.
const ANIMATION_MAX_LINKS = 24;

const nodeElement = (id) => document.querySelector(`.react-flow__node[data-id="${id}"]`);

/** 칩(=필드 위치)의 노드 기준 오프셋을 흐름 좌표로 환산한다. 화면 rect / zoom. */
const fieldOffset = (nodeId, field, zoom) => {
  const el = nodeElement(nodeId);
  if (!el) return null;
  const chip = el.querySelector(`[data-fbind-anchor="${nodeId}:${field}"]`);
  if (!chip) return null;
  const nodeRect = el.getBoundingClientRect();
  const chipRect = chip.getBoundingClientRect();
  if (!nodeRect.height || !chipRect.height) return null;
  return (chipRect.top + chipRect.height / 2 - nodeRect.top) / (zoom || 1);
};

const size = (node) => ({
  width: node?.measured?.width || node?.width || 220,
  height: node?.measured?.height || node?.height || 44,
});

export default function DataLayerOverlay({ nodes, enabled }) {
  const zoom = useStore((state) => state.transform[2]);
  const [geometry, setGeometry] = useState([]);

  const links = useMemo(() => bindingLinks(nodes), [nodes]);

  // 로컬 렌즈: 토글이 꺼져 있어도 선택한 노드가 주고받는 바인딩은 보여준다(§5-3).
  const selected = useMemo(
    () => new Set((nodes || []).filter((n) => n.selected).map((n) => String(n.id))),
    [nodes],
  );

  const visible = useMemo(() => (
    enabled ? links : links.filter((l) => selected.has(l.source) || selected.has(l.target))
  ), [enabled, links, selected]);

  useEffect(() => {
    if (visible.length === 0) {
      setGeometry((prev) => (prev.length ? [] : prev));
      return undefined;
    }
    const byId = new Map((nodes || []).map((n) => [String(n.id), n]));
    // 노드 DOM 이 그려진 뒤에 재야 한다 — 펼침/접힘 직후 프레임에서는 칩이 아직 없다.
    const frame = requestAnimationFrame(() => {
      const next = [];
      visible.forEach((link) => {
        const source = byId.get(link.source);
        const target = byId.get(link.target);
        if (!source || !target) return;
        const sourceSize = size(source);
        const sx = (source.position?.x || 0) + sourceSize.width;
        const sy = (source.position?.y || 0) + sourceSize.height / 2;
        const offset = fieldOffset(link.target, link.field, zoom);
        // 도착점은 항상 노드 왼쪽 경계다 — 선이 노드 뒤에 있으므로 안쪽으로 들어가면 가려진다.
        // 접힌 노드는 필드 포트를 그리지 않으니(§5-4) 세로 위치만 노드 중앙으로 떨어진다.
        const tx = target.position?.x || 0;
        const ty = (target.position?.y || 0) + (offset == null ? size(target).height / 2 : offset);
        const bend = Math.max(36, Math.abs(tx - sx) * 0.42);
        next.push({
          id: link.id,
          color: getEditorNodeMeta(source.type).color || '#60a5fa',
          d: `M ${sx},${sy} C ${sx + bend},${sy} ${tx - bend},${ty} ${tx},${ty}`,
          tx,
          ty,
        });
      });
      setGeometry(next);
    });
    return () => cancelAnimationFrame(frame);
  }, [visible, nodes, zoom]);

  if (geometry.length === 0) return null;

  return (
    <ViewportPortal>
      <svg className={`data-layer-svg ${geometry.length <= ANIMATION_MAX_LINKS ? 'is-animated' : ''}`}
           width="1" height="1" aria-hidden="true">
        {geometry.map((item) => (
          <g key={item.id}>
            <path className="data-layer-link" d={item.d} stroke={item.color} />
            <circle className="data-layer-end" cx={item.tx} cy={item.ty} r="3.5" fill={item.color} />
          </g>
        ))}
      </svg>
    </ViewportPortal>
  );
}
