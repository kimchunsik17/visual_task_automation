import { TUTORIAL_LESSONS, TUTORIAL_TRACKS, getTutorialLesson } from './tutorialLessons';
import { resetMilestoneCelebrations } from './milestoneCelebrations';

export const TUTORIAL_PROGRESS_KEY = 'learning_center_progress_v2';
export const LEGACY_TUTORIAL_PROGRESS_KEY = 'learning_center_progress_v1';
export const TUTORIAL_PROGRESS_EVENT = 'learning-center-progress';

const createEmptyProgress = () => ({
  version: 2,
  activeTrackId: 'foundation',
  lastLessonByTrack: { foundation: 'structure' },
  completed: {},
});

const normalizeProgress = (progress) => {
  const validTrackIds = new Set(TUTORIAL_TRACKS.map((track) => track.id));
  const validLessonIds = new Set(TUTORIAL_LESSONS.map((lesson) => lesson.id));
  const completed = Object.fromEntries(
    Object.entries(progress?.completed || {}).filter(([lessonId]) => validLessonIds.has(lessonId)),
  );
  const lastLessonByTrack = { foundation: 'structure' };

  Object.entries(progress?.lastLessonByTrack || {}).forEach(([trackId, lessonId]) => {
    const lesson = getTutorialLesson(lessonId);
    if (validTrackIds.has(trackId) && lesson.trackId === trackId) lastLessonByTrack[trackId] = lessonId;
  });

  return {
    version: 2,
    activeTrackId: validTrackIds.has(progress?.activeTrackId) ? progress.activeTrackId : 'foundation',
    lastLessonByTrack,
    completed,
  };
};

const migrateLegacyProgress = () => {
  try {
    const legacy = JSON.parse(localStorage.getItem(LEGACY_TUTORIAL_PROGRESS_KEY));
    if (!legacy || legacy.version !== 1) return null;
    const lastLesson = getTutorialLesson(legacy.lastLessonId);
    return normalizeProgress({
      activeTrackId: lastLesson.trackId,
      lastLessonByTrack: { [lastLesson.trackId]: lastLesson.id },
      completed: legacy.completed || {},
    });
  } catch {
    return null;
  }
};

export function getTutorialProgress() {
  try {
    const saved = JSON.parse(localStorage.getItem(TUTORIAL_PROGRESS_KEY));
    if (saved?.version === 2) return normalizeProgress(saved);
  } catch {
    // Fall through to the legacy migration.
  }

  const migrated = migrateLegacyProgress();
  if (migrated) {
    localStorage.setItem(TUTORIAL_PROGRESS_KEY, JSON.stringify(migrated));
    return migrated;
  }
  return createEmptyProgress();
}

function saveTutorialProgress(progress) {
  const normalized = normalizeProgress(progress);
  localStorage.setItem(TUTORIAL_PROGRESS_KEY, JSON.stringify(normalized));
  window.dispatchEvent(new CustomEvent(TUTORIAL_PROGRESS_EVENT, { detail: normalized }));
  return normalized;
}

export function setActiveTutorialTrack(activeTrackId) {
  return saveTutorialProgress({ ...getTutorialProgress(), activeTrackId });
}

export function setLastTutorialLesson(lastLessonId) {
  const lesson = getTutorialLesson(lastLessonId);
  const current = getTutorialProgress();
  return saveTutorialProgress({
    ...current,
    activeTrackId: lesson.trackId,
    lastLessonByTrack: { ...current.lastLessonByTrack, [lesson.trackId]: lesson.id },
  });
}

export function completeTutorialLesson(lessonId) {
  const lesson = getTutorialLesson(lessonId);
  const current = getTutorialProgress();
  if (current.completed[lesson.id]) return current;
  return saveTutorialProgress({
    ...current,
    activeTrackId: lesson.trackId,
    lastLessonByTrack: { ...current.lastLessonByTrack, [lesson.trackId]: lesson.id },
    completed: { ...current.completed, [lesson.id]: new Date().toISOString() },
  });
}

export function resetTutorialLearningProgress() {
  localStorage.removeItem(TUTORIAL_PROGRESS_KEY);
  localStorage.removeItem(LEGACY_TUTORIAL_PROGRESS_KEY);
  resetMilestoneCelebrations('tutorial-');
  const empty = createEmptyProgress();
  window.dispatchEvent(new CustomEvent(TUTORIAL_PROGRESS_EVENT, { detail: empty }));
  return empty;
}
