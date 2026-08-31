// 노드 Inspector (EDITOR_SHORTCUTS §7.1~§7.4, Slice 4).
//
// 한 노드의 입력·출력·로그·Raw 를 노드 가까이에서 보여주고, **외부 API 를 실제로 부르지 않고**
// 그 노드만 돌려볼 수 있게 한다(목업 실행). 실제 실행은 별도 버튼이고, 외부로 무언가를 보내는
// 노드면 확인을 받는다 — §7.1 "기본은 mock/dry-run, 실제 외부 쓰기는 별도 확인".
import { useEffect, useMemo, useRef, useState } from 'react';
import { Copy, Download, FlaskConical, Play, Pin, PinOff, Search, AlertTriangle } from 'lucide-react';
import NodeErrorCard from './NodeErrorCard';

const TABS = [
  { id: 'input', label: '입력' },
  { id: 'output', label: '출력' },
  { id: 'logs', label: '로그' },
  { id: 'raw', label: 'Raw' },
];

const prettify = (text) => {
  if (typeof text !== 'string' || !text.trim()) return text || '';
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
};

/** 검색어가 있으면 일치하는 줄만 남긴다 — 큰 출력에서 원하는 key/value 를 찾는 용도(§7.2). */
const filterLines = (text, query) => {
  if (!query.trim()) return { text, matched: null };
  const needle = query.toLowerCase();
  const lines = String(text || '').split('\n');
  const hit = lines.filter((line) => line.toLowerCase().includes(needle));
  return { text: hit.join('\n'), matched: hit.length };
};

