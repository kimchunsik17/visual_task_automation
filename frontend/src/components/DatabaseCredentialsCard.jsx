// API 센터의 Database 카드 (ADR-0017 DB-1) — 명명된 자격증명 여러 개를 등록·테스트·삭제한다.
//
// 다른 provider 카드는 "provider 당 값 하나" 이지만 Database 는 개발/운영 DB 처럼 여러 개를 이름으로
// 구분해야 한다. 생성·삭제는 다른 키와 같이 sudo 토큰이 필요하고, 목록·연결 테스트는 비밀값을
// 돌려주지 않으므로 일반 토큰으로 부른다.
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Info, Plug, Plus, Save, Trash2 } from 'lucide-react';
import { Icon } from '../icons';
import { customConfirm } from '../CustomConfirm';
import NodeErrorCard from './NodeErrorCard';
import { invalidateCredentialCache } from './DatabaseQueryPanel';

export default function DatabaseCredentialsCard({ provider, token, sudoToken, focused, onGuide }) {
  const [credentials, setCredentials] = useState([]);
  const [label, setLabel] = useState('');
  const [uri, setUri] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [tests, setTests] = useState({});

  const authHeaders = useCallback((sudo = false) => ({ headers: { Authorization: `Bearer ${sudo ? sudoToken : token}` } }), [token, sudoToken]);

  const refresh = useCallback(async () => {
    try {
      const res = await axios.get('/api/database/credentials', authHeaders());
      setCredentials(res.data?.credentials || []);
      invalidateCredentialCache();
    } catch {
      setCredentials([]);
    }
  }, [authHeaders]);

  useEffect(() => { refresh(); }, [refresh]);

  const save = async () => {
    if (!uri.trim()) return;
    setSaving(true);
    setFormError('');
    try {
      await axios.post('/api/database/credentials', { label: label.trim(), connection_string: uri.trim() }, authHeaders(true));
      setLabel('');
      setUri('');
      await refresh();
    } catch (error) {
      setFormError(error.response?.data?.detail || '저장에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (credential) => {
    if (!(await customConfirm(`"${credential.label || `#${credential.id}`}" 자격증명을 삭제할까요? 이 자격증명을 쓰는 데이터베이스 노드는 실행되지 않습니다.`))) return;
    try {
      await axios.delete(`/api/database/credentials/${credential.id}`, authHeaders(true));
      await refresh();
    } catch {
      alert('삭제에 실패했습니다.');
    }
  };

  const test = async (credential) => {
    setTests((t) => ({ ...t, [credential.id]: { loading: true } }));
    try {
      const res = await axios.post(`/api/database/credentials/${credential.id}/test`, {}, authHeaders());
      setTests((t) => ({ ...t, [credential.id]: res.data }));
    } catch (error) {
      setTests((t) => ({ ...t, [credential.id]: { ok: false, stages: [], error: { code: 'INTERNAL_UNKNOWN', category: 'runtime', userMessage: error.response?.data?.detail || '연결 테스트에 실패했습니다.' } } }));
    }
  };

  return (
    <div id={`provider-${provider.id}`} className={`api-card ${credentials.length ? 'has-key' : ''} ${focused ? 'provider-focus' : ''}`}>
      <div className="api-card-header">
        <div className="api-card-title">
          <span className="api-icon"><Icon name={provider.icon} size={24} /></span>
          <h3>{provider.name}</h3>
        </div>
        <button className="guide-btn" onClick={onGuide}><Info size={16} /> 발급 가이드</button>
      </div>
      <div className="api-card-body">
        {credentials.length === 0 && <div className="db-cred-empty">등록된 접속 문자열이 없습니다. 읽기 전용 계정의 PostgreSQL URI 를 이름과 함께 추가하세요.</div>}
        {credentials.map((credential) => {
          const result = tests[credential.id];
          return (
            <div key={credential.id} className="db-cred-row">
              <div className="db-cred-main">
                <div className="db-cred-label">{credential.label || <i>이름 없음 (기본)</i>}</div>
                <div className="db-cred-meta">{credential.dialect || '?'} · {credential.host || '?'}{credential.database ? `/${credential.database}` : ''} · <code>{credential.reference}</code></div>
                {result && !result.loading && (
                  <div className="db-cred-stages">
                    {(result.stages || []).map((stage) => (
                      <span key={stage.stage} className={`db-cred-stage ${stage.ok ? 'ok' : 'fail'}`} title={stage.message}>{stage.stage}</span>
                    ))}
                    {result.ok ? <span className="db-cred-ok">연결 확인</span> : (result.error && <NodeErrorCard error={result.error} compact />)}
                  </div>
                )}
              </div>
              <div className="db-cred-actions">
                <button className="save-key-btn" disabled={result?.loading} onClick={() => test(credential)}><Plug size={14} /> {result?.loading ? '확인 중…' : '연결 테스트'}</button>
                <button className="delete-key-btn" onClick={() => remove(credential)}><Trash2 size={14} /> 삭제</button>
              </div>
            </div>
          );
        })}
        <div className="key-input-area db-cred-form">
          <input type="text" placeholder="이름 (예: 운영 DB, 분석용 replica)" value={label} onChange={(e) => setLabel(e.target.value)} />
          <input type="password" placeholder={provider.secretFormat || 'postgresql://user:password@host:5432/dbname'} value={uri} onChange={(e) => setUri(e.target.value)} />
          {formError && <div className="db-cred-error">{formError}</div>}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="save-key-btn" disabled={!uri.trim() || saving} onClick={save}><Save size={16} /> {saving ? '저장 중…' : '추가'}</button>
            <span className="db-cred-hint"><Plus size={12} /> 여러 DB 를 이름으로 구분해 등록할 수 있습니다. 노드에서 하나를 선택합니다.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
