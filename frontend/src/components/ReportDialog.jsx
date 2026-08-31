// 신고 창. 대상 종류를 가리지 않는다 — 서버의 reports 표가 하나이므로 화면도 하나여야
// 운영자가 한 큐에서 판단할 수 있다(ADR-0020).
import { useState } from 'react';
import axios from 'axios';
import { Flag, X } from 'lucide-react';
import './ReportDialog.css';

const REASONS = [
  { id: 'spam', label: '스팸·광고' },
  { id: 'harassment', label: '괴롭힘·욕설' },
  { id: 'inappropriate', label: '부적절한 내용' },
  { id: 'copyright', label: '저작권 침해' },
  { id: 'other', label: '기타' },
];

export default function ReportDialog({ targetType, targetId, token, onClose }) {
  const [reason, setReason] = useState('spam');
  const [detail, setDetail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      await axios.post('/api/community/reports',
                       { targetType, targetId, reason, detail: detail.trim() || null },
                       token ? { headers: { Authorization: `Bearer ${token}` } } : {});
      setDone(true);
    } catch (e) {
      setError(e.response?.data?.detail || '신고를 접수하지 못했습니다.');
    } finally { setBusy(false); }
  };

  return (
    <div className="report-backdrop" onClick={onClose} role="presentation">
      <div className="report-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true"
           aria-label="신고하기">
        <div className="report-head">
          <h2><Flag size={16} /> 신고하기</h2>
          <button type="button" onClick={onClose} aria-label="닫기"><X size={16} /></button>
        </div>

        {done ? (
          <div className="report-done">
            <p>신고가 접수됐습니다. 운영자가 확인한 뒤 조치합니다.</p>
            <button type="button" className="management-button primary" onClick={onClose}>확인</button>
          </div>
        ) : (
          <>
            <p className="report-note">
              무엇이 문제인지 골라주세요. 접수된 신고는 운영자만 볼 수 있습니다.
            </p>
            <div className="report-reasons">
              {REASONS.map((r) => (
                <label key={r.id} className={reason === r.id ? 'is-on' : ''}>
                  <input type="radio" name="report-reason" value={r.id}
                         checked={reason === r.id} onChange={() => setReason(r.id)} />
                  {r.label}
                </label>
              ))}
            </div>
            <label className="report-label" htmlFor="report-detail">덧붙일 말 (선택)</label>
            <textarea id="report-detail" rows={3} value={detail}
                      onChange={(e) => setDetail(e.target.value)}
                      placeholder="어떤 점이 문제인지 알려주시면 판단에 도움이 됩니다." />
            {error && <p className="report-error">{error}</p>}
            <div className="report-foot">
              <button type="button" className="management-button" onClick={onClose}>취소</button>
              <button type="button" className="management-button primary" onClick={submit} disabled={busy}>
                {busy ? '접수 중…' : '신고 접수'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