const download = (name, text) => {
  const blob = new Blob([text ?? ''], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
};

export default function NodeInspector({
  node,
  meta,
  ownLog,
  inputs,
  isOwner,
  writesExternally,
  nodeErrorV1,
  sampleInput,
  onSampleInputChange,
  pinnedFixture,
  pinnedStale,
  onPinOutput,
  onUnpinOutput,
  onFocusNode,
  onFocusField,
  onNavigate,
  onMockRun,        // (nodeId, {only}) — 목업 실행
  onRealRun,        // (nodeId) — 실제 실행
  onRunUpTo,        // (nodeId) — 여기까지 실제 실행
  onReplayLast,     // (nodeId) — 직전 실행의 입력으로 다시 목업 실행
  busy,
}) {
  const [tab, setTab] = useState('output');
  const [query, setQuery] = useState('');
  const sampleRef = useRef(null);

  useEffect(() => { setQuery(''); }, [node?.id]);

  const outputText = ownLog?.result_data ?? '';
  const inputText = useMemo(
    () => inputs.map(({ sourceId, log }) => `# ${sourceId}\n${log?.result_data ?? '(기록 없음)'}`).join('\n\n'),
    [inputs],
  );
  const logsText = useMemo(() => {
    if (!ownLog) return '';
    return [
      `node_id     ${ownLog.node_id}`,
      `node_type   ${ownLog.node_type}`,
      `status      ${ownLog.status}${ownLog.pinned ? ' (고정 데이터 — 실행하지 않음)' : ''}`,
      ownLog.result_status ? `result      ${ownLog.result_status}` : null,
      `start       ${ownLog.start_time || '-'}`,
      `end         ${ownLog.end_time || '-'}`,
      ownLog.error?.code ? `error       ${ownLog.error.code} (${ownLog.error.category})` : null,
      ownLog.error?.requestId ? `request_id  ${ownLog.error.requestId}` : null,
      ownLog.error_message ? `message     ${ownLog.error_message}` : null,
    ].filter(Boolean).join('\n');
  }, [ownLog]);
  const rawText = useMemo(() => (ownLog ? JSON.stringify(ownLog, null, 2) : ''), [ownLog]);

  const active = {
    input: inputText,
    output: prettify(outputText),
    logs: logsText,
    raw: rawText,
  }[tab] || '';
  const { text: shown, matched } = filterLines(active, query);
  const copyText = (text) => navigator.clipboard?.writeText(text || '');
  const empty = '(최근 실행 기록 없음 — 목업으로 이 노드를 돌려보세요)';

  return (
    <div className="exec-section">
      <div className="exec-row">
        <div className="exec-title">
          <span className="exec-node-tile" style={{ '--node-color': meta.color }}>{meta.label.slice(0, 1)}</span>
          <strong>{meta.label}</strong>
          <code>{node.id}</code>
          {ownLog && (
            <span className={`exec-badge ${ownLog.status === 'error' ? 'danger' : 'success'}`}>
              최근 실행 {ownLog.status === 'error' ? '오류' : '성공'}
            </span>
          )}
          {ownLog?.pinned && <span className="exec-badge info">고정 데이터</span>}
          {writesExternally && <span className="exec-badge warning">외부 전송</span>}
        </div>
        <div className="exec-actions">
          <button type="button" className="btn-secondary exec-btn" onClick={() => onFocusNode(node.id)}>캔버스에서 보기</button>
        </div>
      </div>

      {isOwner && node.type !== 'memoNode' && (
        <div className="exec-field">
          <label>
            테스트 실행
            <small>목업은 외부 API를 부르지 않습니다 — 자격증명 없이도 이 노드의 입력·출력을 확인할 수 있습니다</small>
          </label>
          <div className="exec-actions wrap">
            <button type="button" className="btn-run exec-btn" disabled={busy} onClick={() => onMockRun(node.id, { only: true })}>
              <FlaskConical size={14} /> 이 노드만 목업
            </button>
            <button type="button" className="btn-secondary exec-btn" disabled={busy} onClick={() => onMockRun(node.id, { only: false })}>
              <FlaskConical size={14} /> 여기부터 목업
            </button>
            <button type="button" className="btn-secondary exec-btn" disabled={busy || !ownLog} onClick={() => onReplayLast(node.id)}
              title={ownLog ? '직전 실행에서 이 노드가 받은 입력으로 다시 돌립니다' : '먼저 한 번 실행해야 합니다'}>
              직전 입력으로 다시
            </button>
            <button type="button" className="btn-secondary exec-btn" disabled={busy} onClick={() => onRunUpTo(node.id)}>
              <Play size={14} /> 여기까지 실제 실행
            </button>
            <button type="button" className="btn-secondary exec-btn" disabled={busy} onClick={() => onRealRun(node.id)}>
              <Play size={14} /> 이 노드부터 실제 실행
            </button>
          </div>
        </div>
      )}

      <div className="exec-field">
        <label>
          샘플 입력
          <small>목업·부분 실행에서 직전 노드 출력 자리에 들어갑니다 — 브라우저에만 저장</small>
        </label>
        <textarea
          key={node.id}
          ref={sampleRef}
          className="exec-textarea"
          defaultValue={sampleInput}
          onChange={(event) => onSampleInputChange(node.id, event.target.value)}
          placeholder="예: 요약할 원문, 파싱할 JSON 등 테스트 입력"
        />
      </div>

      <div className="exec-field">
        <div className="exec-io-head">
          <div className="exec-tabs">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`exec-tab ${tab === item.id ? 'active' : ''}`}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="exec-actions">
            <button type="button" className="exec-link muted" onClick={() => copyText(active)} title="복사">
              <Copy size={12} /> 복사
            </button>
            <button type="button" className="exec-link muted" onClick={() => download(`${node.id}-${tab}.json`, active)} title="다운로드">
              <Download size={12} /> 저장
            </button>
          </div>
        </div>

        <div className="exec-search">
          <Search size={13} />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="key 또는 값으로 검색 — 일치하는 줄만 보여줍니다"
          />
          {query && <span className="exec-search-count">{matched ?? 0}줄</span>}
        </div>

        <pre className="exec-pre">{shown || (query ? '(검색 결과 없음)' : empty)}</pre>

        {tab === 'output' && ownLog?.error && nodeErrorV1 && (
          <NodeErrorCard
            error={ownLog.error}
            nodeId={String(node.id)}
            nodeType={node.type}
            onFocusNode={onFocusNode}
            onFocusField={onFocusField}
            onRetry={isOwner ? onRealRun : undefined}
            onNavigate={onNavigate}
            compact
          />
        )}
        {tab === 'output' && ownLog?.error && !nodeErrorV1 && ownLog.error_message && (
          <pre className="exec-pre danger">{ownLog.error_message}</pre>
        )}
      </div>

      <div className="exec-field">
        <div className="exec-io-head">
          <label>
            출력 고정
            <small>이 노드를 실행하지 않고 고정한 값을 하류로 흘립니다 — 상류 외부 API를 다시 부르지 않습니다</small>
          </label>
          {pinnedFixture ? (
            <button type="button" className="exec-link" onClick={() => onUnpinOutput(node.id)}>
              <PinOff size={12} /> 고정 해제
            </button>
          ) : (
            <button type="button" className="exec-link" disabled={!outputText} onClick={() => onPinOutput(node)}
              title={outputText ? '' : '고정할 출력이 없습니다 — 먼저 실행하세요'}>
              <Pin size={12} /> 최근 출력 고정
            </button>
          )}
        </div>
        {pinnedFixture && (
          <>
            {pinnedStale && (
              <div className="exec-card danger">
                <AlertTriangle size={14} /> 고정한 뒤 노드 설정이 바뀌었습니다. 지금 설정의 출력과 다를 수 있으니 다시 실행해 고정하세요.
              </div>
            )}
            <pre className="exec-pre">{pinnedFixture.value}</pre>
            <span className="exec-hint">고정 시각 {new Date(pinnedFixture.savedAt).toLocaleString()} · 시크릿은 저장 전에 가려집니다</span>
          </>
        )}
      </div>
    </div>
  );
}
