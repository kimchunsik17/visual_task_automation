import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Play, RefreshCw, AlertTriangle, CheckCircle2, Clock } from 'lucide-react';
import { Icon } from '../icons';
import './MockPanel.css';

/**
 * 목업 실행 패널 (ADR-0009).
 *
 * 실제 자격증명 없이 워크플로우를 끝까지 돌려보고, 오간 요청을 그대로 보여준다.
 * 어떤 노드를 무엇으로 흉내 낼 수 있는지는 서버가 그래프를 보고 알려주므로, 노드가 늘어도
 * 이 화면은 고칠 것이 없다.
 */
export default function MockPanel({ projectId, authHeaders, getGraphData, onRunSucceeded }) {
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [scenario, setScenario] = useState('success');
  const [entryNodeId, setEntryNodeId] = useState('');
  const [payloadText, setPayloadText] = useState('{}');
  const [result, setResult] = useState(null);

  const loadCatalog = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError('');
    try {
      const res = await axios.get(`/api/projects/${projectId}/mock/scenarios`, authHeaders());
      setCatalog(res.data);
      const firstEntry = res.data.entries?.[0];
      if (firstEntry) {
        setEntryNodeId(firstEntry.node_id);
        const firstSample = firstEntry.samples?.[0];
        if (firstSample) setPayloadText(JSON.stringify(firstSample.payload, null, 2));
      }
    } catch (err) {
      setError(err?.response?.data?.detail || '목업 정보를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [projectId, authHeaders]);

  useEffect(() => { loadCatalog(); }, [loadCatalog]);

  const selectedEntry = catalog?.entries?.find((entry) => entry.node_id === entryNodeId);

  const runMock = async () => {
    setRunning(true);
    setError('');
    try {
      let payload = null;
      if (payloadText.trim()) {
        try {
          payload = JSON.parse(payloadText);
        } catch {
          // JSON 이 아니면 그대로 문자열로 보낸다 — 웹훅이 항상 JSON 을 받는 것은 아니다.
          payload = payloadText;
        }
      }
      const res = await axios.post(
        `/api/projects/${projectId}/mock/run`,
        // 저장 전 캔버스 상태로 돌린다 — "저장해야 테스트 가능"은 불필요한 마찰이다.
        { graph_data: getGraphData(), entry_node_id: entryNodeId, payload, scenario },
        authHeaders(),
      );
      setResult(res.data);
      // 목업이라도 "끝까지 도는 것을 확인했다"는 사실은 실제 실행과 같다 — 온보딩의
      // 결과 확인 단계를 여기서 완료 처리한다(토큰도 자격증명도 쓰지 않고).
      if (res.data.success && onRunSucceeded) onRunSucceeded();
    } catch (err) {
      setError(err?.response?.data?.detail || '목업 실행에 실패했습니다.');
    } finally {
      setRunning(false);
    }
  };

  // 목업 시나리오는 서버가 저장된 그래프를 보고 알려주므로 프로젝트 id 가 필요하다.
  // 안내 없이 "불러오지 못했습니다"만 띄우면 무엇을 해야 할지 알 수 없다.
  if (!projectId) {
    return (
      <div className="mock-panel mock-panel-empty">
        목업으로 실행하려면 워크플로우를 먼저 저장해주세요. 저장 후에는 캔버스의 최신 상태 그대로 실행됩니다.
      </div>
    );
  }

  if (loading) return <div className="mock-panel mock-panel-empty">목업 정보를 불러오는 중…</div>;

  if (!catalog) {
    return (
      <div className="mock-panel mock-panel-empty">
        {error || '목업 정보를 불러오지 못했습니다.'}
        <button className="mock-btn" onClick={loadCatalog}><RefreshCw size={14} /> 다시 시도</button>
      </div>
    );
  }

  const mockable = catalog.mockable_nodes || [];
  const unsupported = catalog.unsupported_nodes || [];

  return (
    <div className="mock-panel">
      <div className="mock-controls">
        <div className="mock-field">
          <label>시작 노드</label>
          <select value={entryNodeId} onChange={(e) => setEntryNodeId(e.target.value)}>
            <option value="">(입력 없이 실행)</option>
            {catalog.entries.map((entry) => (
              <option key={entry.node_id} value={entry.node_id}>
                {entry.node_id} · {entry.node_type}
              </option>
            ))}
          </select>
        </div>

        <div className="mock-field">
          <label>상황</label>
          <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
            {catalog.scenario_presets.map((preset) => (
              <option key={preset.id} value={preset.id}>{preset.label}</option>
            ))}
          </select>
        </div>

        <button className="mock-btn mock-btn-run" onClick={runMock} disabled={running}>
          <Play size={14} /> {running ? '실행 중…' : '목업 실행'}
        </button>
        <span className="mock-hint">실제 API 키 없이 실행됩니다. 바깥으로 나가는 요청은 없습니다.</span>
      </div>

      {selectedEntry?.samples?.length > 0 && (
        <div className="mock-samples">
          <span>예시 payload:</span>
          {selectedEntry.samples.map((sample) => (
            <button
              key={sample.id}
              className="mock-chip"
              onClick={() => setPayloadText(JSON.stringify(sample.payload, null, 2))}
            >
              {sample.label}
            </button>
          ))}
        </div>
      )}

      {entryNodeId && (
        <div className="mock-field mock-payload">
          <label>보낼 payload</label>
          <textarea value={payloadText} onChange={(e) => setPayloadText(e.target.value)} rows={6} spellCheck={false} />
        </div>
      )}

      <div className="mock-nodes">
        {mockable.length > 0 && (
          <div className="mock-node-list">
            <strong>목업으로 대체되는 노드</strong>
            {mockable.map((node) => (
              <span key={node.node_id} className="mock-node-chip">
                {node.node_id} · {node.label}
              </span>
            ))}
          </div>
        )}
        {unsupported.length > 0 && (
          <div className="mock-node-list mock-node-warning">
            <AlertTriangle size={14} />
            <strong>아직 목업할 수 없는 노드</strong>
            {unsupported.map((node) => (
              <span key={node.node_id} className="mock-node-chip">{node.node_id} · {node.node_type}</span>
            ))}
            <em>이 노드들은 목업 실행에서도 실제 호출을 시도합니다.</em>
          </div>
        )}
      </div>

      {error && <div className="mock-error"><AlertTriangle size={14} /> {error}</div>}

      {result && (
        <div className="mock-result">
          <div className={`mock-summary ${result.success ? 'ok' : 'fail'}`}>
            {result.success ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            <strong>{result.success ? '성공' : `실패한 요청 ${result.failed_request_count}건`}</strong>
            <span><Clock size={13} /> {result.duration_ms}ms</span>
            {result.simulated_wait_seconds > 0 && (
              <span className="mock-wait">
                실제 실행이었다면 재시도로 {result.simulated_wait_seconds}초 더 기다렸을 요청입니다
              </span>
            )}
          </div>

          <div className="mock-requests">
            {result.requests.length === 0 && <div className="mock-none">오간 요청이 없습니다.</div>}
            {result.requests.map((request, index) => (
              <details key={index} className="mock-request">
                <summary>
                  <span className={`mock-status s${String(request.status || 'x')[0]}`}>{request.status ?? '—'}</span>
                  <code>{request.method}</code>
                  <span className="mock-url">{request.url}</span>
                  <span className="mock-meta">{request.node_id} · {request.service} · {request.latency_ms}ms</span>
                </summary>
                <div className="mock-request-body">
                  <div><label>요청 헤더</label><pre>{JSON.stringify(request.request_headers, null, 2)}</pre></div>
                  <div><label>요청 본문</label><pre>{JSON.stringify(request.request_body, null, 2)}</pre></div>
                  <div><label>응답 본문</label><pre>{JSON.stringify(request.response_body, null, 2)}</pre></div>
                </div>
              </details>
            ))}
          </div>

          <div className="mock-final">
            <label>최종 결과</label>
            <pre>{String(result.result)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
