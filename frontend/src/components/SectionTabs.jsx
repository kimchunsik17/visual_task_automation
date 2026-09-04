// 섹션 상단 보조 내비게이션 (HOME_SIDEBAR_INFORMATION_ARCHITECTURE_PLAN §1).
// 사이드바에는 1차 목적지만 두고, 섹션 안의 하위 페이지 이동은 이 탭이 담당한다 —
// 아코디언 사이드바는 축소/모바일 상태에서 위계가 불안정해 계획에서 배제됐다.
import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { isDemoUi, loadFeatures } from '../features';

export default function SectionTabs({ tabs, ariaLabel = '하위 페이지' }) {
  const navigate = useNavigate();
  const location = useLocation();
  // 시연 UI 트림(DEMO_UI) — demoHidden 표시가 붙은 탭을 숨긴다(navigation.js 참조).
  const [demoUi, setDemoUi] = useState(isDemoUi());
  useEffect(() => {
    let alive = true;
    loadFeatures().then(() => { if (alive) setDemoUi(isDemoUi()); });
    return () => { alive = false; };
  }, []);
  const visibleTabs = demoUi ? tabs.filter((tab) => !tab.demoHidden) : tabs;
  return (
    <nav className="section-tabs" aria-label={ariaLabel}>
      {visibleTabs.map((tab) => {
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
