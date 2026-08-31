// Database Query v2 노드 UI (ADR-0017, 우선 백로그 19 DB-3).
//
// 노드 본문에서 자격증명 선택 → 연결 테스트 → schema 탐색 → 쿼리 → 파라미터 → Test step 까지
// 한 흐름으로 끝나게 한다. 서버는 어떤 응답에도 접속 문자열을 싣지 않는다 — 여기서 보이는 것은
// label·host·database 이름과 구조화 오류(NodeError v1)뿐이다.
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { ChevronDown, ChevronRight, Play, Plug, Plus, RefreshCw, Table2, Trash2 } from 'lucide-react';
import { getFieldDefault, getFieldOptions } from '../nodeDefinitions';
import NodeErrorCard from './NodeErrorCard';
import './DatabaseQueryPanel.css';

export const DEFAULT_DB_REF = '{{API_CENTER:database}}';
const REF_RE = /^\{\{API_CENTER:database(?:#(\d+))?\}\}$/;

export const referenceFor = (credentialId) =>
  (credentialId === null || credentialId === undefined || credentialId === '')
    ? DEFAULT_DB_REF
    : `{{API_CENTER:database#${credentialId}}}`;

/** reference 가 아니면 undefined, 기본 reference 면 null, 아니면 credential id */
export const credentialIdFromReference = (reference) => {
  const match = REF_RE.exec(String(reference || '').trim());
  if (!match) return undefined;
  return match[1] ? Number(match[1]) : null;
};

const authHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { headers: { Authorization: `Bearer ${token}` } } : {};
};

let featuresPromise = null;
export const loadFeatures = () => {
  if (!featuresPromise) {
    featuresPromise = axios.get('/api/features').then((res) => res.data || {}).catch(() => ({}));
  }
  return featuresPromise;
};

export const useFeatures = () => {
  const [features, setFeatures] = useState(null);
  useEffect(() => {
    let alive = true;
    loadFeatures().then((data) => { if (alive) setFeatures(data); });
    return () => { alive = false; };
  }, []);
  return features;
};

let credentialsPromise = null;
const loadCredentials = (force = false) => {
  if (force || !credentialsPromise) {
    credentialsPromise = axios.get('/api/database/credentials', authHeaders())
      .then((res) => res.data?.credentials || [])
      .catch(() => []);
  }
  return credentialsPromise;
};
export const invalidateCredentialCache = () => { credentialsPromise = null; };

const Section = ({ title, icon, open, onToggle, right, children }) => (
  <div className="dbq-section">
    <div className="dbq-section-head" onClick={onToggle} role="button" tabIndex={0}>
      {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      {icon}
      <span>{title}</span>
      <span className="dbq-section-right">{right}</span>
    </div>
    {open && <div className="dbq-section-body nodrag">{children}</div>}
  </div>
);

// ── 연결: 자격증명 선택 · 연결 테스트 · schema 탐색 ────────────────────────────
export const DatabaseConnectionPanel = ({ id, data, onInsertSql }) => {
  const reference = data.connectionString || '';
  const selectedId = credentialIdFromReference(reference);
  const isReference = selectedId !== undefined;
  const [credentials, setCredentials] = useState(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [schema, setSchema] = useState(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [openTables, setOpenTables] = useState({});

  useEffect(() => {
    let alive = true;
    loadCredentials().then((list) => { if (alive) setCredentials(list); });
    return () => { alive = false; };
  }, []);

  // 실제로 접속할 자격증명 — 기본 reference 는 등록된 것이 하나일 때만 뜻이 있다.
  const effective = useMemo(() => {
    if (!credentials) return null;
    if (selectedId) return credentials.find((c) => c.id === selectedId) || null;
    return credentials.length === 1 ? credentials[0] : null;
  }, [credentials, selectedId]);
  const ambiguous = isReference && selectedId === null && (credentials?.length || 0) > 1;

  const commit = (value) => data.onChange && data.onChange(id, 'connectionString', value);

  const runTest = async () => {
    if (!effective) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await axios.post(`/api/database/credentials/${effective.id}/test`, {}, authHeaders());
      setTestResult(res.data);
    } catch (error) {
      setTestResult({ ok: false, stages: [], error: { code: 'INTERNAL_UNKNOWN', category: 'runtime', userMessage: error.response?.data?.detail || '연결 테스트 요청에 실패했습니다.' } });
    } finally {
      setTesting(false);
    }
  };

  const loadSchema = async (refresh = false) => {
    if (!effective) return;
    setSchemaLoading(true);
    try {
      const schemaName = String(data.allowedSchemas || 'public').split(',')[0].trim() || 'public';
      const res = await axios.get(`/api/database/credentials/${effective.id}/schema`, { ...authHeaders(), params: { schema: schemaName, refresh } });
      setSchema(res.data);
      setSchemaOpen(true);
    } catch (error) {
      setSchema({ ok: false, tables: [], error: { code: 'INTERNAL_UNKNOWN', category: 'runtime', userMessage: error.response?.data?.detail || 'schema 를 불러오지 못했습니다.' } });
    } finally {
      setSchemaLoading(false);
    }
  };

  return (
    <div className="dbq-panel">
      <label>DB 연결 (읽기 전용)</label>
      {!isReference && reference && (
        <div className="dbq-warning">
          보안을 위해 노드에 직접 입력한 접속 문자열은 더 이상 실행되지 않습니다.
          <button type="button" className="dbq-btn nodrag" onClick={() => commit(DEFAULT_DB_REF)}>API 센터 자격증명 사용</button>
        </div>
      )}
      {credentials && credentials.length === 0 && (
        <div className="dbq-warning">
          등록된 Database 자격증명이 없습니다. <a href="/settings/api-center?provider=database" target="_blank" rel="noreferrer">API 센터</a>에서 읽기 전용 접속 문자열을 등록하세요.
        </div>
      )}
      <div className="dbq-row">
        <select
          className="nodrag"
          value={selectedId ? String(selectedId) : ''}
          onChange={(e) => commit(referenceFor(e.target.value || null))}
        >
          <option value="">{(credentials?.length || 0) > 1 ? '자격증명을 선택하세요' : '기본 자격증명'}</option>
          {(credentials || []).map((c) => (
            <option key={c.id} value={String(c.id)}>
              {c.label || `#${c.id}`}{c.host ? ` · ${c.host}${c.database ? `/${c.database}` : ''}` : ''}
            </option>
          ))}
        </select>
        <button type="button" className="dbq-btn nodrag" disabled={!effective || testing} onClick={runTest} title="driver → dns → tcp → auth → read-only 순서로 확인합니다">
          <Plug size={12} /> {testing ? '확인 중…' : '연결 테스트'}
        </button>
      </div>
      {ambiguous && <div className="dbq-warning">자격증명이 여러 개입니다 — 실행하려면 하나를 선택해야 합니다.</div>}
      {effective && (
        <div className="dbq-muted">
          {effective.dialect || '?'} · {effective.host || '?'}{effective.database ? `/${effective.database}` : ''}
        </div>
      )}
      {testResult && (
        <div className="dbq-stages">
          {(testResult.stages || []).map((stage) => (
            <div key={stage.stage} className={`dbq-stage ${stage.ok ? 'ok' : 'fail'}`}>
              <span className="dbq-stage-dot" />
              <b>{stage.stage}</b>
              <span>{stage.message}</span>
            </div>
          ))}
          {testResult.ok
            ? <div className="dbq-ok">연결·인증·읽기 전용 조회가 모두 확인됐습니다.</div>
            : testResult.error && <NodeErrorCard error={testResult.error} compact />}
        </div>
      )}

      <Section
        title="테이블·컬럼"
        icon={<Table2 size={12} />}
        open={schemaOpen}
        onToggle={() => { setSchemaOpen((v) => !v); if (!schema && effective) loadSchema(false); }}
        right={effective && (
          <button type="button" className="dbq-link nodrag" disabled={schemaLoading} onClick={(e) => { e.stopPropagation(); loadSchema(true); }}>
            <RefreshCw size={11} /> {schemaLoading ? '불러오는 중…' : '새로 고침'}
          </button>
        )}
      >
        {!effective && <div className="dbq-muted">자격증명을 먼저 선택하세요.</div>}
        {schema && !schema.ok && schema.error && <NodeErrorCard error={schema.error} compact />}
        {schema && schema.ok && schema.tables.length === 0 && <div className="dbq-muted">schema "{schema.schema}" 에 테이블이 없습니다.</div>}
        {schema && schema.ok && schema.tables.map((table) => (
          <div key={`${table.schema}.${table.name}`} className="dbq-table">
            <div className="dbq-table-head">
              <button type="button" className="dbq-link nodrag" onClick={() => setOpenTables((o) => ({ ...o, [table.name]: !o[table.name] }))}>
                {openTables[table.name] ? <ChevronDown size={11} /> : <ChevronRight size={11} />} {table.name}
                <span className="dbq-muted"> {table.kind}</span>
              </button>
              {onInsertSql && (
                <button type="button" className="dbq-link nodrag" title="이 테이블을 조회하는 쿼리를 넣습니다" onClick={() => onInsertSql(`SELECT * FROM ${table.name} LIMIT 100`, 'query')}>
                  쿼리로
                </button>
              )}
            </div>
            {openTables[table.name] && (
              <div className="dbq-columns">
                {table.columns.map((column) => (
                  <button key={column.name} type="button" className="dbq-chip nodrag" title={`${column.type}${column.nullable ? ' · null 허용' : ''}`}
                    onClick={() => onInsertSql && onInsertSql(column.name, 'append')}>
                    {column.name} <span className="dbq-muted">{column.type}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {schema?.cached && <div className="dbq-muted">캐시된 결과 (최대 {Math.round((schema.ttl_seconds || 300) / 60)}분)</div>}
      </Section>
    </div>
  );
};

// ── 파라미터 · 고급 설정 · Test step ─────────────────────────────────────────
const TYPE_OPTIONS = getFieldOptions('databaseNode', 'parameters.type');
const SOURCE_OPTIONS = getFieldOptions('databaseNode', 'parameters.source');
const OUTPUT_OPTIONS = getFieldOptions('databaseNode', 'outputFormat');

const newParameter = () => ({
  name: '', source: getFieldDefault('databaseNode', 'parameters.source') || 'value', value: '', path: '',
  type: getFieldDefault('databaseNode', 'parameters.type') || 'string', required: true,
});

export const DatabaseQueryToolsPanel = ({ id, data }) => {
  const parameters = Array.isArray(data.parameters) ? data.parameters : [];
  const [paramsOpen, setParamsOpen] = useState(parameters.length > 0);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [testValues, setTestValues] = useState({});
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState(null);

  const commit = useCallback((key, value) => data.onChange && data.onChange(id, key, value), [data, id]);
  const updateParameter = (index, patch) => commit('parameters', parameters.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  const removeParameter = (index) => commit('parameters', parameters.filter((_, i) => i !== index));

  const inputParameters = parameters.filter((p) => p.source === 'input');

  const runPreview = async () => {
    setPreviewing(true);
    setPreview(null);
    try {
      const res = await axios.post('/api/database/preview', {
        connection_string: data.connectionString || DEFAULT_DB_REF,
        query: data.query || '',
        parameters,
        parameter_values: Object.fromEntries(inputParameters.filter((p) => p.name).map((p) => [p.name, testValues[p.name] ?? ''])),
        max_rows: Math.min(Number(data.maxRows) || 100, 50),
        timeout_seconds: Number(data.timeoutSeconds) || 10,
        allowed_schemas: data.allowedSchemas || 'public',
        output_format: 'rows',
      }, authHeaders());
      setPreview(res.data);
    } catch (error) {
      setPreview({ ok: false, error: { code: 'INTERNAL_UNKNOWN', category: 'runtime', userMessage: error.response?.data?.detail || '미리보기 요청에 실패했습니다.' } });
    } finally {
      setPreviewing(false);
    }
  };

  const previewColumns = preview?.data?.columns || [];
  const previewRows = (preview?.data?.rows || []).slice(0, 20);

  return (
    <div className="dbq-panel">
      <Section
        title={`쿼리 파라미터${parameters.length ? ` (${parameters.length})` : ''}`}
        open={paramsOpen}
        onToggle={() => setParamsOpen((v) => !v)}
        right={<button type="button" className="dbq-link nodrag" onClick={(e) => { e.stopPropagation(); setParamsOpen(true); commit('parameters', [...parameters, newParameter()]); }}><Plus size={11} /> 추가</button>}
      >
        <div className="dbq-muted">쿼리에는 <code>:이름</code> 으로 적고 값은 여기서 바인드합니다. 문자열을 이어붙이지 마세요.</div>
        {parameters.map((param, index) => (
          <div key={index} className="dbq-param">
            <input className="nodrag" placeholder="이름" value={param.name || ''} onChange={(e) => updateParameter(index, { name: e.target.value.replace(/[^A-Za-z0-9_]/g, '_') })} />
            <select className="nodrag" value={param.source || 'value'} onChange={(e) => updateParameter(index, { source: e.target.value })}>
              {SOURCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            {param.source === 'input' ? (
              <input className="nodrag" placeholder="JSON 경로 (비우면 전체)" value={param.path || ''} onChange={(e) => updateParameter(index, { path: e.target.value })} />
            ) : (
              <input className="nodrag" placeholder="값" value={param.value ?? ''} onChange={(e) => updateParameter(index, { value: e.target.value })} />
            )}
            <select className="nodrag" value={param.type || 'string'} onChange={(e) => updateParameter(index, { type: e.target.value })}>
              {TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <label className="dbq-check" title="비어 있으면 실행 전에 오류로 알립니다">
              <input type="checkbox" className="nodrag" checked={param.required !== false} onChange={(e) => updateParameter(index, { required: e.target.checked })} /> 필수
            </label>
            <button type="button" className="dbq-icon-btn nodrag" onClick={() => removeParameter(index)} title="삭제"><Trash2 size={12} /></button>
          </div>
        ))}
      </Section>

      <Section title="고급 설정" open={advancedOpen} onToggle={() => setAdvancedOpen((v) => !v)}>
        <div className="dbq-grid">
          <label>최대 행 수
            <input type="number" min={1} max={1000} className="nodrag" value={data.maxRows ?? 100} onChange={(e) => commit('maxRows', Number(e.target.value))} />
          </label>
          <label>제한 시간(초)
            <input type="number" min={1} max={30} className="nodrag" value={data.timeoutSeconds ?? 10} onChange={(e) => commit('timeoutSeconds', Number(e.target.value))} />
          </label>
          <label>허용 schema
            <input className="nodrag" value={data.allowedSchemas ?? 'public'} placeholder="public, sales" onChange={(e) => commit('allowedSchemas', e.target.value)} />
          </label>
          <label>출력 형식
            <select className="nodrag" value={data.outputFormat || 'rows'} onChange={(e) => commit('outputFormat', e.target.value)}>
              {OUTPUT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
        </div>
        <div className="dbq-muted">"구조화 결과"는 다음 노드가 <code>ok</code>·<code>data.rows</code>·<code>error</code> 를 JSON 으로 읽어야 할 때 고릅니다.</div>
      </Section>

      <Section
        title="쿼리 테스트"
        icon={<Play size={12} />}
        open={previewOpen}
        onToggle={() => setPreviewOpen((v) => !v)}
        right={<button type="button" className="dbq-btn nodrag" disabled={previewing || !(data.query || '').trim()} onClick={(e) => { e.stopPropagation(); setPreviewOpen(true); runPreview(); }}><Play size={11} /> {previewing ? '실행 중…' : '실행'}</button>}
      >
        {inputParameters.length > 0 && (
          <div className="dbq-test-values">
            <div className="dbq-muted">직전 노드 출력에서 오는 파라미터의 시험 값</div>
            {inputParameters.map((p) => (
              <label key={p.name || Math.random()}>:{p.name}
                <input className="nodrag" value={testValues[p.name] ?? ''} onChange={(e) => setTestValues((v) => ({ ...v, [p.name]: e.target.value }))} />
              </label>
            ))}
          </div>
        )}
        {preview && preview.ok && (
          <>
            <div className="dbq-muted">
              {preview.data.rowCount}행{preview.data.truncated ? ' (잘림)' : ''} · {preview.data.durationMs}ms · {preview.data.dialect}
              {previewRows.length < preview.data.rowCount ? ` · 처음 ${previewRows.length}행 표시` : ''}
            </div>
            <div className="dbq-table-wrap">
              <table className="dbq-result">
                <thead><tr>{previewColumns.map((c) => <th key={c.name} title={c.type || ''}>{c.name}</th>)}</tr></thead>
                <tbody>
                  {previewRows.map((row, i) => (
                    <tr key={i}>{previewColumns.map((c) => <td key={c.name}>{row[c.name] === null || row[c.name] === undefined ? <i>null</i> : (typeof row[c.name] === 'object' ? JSON.stringify(row[c.name]) : String(row[c.name]))}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {preview && !preview.ok && preview.error && <NodeErrorCard error={preview.error} nodeId={id} nodeType="databaseNode" onNavigate={(target) => window.open(target, '_blank', 'noreferrer')} compact />}
        {!preview && !previewing && <div className="dbq-muted">저장하지 않고 이 쿼리를 한 번 실행해 결과와 오류를 확인합니다.</div>}
      </Section>
    </div>
  );
};
