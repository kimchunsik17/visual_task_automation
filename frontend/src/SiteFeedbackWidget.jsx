import React, { useState, useEffect } from 'react';
import { Star, X, MessageSquarePlus, CheckCircle2 } from 'lucide-react';
import axios from 'axios';

const CATEGORIES = [
  {
    title: 'LLM 기반 워크플로우 생성 퀄리티',
    questions: [
      ['gen_intent_match', '프롬프트 입력 시 사용자가 의도한 대로 워크플로우가 정확하게 생성되는가'],
      ['gen_logic_match', 'LLM이 제안한 자동화 단계가 실제 업무 로직과 잘 일치하는가'],
      ['gen_edit_convenience', '자동 생성된 워크플로우를 사용자가 상황에 맞게 수정하고 편집하기 편리한가'],
      ['gen_detail_completeness', '복잡한 조건을 요구했을 때 누락 없이 디테일한 부분까지 잘 반영하여 생성하는가'],
    ],
  },
  {
    title: 'UI/UX 및 사용 편의성',
    questions: [
      ['ux_intuitiveness', '전반적인 인터페이스가 직관적이고 처음 접속해도 적응하기 쉬운가'],
      ['ux_visual_clarity', '복잡한 자동화 흐름을 시각적으로 쉽게 파악할 수 있도록 화면이 구성되었는가'],
      ['ux_menu_layout', '메뉴 및 기능 버튼의 배치가 업무 흐름을 방해하지 않고 자연스러운가'],
      ['ux_customization', '다크모드 지원이나 화면 분할 등 작업 환경을 커스터마이징하기 좋은가'],
    ],
  },
  {
    title: '시스템 성능 및 안정성',
    questions: [
      ['perf_speed', '워크플로우가 실행될 때 지연 없이 빠른 속도로 처리되는가'],
      ['perf_stability', '작업 실행 중 원인을 알 수 없는 오류나 멈춤 현상이 발생하지 않는가'],
      ['perf_error_clarity', '에러가 발생했을 때 어디서 문제가 생겼는지 명확하고 쉽게 안내해 주는가'],
    ],
  },
  {
    title: '외부 서비스 연동 및 확장성',
    questions: [
      ['integration_smoothness', '평소 자주 사용하는 외부 서비스나 앱과의 연동이 매끄럽게 이루어지는가'],
      ['integration_extensibility', '새로운 API를 추가하거나 커스텀 기능을 설정하는 과정이 편리한가'],
    ],
  },
];

const TOTAL_QUESTIONS = CATEGORIES.reduce((sum, c) => sum + c.questions.length, 0);

const StarRating = ({ value, onChange }) => (
  <div style={{ display: 'flex', gap: '0.25rem' }}>
    {[1, 2, 3, 4, 5].map((n) => (
      <button
        key={n}
        type="button"
        onClick={() => onChange(n)}
        title={`${n}점`}
        style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '0.15rem', display: 'flex' }}
      >
        <Star
          size={20}
          color={n <= value ? '#f59e0b' : 'var(--border-color)'}
          fill={n <= value ? '#f59e0b' : 'none'}
        />
      </button>
    ))}
  </div>
);

const SiteFeedbackWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [scores, setScores] = useState({});
  const [comment, setComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [alreadySubmitted, setAlreadySubmitted] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    axios.get('/api/site-feedback/me', { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => setAlreadySubmitted(!!res.data.submitted))
      .catch((e) => console.error('Failed to check site feedback status', e));
  }, []);

  const answeredCount = Object.keys(scores).length;
  const isComplete = answeredCount === TOTAL_QUESTIONS;

  const setScore = (key, val) => setScores((prev) => ({ ...prev, [key]: val }));

  const handleSubmit = async () => {
    if (!isComplete || alreadySubmitted) return;
    setIsSubmitting(true);
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await axios.post('/api/site-feedback', { scores, comment: comment.trim() || null }, { headers });
      alert('소중한 의견 감사합니다! 서비스 개선에 반영하겠습니다.');
      setScores({});
      setComment('');
      setIsOpen(false);
      setAlreadySubmitted(true);
    } catch (error) {
      console.error(error);
      if (error.response?.status === 409) {
        // 다른 탭 등에서 이미 제출한 경우 — 서버가 최종적으로 막아준다
        setAlreadySubmitted(true);
        setIsOpen(false);
      }
      alert(error.response?.data?.detail || '평가 제출 중 오류가 발생했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        style={{
          position: 'fixed',
          right: '1.5rem',
          bottom: '1.5rem',
          zIndex: 900,
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.75rem 1.1rem',
          borderRadius: '999px',
          background: alreadySubmitted ? 'var(--card-bg)' : 'var(--primary-color)',
          color: alreadySubmitted ? 'var(--text-muted)' : '#fff',
          border: alreadySubmitted ? '1px solid var(--border-color)' : 'none',
          boxShadow: '0 6px 18px rgba(0, 0, 0, 0.3)',
          cursor: 'pointer',
          fontSize: '0.85rem',
          fontWeight: 600,
        }}
        title={alreadySubmitted ? '이미 평가를 제출하셨습니다' : '웹사이트 평가하기'}
      >
        {alreadySubmitted ? <CheckCircle2 size={18} /> : <MessageSquarePlus size={18} />}
        {alreadySubmitted ? '평가 완료' : '웹사이트 평가하기'}
      </button>

      {isOpen && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.7)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          {alreadySubmitted ? (
            <div
              style={{
                backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)',
                borderRadius: '12px', width: '360px', maxWidth: '92vw',
                padding: '2rem', position: 'relative', display: 'flex', flexDirection: 'column',
                alignItems: 'center', textAlign: 'center', gap: '0.75rem',
              }}
            >
              <button
                onClick={() => setIsOpen(false)}
                style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
              <CheckCircle2 size={40} color="#10b981" />
              <h2 style={{ margin: 0, color: 'var(--text-color)', fontSize: '1.1rem' }}>이미 평가를 제출하셨습니다</h2>
              <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                소중한 의견 감사합니다! 평가는 계정당 한 번만 제출할 수 있어요.
              </p>
            </div>
          ) : (
          <div
            style={{
              backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)',
              borderRadius: '12px', width: '640px', maxWidth: '92vw', maxHeight: '85vh',
              padding: '1.5rem', position: 'relative', display: 'flex', flexDirection: 'column',
            }}
          >
            <button
              onClick={() => setIsOpen(false)}
              style={{ position: 'absolute', top: '1.5rem', right: '1.5rem', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
            >
              <X size={20} />
            </button>

            <h2 style={{ margin: '0 0 0.25rem 0', color: 'var(--text-color)', fontSize: '1.3rem' }}>⭐ 웹사이트 평가하기</h2>
            <p style={{ margin: '0 0 1.25rem 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              각 문항을 1~5점으로 평가해주세요 ({answeredCount}/{TOTAL_QUESTIONS})
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto', paddingRight: '0.5rem', flex: 1 }}>
              {CATEGORIES.map((cat) => (
                <div key={cat.title} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <h3 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-color)', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                    {cat.title}
                  </h3>
                  {cat.questions.map(([key, label]) => (
                    <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-color)', lineHeight: 1.4 }}>{label}</span>
                      <StarRating value={scores[key] || 0} onChange={(v) => setScore(key, v)} />
                    </div>
                  ))}
                </div>
              ))}

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-color)', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                  추가 의견 (선택)
                </h3>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="자유롭게 의견을 남겨주세요..."
                  style={{ width: '100%', minHeight: '70px', padding: '0.6rem', borderRadius: '6px', background: 'var(--btn-active-bg)', color: 'var(--text-color)', border: '1px solid var(--border-color)', resize: 'vertical', fontFamily: 'inherit' }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '1.25rem', paddingTop: '1.25rem', borderTop: '1px solid var(--border-color)' }}>
              <button className="btn-secondary" onClick={() => setIsOpen(false)} disabled={isSubmitting}>취소</button>
              <button className="btn-run" onClick={handleSubmit} disabled={isSubmitting || !isComplete}>
                {isSubmitting ? '제출 중...' : isComplete ? '제출하기' : `${TOTAL_QUESTIONS - answeredCount}개 문항 남음`}
              </button>
            </div>
          </div>
          )}
        </div>
      )}
    </>
  );
};

export default SiteFeedbackWidget;
