// 운영 개요 (IA 계획 §3.1) — "이미 만들어진 자동화가 언제, 어디에서 실행되고 있는가"의
// 읽기 전용 요약. 초기 버전은 세 관리 API(웹훅/봇/스케줄)의 결과를 합산해 보여주고,
// 통합 백엔드 API는 화면 요구가 안정된 뒤 도입한다(과도한 선행 작업 회피).
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import MainSidebar from '../MainSidebar';
import SectionTabs from '../components/SectionTabs';
import { OPERATIONS_SECTION_TABS } from '../navigation';
import { Icon } from '../icons';
import './MainPage.css';
import './SchedulerPage.css';

const isActive = (item) => Boolean(
  item?.is_live ?? item?.isLive ?? item?.active ?? item?.is_active ?? item?.enabled ?? true,
);

export default function OperationsOverviewPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState({ webhooks: null, bots: null, schedules: null });

  const load = useCallback(async () => {
    const headers = { headers: { Authorization: `Bearer ${token}` } };
    const fetchList = async (url, pick) => {
      try {
        const res = await axios.get(url, headers);
        const list = Array.isArray(res.data) ? res.data : (pick ? res.data?.[pick] : res.data) || [];
        return Array.isArray(list) ? list : [];
      } catch (e) {
        return null; // 실패한 축은 '확인 불가'로 표시한다 — 0으로 속이지 않는다.
      }
    };
    const [webhooks, bots, schedules] = await Promise.all([
      fetchList('/api/webhooks'),
      fetchList('/api/bots'),
      fetchList('/api/schedules'),
    ]);
    setSummary({ webhooks, bots, schedules });
    setLoading(false);
  }, [token]);

  useEffect(() => { if (token) load(); }, [token, load]);

  const cards = [
    { key: 'webhooks', label: '웹훅', icon: 'nav-webhooks', path: '/operations/webhooks',
      description: '외부 서비스가 호출하는 수신 엔드포인트' },
    { key: 'bots', label: '봇', icon: 'nav-bots', path: '/operations/bots',
      description: '디스코드·텔레그램에 연결된 대화형 실행' },
    { key: 'schedules', label: '스케줄', icon: 'nav-scheduler', path: '/operations/schedules',
      description: '주기적으로 자동 실행되는 워크플로우' },
  ];

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <SectionTabs ariaLabel="운영 섹션" tabs={OPERATIONS_SECTION_TABS} />
        <div className="content-area" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto' }}>
          <div className="page-header">
            <div>
              <h1 className="page-title">운영 개요</h1>
              <p className="page-subtitle">만들어진 자동화가 언제, 어디에서 실행되고 있는지 한눈에 확인하세요.</p>
            </div>
            <button className="btn-refresh" onClick={() => { setLoading(true); load(); }} disabled={loading}>새로고침</button>
          </div>

          {loading ? <p>불러오는 중...</p> : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
              {cards.map((card) => {
                const list = summary[card.key];
                const total = list ? list.length : null;
                const activeCount = list ? list.filter(isActive).length : null;
                return (
                  <div key={card.key} style={{ border: '1px solid var(--border-color)', borderRadius: '12px', padding: '18px 20px', background: 'var(--card-bg)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      <Icon name={card.icon} size={17} /> {card.label}
                    </div>
                    <div style={{ fontSize: '1.9rem', fontWeight: 700, margin: '10px 0 2px' }}>
                      {total === null ? '—' : `${total}개`}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', minHeight: '2.4em' }}>
                      {total === null
                        ? '목록을 불러오지 못했습니다.'
                        : total === 0 ? card.description : `활성 ${activeCount}개 · ${card.description}`}
                    </div>
                    <button
                      onClick={() => navigate(card.path)}
                      style={{ marginTop: '10px', padding: '7px 14px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-color)', cursor: 'pointer', fontSize: '0.8rem' }}
                    >
                      {card.label} 관리로 이동
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
