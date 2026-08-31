import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  GripVertical,
  Lock,
  MousePointer2,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import { useAuth } from '../AuthContext';
import { Icon } from '../icons';
import { EDITOR_NODE_CATALOG } from '../editorNodeCatalog';
import demo1 from '../assets/demo-1.webp';
import logoImg from '../logo.png';
import './IntroPage.css';

const NODE_LIBRARY = {
  scheduleNode: { label: '매일 09:00', caption: 'Trigger', icon: 'node-schedule', color: '#a78bfa' },
  webhookNode: { label: 'Webhook 수신', caption: 'Trigger', icon: 'node-webhook', color: '#38bdf8' },
  gmailTriggerNode: { label: '새 메일', caption: 'Trigger', icon: 'node-email', color: '#fb7185' },
  llmNode: { label: 'AI 분류·요약', caption: 'Intelligence', icon: 'node-llm', color: '#818cf8' },
  humanApprovalNode: { label: '담당자 승인', caption: 'Human step', icon: 'node-human-approval', color: '#f472b6' },
  googleDriveNode: { label: 'Drive 저장', caption: 'Action', icon: 'node-file-modifier', color: '#34d399' },
  discordNode: { label: '팀 채널 전송', caption: 'Action', icon: 'node-discord-send', color: '#60a5fa' },
  emailNode: { label: '이메일 발송', caption: 'Action', icon: 'node-email', color: '#fb7185' },
  slackNode: { label: 'Slack 메시지', caption: 'Action', icon: 'node-slack', color: '#0ea5e9' },
  googleSheetsNode: { label: '구글 시트', caption: 'Action', icon: 'node-google-sheets', color: '#0f9d58' },
  notionNode: { label: 'Notion 저장', caption: 'Action', icon: 'node-notion', color: '#9b9b9b' },
  youtubeTriggerNode: { label: '새 YouTube 영상', caption: 'Trigger', icon: 'node-youtube', color: '#ff0033' },
};

const PALETTE_TYPES = ['webhookNode', 'llmNode', 'humanApprovalNode', 'googleDriveNode', 'emailNode'];

const PRESETS = {
  report: {
    label: '아침 리포트',
    types: ['scheduleNode', 'llmNode', 'discordNode'],
  },
  support: {
    label: '문의 분류',
    types: ['webhookNode', 'llmNode', 'humanApprovalNode', 'emailNode'],
  },
  archive: {
    label: '문서 정리',
    types: ['gmailTriggerNode', 'llmNode', 'googleDriveNode'],
  },
};

const NODE_POSITIONS = [
  { x: 5, y: 12 },
  { x: 35, y: 48 },
  { x: 66, y: 13 },
  { x: 56, y: 60 },
];

const createPresetNodes = (presetKey) => PRESETS[presetKey].types.map((type, index) => ({
  instanceId: `${presetKey}-${index}`,
  type,
  ...NODE_POSITIONS[index],
}));

const INTEGRATION_LABELS = [...new Map(
  EDITOR_NODE_CATALOG
    .filter((meta) => (meta.category === 'integration' || meta.kind === 'trigger') && meta.icon)
    .filter((meta) => !['startNode', 'scheduleNode', 'webhookNode', 'posterGeneratorNode'].includes(meta.type))
    .map((meta) => [meta.type, {
      type: meta.type,
      label: meta.label.replace(/ \(시작\)$/, ''),
      icon: meta.icon,
      color: meta.color,
      kind: meta.kind === 'trigger' ? 'TRIGGER' : 'ACTION',
  }]),
).values()];

const INTEGRATION_LANES = Array.from({ length: 3 }, (_, laneIndex) => (
  INTEGRATION_LABELS.filter((_, index) => index % 3 === laneIndex)
));

const PRINCIPLES = [
  {
    number: '01',
    title: 'COMPOSE',
    heading: '업무를 작은 블록으로',
    description: '입력, 판단, 승인, 실행을 눈에 보이는 단위로 나눠 직접 배치합니다.',
  },
  {
    number: '02',
    title: 'INTERVENE',
    heading: '필요한 순간에 사람이',
    description: '외부 발송 전 실행을 멈추고 결과를 확인한 다음 승인하거나 거절합니다.',
  },
  {
    number: '03',
    title: 'OBSERVE',
    heading: '실행의 모든 단계를 추적',
    description: '어디서 멈췄는지, 어떤 결과가 나왔는지 노드 단위로 확인합니다.',
  },
];

