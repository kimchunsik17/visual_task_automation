import React, { useEffect, useMemo, useState } from 'react';
import { Search, ChevronRight, Puzzle, X, Shapes } from 'lucide-react';
import { Icon } from './icons';
import { NODE_CATEGORY_LABELS, visibleEditorNodes } from './editorNodeCatalog';
import { loadFeatures } from './features';

/**
 * 노드 팔레트.
 *
 * 노드 목록은 editorNodeCatalog.js 하나에서 온다. 예전에는 이 파일에 40여 개 목록이 따로 있어
 * 카탈로그와 색·카테고리가 어긋났다(rssTriggerNode 가 팔레트에서는 'trigger', 카탈로그에서는
 * 'input'). 명령 팔레트·노드 피커·교체 후보·미니맵이 이미 카탈로그를 쓰므로 팔레트도 같은 곳을 본다.
 *
 * 카테고리 접힘 상태는 localStorage 에 기억한다 — 새로 고칠 때마다 접혀 있던 목록이 다시 펼쳐지지 않게.
 */
const CATEGORY_ORDER = ['core', 'input', 'ai', 'logic', 'code', 'integration', 'document', 'advanced'];
const DEFAULT_EXPANDED = { core: true, input: true, ai: true, logic: false, code: false, integration: false, document: false, advanced: false };
const STORAGE_KEY = 'editor.palette.categories';

const readExpanded = () => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_EXPANDED, ...JSON.parse(raw) } : DEFAULT_EXPANDED;
  } catch {
    return DEFAULT_EXPANDED;
  }
};

const Sidebar = ({ isMobileOpen, onClose, onNodeTap }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedCategories, setExpandedCategories] = useState(readExpanded);
  // 시연 노드 비가시화(features.hidden_nodes) — 플래그가 로드되면 팔레트를 다시 계산한다.
  const [catalog, setCatalog] = useState(() => visibleEditorNodes());

  useEffect(() => {
    let alive = true;
    loadFeatures().then(() => { if (alive) setCatalog(visibleEditorNodes()); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(expandedCategories)); } catch { /* 저장 불가 환경은 무시 */ }
  }, [expandedCategories]);

  const onDragStart = (event, nodeType, label) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('application/reactflow-label', label);
    event.dataTransfer.effectAllowed = 'move';
  };

  const toggleCategory = (categoryId) => {
    setExpandedCategories((prev) => ({ ...prev, [categoryId]: !prev[categoryId] }));
  };

  const needle = searchTerm.trim().toLowerCase();
  const isSearching = needle !== '';
  const visibleNodes = useMemo(() => (
    isSearching
      ? catalog.filter((node) => node.label.toLowerCase().includes(needle) || node.type.toLowerCase().includes(needle))
      : catalog
  ), [isSearching, needle, catalog]);

  const renderNode = (node, showCategory = false) => (
    <div
      key={node.type}
      className="dnd-node"
      draggable
      onDragStart={(event) => onDragStart(event, node.type, node.label)}
      onClick={() => onNodeTap && onNodeTap(node.type, node.label)}
      title={`${node.label} — 캔버스로 드래그`}
    >
      <span className="dnd-node-icon" style={{ '--node-color': node.color }}>
        {node.icon ? <Icon name={node.icon} size={15} /> : <Puzzle size={15} />}
      </span>
      <span className="dnd-node-label">{node.label}</span>
      {showCategory && <span className="dnd-node-category">{node.categoryLabel}</span>}
    </div>
  );

  return (
    <>
      {isMobileOpen && <div className="mobile-palette-overlay" onClick={onClose}></div>}
      <aside className={`sidebar ${isMobileOpen ? 'mobile-open' : ''}`} aria-label="노드 팔레트">
        <div className="sidebar-header">
          <h2 className="sidebar-title">
            <Shapes size={14} /> 노드
            <span className="sidebar-count">{catalog.length}</span>
          </h2>
          <button className="mobile-palette-close-btn editor-icon-button" onClick={onClose} aria-label="노드 팔레트 닫기">
            <X size={18} />
          </button>
        </div>

        <div className="sidebar-search">
          <Search size={14} />
          <input
            type="text"
            placeholder="노드 검색"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            aria-label="노드 검색"
          />
          {isSearching && (
            <button type="button" className="sidebar-search-clear" onClick={() => setSearchTerm('')} aria-label="검색 지우기">
              <X size={12} />
            </button>
          )}
        </div>

        <div className="node-list">
          {isSearching ? (
            // 검색 중에는 카테고리 구분 없이 일치하는 노드를 보여주고, 카테고리는 항목 옆 캡션으로
            visibleNodes.length === 0
              ? <div className="node-list-empty">일치하는 노드가 없습니다</div>
              : visibleNodes.map((node) => renderNode(node, true))
          ) : (
            CATEGORY_ORDER.map((categoryId) => {
              const categoryNodes = visibleNodes.filter((node) => node.category === categoryId);
              if (categoryNodes.length === 0) return null;
              const isExpanded = expandedCategories[categoryId] !== false;
              return (
                <div key={categoryId} className="sidebar-category">
                  <button
                    type="button"
                    className="sidebar-category-header"
                    onClick={() => toggleCategory(categoryId)}
                    aria-expanded={isExpanded}
                  >
                    <ChevronRight size={13} className="chevron" />
                    {NODE_CATEGORY_LABELS[categoryId]}
                    <span className="sidebar-count">{categoryNodes.length}</span>
                  </button>
                  {isExpanded && (
                    <div className="sidebar-category-nodes">
                      {categoryNodes.map((node) => renderNode(node))}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </aside>
    </>
  );
};

export default Sidebar;
