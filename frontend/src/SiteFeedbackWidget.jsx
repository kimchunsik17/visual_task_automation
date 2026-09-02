import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, Send, Star, X, MessageSquarePlus } from 'lucide-react';
import { Icon } from './icons';
import axios from 'axios';
import './SiteFeedbackWidget.css';

// 점수 옆에 말로 뜻을 붙인다 — 별 개수만 보고 "3점이 보통인가?" 를 고민하지 않게.
const SCORE_LABELS = ['', '별로예요', '아쉬워요', '보통이에요', '좋아요', '아주 좋아요'];
const SKIPPED = 'skip';

const StarRating = ({ value, onChange, questionTitle }) => (
  <div className="feedback-stars" role="group" aria-label={`${questionTitle} 점수`}>
    {[1, 2, 3, 4, 5].map((n) => {
      const on = typeof value === 'number' && n <= value;
      return (
        <button
          key={n}
          type="button"
          className={on ? 'is-on' : ''}
          onClick={() => onChange(n)}
          aria-label={`${n}점 ${SCORE_LABELS[n]}`}
          aria-pressed={value === n}
        >
          <Star size={22} fill={on ? 'currentColor' : 'none'} />
        </button>
      );
    })}
  </div>
);

const SiteFeedbackWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [sections, setSections] = useState([]);
  const [loadFailed, setLoadFailed] = useState(false);
  // 값은 1~5 또는 SKIPPED('잘 모르겠어요'). 둘 다 "답했다"로 치되 SKIPPED 는 서버에 보내지 않는다.
  const [answers, setAnswers] = useState({});
  const [comment, setComment] = useState('');
  const [step, setStep] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [alreadySubmitted, setAlreadySubmitted] = useState(false);

  const authHeaders = useCallback(() => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, []);

  useEffect(() => {
    if (!localStorage.getItem('token')) return;
    axios.get('/api/site-feedback/me', { headers: authHeaders() })
      .then((res) => setAlreadySubmitted(!!res.data.submitted))
      .catch((e) => console.error('Failed to check site feedback status', e));
  }, [authHeaders]);

  // 문항 정본은 서버에 있다. 여기에 같은 목록을 두면 한쪽만 고쳐졌을 때 조용히 갈라진다.
  useEffect(() => {
    if (!isOpen || sections.length > 0) return;
    axios.get('/api/site-feedback/questions')
      .then((res) => setSections(res.data?.sections || []))
      .catch(() => setLoadFailed(true));
  }, [isOpen, sections.length]);

  // 마지막 한 걸음은 자유 의견이다 — 문항 구획 뒤에 붙는다.
  const totalSteps = sections.length + 1;
  const isCommentStep = step >= sections.length;
  const currentSection = sections[step];

  const allQuestions = useMemo(
    () => sections.flatMap((section) => section.questions),
    [sections],
  );
  const ratedCount = useMemo(
    () => allQuestions.filter((q) => typeof answers[q.key] === 'number').length,
    [allQuestions, answers],
  );
  const remainingHere = currentSection
    ? currentSection.questions.filter((q) => answers[q.key] === undefined).length
    : 0;

  const setAnswer = (key, value) => setAnswers((prev) => ({ ...prev, [key]: value }));

  const close = () => setIsOpen(false);

  const handleSubmit = async () => {
    if (alreadySubmitted || isSubmitting) return;
    const scores = Object.fromEntries(
      Object.entries(answers).filter(([, value]) => typeof value === 'number'),
    );
    if (Object.keys(scores).length === 0) {
      alert('점수를 매긴 문항이 하나도 없습니다. 한 문항이라도 별점을 남겨주세요.', 'warning');
      return;
    }
    setIsSubmitting(true);
    try {
      await axios.post('/api/site-feedback', { scores, comment: comment.trim() || null },
                       { headers: authHeaders() });
      setAnswers({});
      setComment('');
      setStep(0);
      setIsOpen(false);
      setAlreadySubmitted(true);
      alert('소중한 의견 감사합니다! 서비스 개선에 반영하겠습니다.');
    } catch (error) {
      console.error(error);
      if (error.response?.status === 409) {
        // 다른 탭에서 이미 냈다. 막는 것은 서버이므로 화면 상태만 맞춰 준다.
        setAlreadySubmitted(true);
        setIsOpen(false);
      }
      alert(error.response?.data?.detail || '평가 제출 중 오류가 발생했습니다.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderQuestion = (question, index) => {
    const value = answers[question.key];
    const skipped = value === SKIPPED;
    return (
      <div
        key={question.key}
        className={`feedback-question ${value !== undefined ? 'is-answered' : ''} ${skipped ? 'is-skipped' : ''}`}
      >
        <div className="feedback-question-copy">
          <span className="feedback-question-no">{index + 1}.</span>
          <span>
            <strong>{question.title}</strong>
            <span>{question.help}</span>
          </span>
        </div>
        <div className="feedback-answer">
          <StarRating
            value={skipped ? 0 : value}
            onChange={(n) => setAnswer(question.key, n)}
            questionTitle={question.title}
          />
          <span className={`feedback-answer-label ${typeof value === 'number' ? '' : 'is-empty'}`}>
            {typeof value === 'number' ? SCORE_LABELS[value] : skipped ? '건너뜀' : '선택 전'}
          </span>
          <button
            type="button"
            className={`feedback-skip ${skipped ? 'is-on' : ''}`}
            onClick={() => setAnswer(question.key, skipped ? undefined : SKIPPED)}
            aria-pressed={skipped}
          >
            잘 모르겠어요
          </button>
        </div>
      </div>
    );
  };

  return (
    <>
      <button
        type="button"
        className={`feedback-fab ${alreadySubmitted ? 'is-done' : ''}`}
        onClick={() => setIsOpen(true)}
        title={alreadySubmitted ? '이미 평가를 제출하셨습니다' : '웹사이트 평가하기'}
      >
        {alreadySubmitted ? <Icon name="status-success" size={17} /> : <MessageSquarePlus size={17} />}
        {alreadySubmitted ? '평가 완료' : '웹사이트 평가하기'}
      </button>

      {isOpen && (
        <div className="feedback-overlay" role="dialog" aria-modal="true" aria-label="웹사이트 평가">
          {alreadySubmitted ? (
            <div className="feedback-done">
              <button type="button" className="feedback-close" onClick={close} aria-label="닫기"><X size={18} /></button>
              <Icon name="status-success" size={38} color="#10b981" />
              <h2>이미 평가를 제출하셨습니다</h2>
              <p>소중한 의견 감사합니다. 평가는 계정당 한 번만 남길 수 있어요.</p>
            </div>
          ) : (
            <div className="feedback-modal">
              <header className="feedback-head">
                <div className="feedback-head-copy">
                  <h2>웹사이트 평가하기</h2>
                  <p>{isCommentStep
                    ? '마지막이에요. 하고 싶은 말이 있다면 자유롭게 남겨주세요.'
                    : '네 문항씩 나눠서 여쭤볼게요. 편하게 느낀 대로 골라주세요.'}</p>
                </div>
                <button type="button" className="feedback-close" onClick={close} aria-label="닫기"><X size={18} /></button>
              </header>

              {sections.length > 0 && (
                <div className="feedback-steps">
                  <div className="feedback-steps-track" aria-hidden="true">
                    {Array.from({ length: totalSteps }).map((unused, index) => (
                      <i
                        key={index}
                        className={index < step ? 'is-done' : index === step ? 'is-current' : ''}
                      />
                    ))}
                  </div>
                  <small>{step + 1} / {totalSteps} 단계</small>
                </div>
              )}

              <div className="feedback-body">
                {loadFailed ? (
                  <p className="feedback-loading">문항을 불러오지 못했습니다. 잠시 후 다시 열어주세요.</p>
                ) : sections.length === 0 ? (
                  <p className="feedback-loading">문항을 불러오는 중…</p>
                ) : isCommentStep ? (
                  <div className="feedback-comment">
                    <label htmlFor="feedback-comment-input">더 하고 싶은 말 (선택)</label>
                    <textarea
                      id="feedback-comment-input"
                      value={comment}
                      onChange={(event) => setComment(event.target.value)}
                      placeholder="불편했던 점, 있으면 좋겠는 기능 등 무엇이든 좋아요."
                    />
                    <div className="feedback-recap">
                      <Icon name="status-success" size={16} />
                      <span>
                        전체 {allQuestions.length}문항 중 <strong>{ratedCount}문항</strong>에 점수를 남기셨어요.
                        {ratedCount < allQuestions.length && ' 나머지는 ‘잘 모르겠어요’로 넘어갑니다.'}
                      </span>
                    </div>
                  </div>
                ) : (
                  <>
                    <h3 className="feedback-section-title">{currentSection.title}</h3>
                    <p className="feedback-section-hint">{currentSection.hint}</p>
                    {currentSection.questions.map(renderQuestion)}
                  </>
                )}
              </div>

              <footer className="feedback-foot">
                {step > 0 && (
                  <button type="button" className="feedback-btn" onClick={() => setStep((s) => s - 1)}>
                    <ArrowLeft size={15} /> 이전
                  </button>
                )}
                <span className="feedback-foot-note">
                  {isCommentStep
                    ? '제출하면 수정할 수 없어요.'
                    : remainingHere > 0
                      ? `이 단락에서 ${remainingHere}문항 남았어요.`
                      : '다 고르셨어요. 다음으로 넘어가세요.'}
                </span>
                {isCommentStep ? (
                  <button
                    type="button"
                    className="feedback-btn is-primary"
                    onClick={handleSubmit}
                    disabled={isSubmitting || ratedCount === 0}
                  >
                    <Send size={15} /> {isSubmitting ? '제출 중…' : '평가 제출하기'}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="feedback-btn is-primary"
                    onClick={() => setStep((s) => s + 1)}
                    disabled={sections.length === 0 || remainingHere > 0}
                  >
                    {step === sections.length - 1 ? '마지막 단계로' : '다음 단락'} <ArrowRight size={15} />
                  </button>
                )}
              </footer>
            </div>
          )}
        </div>
      )}
    </>
  );
};

export default SiteFeedbackWidget;
