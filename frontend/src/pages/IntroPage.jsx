import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart, Bot, FileText, ArrowRight, Play, MessageCircle, Calendar, Hash, Mail, Send, BookOpen, Wand2, LayoutGrid, Shield, Star } from 'lucide-react';
import './IntroPage.css';
import demo1 from '../assets/demo-1.webp';
import demo2 from '../assets/demo-2.webp';
import demo3 from '../assets/demo-3.webp';

function IntroPage() {
  const navigate = useNavigate();

  // Simple intersection observer to trigger fade-up animations on scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
          }
        });
      },
      { threshold: 0.1 }
    );

    const elements = document.querySelectorAll('.fade-up-element');
    elements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);

  return (
    <div className="intro-page-layout">
      {/* Background Orbs for modern SaaS look */}
      <div className="bg-orb orb-1"></div>
      <div className="bg-orb orb-2"></div>
      <div className="bg-orb orb-3"></div>

      <main className="intro-content">

        {/* HERO SECTION */}
        <section className="intro-hero">
          <div className="hero-glow-bg"></div>
          <div className="hero-text fade-up-element" style={{ transitionDelay: '0ms' }}>
            <h1 className="hero-title">
              <span className="text-gradient hero-title-top">코딩 없이 연결하는</span><br />시각적 업무 자동화
            </h1>
            <p className="hero-subtitle">
              반복되는 업무를 줄이고 중요한 일에 집중하세요.<br />
              드래그 앤 드롭으로 나만의 업무 자동화를 구축할 수 있습니다.
            </p>
            <div className="hero-actions">
              <button className="btn-primary-glow" onClick={() => navigate('/workflows')}>
                무료로 시작하기 <ArrowRight size={18} />
              </button>
            </div>
          </div>

          <div className="hero-image-wrapper fade-up-element" style={{ transitionDelay: '200ms' }}>
            <div className="hero-image-glow"></div>
            <div className="hero-image-container floating-anim">
              <div className="hero-gif-grid">
                <div className="major-feature-visual">
                  <img
                    src={demo1}
                    alt="생성형 AI 워크플로우 시연"
                    style={{ width: '100%', borderRadius: '20px', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)' }}
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* PURPOSE & TARGET SECTION */}
        <section className="intro-purpose-target">
          <div className="purpose-target-container">
            <div className="purpose-box fade-up-element" style={{ transitionDelay: '0ms' }}>
              <h2 className="intro-section-title">왜 이 서비스를 만들었나요?</h2>
              <p className="purpose-text">
                기존의 해외 자동화 툴들은 국내 환경에 맞춘 연동이 부족하고 진입 장벽이 높았습니다.
                우리는 누구나 쉽게 접근할 수 있는 직관적인 시각적 인터페이스를 바탕으로,
                국내 생태계에 최적화된 강력한 AI 워크플로우를 제공하고자 합니다.
              </p>
            </div>

            <div className="target-box fade-up-element" style={{ transitionDelay: '200ms' }}>
              <h2 className="intro-section-title">이런 분이 사용하면 좋아요</h2>
              <ul className="target-list">
                <li>
                  <div className="target-icon"><MessageCircle size={20} /></div>
                  <span>한국어 서비스와의 연동을 바라시는 분</span>
                </li>
                <li>
                  <div className="target-icon"><Bot size={20} /></div>
                  <span>코딩은 어렵지만 LLM 업무 자동화를 구현하시고 싶은 분</span>
                </li>
              </ul>
            </div>
          </div>
        </section>

        {/* INFINITE MARQUEE (AVAILABLE TASKS) */}
        <section className="intro-marquee-section fade-up-element">
          <p className="marquee-label">AVAILABLE TASKS</p>
          <div className="marquee-container">
            <div className="marquee-track">
              {[...Array(6)].map((_, i) => (
                <React.Fragment key={`track-${i}`}>
                  <div className="marquee-item"><MessageCircle size={20} /> KakaoTalk</div>
                  <div className="marquee-item"><Calendar size={20} /> Google Calendar</div>
                  <div className="marquee-item"><Hash size={20} /> Slack</div>
                  <div className="marquee-item"><BookOpen size={20} /> Notion</div>
                  <div className="marquee-item"><Mail size={20} /> Gmail</div>
                  <div className="marquee-item"><Bot size={20} /> OpenAI</div>
                  <div className="marquee-item"><Send size={20} /> Telegram</div>
                </React.Fragment>
              ))}
            </div>
          </div>
        </section>

        {/* FEATURES / BENTO GRID SECTION */}
        <section className="intro-features">
          <div className="intro-section-header fade-up-element">
            <h2 className="intro-section-title">무엇을 할 수 있나요?</h2>
            <p className="intro-section-subtitle">복잡한 코딩 없이, 수십 가지 작업을 자동화하여 업무 효율을 극대화하세요.</p>
          </div>

          <div className="bento-grid">
            {/* Card 1: Large Span 2 */}
            <div className="bento-card bento-large fade-up-element" style={{ transitionDelay: '0ms' }}>
              <div className="bento-content">
                <div className="feature-icon"><BarChart size={24} /></div>
                <h3>정기적인 데이터 수집 및 AI 리포팅</h3>
                <p>웹 스크래핑과 스케줄러 노드를 결합하여 매일 원하는 시간에 데이터를 수집하세요. 수집된 데이터는 LLM 노드를 거쳐 요약된 인사이트 리포트로 변환되며, 이메일이나 슬랙으로 자동 발송됩니다. 매일 아침 직접 뉴스를 찾아볼 필요가 없습니다.</p>
              </div>
              <div className="bento-bg-glow"></div>
            </div>

            {/* Card 2: Small Span 1 */}
            <div className="bento-card bento-small fade-up-element" style={{ transitionDelay: '150ms' }}>
              <div className="bento-content">
                <div className="feature-icon"><MessageCircle size={24} /></div>
                <h3>실시간 모니터링 알림</h3>
                <p>웹훅(Webhook)을 통해 특정 이벤트가 발생할 때마다 카카오톡이나 텔레그램으로 즉시 알림을 받을 수 있습니다. 장애 상황이나 중요 알람을 놓치지 마세요.</p>
              </div>
            </div>

            {/* Card 3: Small Span 1 */}
            <div className="bento-card bento-small fade-up-element" style={{ transitionDelay: '300ms' }}>
              <div className="bento-content">
                <div className="feature-icon"><FileText size={24} /></div>
                <h3>구글 캘린더 & 시트 문서 자동화</h3>
                <p>스케줄러와 구글 API를 연동하여 일정을 관리하고, 고객 정보나 로그 데이터를 구글 시트에 차곡차곡 자동으로 기록하세요.</p>
              </div>
            </div>

            {/* Card 4: Large Span 2 */}
            <div className="bento-card bento-large fade-up-element" style={{ transitionDelay: '450ms' }}>
              <div className="bento-content">
                <div className="feature-icon"><Bot size={24} /></div>
                <h3>고객 CS 자동화 봇 구축</h3>
                <p>고객의 문의 메일이나 메시지가 들어오면 GPT-4 또는 Claude 3가 내용을 분석하여 적절한 답변 초안을 작성하거나 바로 회신합니다. 당신의 훌륭한 AI 비서가 되어드립니다.</p>
              </div>
              <div className="bento-bg-glow"></div>
            </div>

            {/* Card 5: Small Span 1 (formerly 6) */}
            <div className="bento-card bento-small fade-up-element" style={{ transitionDelay: '0ms' }}>
              <div className="bento-content">
                <div className="feature-icon"><LayoutGrid size={24} /></div>
                <h3>조건부 분기 처리</h3>
                <p>If/Else 노드를 사용하여 데이터의 값이나 상황에 따라 다르게 동작하도록 복잡한 로직도 쉽게 설계할 수 있습니다.</p>
              </div>
            </div>

            {/* Card 6: Large Span 2 (formerly 7) */}
            <div className="bento-card bento-large fade-up-element" style={{ transitionDelay: '150ms' }}>
              <div className="bento-content">
                <div className="feature-icon"><Shield size={24} /></div>
                <h3>안전하고 투명한 모니터링</h3>
                <p>모든 노드의 실행 기록과 실시간 로그를 한눈에 파악하세요. 시각적 인터페이스를 통해 어디서 데이터가 멈췄는지 직관적으로 확인하고, 예상치 못한 에러에 빠르게 대응할 수 있습니다.</p>
              </div>
              <div className="bento-bg-glow"></div>
            </div>
          </div>
        </section>

        {/* MAJOR FEATURE 1: Generative LLM */}
        <section className="intro-major-feature fade-up-element">
          <div className="major-feature-content">
            <h2 className="major-feature-title">한국말로 만드는 업무 자동화</h2>
            <p className="major-feature-desc">
              "매일 아침 날씨와 주요 뉴스를 요약해서 카카오톡으로 보내줘" 라고 입력해보세요.<br /><br />
              직접 노드를 찾고 연결할 필요가 없습니다. 내장된 LLM이 사용자의 의도를 정확히 파악하여 필요한 노드들을 자동으로 배치해 완벽하게 동작하는 파이프라인을 즉석에서 구축해 줍니다.
            </p>
          </div>
          <div className="major-feature-visual">
            <img
              src={demo2}
              alt="생성형 AI 워크플로우 시연"
              style={{ width: '100%', borderRadius: '20px', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)' }}
            />
          </div>
        </section>

        {/* MAJOR FEATURE 2: Evaluation */}
        <section className="intro-major-feature reverse fade-up-element">
          <div className="major-feature-content">
            <h2 className="major-feature-title">얼마나 좋아?<br></br>완벽을 기하는 파이프라인 평가</h2>
            <p className="major-feature-desc">
              단순히 답변을 생성하는 데 그치지 마세요. 생성된 워크플로우나 봇이 얼마나 정확하고 유용한 답변을 하는지 체계적으로 평가하세요.<br /><br />
              평가 전용 노드를 통해 답변의 품질을 자동으로 측정하고 분석하여, 지속적으로 프롬프트와 파이프라인을 개선할 수 있는 강력한 피드백 루프를 제공합니다.
            </p>
          </div>
          <div className="major-feature-visual">
            <img
              src={demo3}
              alt="평가 기능 시연"
              style={{ width: '100%', borderRadius: '20px', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)' }}
            />
          </div>
        </section>

        {/* HOW IT WORKS SECTION */}
        <section className="intro-how-it-works">
          <div className="intro-section-header fade-up-element">
            <h2 className="intro-section-title">어떻게 사용하나요?</h2>
            <p className="intro-section-subtitle">쉽고 빠르지만 놀랄만큼 강력합니다.</p>
          </div>

          <div className="intro-steps-container">
            <div className="intro-step-item fade-up-element" style={{ transitionDelay: '0ms' }}>
              <div className="intro-step-icon-wrapper">
                <div className="intro-step-number">1</div>
              </div>
              <h4>배치</h4>
              <p>원하는 기능의 노드를 작업 공간에 드래그해서 배치해보세요.</p>
            </div>
            <div className="intro-step-line fade-up-element" style={{ transitionDelay: '150ms' }}></div>
            <div className="intro-step-item fade-up-element" style={{ transitionDelay: '200ms' }}>
              <div className="intro-step-icon-wrapper">
                <div className="intro-step-number">2</div>
              </div>
              <h4>연결</h4>
              <p>각 노드를 원하는 실행 순서에 따라 연결해보세요.</p>
            </div>
            <div className="intro-step-line fade-up-element" style={{ transitionDelay: '350ms' }}></div>
            <div className="intro-step-item fade-up-element" style={{ transitionDelay: '400ms' }}>
              <div className="intro-step-icon-wrapper">
                <div className="intro-step-number">3</div>
              </div>
              <h4>실행</h4>
              <p>실행 버튼을 누르거나 스케줄러를 등록하여 파이프라인을 24시간 자동화하세요.</p>
            </div>
          </div>
        </section>

        {/* BOTTOM CTA */}
        <section className="intro-cta fade-up-element">
          <h2>지금 바로 나만의 자동화를 만들어보세요.</h2>
          <button className="btn-primary-glow" onClick={() => navigate('/workflows')}>
            <Play size={18} /> 시작하기
          </button>
        </section>

        {/* FOOTER / TECH STACK & DEVELOPERS */}
        <section className="intro-footer fade-up-element">
          <div className="footer-tech-stack">
            <h4>기술 스택</h4>
            <div className="tech-badges">
              <span className="tech-badge">React</span>
              <span className="tech-badge">Vite</span>
              <span className="tech-badge">FastAPI</span>
              <span className="tech-badge">PostgreSQL</span>
              <span className="tech-badge">AWS EC2</span>
            </div>
          </div>
          <div className="footer-developers">
            <p>Developed by 이온규, 신예나, 김동훈</p>
          </div>
        </section>

      </main>
    </div>
  );
}

export default IntroPage;
