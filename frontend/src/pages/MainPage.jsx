import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import axios from 'axios';
import AiThinking from '../components/AiThinking';
import { ArrowRight, ArrowUp, BarChart3, BellRing, CalendarClock, Check, ChevronDown, ChevronLeft, ChevronRight, Database, FileSpreadsheet, FileText, LayoutGrid, Mail, MessageSquare, PackageSearch, Paperclip, Plus, SlidersHorizontal, Zap, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import MainSidebar from '../MainSidebar';
import SiteFeedbackWidget from '../SiteFeedbackWidget';
import TutorialOverlay from '../TutorialOverlay';
import OnboardingChecklist from '../OnboardingChecklist';
import { completeOnboardingStep } from '../onboardingProgress';
import './MainPage.css';

const MAIN_TUTORIAL_STEPS = [
  {
    target: '.main-sidebar',
    title: '왼쪽 메뉴',
    description: '내 워크플로우, 커뮤니티 템플릿, 봇/웹훅 관리 등 모든 기능은 이 메뉴에서 접근할 수 있어요.',
    placement: 'right',
  },
  {
    target: '.auto-gen-input-wrapper-minimal',
    title: '자동화 요청하기',
    description: '만들고 싶은 업무 자동화를 자연어로 설명해보세요. 예: "매일 아침 뉴스 요약해서 이메일로 보내줘"',
    placement: 'top',
  },
  {
    target: '[data-tutorial="complexity-btn"]',
    title: '생성 모드 선택',
    description: '빠름/기본/정밀 중 원하는 수준을 골라 워크플로우 생성 방식을 조절할 수 있어요.',
    placement: 'top',
  },
  {
    target: '.btn-generate-minimal',
    title: '워크플로우 생성',
    description: '이 버튼을 누르면 요청에 맞는 워크플로우가 생성돼요. 이후 에디터에서 자유롭게 다듬을 수 있어요.',
    placement: 'top',
  },
];

// 홈 아이디어 목록이 채워지는 방식은 두 갈래다.
//
// 1순위는 **실제로 많이 설치된 커뮤니티 템플릿**(`?sort=installs`)이다. 여기에 사용 수를 함께
//   보여주므로 "인기"라는 말이 근거를 갖는다.
// 2순위는 아래 큐레이션 목록이다. 서비스 초기에는 설치 기록이 거의 없어 1순위만으로는 칸이
//   비므로 나머지를 이걸로 채우고, 카드마다 **'추천' 배지로 구분**한다 — 사용 기록이 없는 것을
//   인기 있는 것처럼 보이게 하지 않기 위해서다.
const RECOMMENDED_IDEAS = [
  { key: 'r-tool', icon: LayoutGrid, label: '사내 도구', prompt: '직원 출퇴근과 휴가 신청을 한곳에서 관리하는 앱 만들기' },
  { key: 'r-cs', icon: MessageSquare, label: '고객 응대', prompt: '고객 문의를 분류하고 담당자에게 자동으로 전달하기' },
  { key: 'r-report', icon: BarChart3, label: '리포트', prompt: '매주 월요일 팀 성과를 요약한 주간 리포트 만들기' },
  { key: 'r-connect', icon: Zap, label: '외부 연동', prompt: '네이버 스토어 주문과 카카오톡 알림 연결하기' },
  { key: 'r-doc', icon: FileSpreadsheet, label: '문서 자동화', prompt: '설문 응답을 엑셀로 정리하고 결과 보고서 만들기' },
  { key: 'r-cal', icon: CalendarClock, label: '일정 관리', prompt: '마감일이 다가오면 담당자에게 단계별로 알림 보내기' },
  { key: 'r-data', icon: Database, label: '데이터 관리', prompt: '여러 부서의 요청 데이터를 모아 검색 가능한 목록 만들기' },
  { key: 'r-mail', icon: Mail, label: '메일 업무', prompt: '중요 메일을 분류하고 답변이 필요한 항목만 모아보기' },
  { key: 'r-stock', icon: PackageSearch, label: '재고 확인', prompt: '상품 재고가 기준 이하로 내려가면 구매 담당자에게 알리기' },
  { key: 'r-watch', icon: BellRing, label: '모니터링', prompt: '서비스 상태를 주기적으로 확인하고 장애 징후 알림 받기' },
];

// 템플릿 분류(community_templates.CATEGORIES)를 아이디어 카드의 표시 이름·아이콘으로 옮긴다.
const TEMPLATE_CATEGORY = {
  automation: { label: '자동화', icon: Zap },
  content: { label: '콘텐츠', icon: FileText },
  data: { label: '데이터', icon: Database },
  notification: { label: '알림', icon: BellRing },
  document: { label: '문서', icon: FileSpreadsheet },
  etc: { label: '기타', icon: LayoutGrid },
};

const IDEA_SLOTS = 8;

function MainPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, token } = useAuth();
  const [autoPrompt, setAutoPrompt] = useState('');
  const [complexityLevel, setComplexityLevel] = useState('low'); // Set low as default
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);
  const promptInputRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  const [isAutoGenerating, setIsAutoGenerating] = useState(false);
  const [generationStage, setGenerationStage] = useState('대기 중');
  const [messages, setMessages] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [activeIdeaIndex, setActiveIdeaIndex] = useState(0);
  const [isIdeaHovered, setIsIdeaHovered] = useState(false);
  const [isIdeaFocused, setIsIdeaFocused] = useState(false);
  // 인기 아이디어의 근거는 커뮤니티 템플릿의 **실제 설치 수**다.
  const [popularIdeas, setPopularIdeas] = useState([]);

  useEffect(() => {
    let cancelled = false;
    axios.get('/api/community/templates', { params: { sort: 'installs', limit: IDEA_SLOTS } })
      .then((res) => {
        if (cancelled) return;
        setPopularIdeas((res.data?.templates || []).map((template) => {
          const category = TEMPLATE_CATEGORY[template.category] || TEMPLATE_CATEGORY.etc;
          return {
            key: `t-${template.slug}`,
            icon: category.icon,
            label: category.label,
            // 제목은 "A → B → C" 꼴이라 프롬프트로 그대로 쓰기 어색하다. 소개 문장이 낫다.
            prompt: (template.description || template.title || '').trim(),
            installs: template.signals?.installs || 0,
          };
        // 설치 기록이 0인 템플릿은 인기 있는 게 아니다 — 그 자리는 추천 아이디어가 채운다.
        }).filter((idea) => idea.prompt && idea.installs > 0));
      })
      // 홈 첫 화면이라 오류 문구를 띄울 자리가 아니다. 목록은 추천 아이디어로 채워진다.
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const ideas = useMemo(
    () => [...popularIdeas, ...RECOMMENDED_IDEAS.slice(0, Math.max(0, IDEA_SLOTS - popularIdeas.length))],
    [popularIdeas],
  );
  // 목록이 짧아졌을 때 선택 위치가 밖으로 나가지 않게 한다.
  useEffect(() => {
    setActiveIdeaIndex((current) => (current < ideas.length ? current : 0));
  }, [ideas.length]);
  const messagesEndRef = useRef(null);
  const draftIdRef = useRef(`draft-${Date.now()}`);
  // 대화 기록을 불러올 때는 전체를 스르륵 훑고 지나가는 느낌 없이 바로 맨 아래로 이동시키기
  // 위한 플래그. 새 메시지가 오갈 때는 그대로 부드럽게 스크롤한다.
  const skipSmoothScrollRef = useRef(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: skipSmoothScrollRef.current ? "auto" : "smooth" });
    skipSmoothScrollRef.current = false;
  }, [messages, isAutoGenerating]);

  useEffect(() => {
    if (location.state?.session) {
      handleSelectSession(location.state.session);
      window.history.replaceState({}, document.title);
    } else if (location.state?.newChat) {
      setMessages([]);
      setActiveSessionId(null);
      draftIdRef.current = `draft-${Date.now()}`;
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  useEffect(() => {
    if (!autoPrompt && promptInputRef.current) promptInputRef.current.style.height = 'auto';
  }, [autoPrompt]);

  useEffect(() => {
    if (messages.length > 0 || isIdeaHovered || isIdeaFocused) return undefined;
    const rotationTimer = window.setInterval(() => {
      setActiveIdeaIndex((current) => (current + 1) % ideas.length);
    }, 4800);
    return () => window.clearInterval(rotationTimer);
  }, [ideas.length, isIdeaFocused, isIdeaHovered, messages.length]);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { headers: { Authorization: `Bearer ${token}` } } : {};
  };

  // overrideMessage: AI가 ask_clarification으로 되물었을 때 뜨는 선택지 칩을 클릭하면, 그 칩의
  // 문구를 입력창에 채워넣는 대신(hint-chip과 달리) 바로 다음 사용자 메시지로 전송한다 — 클로드의
  // 선택지 UI처럼 한 번의 클릭으로 대화가 이어지게 하기 위함.
  const handleAutoGenerate = async (overrideMessage) => {
    const userMessage = (overrideMessage ?? autoPrompt).trim();
    if (!userMessage && selectedFiles.length === 0) return;

    setMessages(prev => [...prev, { role: 'user', content: userMessage || '문서를 첨부했습니다.' }]);
    setAutoPrompt('');
    setIsAutoGenerating(true);
    setGenerationStage('유저의 의도를 파악하고 있어요');

    const stageSteps = [
      '유저의 의도를 파악하고 있어요',
      '요청을 구조로 풀고 있어요',
      '결과를 검증하고 있어요',
      '워크플로우를 정리하고 있어요',
      '최종 결과를 다듬고 있어요',
    ];
    let stageIndex = 0;
    const stageTimer = setInterval(() => {
      stageIndex = Math.min(stageIndex + 1, stageSteps.length - 1);
      setGenerationStage(stageSteps[stageIndex]);
    }, 2500);

    try {
      if (selectedFiles.length > 0) {
        setIsUploading(true);
        const formData = new FormData();
        formData.append('project_id', draftIdRef.current);
        selectedFiles.forEach(f => formData.append('files', f));
        
        const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};
        await axios.post('/api/chat/upload_context', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
            ...authHeaders
          }
        });
        setSelectedFiles([]);
        setIsUploading(false);
      }
      const payload = {
        project_id: draftIdRef.current,
        message: userMessage,
        graph_data: { nodes: [], edges: [] },
        complexity_level: complexityLevel,
        training_consent: localStorage.getItem('llmTrainingConsent') === 'true',
      };
      const authHeaders = token ? { headers: { Authorization: `Bearer ${token}` } } : {};
      const res = await axios.post('/api/chat', payload, authHeaders);
      const { reply, graph_data, clarification, type, app_id, app_title, app_data, workflow_id, trace_id, generation_outcome } = res.data;

      if (graph_data?.nodes?.length > 0) {
        completeOnboardingStep('workflow_created');
      }

      if (reply) {
        setMessages(prev => [...prev, { 
          role: 'ai', 
          content: reply, 
          graph_data, 
          clarification, 
          prompt: userMessage,
          trace_id, 
          generation_outcome,
          type: type || (app_id ? 'app' : 'workflow'),
          app_id,
          app_title,
          app_data,
          workflow_id
        }]);
      }
    } catch (error) {
      console.error(error);
      setMessages(prev => [
        ...prev,
        { role: 'ai', content: '오류가 발생했습니다: ' + (error.response?.data?.detail || error.message) }
      ]);
    } finally {
      clearInterval(stageTimer);
      setGenerationStage('완료');
      setIsAutoGenerating(false);
    }
  };

  const handleSelectSession = (session) => {
    // Load messages into MainPage regardless of whether it's an existing project or draft
    draftIdRef.current = session.project_id;
    setActiveSessionId(session.id);
    skipSmoothScrollRef.current = true;
    setMessages(session.messages || []);
  };

  const handleDeletedSession = (sessionId) => {
    if (String(activeSessionId) !== String(sessionId)) return;
    setMessages([]);
    setActiveSessionId(null);
    draftIdRef.current = `draft-${Date.now()}`;
  };

  const startNewChat = () => {
    setMessages([]);
    setActiveSessionId(null);
    setAutoPrompt('');
    setSelectedFiles([]);
    draftIdRef.current = `draft-${Date.now()}`;
    window.setTimeout(() => promptInputRef.current?.focus(), 0);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAutoGenerate();
    }
  };

  const renderInputBox = () => (
    <div className={`auto-gen-container-minimal${messages.length === 0 ? ' hero' : ' conversation'}`}>
      {/* 생성 단계는 대화 안에서 보여준다(AiThinking). 예전에는 입력창 위에도 같은 문구를
          띄워 한 화면에 두 번 나왔다 — 기다리는 사람이 볼 자리는 대화 쪽이다. */}
      {selectedFiles.length > 0 && (
        <div className="home-attached-files">
          {selectedFiles.map((file, index) => (
            <div key={`${file.name}-${index}`} className="home-file-chip">
              <FileText size={12} />
              <span title={file.name}>{file.name}</span>
              <button type="button" onClick={() => setSelectedFiles(selectedFiles.filter((_, fileIndex) => fileIndex !== index))} aria-label={`${file.name} 첨부 취소`}><X size={12} /></button>
            </div>
          ))}
        </div>
      )}
      <div className="auto-gen-input-wrapper-minimal">
        <textarea
          ref={promptInputRef}
          className="auto-gen-input-minimal"
          data-onboarding="workflow-prompt"
          value={autoPrompt}
          onChange={(e) => setAutoPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="만들고 싶은 업무나 앱을 자연스럽게 설명해보세요."
          rows={1}
          onInput={(event) => {
            event.target.style.height = 'auto';
            event.target.style.height = `${event.target.scrollHeight}px`;
          }}
        />
      </div>

      <div className="home-composer-toolbar">
        <input 
          type="file" multiple ref={fileInputRef} className="home-file-input"
          accept=".pdf,.doc,.docx,.txt"
          onChange={(event) => setSelectedFiles((current) => [...current, ...Array.from(event.target.files)])}
        />
        <button type="button" className="home-composer-tool" onClick={() => fileInputRef.current?.click()} title="문서 첨부">
          <Paperclip size={15} /><span>문서 첨부</span>
        </button>

        <div className="home-composer-actions">
          <div className="home-complexity" ref={dropdownRef}>
            <button
              type="button"
              className="home-complexity-trigger"
              data-tutorial="complexity-btn"
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              aria-expanded={isDropdownOpen}
            >
              <SlidersHorizontal size={13} />
              {complexityLevel === 'low' ? '빠름' : complexityLevel === 'medium' ? '기본' : '정밀'}
              <ChevronDown size={14} />
            </button>

            {isDropdownOpen && (
              <div className="home-complexity-menu">
                {[
                  { id: 'low', title: '빠름', desc: '핵심 구조를 빠르게 생성합니다.' },
                  { id: 'medium', title: '기본', desc: '상세도와 속도의 균형을 맞춥니다.' },
                  { id: 'high', title: '정밀', desc: '복잡한 요구사항을 더 깊게 검토합니다.' },
                ].map((option) => (
                  <button key={option.id} type="button" className={complexityLevel === option.id ? 'active' : ''}
                          onClick={() => { setComplexityLevel(option.id); setIsDropdownOpen(false); }}>
                    <span className="home-complexity-check">{complexityLevel === option.id && <Check size={13} />}</span>
                    <span><strong>{option.title}</strong><small>{option.desc}</small></span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            className="btn-generate-minimal"
            onClick={() => handleAutoGenerate()}
            disabled={isAutoGenerating || (!autoPrompt.trim() && selectedFiles.length === 0)}
            aria-label="요청 보내기"
          >
            <ArrowUp size={17} />
          </button>
        </div>
      </div>
    </div>
  );

  const openLatestWorkflow = () => {
    const latestWorkflow = [...messages].reverse().find((message) => message.graph_data?.nodes?.length > 0);
    if (!latestWorkflow) {
      navigate('/workflows');
      return;
    }
    navigate('/editor', {
      state: {
        initialGraph: latestWorkflow.graph_data,
        prompt: latestWorkflow.prompt || '',
        draftId: draftIdRef.current,
        traceId: latestWorkflow.generation_outcome === 'graph' ? latestWorkflow.trace_id : null,
      },
    });
  };

  const handleOnboardingAction = (stepId) => {
    if (stepId === 'workflow_created') {
      const promptInput = document.querySelector('[data-onboarding="workflow-prompt"]');
      if (!promptInput) return;
      promptInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
      promptInput.focus();
      const inputContainer = promptInput.closest('.auto-gen-container-minimal');
      inputContainer?.classList.add('onboarding-target-pulse');
      window.setTimeout(() => inputContainer?.classList.remove('onboarding-target-pulse'), 1600);
      return;
    }
    openLatestWorkflow();
  };

  return (
    <div className="main-page-layout home-workspace">
      <MainSidebar
        onSelectSession={handleSelectSession}
        currentChatSessionId={activeSessionId}
        onChatSessionDeleted={handleDeletedSession}
      />
      <OnboardingChecklist onAction={handleOnboardingAction} />

      <main className="main-page-content home-chat-page">

        {messages.length === 0 ? (
          <>
            <section className="home-chat-empty">
              <div className="home-chat-empty-inner">
                <header className="home-chat-hero">
                  <div className="home-hero-eyebrow" aria-hidden="true"><span>WORKSPACE</span><i></i><em>01</em></div>
                  <h1 className="main-hero-title">업무를 어떻게 바꿔볼까요?</h1>
                  <p>반복되는 업무나 필요한 도구를 적어보세요. 흐름을 정리하고 실제로 사용할 수 있는 형태까지 완성합니다.</p>
                </header>
                {renderInputBox()}
              </div>
            </section>
            {/* 아이디어 목록은 화면 맨 아래에 둔다 — 입력창이 화면 가운데를 차지하고,
                아이디어는 눈이 마지막에 닿는 자리에서 거들기만 한다. */}
            <div
              className={`home-suggestions${isIdeaHovered || isIdeaFocused ? ' is-paused' : ''}`}
              onMouseEnter={() => setIsIdeaHovered(true)}
              onMouseLeave={() => setIsIdeaHovered(false)}
              onFocus={() => setIsIdeaFocused(true)}
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) setIsIdeaFocused(false);
              }}
            >
              <div className="home-suggestions-head">
                <span>지금 인기 있는 아이디어</span>
                <small>{String(activeIdeaIndex + 1).padStart(2, '0')} / {String(ideas.length).padStart(2, '0')}</small>
              </div>
              <div className="home-idea-viewport">
                {(() => {
                  const idea = ideas[activeIdeaIndex] || ideas[0];
                  if (!idea) return null;
                  const IdeaIcon = idea.icon;
                  return (
                    <button
                      key={idea.key}
                      type="button"
                      className="home-idea-card"
                      onClick={() => {
                        setAutoPrompt(idea.prompt);
                        window.setTimeout(() => promptInputRef.current?.focus(), 0);
                      }}
                    >
                      <span className="home-idea-index">{String(activeIdeaIndex + 1).padStart(2, '0')}</span>
                      <span className="home-idea-icon"><IdeaIcon size={17} /></span>
                      <span className="home-idea-copy">
                        <small>
                          {idea.label}
                          {/* 실제 사용 기록이 있는 것만 숫자를 붙인다. 나머지는 추천이라고 밝힌다. */}
                          {idea.installs > 0
                            ? <em className="home-idea-badge is-popular">{idea.installs}명이 사용</em>
                            : <em className="home-idea-badge">추천</em>}
                        </small>
                        <strong>{idea.prompt}</strong>
                      </span>
                      <span className="home-idea-use">이 아이디어 사용 <ArrowRight size={14} /></span>
                    </button>
                  );
                })()}
              </div>
              <div className="home-idea-navigation">
                <div className="home-idea-progress" aria-label="아이디어 선택">
                  {ideas.map((idea, index) => (
                    <button
                      key={idea.key}
                      type="button"
                      className={index === activeIdeaIndex ? 'active' : ''}
                      onClick={() => setActiveIdeaIndex(index)}
                      aria-label={`${index + 1}번째 아이디어 보기`}
                      aria-current={index === activeIdeaIndex ? 'true' : undefined}
                    />
                  ))}
                </div>
                <div className="home-idea-controls">
                  <button type="button" onClick={() => setActiveIdeaIndex((current) => (current - 1 + ideas.length) % ideas.length)} aria-label="이전 아이디어"><ChevronLeft size={15} /></button>
                  <button type="button" onClick={() => setActiveIdeaIndex((current) => (current + 1) % ideas.length)} aria-label="다음 아이디어"><ChevronRight size={15} /></button>
                </div>
              </div>
            </div>
          </>
        ) : (
          <>
            <header className="home-conversation-head">
              <div><span className="home-conversation-mark" aria-hidden="true">W</span><div><strong>작업 공간</strong><small>{activeSessionId ? '저장된 작업을 이어가는 중' : '새 자동화를 구성하는 중'}</small></div></div>
              <button type="button" onClick={startNewChat}><Plus size={14} /> 새 작업</button>
            </header>
            <div className="home-conversation-scroll">
              <div className="home-conversation-inner">
                <div className="chat-history">
                  {messages.map((msg, idx) => (
                    <div key={idx} className={`chat-message ${msg.role}`}>
                      <div className={`chat-avatar ${msg.role === 'ai' ? 'ai-avatar' : ''}`}>
                        {msg.role === 'ai' && <span aria-hidden="true">W</span>}
                      </div>
                      <div className="chat-bubble">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                        {msg.app_id ? (
                          <div className="generated-result-actions">
                            <button className="app" onClick={() => navigate(`/app-builder/${msg.app_id}`, { state: { initialAppData: msg.app_data } })}>
                              앱 빌더에서 편집 <ArrowRight size={14} />
                            </button>
                            <button className="run" onClick={() => window.open(`/custom-app/${msg.app_id}`, '_blank')}>
                              앱 실행 <ArrowRight size={14} />
                            </button>
                            {msg.workflow_id && (
                              <button className="secondary" onClick={() => navigate(`/editor/${msg.workflow_id}`)}>
                                연동 워크플로우 보기
                              </button>
                            )}
                          </div>
                        ) : msg.graph_data?.nodes?.length > 0 ? (
                          <div className="generated-result-actions">
                            <button className="workflow"
                              onClick={() => navigate('/editor', { state: {
                                initialGraph: msg.graph_data,
                                prompt: msg.prompt || '',
                                draftId: draftIdRef.current,
                                traceId: msg.generation_outcome === 'graph' ? msg.trace_id : null,
                              } })}
                            >
                              에디터에서 워크플로우 열기 <ArrowRight size={14} />
                            </button>
                          </div>
                        ) : null}
                        {msg.clarification?.options?.length > 0 && idx === messages.length - 1 && (
                          <div className="clarify-chips">
                            {msg.clarification.options.map((opt, optIdx) => (
                              <button
                                key={`clarify-${idx}-${optIdx}`}
                                className="clarify-chip"
                                disabled={isAutoGenerating}
                                onClick={() => handleAutoGenerate(opt)}
                              >
                                {opt}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {/* 무엇을 하는 중인지 대화 안에서 보여준다. 예전에는 점 세 개만 뛰고
                      단계 문구는 딴 곳에 있어서, 기다리는 사람이 볼 자리에 정보가 없었다. */}
                  {isAutoGenerating && (
                    <div className="chat-message ai">
                      <AiThinking label={generationStage} size="lg" />
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </div>
            </div>

            <footer className="home-composer-dock">
              <div>
                {renderInputBox()}
                <p>생성된 워크플로우는 실행 전에 설정과 권한을 확인해주세요.</p>
              </div>
            </footer>
          </>
        )}
        <SiteFeedbackWidget />
      </main>
      <TutorialOverlay steps={MAIN_TUTORIAL_STEPS} storageKey="tutorial_main_seen_v1" />
    </div>
  );
}

export default MainPage;