const WORKFLOW_RECIPES = [
  {
    number: '01',
    eyebrow: 'CUSTOMER OPERATIONS',
    title: '들어오는 문의를 놓치지 않는 흐름',
    description: 'Webhook으로 문의를 받고 AI가 내용을 분류합니다. 답변 초안은 담당자 승인 뒤 이메일로 전달됩니다.',
    types: ['webhookNode', 'llmNode', 'humanApprovalNode', 'emailNode'],
  },
  {
    number: '02',
    eyebrow: 'DAILY INTELLIGENCE',
    title: '매일 아침 팀이 함께 보는 리포트',
    description: '정해진 시간에 데이터를 모아 AI가 요약하고, 팀이 확인하는 채널과 문서 공간에 결과를 남깁니다.',
    types: ['scheduleNode', 'llmNode', 'discordNode', 'notionNode'],
  },
  {
    number: '03',
    eyebrow: 'CONTENT PIPELINE',
    title: '새 콘텐츠를 자동으로 정리하는 흐름',
    description: '새 영상이 게시되면 핵심 내용을 추출하고 구조화해 팀의 스프레드시트에 차곡차곡 쌓습니다.',
    types: ['youtubeTriggerNode', 'llmNode', 'googleSheetsNode'],
  },
];

const PROMPT_EXAMPLES = [
  {
    label: '메일 요약',
    prompt: '새 메일이 오면 내용을 세 줄로 요약해서 Slack에 보내줘',
    types: ['gmailTriggerNode', 'llmNode', 'slackNode'],
  },
  {
    label: '승인 요청',
    prompt: '문의가 접수되면 답변을 만들고, 담당자 승인 후 이메일로 발송해줘',
    types: ['webhookNode', 'llmNode', 'humanApprovalNode', 'emailNode'],
  },
  {
    label: '영상 아카이브',
    prompt: '새 YouTube 영상이 올라오면 요약해서 Notion에 정리해줘',
    types: ['youtubeTriggerNode', 'llmNode', 'notionNode'],
  },
];

function PrincipleVisual({ number }) {
  if (number === '01') {
    return (
      <div className="lab-principle-diagram diagram-compose" aria-hidden="true">
        <div className="principle-diagram-bar"><span>FLOW / 03 BLOCKS</span><em>READY</em></div>
        <div className="principle-mini-flow">
          {['webhookNode', 'llmNode', 'emailNode'].map((type, index) => {
            const meta = NODE_LIBRARY[type];
            return [
              index > 0 ? <i key={`${type}-connector`} /> : null,
              <div key={type} style={{ '--node-accent': meta.color }}>
                <span><Icon name={meta.icon} size={18} /></span>
                <strong>{meta.label}</strong>
                <small>{meta.caption}</small>
              </div>,
            ];
          })}
        </div>
      </div>
    );
  }

  if (number === '02') {
    return (
      <div className="lab-principle-diagram diagram-intervene" aria-hidden="true">
        <div className="principle-event-row"><Zap size={14} /><span>외부 발송 요청</span><em>09:41:02</em></div>
        <div className="principle-approval-gate">
          <span><Lock size={17} /></span>
          <div><small>HUMAN CHECKPOINT</small><strong>담당자 승인을 기다리는 중</strong></div>
          <em>PAUSED</em>
        </div>
        <div className="principle-gate-actions"><span>거절</span><strong>검토 후 승인</strong></div>
      </div>
    );
  }

  return (
    <div className="lab-principle-diagram diagram-observe" aria-hidden="true">
      <div className="principle-diagram-bar"><span>RUN / #WF-2841</span><em>12.4s</em></div>
      <div className="principle-trace">
        <div><i className="done" /><span>trigger.received</span><em>0.2s</em></div>
        <div><i className="done" /><span>ai.summary.complete</span><em>8.6s</em></div>
        <div><i className="active" /><span>approval.waiting</span><em>LIVE</em></div>
      </div>
      <div className="principle-progress"><span /></div>
    </div>
  );
}

