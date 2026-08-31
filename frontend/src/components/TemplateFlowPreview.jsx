// 소개 페이지의 워크플로우 구조 미리보기.
//
// 가져오기 전에 "몇 단계이고 어디서 갈라지는가" 를 보려는 것이라, 캔버스를 그대로 축소하지
// 않고 **연결 구조만** 그린다. 값도 설정도 그리지 않는다.
//
// 좌표는 서버가 준 실제 배치를 그대로 쓴다(열 470px · 행 280px 격자). 새로 배치하면 캔버스에서
// 볼 모습과 달라져서, 가져온 뒤 "그림과 다르다" 가 된다.
import { useMemo } from 'react';
import { getEditorNodeMeta } from '../editorNodeCatalog';
import './TemplateFlowPreview.css';

const COL = 168;      // 미리보기 한 열 폭 (캔버스 470px 에 대응)
const ROW = 82;       // 미리보기 한 행 높이 (캔버스 280px 에 대응)
const BOX_W = 132;
const BOX_H = 46;
const PAD = 16;

// 갈래 이름은 그대로 두면 뜻이 안 통한다.
const HANDLE_LABEL = {
  done: '완료', true: '참', false: '거짓', else: '아니면', skip: '건너뜀',
  loop_start: '반복 시작', tools: '도구', template: '서식',
  approved: '승인', rejected: '거절',
};

export default function TemplateFlowPreview({ outline }) {
  const model = useMemo(() => {
    const nodes = outline?.nodes || [];
    if (!nodes.length) return null;
    const minX = Math.min(...nodes.map((n) => n.x));
    const minY = Math.min(...nodes.map((n) => n.y));
    const placed = new Map();
    nodes.forEach((node) => {
      placed.set(node.id, {
        ...node,
        px: PAD + ((node.x - minX) / 470) * COL,
        py: PAD + ((node.y - minY) / 280) * ROW,
        meta: getEditorNodeMeta(node.type),
      });
    });
    const list = [...placed.values()];
    return {
      nodes: list,
      edges: (outline?.edges || [])
        .map((e) => ({ ...e, from: placed.get(e.source), to: placed.get(e.target) }))
        .filter((e) => e.from && e.to),
      width: Math.max(...list.map((n) => n.px)) + BOX_W + PAD,
      height: Math.max(...list.map((n) => n.py)) + BOX_H + PAD + 46,   // 아래로 우회한 선 자리
    };
  }, [outline]);

  if (!model) return null;

  return (
    <div className="tplflow">
      <div className="tplflow-scroll">
        <svg width={model.width} height={model.height}
             viewBox={`0 0 ${model.width} ${model.height}`}
             role="img" aria-label="워크플로우 연결 구조">
          <defs>
            <marker id="tplflow-arrow" viewBox="0 0 8 8" refX="7" refY="4"
                    markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
            </marker>
          </defs>

          {model.edges.map((edge) => {
            const x1 = edge.from.px + BOX_W;
            const y1 = edge.from.py + BOX_H / 2;
            const x2 = edge.to.px;
            const y2 = edge.to.py + BOX_H / 2;
            const bend = Math.max(18, Math.abs(x2 - x1) / 2);
            const label = HANDLE_LABEL[edge.handle] || edge.handle;
            // 한 칸을 넘어가는 선(반복의 '완료' 가 대표적)은 **아래로 우회시킨다**. 곧게 그으면
            // 사이에 낀 노드 상자 뒤로 숨어서, 이어져 있는데도 끊긴 것처럼 보인다.
            const isLong = x2 - x1 > COL * 1.2;
            // 제어점을 **행 아래로 깊게** 내리고 가로 오프셋은 짧게 준다. 그래야 중간 노드
            // 아래로 지나간 뒤 목표 바로 앞에서 가파르게 올라와, 상자에 가려지는 구간이 없다.
            const low = Math.max(y1, y2) + BOX_H * 1.15;
            // 곡선을 목표 **조금 앞**에서 끝내고 마지막 18px 만 가로 직선으로 붙인다 —
            // 곡선이 그대로 꽂히면 화살촉이 비스듬히 돌아가 어느 쪽으로 가는 선인지 헷갈린다.
            const path = isLong
              ? `M${x1},${y1} C${x1 + 40},${low} ${x2 - 62},${low} ${x2 - 18},${y2} L${x2},${y2}`
              : `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`;
            return (
              <g key={`${edge.source}-${edge.target}-${edge.handle}`} className="tplflow-edge">
                <path d={path} fill="none" markerEnd="url(#tplflow-arrow)" />
                {label && (
                  <text x={(x1 + x2) / 2} y={isLong ? low - 2 : (y1 + y2) / 2 - 5}
                        textAnchor="middle" className="tplflow-edge-label">{label}</text>
                )}
              </g>
            );
          })}

          {model.nodes.map((node) => (
            <g key={node.id} className="tplflow-node">
              <rect x={node.px} y={node.py} width={BOX_W} height={BOX_H} rx="9" />
              {/* 왼쪽 색 띠로 종류를 구분한다 — 캔버스의 노드 색과 같은 값이다. */}
              <rect x={node.px} y={node.py} width="4" height={BOX_H} rx="2"
                    fill={node.meta.color} />
              <text x={node.px + 14} y={node.py + BOX_H / 2 + 4} className="tplflow-node-label">
                {node.meta.label.length > 13 ? `${node.meta.label.slice(0, 12)}…` : node.meta.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
      {outline?.truncated && (
        <p className="tplflow-note">노드가 많아 앞부분만 표시했습니다. 가져오면 전체를 볼 수 있어요.</p>
      )}
    </div>
  );
}
