// 섹션 상단 보조 내비게이션 (HOME_SIDEBAR_INFORMATION_ARCHITECTURE_PLAN §1).
// 사이드바에는 1차 목적지만 두고, 섹션 안의 하위 페이지 이동은 이 탭이 담당한다 —
// 아코디언 사이드바는 축소/모바일 상태에서 위계가 불안정해 계획에서 배제됐다.
import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export default function SectionTabs({ tabs, ariaLabel = '하위 페이지' }) {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <nav className="section-tabs" aria-label={ariaLabel}>
      {tabs.map((tab) => {
        const active = tab.match
          ? tab.match(location.pathname)
          : location.pathname.startsWith(tab.path);
        return (
          <button
            key={tab.path}
            type="button"
            className={`section-tab ${active ? 'active' : ''}`}
            aria-current={active ? 'page' : undefined}
            onClick={() => { if (!active) navigate(tab.path); }}
          >
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}
