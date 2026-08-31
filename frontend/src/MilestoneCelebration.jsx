import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import tutorialTrackArt from './assets/editorial/celebrations/tutorial-track-complete.webp';
import tutorialAllArt from './assets/editorial/celebrations/tutorial-all-complete.webp';
import onboardingArt from './assets/editorial/celebrations/onboarding-complete.webp';
import firstRunArt from './assets/editorial/celebrations/first-run-success.webp';
import firstDeployArt from './assets/editorial/celebrations/first-deploy-success.webp';
import { MILESTONE_CELEBRATION_EVENT } from './milestoneCelebrations';
import './MilestoneCelebration.css';

const CELEBRATIONS = {
  'tutorial-track': {
    image: tutorialTrackArt,
    eyebrow: 'LEARNING MILESTONE',
    title: '트랙 완료!',
    copy: '한 단계 더 익혔어요. 다음 학습에서도 이 흐름을 이어가세요.',
  },
  'tutorial-all': {
    image: tutorialAllArt,
    eyebrow: 'LEARNING CENTER COMPLETE',
    title: '학습 센터 졸업!',
    copy: '모든 트랙을 완주했습니다. 이제 실제 Workflow에 배운 내용을 적용해보세요.',
  },
  onboarding: {
    image: onboardingArt,
    eyebrow: 'FIRST WORKFLOW READY',
    title: '첫 준비를 모두 마쳤어요',
    copy: '만들기부터 테스트와 배포 확인까지, 자동화를 운영할 준비가 됐습니다.',
  },
  'first-run': {
    image: firstRunArt,
    eyebrow: 'FIRST RUN COMPLETE',
    title: '첫 실행 성공!',
    copy: '데이터가 Workflow를 끝까지 통과했습니다. 결과와 로그도 함께 확인해보세요.',
  },
  'first-deploy': {
    image: firstDeployArt,
    eyebrow: 'FIRST DEPLOY COMPLETE',
    title: '첫 배포 완료!',
    copy: '만든 Workflow를 실제로 사용할 수 있는 화면으로 내보냈습니다.',
  },
};

const PARTICLES = [
  [-132, -74, '#3b82f6', -16], [-106, -122, '#8b5cf6', 22], [-58, -146, '#10b981', 45],
  [4, -158, '#3b82f6', -28], [70, -140, '#8b5cf6', 18], [122, -94, '#10b981', 38],
  [146, -30, '#3b82f6', -14], [132, 46, '#8b5cf6', 30], [90, 108, '#10b981', -24],
  [24, 132, '#3b82f6', 16], [-48, 124, '#8b5cf6', -38], [-112, 82, '#10b981', 24],
];

function CelebrationCard({ item, onDone }) {
  const config = CELEBRATIONS[item.variant];

  useEffect(() => {
    const timer = window.setTimeout(onDone, item.variant === 'tutorial-all' ? 2900 : 2400);
    return () => window.clearTimeout(timer);
  }, [item, onDone]);

  if (!config) return null;

  return (
    <div className="milestone-overlay" role="status" aria-live="polite" aria-atomic="true">
      <button className="milestone-backdrop" type="button" onClick={onDone} aria-label="축하 화면 닫기" />
      <section className={`milestone-card milestone-${item.variant}`}>
        <button className="milestone-close" type="button" onClick={onDone} aria-label="닫기"><X size={17} /></button>
        <div className="milestone-visual" aria-hidden="true">
          <span className="milestone-ring" />
          <span className="milestone-ring milestone-ring-secondary" />
          <div className="milestone-particles">
            {PARTICLES.map(([x, y, color, rotate], index) => (
              <i
                key={`${x}-${y}`}
                style={{ '--particle-x': `${x}px`, '--particle-y': `${y}px`, '--particle-color': color, '--particle-rotate': `${rotate}deg`, '--particle-delay': `${index * 24}ms` }}
              />
            ))}
          </div>
          <img src={config.image} alt="" />
        </div>
        <span className="milestone-eyebrow">{config.eyebrow}</span>
        <h2>{config.title}</h2>
        <p>{config.copy}</p>
      </section>
    </div>
  );
}

export default function MilestoneCelebrationHost() {
  const [queue, setQueue] = useState([]);

  useEffect(() => {
    const handleCelebration = (event) => {
      if (!CELEBRATIONS[event.detail?.variant]) return;
      setQueue((current) => [...current, event.detail]);
    };
    window.addEventListener(MILESTONE_CELEBRATION_EVENT, handleCelebration);
    return () => window.removeEventListener(MILESTONE_CELEBRATION_EVENT, handleCelebration);
  }, []);

  const active = queue[0];
  if (!active) return null;

  return <CelebrationCard item={active} onDone={() => setQueue((current) => current.slice(1))} />;
}