function AssemblyCanvas() {
  const [presetKey, setPresetKey] = useState('report');
  const [nodes, setNodes] = useState(() => createPresetNodes('report'));
  const [isDragOver, setIsDragOver] = useState(false);
  const [activeNodeId, setActiveNodeId] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [runState, setRunState] = useState('idle');
  const [runMessage, setRunMessage] = useState('캔버스가 준비되었습니다.');
  const canvasRef = useRef(null);
  const instanceCounter = useRef(0);
  const pointerDrag = useRef(null);
  const runTimers = useRef([]);

  const orderedNodes = useMemo(() => [...nodes].sort((a, b) => a.x - b.x), [nodes]);
  const selectedNode = nodes.find((node) => node.instanceId === selectedNodeId) || null;

  const stopRun = () => {
    runTimers.current.forEach((timer) => window.clearTimeout(timer));
    runTimers.current = [];
    setActiveNodeId(null);
  };

  useEffect(() => () => {
    runTimers.current.forEach((timer) => window.clearTimeout(timer));
  }, []);

  const changePreset = (nextPresetKey) => {
    stopRun();
    setPresetKey(nextPresetKey);
    setNodes(createPresetNodes(nextPresetKey));
    setSelectedNodeId(null);
    setRunState('idle');
    setRunMessage(`${PRESETS[nextPresetKey].label} 레시피를 불러왔습니다.`);
  };

  const addNode = (type, position) => {
    const meta = NODE_LIBRARY[type];
    if (!meta) return;
    instanceCounter.current += 1;
    const fallbackIndex = nodes.length % NODE_POSITIONS.length;
    const fallback = NODE_POSITIONS[fallbackIndex];
    setNodes((current) => [
      ...current,
      {
        instanceId: `custom-${instanceCounter.current}`,
        type,
        x: position?.x ?? Math.min(70, fallback.x + (current.length > 3 ? -8 : 0)),
        y: position?.y ?? Math.min(67, fallback.y + (current.length > 3 ? 5 : 0)),
      },
    ]);
    setRunState('idle');
    setRunMessage(`${meta.label} 블록을 추가했습니다.`);
  };

  const handlePaletteDragStart = (event, type) => {
    event.dataTransfer.effectAllowed = 'copy';
    event.dataTransfer.setData('application/x-workflow-node', JSON.stringify({ type, source: 'palette' }));
    event.dataTransfer.setData('text/plain', type);
  };

  const handleNodePointerDown = (event, node) => {
    if (event.button !== 0 || event.target.closest('button, input, select')) return;
    const canvasBounds = canvasRef.current?.getBoundingClientRect();
    const nodeBounds = event.currentTarget.getBoundingClientRect();
    if (!canvasBounds) return;

    event.currentTarget.setPointerCapture(event.pointerId);
    pointerDrag.current = {
      nodeId: node.instanceId,
      pointerId: event.pointerId,
      offsetX: event.clientX - nodeBounds.left,
      offsetY: event.clientY - nodeBounds.top,
      startX: event.clientX,
      startY: event.clientY,
      nodeWidth: nodeBounds.width,
      nodeHeight: nodeBounds.height,
      moved: false,
    };
    setSelectedNodeId(node.instanceId);
    event.preventDefault();
  };

  const handleNodePointerMove = (event) => {
    const drag = pointerDrag.current;
    if (!drag || drag.pointerId !== event.pointerId || !canvasRef.current) return;
    const bounds = canvasRef.current.getBoundingClientRect();
    const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
    if (distance > 3) drag.moved = true;
    const maxX = ((bounds.width - drag.nodeWidth - 6) / bounds.width) * 100;
    const maxY = ((bounds.height - drag.nodeHeight - 6) / bounds.height) * 100;
    const x = Math.max(1, Math.min(maxX, ((event.clientX - bounds.left - drag.offsetX) / bounds.width) * 100));
    const y = Math.max(2, Math.min(maxY, ((event.clientY - bounds.top - drag.offsetY) / bounds.height) * 100));
    setNodes((current) => current.map((node) => (
      node.instanceId === drag.nodeId ? { ...node, x, y } : node
    )));
    if (drag.moved) {
      setRunState('idle');
      setRunMessage('블록 위치를 옮겼습니다.');
    }
    event.preventDefault();
  };

  const handleNodePointerUp = (event) => {
    const drag = pointerDrag.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    pointerDrag.current = null;
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragOver(false);
    let payload;
    try {
      payload = JSON.parse(event.dataTransfer.getData('application/x-workflow-node'));
    } catch {
      const type = event.dataTransfer.getData('text/plain');
      payload = type ? { type, source: 'palette' } : null;
    }
    if (!payload) return;

    const bounds = event.currentTarget.getBoundingClientRect();
    const offsetX = payload.source === 'canvas' ? Number(payload.offsetX) || 70 : 72;
    const offsetY = payload.source === 'canvas' ? Number(payload.offsetY) || 30 : 30;
    const maxX = bounds.width < 520 ? 55 : 76;
    const x = Math.max(2, Math.min(maxX, ((event.clientX - bounds.left - offsetX) / bounds.width) * 100));
    const y = Math.max(5, Math.min(72, ((event.clientY - bounds.top - offsetY) / bounds.height) * 100));

    if (payload.source === 'canvas') {
      setNodes((current) => current.map((node) => (
        node.instanceId === payload.nodeId ? { ...node, x, y } : node
      )));
      setRunMessage('블록 위치를 옮겼습니다.');
      setRunState('idle');
      return;
    }
    addNode(payload.type, { x, y });
  };

  const removeNode = (instanceId) => {
    stopRun();
    setNodes((current) => current.filter((node) => node.instanceId !== instanceId));
    if (selectedNodeId === instanceId) setSelectedNodeId(null);
    setRunState('idle');
    setRunMessage('블록을 캔버스에서 제거했습니다.');
  };

  const resetCanvas = () => changePreset(presetKey);

  const runWorkflow = () => {
    if (runState === 'running' || orderedNodes.length === 0) return;
    stopRun();
    setRunState('running');
    setRunMessage('워크플로우를 시작합니다…');

    orderedNodes.forEach((node, index) => {
      const timer = window.setTimeout(() => {
        setActiveNodeId(node.instanceId);
        setRunMessage(`${node.customLabel || NODE_LIBRARY[node.type]?.label || '블록'} 처리 중…`);
      }, index * 620);
      runTimers.current.push(timer);
    });

    const completionTimer = window.setTimeout(() => {
      setActiveNodeId(null);
      setRunState('done');
      setRunMessage(`${orderedNodes.length}개 블록의 실행이 완료되었습니다.`);
    }, orderedNodes.length * 620 + 240);
    runTimers.current.push(completionTimer);
  };

  return (
    <div className="assembly-shell" aria-label="워크플로우 조립 체험">
      <div className="assembly-topbar">
        <div className="assembly-window-title">
          <span className="assembly-live-dot" />
          <span>PLAYGROUND / UNTITLED FLOW</span>
        </div>
        <div className="assembly-topbar-meta">
          <span>{nodes.length} BLOCKS</span>
          <span>LOCAL DEMO</span>
        </div>
      </div>

      <div className="assembly-presets" aria-label="워크플로우 예시 선택">
        <span>RECIPE</span>
        <div>
          {Object.entries(PRESETS).map(([key, preset]) => (
            <button
              type="button"
              key={key}
              className={presetKey === key ? 'active' : ''}
              onClick={() => changePreset(key)}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <div
        className={`assembly-canvas ${isDragOver ? 'is-drag-over' : ''}`}
        ref={canvasRef}
        onPointerDown={(event) => {
          if (event.target === event.currentTarget) setSelectedNodeId(null);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = 'copy';
          setIsDragOver(true);
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setIsDragOver(false);
        }}
        onDrop={handleDrop}
      >
        <div className="assembly-grid" aria-hidden="true" />
        <svg className="assembly-connections" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <marker id="assembly-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" />
            </marker>
          </defs>
          {orderedNodes.slice(0, -1).map((node, index) => {
            const next = orderedNodes[index + 1];
            const startX = Math.min(96, node.x + 18);
            const startY = node.y + 16;
            const endX = next.x;
            const endY = next.y + 16;
            const bend = Math.max(3, (endX - startX) * 0.48);
            return (
              <path
                key={`${node.instanceId}-${next.instanceId}`}
                className={runState === 'running' ? 'is-running' : ''}
                d={`M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`}
                markerEnd="url(#assembly-arrow)"
              />
            );
          })}
        </svg>

        {nodes.length === 0 && (
          <div className="assembly-empty">
            <MousePointer2 size={22} />
            <strong>첫 블록을 놓아보세요</strong>
            <span>아래 팔레트에서 클릭하거나 드래그하세요.</span>
          </div>
        )}

        {nodes.map((node, index) => {
          const meta = NODE_LIBRARY[node.type];
          const displayLabel = node.customLabel || meta?.label;
          if (!meta) return null;
          return (
            <article
              key={node.instanceId}
              className={`assembly-node ${activeNodeId === node.instanceId ? 'is-active' : ''} ${selectedNodeId === node.instanceId ? 'is-selected' : ''}`}
              style={{ '--node-x': `${node.x}%`, '--node-y': `${node.y}%`, '--node-accent': meta.color }}
              onPointerDown={(event) => handleNodePointerDown(event, node)}
              onPointerMove={handleNodePointerMove}
              onPointerUp={handleNodePointerUp}
              onPointerCancel={handleNodePointerUp}
            >
              <div className="assembly-node-header">
                <div className="assembly-node-copy">
                  <div className="assembly-node-icon"><Icon name={meta.icon} size={29} /></div>
                  <strong>{displayLabel}</strong>
                </div>
                <ChevronRight className="assembly-node-chevron" size={15} aria-hidden="true" />
              </div>
              <button
                type="button"
                className="assembly-node-remove"
                aria-label={`${displayLabel} 블록 삭제`}
                onClick={() => removeNode(node.instanceId)}
              >
                <X size={12} />
              </button>
              <span className="assembly-node-port in" aria-hidden="true" />
              <span className="assembly-node-port out" aria-hidden="true" />
              <em>{String(index + 1).padStart(2, '0')} / {meta.caption}</em>
            </article>
          );
        })}

        {selectedNode && (
          <aside className="assembly-inspector" aria-label="선택한 노드 설정" onPointerDown={(event) => event.stopPropagation()}>
            <header>
              <div style={{ '--node-accent': NODE_LIBRARY[selectedNode.type].color }}>
                <Icon name={NODE_LIBRARY[selectedNode.type].icon} size={19} />
              </div>
              <span>
                <small>NODE SETTINGS</small>
                <strong>{selectedNode.customLabel || NODE_LIBRARY[selectedNode.type].label}</strong>
              </span>
              <button type="button" onClick={() => setSelectedNodeId(null)} aria-label="노드 설정 닫기"><X size={14} /></button>
            </header>
            <label>
              <span>노드 이름</span>
              <input
                value={selectedNode.customLabel ?? NODE_LIBRARY[selectedNode.type].label}
                onChange={(event) => setNodes((current) => current.map((node) => (
                  node.instanceId === selectedNode.instanceId ? { ...node, customLabel: event.target.value } : node
                )))}
              />
            </label>
            <label>
              <span>실행 정책</span>
              <select
                value={selectedNode.policy || 'after-success'}
                onChange={(event) => setNodes((current) => current.map((node) => (
                  node.instanceId === selectedNode.instanceId ? { ...node, policy: event.target.value } : node
                )))}
              >
                <option value="after-success">앞 노드 성공 후 실행</option>
                <option value="always">결과와 관계없이 실행</option>
                <option value="manual">수동 승인 후 실행</option>
              </select>
            </label>
            <div className="assembly-inspector-status"><span /> 연결됨 · 설정 저장됨</div>
          </aside>
        )}

        {isDragOver && <div className="assembly-drop-message">여기에 블록 놓기</div>}
      </div>

      <div className="assembly-dock">
        <span className="assembly-dock-label">BLOCKS</span>
        <div className="assembly-palette">
          {PALETTE_TYPES.map((type) => {
            const meta = NODE_LIBRARY[type];
            return (
              <button
                type="button"
                key={type}
                draggable
                onDragStart={(event) => handlePaletteDragStart(event, type)}
                onClick={() => addNode(type)}
                style={{ '--node-accent': meta.color }}
                title={`${meta.label} — 드래그하거나 클릭해 추가`}
              >
                <Icon name={meta.icon} size={16} />
                <span>{meta.label}</span>
                <GripVertical size={12} />
              </button>
            );
          })}
        </div>
      </div>

      <div className="assembly-runbar">
        <div className={`assembly-console ${runState}`} role="status" aria-live="polite">
          <span>&gt;_</span>
          <p>{runMessage}</p>
        </div>
        <div className="assembly-run-actions">
          <button type="button" className="assembly-reset" onClick={resetCanvas} title="현재 레시피 초기화">
            <RotateCcw size={15} />
          </button>
          <button
            type="button"
            className="assembly-run"
            onClick={runWorkflow}
            disabled={runState === 'running' || nodes.length === 0}
          >
            {runState === 'running' ? <Activity size={15} /> : <Play size={14} fill="currentColor" />}
            {runState === 'running' ? 'RUNNING' : runState === 'done' ? 'RUN AGAIN' : 'RUN FLOW'}
          </button>
        </div>
      </div>
    </div>
  );
}

function PromptComposer() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [draftVersion, setDraftVersion] = useState(0);
  const [hasGenerated, setHasGenerated] = useState(false);
  const activeExample = PROMPT_EXAMPLES[activeIndex];

  return (
    <div className="prompt-composer fade-up-element">
      <div className="prompt-composer-bar">
        <span><Sparkles size={14} /> AI FLOW DRAFT</span>
        <em>한국어 입력</em>
      </div>
      <div className="prompt-composer-tabs" aria-label="한국어 자동화 요청 예시">
        {PROMPT_EXAMPLES.map((example, index) => (
          <button
            type="button"
            key={example.label}
            className={activeIndex === index ? 'active' : ''}
            onClick={() => {
              setActiveIndex(index);
              setHasGenerated(false);
            }}
          >
            {example.label}
          </button>
        ))}
      </div>
      <div className="prompt-composer-input">
        <span>YOU</span>
        <p key={activeExample.prompt}>{activeExample.prompt}</p>
        <button
          type="button"
          className="prompt-send-button"
          aria-label="선택한 요청 전송 후 흐름 초안 생성"
          onClick={() => {
            setHasGenerated(true);
            setDraftVersion((current) => current + 1);
          }}
        >
          <span>SEND</span><ArrowRight size={16} />
        </button>
      </div>
      {hasGenerated ? (
        <div className="prompt-composer-result" key={`result-${activeIndex}-${draftVersion}`}>
          <div className="prompt-result-meta">
            <span>GENERATED DRAFT</span>
            <em>{activeExample.types.length}개 노드 · 편집 가능</em>
          </div>
          <div className="prompt-result-flow">
            {activeExample.types.map((type, index) => {
              const meta = NODE_LIBRARY[type];
              return [
                index > 0 ? <i key={`${type}-line-${index}`} aria-hidden="true" /> : null,
                <div key={`${type}-${index}`} style={{ '--node-accent': meta.color }}>
                  <Icon name={meta.icon} size={22} />
                  <span>{meta.label}</span>
                </div>,
              ];
            })}
          </div>
          <p><CheckCircle2 size={14} /> 초안이므로 모든 노드와 연결을 직접 바꿀 수 있습니다.</p>
        </div>
      ) : (
        <div className="prompt-composer-empty" role="status">
          <div><Sparkles size={20} /></div>
          <strong>아직 생성된 초안이 없습니다</strong>
          <p>문장을 확인하고 SEND를 누르면 편집 가능한 노드가 이곳에 나타납니다.</p>
          <span>WAITING FOR INPUT</span>
        </div>
      )}
    </div>
  );
}

function IntroPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const layoutRef = useRef(null);

  useEffect(() => {
    const layout = layoutRef.current;
    if (!layout || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    layout.classList.add('intro-animate');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
        } else if (entry.target.classList.contains('intro-scene')) {
          entry.target.classList.remove('visible');
        }
      });
    }, { root: layout, threshold: 0.1, rootMargin: '-5% 0px -5%' });
    layout.querySelectorAll('.fade-up-element, .intro-scene').forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, []);

  const startLabel = user ? '워크스페이스 열기' : '무료로 시작하기';

  return (
    <div className="intro-page-layout" ref={layoutRef}>
      <header className="intro-site-header">
        <button type="button" className="intro-brand" onClick={() => navigate('/')} aria-label="WorkFlow Ai 홈">
          <img src={logoImg} alt="" />
          <span>WorkFlow <strong>Ai</strong></span>
          <em>LAB</em>
        </button>
        <nav className="intro-site-nav" aria-label="소개 페이지 탐색">
          <a href="#canvas">캔버스</a>
          <a href="#principles">작동 방식</a>
          <a href="#product">제품 화면</a>
          <a href="#app-builder">앱 빌더</a>
          <a href="#integrations">연동</a>
        </nav>
        <div className="intro-site-actions">
          <button type="button" className="intro-header-link" onClick={() => navigate('/documents')}>문서</button>
          <button type="button" className="intro-header-primary" onClick={() => navigate('/workflows')}>
            {user ? '워크스페이스' : '로그인'} <ArrowRight size={15} />
          </button>
        </div>
      </header>

      <main>
        <section className="lab-hero" id="canvas">
          <div className="lab-hero-copy fade-up-element">
            <div className="lab-status-label"><span /> INTERACTIVE PRODUCT DEMO</div>
            <h1>
              자동화는<br />
              보는 것이 아니라<br />
              <span>조립하는 것.</span>
            </h1>
            <p>
              블록을 캔버스에 놓고, 순서를 바꾸고, 직접 실행해보세요.
              복잡한 업무도 눈에 보이는 작은 단위가 되면 다룰 수 있습니다.
            </p>
            <div className="lab-hero-actions">
              <button type="button" className="intro-btn-primary" onClick={() => navigate('/workflows')}>
                {startLabel} <ArrowRight size={17} />
              </button>
              <a href="#principles">어떻게 작동하나요? <span>↓</span></a>
            </div>
            <a
              className="lab-youtube-film"
              href="https://www.youtube.com/watch?v=MMWdtbzdsPQ"
              target="_blank"
              rel="noreferrer"
              aria-label="WorkFlow Ai 사이트 소개 영상을 YouTube에서 보기, 새 창 열림"
            >
              <span className="lab-youtube-play"><Play size={15} fill="currentColor" /></span>
              <span className="lab-youtube-copy">
                <small>PRODUCT FILM / YOUTUBE</small>
                <strong>사이트 소개 영상 보기</strong>
              </span>
              <em>WATCH <span>↗</span></em>
            </a>
            <ol className="lab-mini-manual" aria-label="캔버스 체험 방법">
              <li><span>01</span> 블록을 끌어다 놓기</li>
              <li><span>02</span> 원하는 위치로 정렬</li>
              <li><span>03</span> RUN FLOW로 실행</li>
            </ol>
          </div>
          <div className="lab-canvas-wrap fade-up-element">
            <AssemblyCanvas />
            <p className="lab-canvas-note"><MousePointer2 size={13} /> 이 캔버스는 실제로 작동합니다. 블록을 움직여보세요.</p>
          </div>
        </section>

        <div className="lab-command-strip intro-scene transition-wipe" aria-hidden="true">
          <span>DRAG</span><i />
          <span>DROP</span><i />
          <span>CONNECT</span><i />
          <span>RUN</span><i />
          <span>OBSERVE</span>
        </div>

        <section className="lab-principles intro-scene transition-lift" id="principles">
          <header className="lab-section-heading fade-up-element">
            <span>THE PRODUCT THESIS</span>
            <h2>노코드여도,<br />통제권까지 없어질 필요는 없습니다.</h2>
          </header>
          <div className="lab-principle-grid">
            {PRINCIPLES.map((item) => (
              <article key={item.number} className="lab-principle-card fade-up-element">
                <div className="lab-principle-index"><span>{item.number}</span><em>{item.title}</em></div>
                <h3>{item.heading}</h3>
                <p>{item.description}</p>
                <PrincipleVisual number={item.number} />
              </article>
            ))}
          </div>
        </section>

        <section className="lab-recipes intro-scene transition-slide">
          <header className="lab-section-heading lab-recipes-heading fade-up-element">
            <span>START WITH A REAL JOB</span>
            <h2>흰 캔버스 대신,<br />익숙한 업무에서 시작하세요.</h2>
            <p>완성된 템플릿을 그대로 쓰거나 필요한 블록만 바꿔 내 팀의 방식으로 조정할 수 있습니다.</p>
          </header>
          <div className="lab-recipe-list">
            {WORKFLOW_RECIPES.map((recipe) => (
              <article key={recipe.number} className="lab-recipe-row fade-up-element">
                <div className="lab-recipe-number">{recipe.number}</div>
                <div className="lab-recipe-copy">
                  <span>{recipe.eyebrow}</span>
                  <h3>{recipe.title}</h3>
                  <p>{recipe.description}</p>
                </div>
                <div className="lab-recipe-flow" aria-label={`${recipe.title} 사용 노드`}>
                  {recipe.types.map((type, index) => {
                    const meta = NODE_LIBRARY[type];
                    return [
                      index > 0 ? <i key={`${recipe.number}-line-${index}`} aria-hidden="true" /> : null,
                      <div key={`${recipe.number}-${type}`} style={{ '--node-accent': meta.color }} title={meta.label}>
                        <Icon name={meta.icon} size={19} />
                        <span>{meta.label}</span>
                      </div>,
                    ];
                  })}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="lab-control-section intro-scene transition-lift">
          <div className="lab-control-intro fade-up-element">
            <span className="lab-section-label">CONTROL, NOT MAGIC</span>
            <h2>AI가 만들고,<br />사람이 결정합니다.</h2>
            <p>
              자동 생성된 흐름을 그대로 믿게 하지 않습니다. 실행 전에 검사하고,
              중요한 순간에는 멈추고, 실행 후에는 기록을 남깁니다.
            </p>
          </div>
          <div className="lab-control-grid">
            <article className="lab-control-card lab-approval-card fade-up-element">
              <div className="lab-card-topline">
                <span><ShieldCheck size={17} /> HUMAN IN THE LOOP</span>
                <em>LIVE</em>
              </div>
              <div className="lab-approval-flow" aria-hidden="true">
                <div><Zap size={18} /><span>이벤트</span></div>
                <i />
                <div><Sparkles size={18} /><span>AI 초안</span></div>
                <i className="paused" />
                <div className="approval-gate"><Lock size={18} /><span>승인 대기</span><b>PAUSED</b></div>
                <i />
                <div><CheckCircle2 size={18} /><span>외부 전송</span></div>
              </div>
              <h3>보내기 전에, 한 번 더 확인</h3>
              <p>메일·게시·결제처럼 되돌리기 어려운 행동 앞에 승인 단계를 놓을 수 있습니다.</p>
            </article>

            <article className="lab-control-card lab-preflight-card fade-up-element">
              <div className="lab-card-topline"><span>PREFLIGHT CHECK</span><em>03 / 03</em></div>
              <ul>
                <li><CheckCircle2 size={15} /><span>노드 연결 구조</span><b>PASS</b></li>
                <li><CheckCircle2 size={15} /><span>필수 입력값</span><b>PASS</b></li>
                <li><CheckCircle2 size={15} /><span>외부 영향 표시</span><b>PASS</b></li>
              </ul>
              <h3>실행 전에 문제를 발견</h3>
              <p>구조와 설정을 먼저 검사해 실행 버튼을 누르기 전부터 위험을 줄입니다.</p>
            </article>

            <article className="lab-control-card lab-log-card fade-up-element">
              <div className="lab-card-topline"><span>EXECUTION TRACE</span><em>12.4s</em></div>
              <div className="lab-terminal" aria-hidden="true">
                <p><i className="success" /> 09:00:00 <span>trigger.received</span></p>
                <p><i className="success" /> 09:00:04 <span>ai.summary.complete</span></p>
                <p><i className="waiting" /> 09:00:06 <span>approval.waiting</span></p>
              </div>
              <h3>어디까지 실행됐는지 명확하게</h3>
              <p>노드별 상태와 로그에서 멈춘 지점과 다음 행동을 바로 확인합니다.</p>
            </article>
          </div>
        </section>

        <section className="lab-prompt-section intro-scene transition-scale">
          <div className="lab-prompt-copy fade-up-element">
            <span className="lab-section-label">DESCRIBE, THEN REFINE</span>
            <h2>한국어 한 문장이<br />편집 가능한 초안으로.</h2>
            <p>처음부터 모든 노드를 찾을 필요는 없습니다. 하고 싶은 일을 설명하면 시작점을 만들고, 이후의 결정권은 캔버스에 남겨둡니다.</p>
          </div>
          <PromptComposer />
        </section>

        <section className="lab-product-proof intro-scene transition-clip" id="product">
          <header className="lab-section-heading lab-proof-heading fade-up-element">
            <span>THE REAL CANVAS</span>
            <h2>체험이 마음에 들었다면,<br />실제 캔버스는 더 깊습니다.</h2>
            <p>한국어로 초안을 만들고, 노드를 세밀하게 편집하고, 실행 결과까지 같은 화면에서 확인하세요.</p>
          </header>
          <div className="lab-product-frame fade-up-element">
            <div className="lab-product-bar">
              <span><i /><i /><i /></span>
              <strong>WORKFLOW EDITOR / PRODUCT CAPTURE</strong>
              <em><i /> ACTUAL UI</em>
            </div>
            <img
              src={demo1}
              alt="WorkFlow Ai 실제 워크플로우 편집기 화면"
              width="1280"
              height="720"
              loading="lazy"
              decoding="async"
            />
            <div className="lab-product-caption">
              <span>01 / 한국어 생성</span>
              <span>02 / 자유 배치</span>
              <span>03 / 실행 추적</span>
            </div>
          </div>
        </section>

        <section className="lab-app-builder intro-scene transition-wipe" id="app-builder">
          <div className="lab-app-builder-copy fade-up-element">
            <span className="lab-section-label">BUILD THE INTERFACE TOO</span>
            <h2>자동화 위에,<br />팀이 쓸 앱까지.</h2>
            <p>
              워크플로우의 입력과 결과를 폼, 보드, 대시보드로 구성해 실제 사용 화면으로 연결합니다.
              이 영역에는 App Builder의 완성 화면을 보여줄 전용 이미지를 추가할 예정입니다.
            </p>
            <ul>
              <li><span>01</span> 컴포넌트로 화면 구성</li>
              <li><span>02</span> 워크플로우와 데이터 연결</li>
              <li><span>03</span> 팀용 앱으로 공유</li>
            </ul>
          </div>
          <div className="lab-app-builder-placeholder fade-up-element" role="img" aria-label="App Builder WebP 이미지가 들어갈 빈 자리">
            <div className="app-builder-placeholder-bar">
              <span><i /><i /><i /></span>
              <strong>APP BUILDER / IMAGE SLOT</strong>
              <em>8:5</em>
            </div>
            <div className="app-builder-placeholder-body">
              <span>WEBP PLACEHOLDER</span>
              <strong>1920 × 1200 px</strong>
              <p>App Builder 전체 화면 캡처 또는 연출 이미지를 이 자리에 교체</p>
              <code>app-builder-showcase.webp</code>
            </div>
          </div>
        </section>

        <section className="lab-integrations intro-scene transition-slide" id="integrations">
          <div className="lab-integrations-copy fade-up-element">
            <span className="lab-section-label">PLUG INTO REAL WORK</span>
            <h2>이미 쓰는 도구를<br />하나의 흐름으로.</h2>
            <p>현재 에디터 카탈로그와 동기화된 외부 연결 노드 {INTEGRATION_LABELS.length}개가 하나의 살아 있는 연결망처럼 흐릅니다.</p>
          </div>
          <div
            className="lab-integration-stage fade-up-element"
            role="group"
            aria-label={`사용 가능한 외부 연결 ${INTEGRATION_LABELS.length}개: ${INTEGRATION_LABELS.map(({ label }) => label).join(', ')}`}
          >
            <div className="lab-integration-stage-header" aria-hidden="true">
              <span><i /> CONNECTOR SIGNAL</span>
              <strong>{String(INTEGRATION_LABELS.length).padStart(2, '0')} LIVE ENDPOINTS</strong>
              <em>CATALOG / AUTO-SYNC</em>
            </div>
            <div className="lab-integration-lanes" aria-hidden="true">
              {INTEGRATION_LANES.map((lane, laneIndex) => (
                <div className={`lab-integration-lane lane-${laneIndex + 1}`} key={`lane-${laneIndex}`}>
                  <div className="lab-integration-track">
                    {[0, 1].map((cycle) => (
                      <div className="lab-integration-group" key={`cycle-${cycle}`}>
                        {lane.map(({ type, label, icon, color, kind }) => {
                          const catalogIndex = INTEGRATION_LABELS.findIndex((item) => item.type === type);
                          return (
                            <article
                              key={`${type}-${cycle}`}
                              style={{ '--integration-color': color, '--integration-index': catalogIndex }}
                            >
                              <span>{String(catalogIndex + 1).padStart(2, '0')}</span>
                              <div><Icon name={icon} size={21} /></div>
                              <p><strong>{label}</strong><small>{kind}</small></p>
                              <i />
                            </article>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="lab-integration-stage-footer" aria-hidden="true">
              <span><i /><i /><i /> SIGNALS MOVING</span>
              <em>HOVER TO INSPECT / PAUSE</em>
              <strong>WORKFLOW AI NETWORK ↗</strong>
            </div>
          </div>
        </section>

        <section className="lab-final-cta intro-scene transition-scale">
          <span>YOUR NEXT FLOW STARTS HERE</span>
          <h2>이번에는 진짜 업무를<br />조립해볼 차례입니다.</h2>
          <p>빈 캔버스에서 시작하거나, 하고 싶은 일을 한국어로 설명하세요.</p>
          <div>
            <button type="button" className="intro-btn-primary" onClick={() => navigate('/workflows')}>
              {startLabel} <ArrowRight size={17} />
            </button>
            <button type="button" className="intro-btn-quiet" onClick={() => navigate('/tutorial')}>튜토리얼 보기</button>
          </div>
        </section>
      </main>

      <footer className="intro-footer">
        <button type="button" className="intro-footer-brand" onClick={() => navigate('/')}>
          <img src={logoImg} alt="" />
          <span>WorkFlow <strong>Ai</strong></span>
        </button>
        <p>한국어 업무 자동화를 위한 시각적 워크플로우 도구</p>
        <nav aria-label="하단 탐색">
          <button type="button" onClick={() => navigate('/documents')}>문서</button>
          <button type="button" onClick={() => navigate('/tutorial')}>학습 센터</button>
          <button type="button" onClick={() => navigate('/community/templates')}>커뮤니티</button>
        </nav>
      </footer>
    </div>
  );
}

export default IntroPage;
