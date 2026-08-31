export const MAIN_SIDEBAR_PANEL_KEY = 'main-sidebar-panel';
export const DEFAULT_MAIN_SIDEBAR_PANEL = 'menu';
export const MAIN_SIDEBAR_PANELS = new Set(['menu', 'chat']);

export const normalizeMainSidebarPanel = (value) => (
  MAIN_SIDEBAR_PANELS.has(value) ? value : DEFAULT_MAIN_SIDEBAR_PANEL
);

export const readMainSidebarPanel = (storage) => {
  try {
    return normalizeMainSidebarPanel(storage?.getItem(MAIN_SIDEBAR_PANEL_KEY));
  } catch {
    return DEFAULT_MAIN_SIDEBAR_PANEL;
  }
};

export const writeMainSidebarPanel = (storage, panel) => {
  const normalized = normalizeMainSidebarPanel(panel);
  try {
    storage?.setItem(MAIN_SIDEBAR_PANEL_KEY, normalized);
  } catch {
    // 사생활 보호 모드처럼 sessionStorage를 쓸 수 없어도 현재 화면의 state는 정상 동작한다.
  }
  return normalized;
};

