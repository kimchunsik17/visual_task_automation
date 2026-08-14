import React from 'react';
import { ScrollText, Sparkles, Wrench, Bug } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import { PATCH_NOTES } from '../patchNotes';
import './MainPage.css';
import './SchedulerPage.css'; // page-header/page-title 등 공통 스타일 재사용 (WebhookManagerPage와 동일한 패턴)
import './PatchNotesPage.css';

const SECTION_META = {
  new: { label: '새 기능', icon: Sparkles, color: '#8b5cf6' },
  improved: { label: '개선', icon: Wrench, color: '#0ea5e9' },
  fixed: { label: '버그 수정', icon: Bug, color: '#f97316' },
};

export default function PatchNotesPage() {
  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="content-area" style={{ width: '100%', maxWidth: '900px', margin: '0 auto' }}>
          <div className="page-header">
            <div>
              <h1 className="page-title"><ScrollText className="title-icon" /> 패치 노트</h1>
              <p className="page-subtitle">WorkFlow AI에 추가되거나 개선된 내용을 확인하세요.</p>
            </div>
          </div>

          <div className="patch-notes-list">
            {PATCH_NOTES.map((entry, idx) => (
              <div key={entry.date} className="patch-note-card">
                <div className="patch-note-date-rail">
                  <div className="patch-note-dot" />
                  {idx < PATCH_NOTES.length - 1 && <div className="patch-note-line" />}
                </div>
                <div className="patch-note-body">
                  <div className="patch-note-header">
                    <span className="patch-note-date">{entry.date}</span>
                    <h2 className="patch-note-title">{entry.title}</h2>
                  </div>
                  {['new', 'improved', 'fixed'].map(sectionKey => {
                    const items = entry.sections?.[sectionKey];
                    if (!items || items.length === 0) return null;
                    const meta = SECTION_META[sectionKey];
                    const Icon = meta.icon;
                    return (
                      <div key={sectionKey} className="patch-note-section">
                        <div className="patch-note-section-label" style={{ color: meta.color }}>
                          <Icon size={15} /> {meta.label}
                        </div>
                        <ul className="patch-note-items">
                          {items.map((text, i) => <li key={i}>{text}</li>)}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
