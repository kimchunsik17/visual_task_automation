// 포맷 탭 (/formats) — 포맷 전용 작업 공간.
//
// 포맷 스튜디오는 원래 에디터 안 모달로만 열렸다. 이 페이지는 (1) 내 포맷 라이브러리 관리
// (목록·복제·삭제 — 스튜디오에는 삭제가 없어 실험 포맷이 쌓이는 문제가 있었다), (2) 프리셋
// 둘러보기, (3) 에디터 밖에서 별도 창/탭으로 포맷 작업, 세 가지를 담당한다.
// 편집 자체는 기존 FormatStudio 를 그대로 재사용한다(여기서 모달로 연다).
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Copy, FileText, LayoutTemplate, Palette, PencilLine, Plus, Trash2 } from 'lucide-react';
import { useAuth } from '../AuthContext';
import { customConfirm } from '../CustomConfirm';
import { timeAgo } from '../timeFormat';
import MainSidebar from '../MainSidebar';
import FormatStudio from '../components/FormatStudio';
import documentFormatsBundle from '../generated/documentFormats.json';
import './MainPage.css';
import './ManagementPage.css';
import './FormatsPage.css';

const LAYOUT_LABELS = { document: '문서', design: '디자인' };

function FormatsPage() {
  const { user, token } = useAuth();
  const [userFormats, setUserFormats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [studioOpen, setStudioOpen] = useState(false);
  const [studioFormatId, setStudioFormatId] = useState('');

  const presets = documentFormatsBundle.formats || [];
  const authHeaders = useCallback(
    () => ({ headers: { Authorization: `Bearer ${token || localStorage.getItem('token')}` } }), [token]);

  const fetchFormats = useCallback(async () => {
    if (!token) { setLoading(false); return; }
    setLoading(true);
    try {
      const res = await axios.get('/api/formats', authHeaders());
      setUserFormats(res.data.formats || []);
    } catch { setUserFormats([]); }
    finally { setLoading(false); }
  }, [token, authHeaders]);

  useEffect(() => { fetchFormats(); }, [fetchFormats]);

  const openStudio = (formatId = '') => { setStudioFormatId(formatId); setStudioOpen(true); };

  const duplicateFormat = async (row) => {
    try {
      await axios.post('/api/formats', { name: `${row.name} (복사본)`, spec: row.spec }, authHeaders());
      fetchFormats();
      window.dispatchEvent(new Event('formats-library-changed'));
    } catch (error) {
      alert('복제 실패: ' + (error.response?.data?.detail || error.message));
    }
  };

  const deleteFormat = async (row) => {
    if (!(await customConfirm(`'${row.name}' 포맷을 삭제할까요? 이 포맷을 쓰는 노드는 실행 시 "포맷을 찾을 수 없습니다"로 멈춥니다.`))) return;
    try {
      await axios.delete(`/api/formats/${row.id}`, authHeaders());
      setUserFormats((prev) => prev.filter((f) => f.id !== row.id));
      window.dispatchEvent(new Event('formats-library-changed'));
    } catch (error) {
      alert('삭제 실패: ' + (error.response?.data?.detail || error.message));
    }
  };

  const fieldCount = (row) => (row.spec?.fields || []).length;

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <main className="main-page-content management-page">
        <div className="management-content">
          <header className="management-header">
            <div className="management-heading">
              <span className="management-kicker">FORMATS</span>
              <h1>포맷</h1>
              <p>문서·포스터의 골격과 빈칸을 만들어 두면, 워크플로우의 문서 포맷 노드가 값을 채워 완성 파일을 만듭니다.</p>
            </div>
            <div className="management-header-side" aria-label="포맷 요약">
              <div className="management-stat"><span>내 포맷</span><strong>{userFormats.length}</strong></div>
              <div className="management-stat"><span>프리셋</span><strong>{presets.length}</strong></div>
              <button className="management-button primary" onClick={() => openStudio('')}>
                <Plus size={15} /> 새 포맷
              </button>
            </div>
          </header>

          <section className="formats-section">
            <h2 className="formats-section-title">내 포맷</h2>
            {!user ? (
              <div className="management-empty"><h2>로그인이 필요합니다</h2><p>로그인 후 내 포맷을 관리할 수 있습니다.</p></div>
            ) : loading ? (
              <div className="management-loading" aria-label="포맷을 불러오는 중">{[0, 1, 2].map((i) => <span key={i} />)}</div>
            ) : userFormats.length === 0 ? (
              <div className="management-empty">
                <span className="management-empty-icon"><LayoutTemplate size={20} /></span>
                <h2>아직 만든 포맷이 없습니다</h2>
                <p>새 포맷을 만들거나, 아래 프리셋을 복제해 시작하세요. 갖고 있는 서식 파일(.hwpx/.docx)을 스튜디오에서 가져올 수도 있습니다.</p>
                <button className="management-button primary" onClick={() => openStudio('')}><Plus size={14} /> 첫 포맷 만들기</button>
              </div>
            ) : (
              <div className="formats-grid">
                {userFormats.map((row) => (
                  <article key={row.id} className="formats-card">
                    <div className="formats-card-head">
                      <span className={`formats-layout-badge ${row.layout}`}>
                        {row.layout === 'design' ? <Palette size={12} /> : <FileText size={12} />}
                        {LAYOUT_LABELS[row.layout] || row.layout}
                      </span>
                      {row.updated_at && <span className="formats-updated">{timeAgo(row.updated_at)}</span>}
                    </div>
                    <h3 className="formats-card-name">{row.name}</h3>
                    <p className="formats-card-meta">빈칸 {fieldCount(row)}개 · 출력 {(row.spec?.output?.allowed || []).join(' · ')}</p>
                    <div className="formats-card-actions">
                      <button type="button" onClick={() => openStudio(row.id)}><PencilLine size={13} /> 편집</button>
                      <button type="button" onClick={() => duplicateFormat(row)}><Copy size={13} /> 복제</button>
                      <button type="button" className="danger" onClick={() => deleteFormat(row)}><Trash2 size={13} /> 삭제</button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="formats-section">
            <h2 className="formats-section-title">프리셋 {presets.length}종 <em>복제해서 내 포맷으로 시작합니다</em></h2>
            <div className="formats-grid">
              {presets.map((preset) => (
                <article key={preset.id} className="formats-card preset">
                  <div className="formats-card-head">
                    <span className={`formats-layout-badge ${preset.layout}`}>
                      {preset.layout === 'design' ? <Palette size={12} /> : <FileText size={12} />}
                      {LAYOUT_LABELS[preset.layout] || preset.layout}
                    </span>
                  </div>
                  <h3 className="formats-card-name">{preset.name}</h3>
                  <p className="formats-card-desc">{preset.description}</p>
                  <div className="formats-card-actions">
                    <button type="button" onClick={() => openStudio(preset.id)}><Copy size={13} /> 복제해서 시작</button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </main>

      <FormatStudio
        isOpen={studioOpen}
        onClose={() => { setStudioOpen(false); fetchFormats(); }}
        initialFormatId={studioFormatId}
        onLibraryChanged={fetchFormats}
      />
    </div>
  );
}

export default FormatsPage;
