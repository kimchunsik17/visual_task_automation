import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import SectionTabs from '../components/SectionTabs';
import { TUTORIAL_SECTION_TABS } from '../navigation';
import MainSidebar from '../MainSidebar';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Map,
  MonitorPlay,
  RotateCcw,
} from 'lucide-react';
import { Icon as StatusIcon } from '../icons';
import TutorialSandbox from '../components/TutorialSandbox';
import { TUTORIAL_LESSONS, TUTORIAL_TRACKS, getTutorialTrack } from '../tutorialLessons';
import {
  completeTutorialLesson,
  getTutorialProgress,
  resetTutorialLearningProgress,
  setActiveTutorialTrack,
  setLastTutorialLesson,
  TUTORIAL_PROGRESS_EVENT,
} from '../tutorialProgress';
import { customConfirm } from '../CustomConfirm';
import { celebrateMilestone } from '../milestoneCelebrations';
import './TutorialPage.css';

function TutorialPage() {
  const navigate = useNavigate();
  const { trackId } = useParams();
  const [progress, setProgress] = useState(getTutorialProgress);
  const routeTrack = TUTORIAL_TRACKS.find((item) => item.id === trackId);
  const initialTrack = routeTrack || getTutorialTrack(progress.activeTrackId);
  const initialLessonId = initialTrack.lessons.some((item) => item.id === progress.lastLessonByTrack[initialTrack.id])
    ? progress.lastLessonByTrack[initialTrack.id]
    : initialTrack.lessons[0].id;
  const [selectedLessonId, setSelectedLessonId] = useState(initialLessonId);

  const isTrackCatalog = !trackId;
  const track = routeTrack || initialTrack;
  const selectedIndex = track.lessons.findIndex((item) => item.id === selectedLessonId);
  const lesson = track.lessons[selectedIndex] || track.lessons[0];
  const LessonIcon = lesson.icon;
  const foundationTrack = getTutorialTrack('foundation');

  useEffect(() => {
    const handleProgress = (event) => setProgress(event.detail || getTutorialProgress());
    window.addEventListener(TUTORIAL_PROGRESS_EVENT, handleProgress);
    return () => window.removeEventListener(TUTORIAL_PROGRESS_EVENT, handleProgress);
  }, []);

  useEffect(() => {
    if (!trackId) return;
    if (!routeTrack) {
      navigate('/tutorial', { replace: true });
      return;
    }
    const savedLessonId = getTutorialProgress().lastLessonByTrack[routeTrack.id];
    const nextLesson = routeTrack.lessons.find((item) => item.id === savedLessonId) || routeTrack.lessons[0];
    setSelectedLessonId(nextLesson.id);
    setProgress(setActiveTutorialTrack(routeTrack.id));
  }, [navigate, routeTrack, trackId]);

  const completedCount = useMemo(
    () => TUTORIAL_LESSONS.filter((item) => progress.completed[item.id]).length,
    [progress.completed],
  );
  const trackCompletedCount = track.lessons.filter((item) => progress.completed[item.id]).length;
  const foundationComplete = foundationTrack.lessons.every((item) => progress.completed[item.id]);
  const progressPercent = Math.round((completedCount / TUTORIAL_LESSONS.length) * 100);
  const trackProgressPercent = Math.round((trackCompletedCount / track.lessons.length) * 100);
  const isCurrentComplete = Boolean(progress.completed[lesson.id]);

  const openTrack = (nextTrackId) => {
    setProgress(setActiveTutorialTrack(nextTrackId));
    navigate(`/tutorial/${nextTrackId}`);
  };

  const selectLesson = (lessonId) => {
    const nextLesson = TUTORIAL_LESSONS.find((item) => item.id === lessonId);
    if (!nextLesson) return;
    setSelectedLessonId(nextLesson.id);
    setProgress(setLastTutorialLesson(nextLesson.id));
  };

  const completeCurrentLesson = () => {
    const before = getTutorialProgress();
    if (before.completed[lesson.id]) {
      setProgress(before);
      return;
    }

    const next = completeTutorialLesson(lesson.id);
    setProgress(next);
    const completedTrack = track.lessons.every((item) => next.completed[item.id]);
    const completedAll = TUTORIAL_LESSONS.every((item) => next.completed[item.id]);

    if (completedAll) {
      celebrateMilestone('tutorial-all');
    } else if (completedTrack) {
      celebrateMilestone('tutorial-track', { onceKey: `tutorial-track-${track.id}` });
    }
  };

  const goForward = () => {
    const nextLesson = track.lessons[selectedIndex + 1];
    if (nextLesson) {
      selectLesson(nextLesson.id);
      return;
    }
    const trackIndex = TUTORIAL_TRACKS.findIndex((item) => item.id === track.id);
    const nextTrack = TUTORIAL_TRACKS[trackIndex + 1];
    if (nextTrack) openTrack(nextTrack.id);
    else navigate('/editor');
  };

  const resetAll = async () => {
    const confirmed = await customConfirm('튜토리얼의 모든 학습 진행률을 초기화하시겠습니까?');
    if (!confirmed) return;
    setProgress(resetTutorialLearningProgress());
    if (!isTrackCatalog) {
      setSelectedLessonId(track.lessons[0].id);
      setProgress(setActiveTutorialTrack(track.id));
    }
  };

  const replayScreenTour = (target) => {
    if (target === 'main') {
      localStorage.removeItem('tutorial_main_seen_v1');
      navigate('/');
      return;
    }
    localStorage.removeItem('tutorial_editor_seen_v1');
    navigate('/editor');
  };

  const currentTrackIndex = TUTORIAL_TRACKS.findIndex((item) => item.id === track.id);
  const isFinalTrack = currentTrackIndex === TUTORIAL_TRACKS.length - 1;
  const isFinalLesson = selectedIndex === track.lessons.length - 1;

  const goBack = () => {
    navigate(isTrackCatalog ? '/' : '/tutorial');
  };

  const overallProgress = (
    <div className="tutorial-overall-progress">
      <div><span>전체 진도</span><strong>{completedCount}/{TUTORIAL_LESSONS.length}</strong></div>
      <span className="tutorial-progress-track"><span style={{ width: `${progressPercent}%` }} /></span>
      <button type="button" onClick={resetAll} title="전체 진도 초기화" aria-label="전체 진도 초기화"><RotateCcw size={15} /></button>
    </div>
  );

  const trackCatalog = (
    <div className="tutorial-track-home">
      <div className="tutorial-track-home-inner">
        {/* 문서 페이지의 히어로와 같은 위계(eyebrow → 큰 제목 → 부제 → 구분선)를 쓴다. */}
        <div className="tutorial-track-home-heading">
          <div>
            <span>WORKFLOW AI LEARNING</span>
            <h2>학습 센터</h2>
            <p>기본 과정부터 운영과 앱 제작까지, 필요한 트랙을 선택해 과정과 실습을 차례로 진행하세요.</p>
          </div>
          <div className="tutorial-track-home-side">
            {overallProgress}
            <div className="tutorial-screen-tour-actions">
              <button type="button" onClick={() => replayScreenTour('main')}><MonitorPlay size={15} /> 메인 화면 둘러보기</button>
              <button type="button" onClick={() => replayScreenTour('editor')}><MonitorPlay size={15} /> 에디터 화면 둘러보기</button>
            </div>
          </div>
        </div>

        <section className="tutorial-track-section">
          <div className="tutorial-track-section-title"><span>기본 학습</span><p>Workflow 제작이 처음이라면 여기서 시작하세요.</p></div>
          <TrackCard track={foundationTrack} progress={progress} foundationComplete={foundationComplete} onOpen={openTrack} featured />
        </section>

        <section className="tutorial-track-section">
          <div className="tutorial-track-section-title"><span>심화 학습</span><p>운영 목적에 맞는 주제부터 선택할 수 있습니다.</p></div>
          <div className="tutorial-track-grid">
            {TUTORIAL_TRACKS.filter((item) => item.level === 'advanced').map((item) => (
              <TrackCard key={item.id} track={item} progress={progress} foundationComplete={foundationComplete} onOpen={openTrack} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );

  return (
    <div className="tutorial-page-layout">
      {/* 문서 페이지와 동일하게 사이드바를 유지한다 — 같은 섹션의 두 하위 페이지가
          한쪽만 전체 화면이면 위계가 헷갈린다(사용자 피드백). */}
      <MainSidebar />
      <main className="tutorial-page">
        <SectionTabs ariaLabel="튜토리얼 섹션" tabs={TUTORIAL_SECTION_TABS} />
        {!isTrackCatalog && (
          <header className="tutorial-page-header">
            <div className="tutorial-header-context">
              <button
                type="button"
                className="tutorial-header-back"
                onClick={goBack}
                aria-label="트랙 목록으로 돌아가기"
              >
                <ArrowLeft size={17} />
                <span>트랙 목록</span>
              </button>
              <div className="tutorial-heading">
                <span className="tutorial-heading-icon"><Map size={20} /></span>
                <div>
                  <h1>{track.title}</h1>
                  <p>{track.description}</p>
                </div>
              </div>
            </div>
            {overallProgress}
          </header>
        )}

        {isTrackCatalog ? trackCatalog : <div className="tutorial-workspace">
          <aside className="tutorial-course-rail">
            <div className="tutorial-selected-track">
              <div className="tutorial-selected-track-heading">
                <span>{track.level === 'basic' ? '기본 트랙' : '심화 트랙'}</span>
                {track.level === 'advanced' && !foundationComplete && <em>기본 학습 권장</em>}
              </div>
              <strong>{track.title}</strong>
              <p>{track.description}</p>
              <span className="tutorial-track-progress"><span style={{ width: `${trackProgressPercent}%` }} /></span>
            </div>

            <nav className="tutorial-lesson-nav" aria-label={`${track.title} 과정`}>
              {track.lessons.map((item, index) => {
                const Icon = item.icon;
                const done = Boolean(progress.completed[item.id]);
                const active = item.id === lesson.id;
                return (
                  <button key={item.id} type="button" className={`${active ? 'active' : ''} ${done ? 'done' : ''}`} onClick={() => selectLesson(item.id)}>
                    <span className="tutorial-course-index">{done ? <Check size={13} /> : index + 1}</span>
                    <span className="tutorial-course-icon"><Icon size={16} /></span>
                    <span className="tutorial-course-copy"><strong>{item.title}</strong><span>{item.shortTitle} · {item.duration}</span></span>
                    <ChevronRight size={15} />
                  </button>
                );
              })}
            </nav>

          </aside>

          <section className="tutorial-lesson-stage">
            <div className="tutorial-lesson-heading">
              <div>
                <span>{track.title} · 과정 {selectedIndex + 1}/{track.lessons.length}</span>
                <h2>{lesson.title}</h2>
                <p>{lesson.description}</p>
              </div>
              {isCurrentComplete && <span className="tutorial-complete-badge"><StatusIcon name="status-success" size={15} /> 완료</span>}
            </div>
            <TutorialSandbox key={lesson.id} lesson={lesson} onComplete={completeCurrentLesson} />
          </section>

          <aside className="tutorial-guide-panel">
            <div className="tutorial-guide-section">
              <span className="tutorial-guide-label">이번 목표</span>
              <p>{lesson.objective}</p>
            </div>
            <div className="tutorial-guide-section">
              <span className="tutorial-guide-label">핵심 개념</span>
              <ol>{lesson.concepts.map((concept, index) => <li key={concept}><span>{index + 1}</span>{concept}</li>)}</ol>
            </div>
            <div className={`tutorial-lesson-status ${isCurrentComplete ? 'complete' : ''}`}>
              {isCurrentComplete ? <StatusIcon name="status-success" size={22} /> : <LessonIcon size={22} />}
              <strong>{isCurrentComplete ? '과정을 완료했습니다' : '실습을 진행하세요'}</strong>
              <span>{isCurrentComplete ? '완료 상태가 트랙별로 저장되었습니다.' : '목표 행동을 완료하면 자동으로 기록됩니다.'}</span>
            </div>
            <button type="button" className="tutorial-next-button" onClick={goForward} disabled={!isCurrentComplete}>
              {isFinalLesson ? (isFinalTrack ? '실제 에디터 열기' : '다음 트랙') : '다음 과정'} <ChevronRight size={16} />
            </button>
          </aside>
        </div>}
      </main>
    </div>
  );
}

function TrackCard({ track, progress, foundationComplete, onOpen, featured = false }) {
  const Icon = track.icon;
  const completed = track.lessons.filter((lesson) => progress.completed[lesson.id]).length;
  const percent = Math.round((completed / track.lessons.length) * 100);
  const isComplete = completed === track.lessons.length;
  const actionLabel = isComplete ? '다시 보기' : completed ? '이어하기' : '시작하기';

  return (
    <button type="button" className={`tutorial-track-card ${featured ? 'featured' : ''}`} onClick={() => onOpen(track.id)}>
      <span className="tutorial-track-card-icon"><Icon size={20} /></span>
      <span className="tutorial-track-card-copy">
        <span className="tutorial-track-card-meta">
          <em>{track.level === 'basic' ? '기본' : '심화'}</em>
          {track.level === 'advanced' && !foundationComplete && <small>기본 학습 권장</small>}
        </span>
        <strong>{track.title}</strong>
        <span>{track.shortTitle}</span>
        <p>{track.description}</p>
      </span>
      <span className="tutorial-track-card-progress">
        <span><i style={{ width: `${percent}%` }} /></span>
        <small>{completed}/{track.lessons.length}</small>
      </span>
      <span className="tutorial-track-card-action">{actionLabel}<ArrowRight size={15} /></span>
    </button>
  );
}

export default TutorialPage;
