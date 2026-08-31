import { useCallback, useRef, useState } from 'react';
import { createEditorSnapshot, getSnapshotFingerprint } from './editorCommands';

const HISTORY_LIMIT = 100;

export const useEditorHistory = () => {
  const entriesRef = useRef([]);
  const indexRef = useRef(-1);
  const savedFingerprintRef = useRef(null);
  const [, render] = useState(0);

  const notify = useCallback(() => render((value) => value + 1), []);

  const reset = useCallback((nodes, edges, { saved = true } = {}) => {
    const snapshot = createEditorSnapshot(nodes, edges);
    const fingerprint = getSnapshotFingerprint(snapshot);
    entriesRef.current = [{ snapshot, fingerprint, label: '초기 상태' }];
    indexRef.current = 0;
    savedFingerprintRef.current = saved ? fingerprint : null;
    notify();
  }, [notify]);

  const commit = useCallback((nodes, edges, label = '워크플로우 편집') => {
    const snapshot = createEditorSnapshot(nodes, edges);
    const fingerprint = getSnapshotFingerprint(snapshot);
    const currentEntry = entriesRef.current[indexRef.current];
    if (currentEntry?.fingerprint === fingerprint) return false;

    const retained = entriesRef.current.slice(0, indexRef.current + 1);
    retained.push({ snapshot, fingerprint, label });
    const limited = retained.slice(-HISTORY_LIMIT);
    entriesRef.current = limited;
    indexRef.current = limited.length - 1;
    notify();
    return true;
  }, [notify]);

  const undo = useCallback(() => {
    if (indexRef.current <= 0) return null;
    indexRef.current -= 1;
    notify();
    return entriesRef.current[indexRef.current];
  }, [notify]);

  const redo = useCallback(() => {
    if (indexRef.current < 0 || indexRef.current >= entriesRef.current.length - 1) return null;
    indexRef.current += 1;
    notify();
    return entriesRef.current[indexRef.current];
  }, [notify]);

  const markSaved = useCallback((nodes, edges) => {
    savedFingerprintRef.current = getSnapshotFingerprint(createEditorSnapshot(nodes, edges));
    notify();
  }, [notify]);

  const isDirty = useCallback((nodes, edges) => {
    const current = getSnapshotFingerprint(createEditorSnapshot(nodes, edges));
    return savedFingerprintRef.current === null || current !== savedFingerprintRef.current;
  }, []);

  const currentEntry = entriesRef.current[indexRef.current];

  return {
    reset,
    commit,
    undo,
    redo,
    markSaved,
    isDirty,
    canUndo: indexRef.current > 0,
    canRedo: indexRef.current >= 0 && indexRef.current < entriesRef.current.length - 1,
    undoLabel: indexRef.current > 0 ? currentEntry?.label : null,
    redoLabel: indexRef.current < entriesRef.current.length - 1
      ? entriesRef.current[indexRef.current + 1]?.label
      : null,
  };
};

