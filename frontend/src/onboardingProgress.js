import { resetMilestoneCelebrations } from './milestoneCelebrations';

export const ONBOARDING_STORAGE_KEY = 'workflow_onboarding_v1';
export const ONBOARDING_EVENT = 'workflow-onboarding-progress';

export const ONBOARDING_STEP_IDS = [
  'workflow_created',
  'node_configured',
  'workflow_tested',
  'workflow_saved',
  'deploy_previewed',
];

const EMPTY_PROGRESS = {
  version: 1,
  completed: {},
  collapsed: false,
};

const getEmptyProgress = () => ({
  ...EMPTY_PROGRESS,
  collapsed: typeof window !== 'undefined' && window.innerWidth <= 768,
});

export function getOnboardingProgress() {
  try {
    const saved = JSON.parse(localStorage.getItem(ONBOARDING_STORAGE_KEY));
    if (!saved || saved.version !== EMPTY_PROGRESS.version) return getEmptyProgress();
    return {
      ...EMPTY_PROGRESS,
      ...saved,
      completed: saved.completed || {},
    };
  } catch {
    return getEmptyProgress();
  }
}

function persistOnboardingProgress(progress) {
  localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(progress));
  window.dispatchEvent(new CustomEvent(ONBOARDING_EVENT, { detail: progress }));
  return progress;
}

export function completeOnboardingStep(stepId) {
  if (!ONBOARDING_STEP_IDS.includes(stepId)) return getOnboardingProgress();

  const current = getOnboardingProgress();
  if (current.completed[stepId]) return current;

  return persistOnboardingProgress({
    ...current,
    completed: {
      ...current.completed,
      [stepId]: new Date().toISOString(),
    },
  });
}

export function setOnboardingCollapsed(collapsed) {
  return persistOnboardingProgress({
    ...getOnboardingProgress(),
    collapsed,
  });
}

export function resetOnboardingProgress() {
  localStorage.removeItem(ONBOARDING_STORAGE_KEY);
  resetMilestoneCelebrations('onboarding');
  window.dispatchEvent(new CustomEvent(ONBOARDING_EVENT, { detail: getEmptyProgress() }));
}
