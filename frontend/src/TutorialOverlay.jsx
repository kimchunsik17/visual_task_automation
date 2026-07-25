import { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import './TutorialOverlay.css';

const PADDING = 8;
const GAP = 16;
const VIEWPORT_MARGIN = 12;
const DEFAULT_SIZE = { width: 280, height: 140 }; // 실측 전 첫 프레임용 추정치

// steps: [{ target: 'css selector', title, description, placement?: 'bottom'|'top'|'left'|'right' }]
// storageKey: localStorage key used to remember the tutorial was already seen/skipped.
const TutorialOverlay = ({ steps, storageKey }) => {
  const [started, setStarted] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [rect, setRect] = useState(null);
  const [tooltipSize, setTooltipSize] = useState(DEFAULT_SIZE);
  const tooltipRef = useRef(null);

  // 첫 방문일 때만 시작한다. 타겟 엘리먼트가 아직 렌더링 전일 수 있어 잠깐 재시도한다.
  useEffect(() => {
    if (localStorage.getItem(storageKey)) return;
    let attempts = 0;
    const tryStart = () => {
      attempts += 1;
      const el = document.querySelector(steps[0]?.target);
      if (el) {
        setStarted(true);
      } else if (attempts < 20) {
        setTimeout(tryStart, 150);
      }
    };
    tryStart();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  const updateRect = useCallback(() => {
    if (!started) return;
    const step = steps[stepIndex];
    const el = step && document.querySelector(step.target);
    if (el) {
      setRect(el.getBoundingClientRect());
    } else {
      // 타겟이 없는 스텝(예: 조건부 렌더링된 버튼)은 건너뛴다.
      setStepIndex((i) => (i < steps.length - 1 ? i + 1 : i));
    }
  }, [started, stepIndex, steps]);

  useLayoutEffect(() => {
    updateRect();
  }, [updateRect]);

  useEffect(() => {
    if (!started) return;
    window.addEventListener('resize', updateRect);
    window.addEventListener('scroll', updateRect, true);
    return () => {
      window.removeEventListener('resize', updateRect);
      window.removeEventListener('scroll', updateRect, true);
    };
  }, [started, updateRect]);

  // 툴팁이 실제로 그려진 뒤(내용에 따라 높이가 다름) 크기를 측정해서, 그 크기를 반영한
  // 위치를 다음 렌더에서 바로 잡는다 — useLayoutEffect라 페인트 전에 끝나서 깜빡임이 없다.
  // 의도적으로 deps 없이 매 렌더 후 측정한다 — 내부 동일값 가드가 있어 안정된 크기에서는
  // setState가 트리거되지 않으므로 무한 루프로 이어지지 않는다.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    if (!tooltipRef.current) return;
    const r = tooltipRef.current.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      setTooltipSize((prev) => (prev.width === r.width && prev.height === r.height ? prev : { width: r.width, height: r.height }));
    }
  });

  const finish = () => {
    localStorage.setItem(storageKey, '1');
    setStarted(false);
  };

  if (!started || !rect) return null;

  const step = steps[stepIndex];
  const isLast = stepIndex === steps.length - 1;

  const box = {
    top: Math.max(rect.top - PADDING, 0),
    left: Math.max(rect.left - PADDING, 0),
    width: rect.width + PADDING * 2,
    height: rect.height + PADDING * 2,
  };

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const tw = tooltipSize.width;
  const th = tooltipSize.height;

  // 하이라이트 박스 기준 아래/위/좌/우 중 화면에 들어맞는 위치를 고른 뒤,
  // 뷰포트 경계(모서리 근처 타겟 포함)를 절대 벗어나지 않도록 클램프한다.
  const { left, top } = (() => {
    const preferred = step.placement || 'bottom';
    const spaceBelow = vh - (box.top + box.height);
    const spaceRight = vw - (box.left + box.width);
    let placement = preferred;
    if (preferred === 'bottom' && spaceBelow < th + GAP + 8) placement = 'top';
    if (preferred === 'left' && box.left < tw + GAP + 8) placement = 'right';
    if (preferred === 'right' && spaceRight < tw + GAP + 8) placement = 'left';

    let rawLeft, rawTop;
    if (placement === 'top') {
      rawLeft = box.left;
      rawTop = box.top - GAP - th;
    } else if (placement === 'left') {
      rawLeft = box.left - GAP - tw;
      rawTop = box.top;
    } else if (placement === 'right') {
      rawLeft = box.left + box.width + GAP;
      rawTop = box.top;
    } else {
      rawLeft = box.left;
      rawTop = box.top + box.height + GAP;
    }

    const maxLeft = Math.max(vw - tw - VIEWPORT_MARGIN, VIEWPORT_MARGIN);
    const maxTop = Math.max(vh - th - VIEWPORT_MARGIN, VIEWPORT_MARGIN);
    return {
      left: Math.min(Math.max(rawLeft, VIEWPORT_MARGIN), maxLeft),
      top: Math.min(Math.max(rawTop, VIEWPORT_MARGIN), maxTop),
    };
  })();

  return createPortal(
    <div className="tutorial-overlay-root">
      <div className="tutorial-dim" style={{ top: 0, left: 0, width: '100vw', height: Math.max(box.top, 0) }} />
      <div className="tutorial-dim" style={{ top: box.top + box.height, left: 0, width: '100vw', height: Math.max(vh - (box.top + box.height), 0) }} />
      <div className="tutorial-dim" style={{ top: box.top, left: 0, width: Math.max(box.left, 0), height: box.height }} />
      <div className="tutorial-dim" style={{ top: box.top, left: box.left + box.width, width: Math.max(vw - (box.left + box.width), 0), height: box.height }} />

      <div className="tutorial-highlight" style={box} />

      <div
        ref={tooltipRef}
        className="tutorial-tooltip"
        style={{
          left,
          top,
          width: Math.min(320, vw - VIEWPORT_MARGIN * 2),
        }}
      >
        <button className="tutorial-close" onClick={finish} aria-label="튜토리얼 닫기">
          <X size={16} />
        </button>
        <div className="tutorial-step-count">{stepIndex + 1} / {steps.length}</div>
        <h4 className="tutorial-title">{step.title}</h4>
        <p className="tutorial-desc">{step.description}</p>
        <div className="tutorial-actions">
          <button className="tutorial-skip" onClick={finish}>건너뛰기</button>
          <div className="tutorial-nav">
            {stepIndex > 0 && (
              <button className="tutorial-btn-secondary" onClick={() => setStepIndex((i) => i - 1)}>이전</button>
            )}
            <button className="tutorial-btn-primary" onClick={() => (isLast ? finish() : setStepIndex((i) => i + 1))}>
              {isLast ? '완료' : '다음'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default TutorialOverlay;
