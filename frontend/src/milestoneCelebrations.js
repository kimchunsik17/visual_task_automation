export const MILESTONE_CELEBRATION_EVENT = 'nodi-milestone-celebration';

const STORAGE_PREFIX = 'nodi_milestone_seen_v1:';

export function celebrateMilestone(variant, { onceKey = variant } = {}) {
  if (typeof window === 'undefined') return false;

  if (onceKey) {
    const storageKey = `${STORAGE_PREFIX}${onceKey}`;
    if (localStorage.getItem(storageKey)) return false;
    localStorage.setItem(storageKey, new Date().toISOString());
  }

  window.dispatchEvent(new CustomEvent(MILESTONE_CELEBRATION_EVENT, {
    detail: { variant, nonce: `${Date.now()}-${Math.random().toString(36).slice(2)}` },
  }));
  return true;
}

export function resetMilestoneCelebrations(onceKeyPrefix) {
  if (typeof window === 'undefined') return;
  const targetPrefix = `${STORAGE_PREFIX}${onceKeyPrefix}`;
  Object.keys(localStorage)
    .filter((key) => key.startsWith(targetPrefix))
    .forEach((key) => localStorage.removeItem(key));
}
