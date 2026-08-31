import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_MAIN_SIDEBAR_PANEL,
  MAIN_SIDEBAR_PANEL_KEY,
  normalizeMainSidebarPanel,
  readMainSidebarPanel,
  writeMainSidebarPanel,
} from './mainSidebarState.js';

const createStorage = (initial = {}) => {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
};

test('페이지가 다시 마운트돼도 선택한 대화 기록 탭을 복원한다', () => {
  const storage = createStorage();

  writeMainSidebarPanel(storage, 'chat');

  assert.equal(readMainSidebarPanel(storage), 'chat');
  assert.equal(storage.getItem(MAIN_SIDEBAR_PANEL_KEY), 'chat');
});

test('알 수 없는 탭 값은 메뉴로 안전하게 되돌린다', () => {
  assert.equal(normalizeMainSidebarPanel('unknown'), DEFAULT_MAIN_SIDEBAR_PANEL);
  assert.equal(readMainSidebarPanel(createStorage({ [MAIN_SIDEBAR_PANEL_KEY]: 'broken' })), DEFAULT_MAIN_SIDEBAR_PANEL);
});

test('sessionStorage 접근이 막혀도 기본 탭을 반환한다', () => {
  const blockedStorage = { getItem: () => { throw new Error('blocked'); } };

  assert.equal(readMainSidebarPanel(blockedStorage), DEFAULT_MAIN_SIDEBAR_PANEL);
});

