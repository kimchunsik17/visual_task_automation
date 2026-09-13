// 실패 시 실행할 워크플로우(ENGINE-3 3단계, ADR-0030 추기) — graph_data.errorWorkflowId 를 고른다.
//
// 실행이 failed 로 끝나면 서버(error_trigger.py)가 여기서 고른 워크플로우를 부른다. 그 워크플로우는 default_input 으로
// 실패 payload JSON(failedProjectId·errorSummary·failedNodes …)을 받으므로 "웹훅/시작 → 알림 노드" 모양이면 된다.
// 같은 소유자의 프로젝트만 고를 수 있다 — 서버도 소유자가 다르면 무시한다.
import { useEffect, useState } from 'react';
import axios from 'axios';
import { X, Siren } from 'lucide-react';

export default function ErrorWorkflowModal({ isOpen, onClose, currentProjectId, value, token, onSave }) {
  const [projects, setProjects] = useState([]);
  const [selected, setSelected] = useState(value ? String(value) : '');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen) return undefined;
    let cancelled = false;
    setSelected(value ? String(value) : '');
    setError(null);
    setLoading(true);
    axios.get('/api/projects/my', { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res.data) ? res.data : (res.data?.projects || []);
        setProjects(list.filter((project) => String(project.id) !== String(currentProjectId)));
      })
      .catch(() => { if (!cancelled) setError('워크플로우 목록을 불러오지 못했습니다.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [isOpen, token, currentProjectId, value]);

  if (!isOpen) return null;

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(selected ? Number(selected) : null);
      onClose();
    } catch {
      setError('저장에 실패했습니다. 잠시 뒤 다시 시도하세요.');
    } finally {
      setSaving(false);
    }
  };

  const current = projects.find((project) => String(project.id) === selected);

  return (
    <div className="modal-overlay" onClick={onClose}
      style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="modal-content" onClick={(event) => event.stopPropagation()}
        style={{ backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', width: '520px', maxWidth: '92vw', padding: '1.5rem', position: 'relative', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <button type="button" onClick={onClose} aria-label="닫기"
          style={{ position: 'absolute', top: 12, right: 12, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary, #888)' }}>
          <X size={18} />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Siren size={20} color="var(--ts-danger, #ef4444)" />
          <h3 style={{ margin: 0 }}>실패 시 실행할 워크플로우</h3>
        </div>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary, #888)', lineHeight: 1.5 }}>
          이 워크플로우의 실행이 실패로 끝나면 아래 워크플로우가 자동으로 돕니다. 그 워크플로우는 시작 입력으로 실패 내용
          (어느 노드가 어떤 오류로 실패했는지)을 JSON 으로 받으므로, 웹훅/시작 노드 뒤에 메일·슬랙 같은 알림 노드를 이어 두면 됩니다.
          알림 워크플로우 자신의 실패는 다시 알리지 않습니다.
        </p>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
          <span>워크플로우</span>
          <select value={selected} onChange={(event) => setSelected(event.target.value)} disabled={loading}
            style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--input-bg, transparent)', color: 'inherit' }}>
            <option value="">없음 — 실패해도 아무것도 하지 않음</option>
            {projects.map((project) => (
              <option key={project.id} value={String(project.id)}>#{project.id} · {project.title || '제목 없음'}</option>
            ))}
          </select>
          {loading && <small style={{ color: 'var(--text-secondary, #888)' }}>목록을 불러오는 중…</small>}
          {!loading && projects.length === 0 && <small style={{ color: 'var(--text-secondary, #888)' }}>다른 워크플로우가 없습니다 — 알림용 워크플로우를 먼저 만들어 두세요.</small>}
          {current && <small style={{ color: 'var(--text-secondary, #888)' }}>선택: #{current.id} {current.title}</small>}
        </label>
        {error && <div style={{ color: 'var(--ts-danger, #ef4444)', fontSize: 13 }}>{error}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>취소</button>
          <button type="button" className="btn-primary" onClick={save} disabled={saving || loading}>{saving ? '저장 중…' : '저장'}</button>
        </div>
      </div>
    </div>
  );
}
