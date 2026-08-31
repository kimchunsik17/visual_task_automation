// 발송 노드의 첨부 포트 UI (ADR-0018, 우선 백로그 20 FILE-SEND-4).
//
// 예전에는 파일을 보내려면 앞 노드의 결과 문자열에 `uploads/...` 경로가 우연히 남아 있어야 했다.
// 사용자는 그 규칙을 알 수 없었고, 무엇이 첨부될지 실행 전에는 볼 수도 없었다.
//
// 여기서는 첨부가 명시적이다 — 어떤 파일이, 얼마나 크고, 언제 만료되는지 보여주고, 실제로
// 보내지 않고 검증만 해볼 수 있다. 검증은 런타임과 **같은** 서버 함수를 부른다.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { AlertTriangle, FileCheck2, Paperclip, RefreshCw, X } from 'lucide-react';
import NodeErrorCard from './NodeErrorCard';
import './AttachmentsField.css';

const authHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { headers: { Authorization: `Bearer ${token}` } } : {};
};

const MODES = [
  { value: 'auto', label: '앞 노드가 만든 파일 자동 첨부' },
  { value: 'select', label: '직접 고른 파일만' },
  { value: 'none', label: '첨부하지 않음' },
];

export const formatBytes = (bytes) => {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value}B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)}KB`;
  return `${(value / (1024 * 1024)).toFixed(1)}MB`;
};

const KIND_LABEL = { image: '이미지', pdf: 'PDF', document: '문서', archive: '압축', other: '파일' };

/** 저장된 값이 문자열·배열·객체 어느 모양이든 {mode, artifactIds} 로 읽는다(서버 normalize_config 와 같은 규칙). */
export const readConfig = (raw) => {
  if (Array.isArray(raw)) {
    const ids = raw.map(String).filter(Boolean);
    return { mode: ids.length ? 'select' : 'auto', artifactIds: ids };
  }
  if (raw && typeof raw === 'object') {
    const ids = (raw.artifactIds || []).map(String).filter(Boolean);
    const mode = MODES.some((m) => m.value === raw.mode) ? raw.mode : (ids.length ? 'select' : 'auto');
    return { mode, artifactIds: ids };
  }
  if (typeof raw === 'string' && MODES.some((m) => m.value === raw)) return { mode: raw, artifactIds: [] };
  return { mode: 'auto', artifactIds: [] };
};

/** 만료가 임박했는지 — 하루 안이면 경고한다(첨부해 놨는데 실행 시점에 사라지는 것을 막는다). */
const expiryWarning = (expiresAt) => {
  if (!expiresAt) return null;
  const remaining = new Date(expiresAt).getTime() - Date.now();
  if (Number.isNaN(remaining)) return null;
  if (remaining <= 0) return '만료됨';
  if (remaining < 24 * 60 * 60 * 1000) return '곧 만료';
  return null;
};

export default function AttachmentsField({ id, data, fieldName = 'attachments', provider, help }) {
  const config = useMemo(() => readConfig(data[fieldName]), [data, fieldName]);
  // 아직 저장하지 않은 새 프로젝트면 projectId 가 없다 — 그 경우 소유자 기준으로만 목록을 본다.
  const { projectId } = useParams();

  const [available, setAvailable] = useState([]);
  const [policy, setPolicy] = useState(null);
  const [check, setCheck] = useState(null);   // { ok, error, attachments, totalBytes }
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const commit = useCallback((next) => {
    if (typeof data.onChange === 'function') data.onChange(id, fieldName, next);
    setCheck(null);   // 설정이 바뀌면 이전 검증 결과는 더 이상 이 설정의 결과가 아니다
  }, [data, id, fieldName]);

  const loadFiles = useCallback(async () => {
    setBusy(true);
    try {
      const res = await axios.get('/api/artifacts', {
        ...authHeaders(),
        params: projectId ? { project_id: projectId } : {},
      });
      setAvailable(res.data?.artifacts || []);
    } catch {
      setAvailable([]);
    } finally {
      setBusy(false);
    }
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    axios.get('/api/artifacts/policies')
      .then((res) => { if (!cancelled) setPolicy(res.data?.connectors?.[provider] || null); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [provider]);

  useEffect(() => { if (open) loadFiles(); }, [open, loadFiles]);

  const selected = useMemo(
    () => config.artifactIds
      .map((artifactId) => available.find((item) => item.artifactId === artifactId)
        || (check?.attachments || []).find((item) => item.artifactId === artifactId)
        || { artifactId, filename: artifactId.slice(0, 8), sizeBytes: 0, kind: 'other' })
      .filter(Boolean),
    [config.artifactIds, available, check],
  );

  const totalBytes = selected.reduce((sum, item) => sum + Number(item.sizeBytes || 0), 0);
  const overLimit = policy && totalBytes > policy.maxTotalBytes;
  const overCount = policy && config.artifactIds.length > policy.maxFiles;

  const toggle = (artifactId) => {
    const next = config.artifactIds.includes(artifactId)
      ? config.artifactIds.filter((item) => item !== artifactId)
      : [...config.artifactIds, artifactId];
    commit({ mode: next.length ? 'select' : 'auto', artifactIds: next });
  };

  const validate = async () => {
    setBusy(true);
    try {
      const res = await axios.post('/api/artifacts/validate', {
        provider,
        projectId: projectId ? Number(projectId) : null,
        artifactIds: config.artifactIds,
      }, authHeaders());
      setCheck(res.data);
    } catch (err) {
      setCheck({ ok: false, error: err?.response?.data?.error || null });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="attachments-field nodrag" onClick={(e) => e.stopPropagation()}>
      <label style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <Paperclip size={12} /> 첨부 파일
      </label>

      <select className="nodrag" value={config.mode}
              onChange={(e) => commit({ mode: e.target.value, artifactIds: config.artifactIds })}>
        {MODES.map((mode) => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
      </select>

      {help && <p className="attachments-help">{help}</p>}

      {config.mode === 'select' && (
        <>
          <div className="attachments-chips">
            {selected.length === 0 && <span className="attachments-empty">고른 파일이 없습니다</span>}
            {selected.map((item) => {
              const warning = expiryWarning(item.expiresAt);
              return (
                <span key={item.artifactId} className={`attachments-chip${warning ? ' warn' : ''}`}>
                  <span className="chip-kind">{KIND_LABEL[item.kind] || '파일'}</span>
                  <span className="chip-name" title={item.filename}>{item.filename}</span>
                  <span className="chip-size">{formatBytes(item.sizeBytes)}</span>
                  {warning && <span className="chip-warn"><AlertTriangle size={10} /> {warning}</span>}
                  <button type="button" className="chip-remove" title="첨부에서 빼기"
                          onClick={() => toggle(item.artifactId)}><X size={10} /></button>
                </span>
              );
            })}
          </div>

          {policy && (
            <div className={`attachments-meter${overLimit || overCount ? ' over' : ''}`}>
              <div className="meter-bar">
                <span style={{ width: `${Math.min(100, (totalBytes / policy.maxTotalBytes) * 100)}%` }} />
              </div>
              <span className="meter-text">
                {formatBytes(totalBytes)} / {formatBytes(policy.maxTotalBytes)} ·
                {' '}{config.artifactIds.length}/{policy.maxFiles}개
                {policy.enabled === false && ' · 이 채널의 첨부는 현재 꺼져 있습니다'}
              </span>
            </div>
          )}

          <div className="attachments-actions">
            <button type="button" onClick={() => setOpen((prev) => !prev)}>
              {open ? '파일 목록 닫기' : '파일 고르기'}
            </button>
            <button type="button" onClick={validate} disabled={busy || !config.artifactIds.length}>
              <FileCheck2 size={12} /> 첨부 검증
            </button>
            {open && (
              <button type="button" onClick={loadFiles} disabled={busy} title="목록 새로고침">
                <RefreshCw size={12} />
              </button>
            )}
          </div>

          {open && (
            <ul className="attachments-picker">
              {available.length === 0 && <li className="attachments-empty">고를 수 있는 파일이 없습니다</li>}
              {available.map((item) => (
                <li key={item.artifactId}>
                  <label>
                    <input type="checkbox" className="nodrag"
                           checked={config.artifactIds.includes(item.artifactId)}
                           onChange={() => toggle(item.artifactId)} />
                    <span className="picker-name" title={item.filename}>{item.filename}</span>
                    <span className="picker-meta">{KIND_LABEL[item.kind] || '파일'} · {formatBytes(item.sizeBytes)}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {check && (
        check.ok
          ? <p className="attachments-ok">
              첨부 {check.attachments.length}개 · {formatBytes(check.totalBytes)} — 보낼 수 있습니다
              {' '}(실제로 보내지는 않았습니다)
            </p>
          : <NodeErrorCard error={check.error} />
      )}
    </div>
  );
}
