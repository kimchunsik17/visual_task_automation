import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { customConfirm } from '../CustomConfirm';
import { formatManagementDate } from './managementFormatters';
import MainSidebar from '../MainSidebar';
import { readListCache, writeListCache } from '../listCache';
import { ExternalLink, LayoutTemplate, PencilLine, Plus, Trash2 } from 'lucide-react';
import './MainPage.css';
import './ManagementPage.css';

const CustomAppsDashboardPage = () => {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  // 재방문 첫 프레임부터 마지막 목록을 그린다(listCache.js) — 출렁임 방지.
  const cacheKey = `custom-apps:${user?.id ?? user?.email ?? 'anon'}`;
  const [apps, setAppsState] = useState(() => readListCache(cacheKey) ?? []);
  const [loading, setLoading] = useState(() => readListCache(cacheKey) === null);
  // 목록이 바뀌는 모든 경로(조회·삭제)가 캐시도 함께 갱신한다.
  const setApps = (next) => {
    setAppsState((prev) => {
      const resolved = typeof next === 'function' ? next(prev) : next;
      writeListCache(cacheKey, resolved);
      return resolved;
    });
  };

  useEffect(() => {
    if (!token) return;
    const fetchApps = async () => {
      try {
        const res = await axios.get('/api/apps/custom', {
          headers: { Authorization: `Bearer ${token}` }
        });
        setApps(res.data);
      } catch (err) {
        console.error('Failed to fetch custom apps', err);
      } finally {
        setLoading(false);
      }
    };
    fetchApps();
  }, [token]);

  const handleDeleteApp = async (e, appId) => {
    e.stopPropagation();
    if (!(await customConfirm("정말로 이 앱을 삭제하시겠습니까?"))) return;
    try {
      await axios.delete(`/api/apps/custom/${appId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setApps(prev => prev.filter(a => a.id !== appId));
    } catch (err) {
      alert("앱 삭제 중 오류가 발생했습니다.");
    }
  };

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <main className="main-page-content management-page">
        <div className="management-content">
          <header className="management-header">
            <div className="management-heading">
              <span className="management-kicker">CUSTOM APPS</span>
              <h1>내 커스텀 앱</h1>
              <p>직접 구성한 화면과 연결된 워크플로우를 관리하고, 실제 사용자 화면을 바로 확인하세요.</p>
            </div>
            <div className="management-header-side" aria-label="커스텀 앱 요약">
              <div className="management-stat"><span>전체 앱</span><strong>{apps.length}</strong></div>
              <button className="management-button primary" onClick={() => navigate('/app-builder')}><Plus size={15} /> 새 앱 만들기</button>
            </div>
          </header>

          <div className="management-toolbar">
            <span className="management-toolbar-label">앱을 편집하거나 배포된 화면을 새 창에서 확인할 수 있습니다.</span>
          </div>

          {loading && apps.length === 0 ? (
            <div className="management-loading" aria-label="앱을 불러오는 중">{[0, 1, 2, 3].map(item => <span key={item} />)}</div>
          ) : apps.length === 0 ? (
            <div className="management-empty">
              <span className="management-empty-icon"><LayoutTemplate size={20} /></span>
              <h2>아직 만든 앱이 없습니다</h2>
              <p>워크플로우에 화면을 더하면 팀과 고객이 바로 사용할 수 있는 앱이 됩니다.</p>
              <button className="management-button primary" onClick={() => navigate('/app-builder')}><Plus size={14} /> 첫 앱 만들기</button>
            </div>
          ) : (
            <div className="management-grid">
              {apps.map(app => (
                <article key={app.id} className="management-card">
                  <div className="management-card-body">
                    <div className="management-card-top">
                      <span className="management-resource"><span className="management-resource-icon"><LayoutTemplate size={14} /></span> CUSTOM APP</span>
                      <div className="management-card-tools">
                        <span className="management-status"><span className="management-status-dot" />앱</span>
                        <button type="button" className="management-icon-button danger" onClick={(event) => handleDeleteApp(event, app.id)} aria-label={`${app.title || '제목 없는 앱'} 삭제`} title="앱 삭제"><Trash2 size={14} /></button>
                      </div>
                    </div>
                    <h2 title={app.title}>{app.title || '제목 없는 앱'}</h2>
                    <p className="management-card-description">{app.description || '설명이 아직 추가되지 않았습니다.'}</p>
                    <div className="management-meta-grid">
                      <span className="management-meta-item"><span>컴포넌트</span><strong>{app.component_count ?? 0}개</strong></span>
                      <span className="management-meta-item"><span>워크플로우 연결</span><strong>{app.binding_count ?? 0}개</strong></span>
                      <span className="management-meta-item"><span>최근 수정</span><strong>{formatManagementDate(app.updated_at)}</strong></span>
                      <span className="management-meta-item"><span>생성일</span><strong>{formatManagementDate(app.created_at)}</strong></span>
                      <span className="management-meta-item"><span>앱 ID</span><code>{String(app.id).slice(0, 12)}</code></span>
                    </div>
                  </div>
                  <footer className="management-card-actions">
                    <button className="management-button primary" onClick={() => navigate(`/app-builder/${app.id}`)}><PencilLine size={14} /> 편집하기</button>
                    <button className="management-button" onClick={() => window.open(`/custom-app/${app.id}`, '_blank')}><ExternalLink size={14} /> 화면 보기</button>
                  </footer>
                </article>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default CustomAppsDashboardPage;
