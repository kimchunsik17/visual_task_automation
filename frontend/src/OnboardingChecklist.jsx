import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  Check,
  ChevronDown,
  ChevronUp,
  Circle,
  ListChecks,
  PartyPopper,
} from 'lucide-react';
import {
  getOnboardingProgress,
  ONBOARDING_EVENT,
  ONBOARDING_STORAGE_KEY,
  ONBOARDING_STEP_IDS,
  setOnboardingCollapsed,
} from './onboardingProgress';
import onboardingCompleteArt from './assets/editorial/celebrations/onboarding-complete.webp';
import { celebrateMilestone } from './milestoneCelebrations';
import './OnboardingChecklist.css';

const STEPS = [
  {
    id: 'workflow_created',
    title: '첫 워크플로우 만들기',
    description: '자동화하고 싶은 일을 설명해 워크플로우를 준비하세요.',
    actionLabel: '생성 시작',
  },
  {
    id: 'node_configured',
    title: '노드 설정 바꾸기',
    description: '에디터에서 노드 하나를 열고 입력값을 수정하세요.',
    actionLabel: '에디터에서 계속',
  },
  {
    id: 'workflow_tested',
    title: '결과 확인하기',
    description: 'API 키 없이 목업으로 먼저 돌려보세요. 실제 실행이나 평가로도 완료됩니다.',
    actionLabel: '목업으로 실행해보기',
  },
  {
    id: 'workflow_saved',
    title: '프로젝트 저장하기',
    description: '수정한 워크플로우를 내 프로젝트에 저장하세요.',
    actionLabel: '저장 위치 보기',
  },
  {
    id: 'deploy_previewed',
    title: '배포 방식 살펴보기',
    description: '배포 화면에서 제공되는 실행 방식을 확인하세요.',
    actionLabel: '배포 화면 열기',
  },
];

const readProgress = () => getOnboardingProgress();

function OnboardingChecklist({ onAction }) {
  const [progress, setProgress] = useState(readProgress);

  useEffect(() => {
    const handleProgress = (event) => setProgress(event.detail || readProgress());
    const handleStorage = (event) => {
      if (!event.key || event.key === ONBOARDING_STORAGE_KEY) setProgress(readProgress());
    };
    window.addEventListener(ONBOARDING_EVENT, handleProgress);
    window.addEventListener('storage', handleStorage);
    return () => {
      window.removeEventListener(ONBOARDING_EVENT, handleProgress);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  const completedCount = useMemo(
    () => ONBOARDING_STEP_IDS.filter((id) => progress.completed[id]).length,
    [progress.completed],
  );
  const isComplete = completedCount === STEPS.length;
  const wasComplete = useRef(isComplete);
  const activeStep = STEPS.find((step) => !progress.completed[step.id]);
  const percent = Math.round((completedCount / STEPS.length) * 100);

  useEffect(() => {
    if (isComplete && !wasComplete.current) celebrateMilestone('onboarding');
    wasComplete.current = isComplete;
  }, [isComplete]);

  useEffect(() => {
    if (!isComplete || progress.collapsed) return undefined;
    const timer = window.setTimeout(() => setOnboardingCollapsed(true), 1800);
    return () => window.clearTimeout(timer);
  }, [isComplete, progress.collapsed]);

  const toggleCollapsed = () => {
    setOnboardingCollapsed(!progress.collapsed);
  };

  const runStepAction = (stepId) => {
    if (!onAction) return;
    setOnboardingCollapsed(true);
    window.setTimeout(() => onAction(stepId), 120);
  };

  if (isComplete && progress.collapsed) return null;

  return (
    <aside className={`onboarding-checklist ${progress.collapsed ? 'is-collapsed' : ''}`} aria-label="시작 체크리스트">
      <button className="onboarding-header" type="button" onClick={toggleCollapsed} aria-expanded={!progress.collapsed}>
        <span className="onboarding-header-icon">
          {isComplete ? <PartyPopper size={18} /> : <ListChecks size={18} />}
        </span>
        <span className="onboarding-header-copy">
          <strong>{isComplete ? '첫 워크플로우 준비 완료' : '시작 체크리스트'}</strong>
          <span>{completedCount}/{STEPS.length} 완료</span>
        </span>
        <span className="onboarding-progress-track" aria-label={`${percent}% 완료`}>
          <span style={{ width: `${percent}%` }} />
        </span>
        {progress.collapsed ? <ChevronDown size={17} /> : <ChevronUp size={17} />}
      </button>

      {!progress.collapsed && (
        <div className="onboarding-body">
          <ol className="onboarding-steps">
            {STEPS.map((step) => {
              const done = Boolean(progress.completed[step.id]);
              const active = activeStep?.id === step.id;
              return (
                <li key={step.id} className={`${done ? 'is-done' : ''} ${active ? 'is-active' : ''}`}>
                  <button
                    className="onboarding-step-button"
                    type="button"
                    disabled={!active || !onAction}
                    onClick={() => runStepAction(step.id)}
                  >
                    <span className="onboarding-step-icon" aria-hidden="true">
                      {done ? <Check size={14} /> : <Circle size={13} />}
                    </span>
                    <span className="onboarding-step-copy">
                      <strong>{step.title}</strong>
                      {active && <span>{step.description}</span>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          {!isComplete && activeStep && onAction && (
            <button className="onboarding-action" type="button" onClick={() => runStepAction(activeStep.id)}>
              {activeStep.actionLabel}
              <ArrowRight size={15} />
            </button>
          )}
          {isComplete && (
            <div className="onboarding-complete-state">
              <img
                className="onboarding-complete-art"
                src={onboardingCompleteArt}
                alt=""
                aria-hidden="true"
              />
              <p className="onboarding-complete-copy">이제 직접 만들고 테스트하고 배포할 준비가 됐어요.</p>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}

export default OnboardingChecklist;
