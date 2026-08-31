import { useCallback, useEffect, useRef, useState } from 'react';

const HISTORY_LIMIT = 100;
const SETTLE_MS = 300;

/**
 * 앱 빌더 컴포넌트 트리의 되돌리기/다시 실행.
 *
 * 워크플로우 에디터의 useEditorHistory 는 "명령이 끝났을 때 commit 을 부르는" 모델인데,
 * 앱 빌더는 드래그 한 번에 setComponents 가 수십 번 불리고 속성 입력도 키 입력마다 바뀐다.
 * 그래서 여기서는 트리가 바뀐 뒤 SETTLE_MS 동안 조용해지면 한 항목으로 기록한다 —
 * 드래그 한 번·타이핑 한 번·AI 생성 한 번이 각각 항목 하나가 된다.
 *
 * undo/redo 로 트리를 되돌린 변화는 다시 기록하지 않는다(applyingRef).
 */
export const useAppBuilderHistory = (components, setComponents) => {
  const entriesRef = useRef([]);
  const indexRef = useRef(-1);
  const applyingRef = useRef(false);
  const timerRef = useRef(null);
  const pendingRef = useRef(null);
  const [, render] = useState(0);
  const notify = useCallback(() => render((value) => value + 1), []);

  const push = useCallback((snapshot) => {
    const fingerprint = JSON.stringify(snapshot);
    const current = entriesRef.current[indexRef.current];
    if (current?.fingerprint === fingerprint) return;
    const retained = entriesRef.current.slice(0, indexRef.current + 1);
    retained.push({ snapshot, fingerprint });
    const limited = retained.slice(-HISTORY_LIMIT);
    entriesRef.current = limited;
    indexRef.current = limited.length - 1;
    notify();
  }, [notify]);

  const flushPending = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (pendingRef.current) {
      push(pendingRef.current);
      pendingRef.current = null;
    }
  }, [push]);

  useEffect(() => {
    if (applyingRef.current) {
      applyingRef.current = false;
      return undefined;
    }
    pendingRef.current = components;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      if (pendingRef.current) push(pendingRef.current);
      pendingRef.current = null;
    }, SETTLE_MS);
    return undefined;
  }, [components, push]);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  const apply = useCallback((index) => {
    const entry = entriesRef.current[index];
    if (!entry) return false;
    indexRef.current = index;
    applyingRef.current = true;
    setComponents(JSON.parse(entry.fingerprint));
    notify();
    return true;
  }, [setComponents, notify]);

  const undo = useCallback(() => {
    flushPending();
    if (indexRef.current <= 0) return false;
    return apply(indexRef.current - 1);
  }, [apply, flushPending]);

  const redo = useCallback(() => {
    flushPending();
    if (indexRef.current >= entriesRef.current.length - 1) return false;
    return apply(indexRef.current + 1);
  }, [apply, flushPending]);

  /** 앱을 불러왔을 때 등, 지금 트리를 새 기준점으로 삼고 이전 기록을 버린다. */
  const reset = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    pendingRef.current = null;
    entriesRef.current = [];
    indexRef.current = -1;
    notify();
  }, [notify]);

  return {
    undo,
    redo,
    reset,
    canUndo: indexRef.current > 0 || (indexRef.current === 0 && pendingRef.current !== null
      && JSON.stringify(pendingRef.current) !== entriesRef.current[0]?.fingerprint),
    canRedo: indexRef.current >= 0 && indexRef.current < entriesRef.current.length - 1,
  };
};
