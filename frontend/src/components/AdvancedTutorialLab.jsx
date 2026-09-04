import { useRef, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  Braces,
  Cable,
  Check,
  ChevronRight,
  Clock,
  Container,
  Database,
  Eye,
  Globe,
  Key,
  Link2,
  MapPin,
  MessageCircle,
  Monitor,
  MousePointerClick,
  Play,
  RotateCcw,
  Save,
  Send,
  FileText,
  ShieldAlert,
  Smartphone,
  Sparkles,
  Square,
  TerminalSquare,
  TestTube,
  Webhook,
  Zap,
} from 'lucide-react';

const sleep = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function ChoiceLab({ scenario, finish, feedback }) {
  const configs = {
    'trigger-choice': [
      { id: 'daily', prompt: '매일 평일 오전 9시에 보고서를 생성합니다.', options: ['Schedule', 'Webhook'], answer: 'Schedule' },
      { id: 'payment', prompt: '결제 서비스가 승인 결과를 보내면 후속 처리를 시작합니다.', options: ['Schedule', 'Webhook'], answer: 'Webhook' },
      { id: 'weekly', prompt: '매주 월요일에 팀 요약을 전송합니다.', options: ['Schedule', 'Webhook'], answer: 'Schedule' },
    ],
    'api-errors': [
      { id: '200', prompt: '200 OK · 응답 Body가 정상적으로 도착했습니다.', options: ['다음 노드로 전달', 'API 키 교체', '대기 후 재시도'], answer: '다음 노드로 전달' },
      { id: '401', prompt: '401 Unauthorized · 인증이 거부되었습니다.', options: ['즉시 무한 재시도', 'API 키 교체', '성공으로 처리'], answer: 'API 키 교체' },
      { id: '429', prompt: '429 Too Many Requests · 요청 한도를 초과했습니다.', options: ['대기 후 재시도', 'API 키 공개', '응답 무시'], answer: '대기 후 재시도' },
    ],
    'kr-naver': [
      { id: 'monitor', prompt: '우리 브랜드가 언급된 새 글이 올라오면 자동으로 Workflow를 시작하고 싶습니다.', options: ['네이버 새 글 감지', '네이버 검색', '네이버 카페'], answer: '네이버 새 글 감지' },
      { id: 'collect', prompt: 'Workflow 중간에 최신 블로그 후기를 수집해 요약에 활용합니다.', options: ['네이버 새 글 감지', '네이버 검색', '네이버 카페'], answer: '네이버 검색' },
      { id: 'publish', prompt: '완성된 주간 소식지를 운영 중인 커뮤니티에 게시합니다.', options: ['네이버 새 글 감지', '네이버 검색', '네이버 카페'], answer: '네이버 카페' },
    ],
  };
  const questions = configs[scenario] || [];
  const [answers, setAnswers] = useState({});

  const choose = (question, answer) => {
    const next = { ...answers, [question.id]: answer };
    setAnswers(next);
    if (answer !== question.answer) {
      feedback('조금 다릅니다. 실행 시점과 오류 원인을 다시 확인하세요.', 'warning');
      return;
    }
    feedback('좋습니다. 이 상황에 맞는 선택입니다.', 'success');
    if (questions.every((item) => next[item.id] === item.answer)) {
      finish('모든 상황에 알맞은 처리 방식을 선택했습니다.');
    }
  };

  return (
    <div className="advanced-choice-list">
      {questions.map((question, index) => (
        <section key={question.id} className={answers[question.id] === question.answer ? 'is-correct' : ''}>
          <span>{index + 1}</span>
          <div><strong>{question.prompt}</strong><div>{question.options.map((option) => <button key={option} type="button" className={answers[question.id] === option ? 'active' : ''} onClick={() => choose(question, option)}>{option}</button>)}</div></div>
          {answers[question.id] === question.answer && <Check size={18} />}
        </section>
      ))}
    </div>
  );
}

function ScheduleLab({ finish, feedback }) {
  const [cron, setCron] = useState('');
  const [timezone, setTimezone] = useState('');
  const [saved, setSaved] = useState(false);
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState([]);

  const save = () => {
    if (cron !== '0 9 * * 1-5' || timezone !== 'Asia/Seoul') {
      feedback('평일 오전 9시와 Asia/Seoul 시간대를 선택하세요.', 'warning');
      return;
    }
    setSaved(true);
    setLogs(['Schedule 저장 · 0 9 * * 1-5 · Asia/Seoul']);
    feedback('스케줄을 저장했습니다. 이제 다음 실행을 테스트하세요.', 'success');
  };

  const test = async () => {
    if (!saved || running) return;
    setRunning(true);
    setLogs((current) => [...current, '09:00:00 Trigger 실행 중']);
    await sleep(650);
    setLogs((current) => [...current, '09:00:01 Workflow 완료 · 다음 실행 월요일 09:00']);
    setRunning(false);
    finish('평일 오전 스케줄을 저장하고 Mock 실행 로그를 확인했습니다.');
  };

  return (
    <div className="advanced-split-layout">
      <section className="advanced-control-panel">
        <div className="advanced-panel-title"><Clock size={17} /><div><strong>Schedule 노드</strong><span>실행 시점을 설정합니다</span></div></div>
        <label>실행 주기<select value={cron} onChange={(event) => { setCron(event.target.value); setSaved(false); }}><option value="">주기 선택</option><option value="0 9 * * 1-5">평일 오전 9시</option><option value="0 18 * * *">매일 오후 6시</option></select></label>
        <label>시간대<select value={timezone} onChange={(event) => { setTimezone(event.target.value); setSaved(false); }}><option value="">시간대 선택</option><option value="Asia/Seoul">Asia/Seoul</option><option value="UTC">UTC</option></select></label>
        <div className="advanced-form-actions"><button type="button" onClick={save}><Save size={15} /> 저장</button><button type="button" className="primary" onClick={test} disabled={!saved || running}><Play size={15} /> {running ? '실행 중' : '다음 실행 테스트'}</button></div>
      </section>
      <LogPanel logs={logs} empty="스케줄을 저장하면 실행 로그가 표시됩니다." />
    </div>
  );
}

function WebhookLab({ finish, feedback }) {
  const [method, setMethod] = useState('GET');
  const [payload, setPayload] = useState('{\n  "event": "order.created",\n  "orderId": 1024\n}');
  const [response, setResponse] = useState(null);

  const send = async () => {
    if (method !== 'POST') {
      feedback('Payload를 전달하려면 POST 요청을 선택하세요.', 'warning');
      return;
    }
    try {
      const parsed = JSON.parse(payload);
      if (!parsed.event) throw new Error('event missing');
      setResponse({ pending: true });
      await sleep(550);
      setResponse({ status: 200, body: { received: true, workflowRunId: 'run_tutorial_01' } });
      finish('유효한 Webhook Payload를 보내고 200 응답을 확인했습니다.');
    } catch {
      setResponse({ status: 400, body: { error: 'Invalid JSON payload' } });
      feedback('JSON 형식과 event 필드를 확인하세요.', 'warning');
    }
  };

  return (
    <div className="advanced-request-lab">
      <div className="advanced-endpoint-bar"><Webhook size={17} /><select value={method} onChange={(event) => setMethod(event.target.value)}><option>GET</option><option>POST</option></select><code>https://workflow.local/hooks/tutorial-order</code></div>
      <div className="advanced-request-columns">
        <label><span>JSON Payload</span><textarea value={payload} onChange={(event) => setPayload(event.target.value)} spellCheck="false" /></label>
        <div className="advanced-response-view"><span>Mock Response</span>{response?.pending ? <p>요청 처리 중...</p> : response ? <><strong className={response.status === 200 ? 'success' : 'error'}>{response.status}</strong><pre>{JSON.stringify(response.body, null, 2)}</pre></> : <p>요청을 보내면 응답과 수신 로그가 표시됩니다.</p>}</div>
      </div>
      <button type="button" className="advanced-primary-action" onClick={send}><Send size={16} /> Mock 요청 보내기</button>
    </div>
  );
}

function ApiRequestLab({ finish, feedback }) {
  const [method, setMethod] = useState('GET');
  const [url, setUrl] = useState('/v1');
  const [contentType, setContentType] = useState('');
  const [body, setBody] = useState('{\n  "title": "배송 상태 문의"\n}');
  const [response, setResponse] = useState(null);

  const send = async () => {
    let parsed;
    try { parsed = JSON.parse(body); } catch { feedback('Body를 유효한 JSON으로 작성하세요.', 'warning'); return; }
    if (method !== 'POST' || url !== '/v1/tickets' || contentType !== 'application/json' || !parsed.title) {
      feedback('POST, /v1/tickets, application/json과 title Body를 모두 맞춰보세요.', 'warning');
      return;
    }
    setResponse({ pending: true });
    await sleep(500);
    setResponse({ status: 201, id: 'ticket_2048', title: parsed.title });
    finish('HTTP 요청의 네 요소를 구성하고 201 Created 응답을 받았습니다.');
  };

  return (
    <div className="advanced-request-builder">
      <div className="advanced-request-row"><select value={method} onChange={(event) => setMethod(event.target.value)}><option>GET</option><option>POST</option><option>PUT</option></select><input value={url} onChange={(event) => setUrl(event.target.value)} aria-label="요청 URL" /><button type="button" onClick={send}><Send size={15} /> 전송</button></div>
      <div className="advanced-request-grid">
        <section><span>Headers</span><label>Content-Type<select value={contentType} onChange={(event) => setContentType(event.target.value)}><option value="">선택</option><option value="application/json">application/json</option><option value="text/plain">text/plain</option></select></label><span>Body</span><textarea value={body} onChange={(event) => setBody(event.target.value)} spellCheck="false" /></section>
        <section className="advanced-api-preview"><span>Response</span>{response?.pending ? <p>Mock API 호출 중...</p> : response ? <><strong>201 Created</strong><pre>{JSON.stringify(response, null, 2)}</pre></> : <p>요청을 완성해 응답을 확인하세요.</p>}</section>
      </div>
    </div>
  );
}

function CredentialLab({ mode, finish, feedback }) {
  const isBot = mode === 'bot';
  const [provider, setProvider] = useState('');
  const [secret, setSecret] = useState('');
  const [saved, setSaved] = useState(false);
  const [linked, setLinked] = useState(false);

  const save = () => {
    if (!provider || !secret.startsWith('tutorial_') || secret.length < 14) {
      feedback('Provider를 선택하고 tutorial_로 시작하는 연습용 키를 입력하세요.', 'warning');
      return;
    }
    setSaved(true);
    feedback('연습용 키를 암호화 저장했다고 가정합니다. 실제 서버에는 전송되지 않습니다.', 'success');
  };
  const link = () => {
    if (!saved) return;
    setLinked(true);
    finish(isBot ? '봇 플랫폼과 API Center Token 연결을 완료했습니다.' : 'API Center 키를 HTTP 노드에 안전하게 연결했습니다.');
  };

  return (
    <div className="advanced-credential-layout">
      <section className="advanced-provider-panel">
        <div className="advanced-panel-title">{isBot ? <Bot size={18} /> : <Key size={18} />}<div><strong>{isBot ? '봇 연결 준비' : 'API Center'}</strong><span>민감 정보는 연습 환경에만 저장됩니다</span></div></div>
        <label>Provider<select value={provider} onChange={(event) => { setProvider(event.target.value); setSaved(false); setLinked(false); }}><option value="">Provider 선택</option>{isBot ? <><option value="discord">Discord Bot</option><option value="telegram">Telegram Bot</option></> : <><option value="openai">OpenAI</option><option value="custom">Custom API</option></>}</select></label>
        <label>{isBot ? 'Bot Token' : 'API Key'}<input type="password" value={secret} onChange={(event) => { setSecret(event.target.value); setSaved(false); setLinked(false); }} placeholder="tutorial_key_1234" /></label>
        <button type="button" onClick={save}><Save size={15} /> API Center에 연습용 키 저장</button>
        {saved && <div className="advanced-masked-key"><Check size={15} /><span>{provider}</span><code>tutorial_••••1234</code></div>}
      </section>
      <section className="advanced-link-panel">
        <div className="advanced-mini-node"><span>{isBot ? 'Bot Trigger Node' : 'HTTP Request Node'}</span><small>Credential source</small><strong>{linked ? `API_CENTER:${provider}` : '연결되지 않음'}</strong></div>
        <button type="button" className="advanced-primary-action" onClick={link} disabled={!saved}><Link2 size={16} /> 노드에 연결</button>
      </section>
    </div>
  );
}

function PipelineLab({ finish, feedback }) {
  const required = ['메시지 수신', 'LLM 답변 생성', '메시지 전송'];
  const [sequence, setSequence] = useState([]);
  const [active, setActive] = useState(-1);

  const add = (item) => {
    const expected = required[sequence.length];
    if (item !== expected) {
      setSequence([]);
      feedback('수신 → 처리 → 전송 순서로 다시 구성하세요.', 'warning');
      return;
    }
    setSequence((current) => [...current, item]);
  };
  const run = async () => {
    if (sequence.length !== required.length) return;
    for (let index = 0; index < required.length; index += 1) {
      setActive(index);
      await sleep(480);
    }
    setActive(-1);
    finish('테스트 메시지가 Trigger, LLM, 발신 노드를 순서대로 통과했습니다.');
  };

  return (
    <div className="advanced-pipeline-lab">
      <div className="advanced-palette-row">{required.map((item) => <button key={item} type="button" onClick={() => add(item)} disabled={sequence.includes(item)}>{item}</button>)}</div>
      <div className="advanced-pipeline">{required.map((item, index) => <div key={item} className={`${sequence[index] === item ? 'placed' : ''} ${active === index ? 'running' : ''}`}><span>{index + 1}</span><strong>{sequence[index] || '빈 단계'}</strong>{index < required.length - 1 && <ChevronRight size={18} />}</div>)}</div>
      <button type="button" className="advanced-primary-action" onClick={run} disabled={sequence.length !== required.length}><Play size={16} /> 테스트 메시지 실행</button>
    </div>
  );
}

function BotOperationsLab({ finish, feedback }) {
  const [status, setStatus] = useState('stopped');
  const [logs, setLogs] = useState([]);
  const [selectedCause, setSelectedCause] = useState('');

  const start = async () => {
    setStatus('running');
    setLogs(['Bot process started', 'Discord gateway connected']);
    await sleep(450);
    setLogs((current) => [...current, '401 Unauthorized · Invalid or expired Bot Token']);
    feedback('오류 로그가 발생했습니다. 원인을 선택하세요.', 'warning');
  };
  const diagnose = (cause) => {
    setSelectedCause(cause);
    if (cause === 'token') finish('401 로그에서 만료되거나 잘못된 Bot Token 문제를 찾았습니다.');
    else feedback('네트워크 연결은 성공했습니다. 401 인증 오류에 집중하세요.', 'warning');
  };

  return (
    <div className="advanced-manager-layout">
      <section className="advanced-manager-card"><div><span className={`advanced-status-dot ${status}`} /><div><strong>고객 지원 Discord Bot</strong><small>{status === 'running' ? '실행 중' : '중지됨'}</small></div></div><div className="advanced-manager-actions"><button type="button" onClick={start} disabled={status === 'running'}><Play size={15} /> 시작</button><button type="button" onClick={() => setStatus('stopped')} disabled={status === 'stopped'}><Square size={14} /> 중지</button></div></section>
      <LogPanel logs={logs} empty="봇을 시작하면 상태와 오류 로그를 확인할 수 있습니다." />
      {logs.length > 2 && <div className="advanced-diagnosis"><strong>가장 가능성이 높은 원인은?</strong><button type="button" className={selectedCause === 'network' ? 'active' : ''} onClick={() => diagnose('network')}>네트워크 단절</button><button type="button" className={selectedCause === 'token' ? 'active' : ''} onClick={() => diagnose('token')}>Bot Token 만료</button></div>}
    </div>
  );
}

function EvaluationLab({ finish }) {
  const sections = ['구조', '안정성', '의도 충족'];
  const [evaluated, setEvaluated] = useState(false);
  const [visited, setVisited] = useState([]);
  const reports = {
    '구조': ['시작 노드 존재', '출력 노드 존재', '연결되지 않은 노드 없음'],
    '안정성': ['오류 처리 경로 보완 필요', 'API 키 참조 방식 정상'],
    '의도 충족': ['요청 분류와 알림 단계 확인', '실패 알림 누락'],
  };
  const view = (section) => {
    const next = visited.includes(section) ? visited : [...visited, section];
    setVisited(next);
    if (next.length === sections.length) finish('평가 리포트의 구조, 안정성, 의도 충족 항목을 모두 확인했습니다.');
  };

  return (
    <div className="advanced-evaluation-lab">
      {!evaluated ? <button type="button" className="advanced-evaluate-button" onClick={() => setEvaluated(true)}><TestTube size={20} /> Workflow 평가 실행<span>외부 API를 호출하지 않는 Mock 평가입니다</span></button> : <><div className="advanced-score-row"><div><span>종합 점수</span><strong>82</strong><small>/ 100</small></div><p>배포 가능 · 안정성 개선 권장</p></div><div className="advanced-report-tabs">{sections.map((section) => <button key={section} type="button" className={visited.includes(section) ? 'visited' : ''} onClick={() => view(section)}>{section}{visited.includes(section) && <Check size={13} />}</button>)}</div><div className="advanced-report-grid">{sections.filter((section) => visited.includes(section)).map((section) => <section key={section}><strong>{section}</strong>{reports[section].map((line, index) => <span key={line} className={line.includes('필요') || line.includes('누락') ? 'warning' : ''}>{index === 0 ? <Check size={13} /> : <ChevronRight size={13} />}{line}</span>)}</section>)}</div></>}
    </div>
  );
}

function ImprovementLab({ finish, feedback }) {
  const [selected, setSelected] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const suggestions = [
    { id: 'error-path', title: '오류 알림 경로 추가', safe: true, diff: '+ HTTP 실패 → 관리자 알림 노드' },
    { id: 'expose-key', title: 'API 키를 프롬프트에 포함', safe: false, diff: '+ prompt: sk-live-...' },
  ];
  const apply = () => {
    const suggestion = suggestions.find((item) => item.id === selected);
    if (!suggestion?.safe) { feedback('민감 정보를 노출하는 변경은 적용하면 안 됩니다.', 'warning'); return; }
    if (!reviewed) { feedback('먼저 변경 Diff를 확인하세요.', 'warning'); return; }
    finish('안전한 개선 제안과 Diff를 검토한 뒤 적용했습니다.');
  };

  return (
    <div className="advanced-improvement-lab"><section className="advanced-suggestion-list"><span>개선 제안</span>{suggestions.map((item) => <button key={item.id} type="button" className={selected === item.id ? 'active' : ''} onClick={() => { setSelected(item.id); setReviewed(false); }}><Sparkles size={16} /><div><strong>{item.title}</strong><small>{item.safe ? '검토 후 적용 가능' : '보안 위험 포함'}</small></div></button>)}</section><section className="advanced-diff-panel"><span>변경 내용</span>{selected ? <><pre>{suggestions.find((item) => item.id === selected)?.diff}</pre><label><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /> 변경 내용을 확인했습니다</label><button type="button" onClick={apply}>선택한 개선 적용</button></> : <p>왼쪽에서 제안을 선택하세요.</p>}</section></div>
  );
}

function ReadinessLab({ finish }) {
  const checks = ['API 키가 API Center에 연결됨', '오류 처리 경로가 존재함', '최근 실행 테스트가 성공함'];
  const [tracking, setTracking] = useState(false);
  const [estimated, setEstimated] = useState(false);
  const [checked, setChecked] = useState([]);
  const toggleCheck = (item) => {
    const next = checked.includes(item) ? checked.filter((value) => value !== item) : [...checked, item];
    setChecked(next);
    if (tracking && estimated && next.length === checks.length) finish('사용량과 운영 조건을 모두 확인해 배포 준비를 마쳤습니다.');
  };
  const estimate = () => { setEstimated(true); if (tracking && checked.length === checks.length) finish('사용량과 운영 조건을 모두 확인해 배포 준비를 마쳤습니다.'); };

  return (
    <div className="advanced-readiness-lab"><section><div className="advanced-switch-line"><span><TerminalSquare size={17} /> 노드별 사용량 표시</span><button type="button" className={tracking ? 'active' : ''} onClick={() => setTracking((value) => !value)}><i /></button></div><button type="button" onClick={estimate} disabled={!tracking}>예상 사용량 계산</button>{estimated && <div className="advanced-token-bars"><span>Prompt <i style={{ width: '38%' }} /></span><span>LLM <i style={{ width: '82%' }} /></span><span>Output <i style={{ width: '14%' }} /></span><strong>예상 2,840 tokens</strong></div>}</section><section><strong>배포 준비 체크</strong>{checks.map((item) => <label key={item}><input type="checkbox" checked={checked.includes(item)} onChange={() => toggleCheck(item)} />{item}</label>)}</section></div>
  );
}

function ComponentsLab({ finish, feedback }) {
  const [items, setItems] = useState([]);
  const [offset, setOffset] = useState(0);
  const add = (item) => setItems((current) => current.includes(item) ? current : [...current, item]);
  const move = () => {
    if (!['입력', '버튼'].every((item) => items.includes(item))) { feedback('Container 안에 입력과 버튼을 먼저 추가하세요.', 'warning'); return; }
    setOffset(34);
    finish('Container와 두 자식 컴포넌트가 같은 거리만큼 함께 이동했습니다.');
  };
  return (
    <div className="advanced-builder-lab"><aside><span>Components</span><button type="button" onClick={() => add('입력')}>입력</button><button type="button" onClick={() => add('버튼')}>버튼</button></aside><section className="advanced-builder-canvas"><div className="advanced-builder-container" style={{ transform: `translate(${offset}px, ${offset / 2}px)` }}><strong>Container</strong>{items.includes('입력') && <input readOnly placeholder="문의 내용을 입력하세요" />}{items.includes('버튼') && <button type="button">실행</button>}</div></section><aside className="advanced-hierarchy"><span>Hierarchy</span><strong>Container</strong>{items.map((item) => <small key={item}>↳ {item}</small>)}<button type="button" onClick={move}>Container 이동</button></aside></div>
  );
}

function MappingLab({ finish, feedback }) {
  const [workflow, setWorkflow] = useState('');
  const [input, setInput] = useState('');
  const [mapped, setMapped] = useState(false);
  const [result, setResult] = useState('');
  const map = () => {
    if (!workflow || !input) { feedback('Workflow와 입력 컴포넌트를 모두 선택하세요.', 'warning'); return; }
    setMapped(true);
    feedback('버튼 Action과 Workflow 입력을 연결했습니다.', 'success');
  };
  const preview = async () => { if (!mapped) return; setResult('실행 중...'); await sleep(500); setResult('문의가 배송 팀으로 분류되었습니다.'); finish('버튼 Action과 입력값 매핑을 Preview에서 검증했습니다.'); };
  return (
    <div className="advanced-mapping-lab"><section><div className="advanced-panel-title"><MousePointerClick size={18} /><div><strong>실행 버튼 Action</strong><span>클릭 이벤트 설정</span></div></div><label>Workflow<select value={workflow} onChange={(event) => { setWorkflow(event.target.value); setMapped(false); }}><option value="">선택</option><option value="support">고객 문의 분류</option></select></label><label>user_input 매핑<select value={input} onChange={(event) => { setInput(event.target.value); setMapped(false); }}><option value="">선택</option><option value="question">문의 입력.value</option></select></label><button type="button" onClick={map}><Link2 size={15} /> 연결</button></section><section className="advanced-app-preview"><span>Preview</span><input defaultValue="배송이 언제 도착하나요?" readOnly /><button type="button" onClick={preview} disabled={!mapped}>Workflow 실행</button><output>{result || '실행 결과가 여기에 표시됩니다.'}</output></section></div>
  );
}

function BuilderDeployLab({ finish, feedback }) {
  const [preset, setPreset] = useState('desktop');
  const [visited, setVisited] = useState(['desktop']);
  const [saved, setSaved] = useState(false);
  const selectPreset = (next) => { setPreset(next); setVisited((current) => current.includes(next) ? current : [...current, next]); };
  const deploy = () => {
    if (visited.length < 2) { feedback('데스크톱과 모바일 화면을 모두 확인하세요.', 'warning'); return; }
    if (!saved) { feedback('배포 전에 앱을 저장하세요.', 'warning'); return; }
    finish('두 화면 크기의 Preview를 확인하고 연습 앱을 배포했습니다.');
  };
  return (
    <div className="advanced-deploy-lab"><div className="advanced-device-toolbar"><button type="button" className={preset === 'desktop' ? 'active' : ''} onClick={() => selectPreset('desktop')}><Monitor size={16} /> Desktop</button><button type="button" className={preset === 'mobile' ? 'active' : ''} onClick={() => selectPreset('mobile')}><Smartphone size={16} /> Mobile</button><span>{preset === 'desktop' ? '1280 × 800' : '390 × 844'}</span></div><div className={`advanced-device-preview ${preset}`}><div><strong>문의 분류 앱</strong><input readOnly placeholder="문의 내용을 입력하세요" /><button type="button">Workflow 실행</button><small>결과가 여기에 표시됩니다</small></div></div><div className="advanced-form-actions"><button type="button" onClick={() => setSaved(true)}>{saved ? <Check size={15} /> : <Save size={15} />}{saved ? '저장됨' : '저장'}</button><button type="button" className="primary" onClick={deploy}><Eye size={15} /> 저장 및 배포</button></div></div>
  );
}

function QueryLab({ finish, feedback }) {
  const [query, setQuery] = useState('');
  const [logs, setLogs] = useState([]);
  const [blockedSeen, setBlockedSeen] = useState(false);
  const [selectDone, setSelectDone] = useState(false);
  const [running, setRunning] = useState(false);

  const QUERIES = {
    select: { label: '최근 주문 10건 조회 (SELECT)', safe: true },
    drop: { label: '주문 테이블 삭제 (DROP TABLE)', safe: false },
    update: { label: 'WHERE 없는 전체 수정 (UPDATE)', safe: false },
  };

  const run = async () => {
    if (!query || running) return;
    setRunning(true);
    const meta = QUERIES[query];
    if (!meta.safe) {
      setLogs((current) => [...current, `SQL Guard · ${meta.label} 차단됨 — 읽기 전용 모드에서는 변경 쿼리를 실행할 수 없습니다.`]);
      setBlockedSeen(true);
      setRunning(false);
      if (selectDone) finish('차단과 조회를 모두 확인했습니다. 변경 쿼리는 실행 전에 걸러집니다.');
      else feedback('변경 쿼리가 실행 전에 차단되었습니다. 이제 조회 쿼리를 실행해보세요.', 'warning');
      return;
    }
    setLogs((current) => [...current, 'SQL Guard · 조회 쿼리 확인 — 통과']);
    await sleep(500);
    setLogs((current) => [...current, 'SELECT 실행 · 10행 반환', 'rows[0] = { id: 1024, status: "배송중", amount: 42000 }', '결과가 다음 노드의 입력으로 전달됩니다.']);
    setSelectDone(true);
    setRunning(false);
    if (blockedSeen) finish('차단과 조회를 모두 확인했습니다. 변경 쿼리는 실행 전에 걸러집니다.');
    else feedback('조회에 성공했습니다. 위험한 쿼리도 한번 실행해 차단을 확인하세요.', 'success');
  };

  return (
    <div className="advanced-split-layout">
      <section className="advanced-control-panel">
        <div className="advanced-panel-title"><Database size={17} /><div><strong>데이터베이스 노드</strong><span>읽기 전용 연결 · Mock DB</span></div></div>
        <label>실행할 쿼리<select value={query} onChange={(event) => setQuery(event.target.value)}><option value="">쿼리 선택</option>{Object.entries(QUERIES).map(([id, item]) => <option key={id} value={id}>{item.label}</option>)}</select></label>
        <div className="advanced-form-actions">
          <button type="button" className="primary" onClick={run} disabled={!query || running}><Play size={15} /> {running ? '실행 중' : '쿼리 실행'}</button>
        </div>
        <div className="advanced-guard-status"><ShieldAlert size={14} /> SQL Guard: {blockedSeen ? '차단 확인됨' : '대기 중'} · 조회: {selectDone ? '성공' : '대기 중'}</div>
      </section>
      <LogPanel logs={logs} empty="쿼리를 실행하면 SQL Guard 검사와 결과가 표시됩니다." />
    </div>
  );
}

function CrawlerLab({ finish, feedback }) {
  const [target, setTarget] = useState('');
  const [logs, setLogs] = useState([]);
  const [quota, setQuota] = useState(50);
  const [blockedSeen, setBlockedSeen] = useState(false);
  const [successSeen, setSuccessSeen] = useState(false);
  const [running, setRunning] = useState(false);

  const TARGETS = {
    notice: { label: '공지 게시판 (수집 허용)', allowed: true },
    admin: { label: '/admin 관리 페이지 (robots 차단)', allowed: false },
    news: { label: '뉴스 목록 (수집 허용)', allowed: true },
  };

  const run = async () => {
    if (!target || running) return;
    setRunning(true);
    const meta = TARGETS[target];
    setLogs((current) => [...current, `robots.txt 확인 · ${meta.label}`]);
    await sleep(450);
    if (!meta.allowed) {
      setLogs((current) => [...current, 'Disallow 경로 — 수집을 중단합니다.']);
      setBlockedSeen(true);
      setRunning(false);
      if (successSeen) finish('차단과 수집을 모두 확인했습니다. 크롤러는 robots·간격·상한을 지킵니다.');
      else feedback('robots.txt가 거부한 경로는 수집하지 않습니다. 허용된 페이지를 수집해보세요.', 'warning');
      return;
    }
    setLogs((current) => [...current, '허용 경로 — 요청 간격 2초 대기']);
    await sleep(600);
    setQuota((current) => current - 1);
    setLogs((current) => [...current, '본문 추출 완료 · 제목/본문/작성일', `오늘 남은 수집량 ${quota - 1}건`]);
    setSuccessSeen(true);
    setRunning(false);
    if (blockedSeen) finish('차단과 수집을 모두 확인했습니다. 크롤러는 robots·간격·상한을 지킵니다.');
    else feedback('수집에 성공했습니다. 차단되는 페이지도 실행해 차이를 확인하세요.', 'success');
  };

  return (
    <div className="advanced-split-layout">
      <section className="advanced-control-panel">
        <div className="advanced-panel-title"><Globe size={17} /><div><strong>웹 크롤러 노드</strong><span>robots · 요청 간격 · 일일 상한</span></div></div>
        <label>수집할 페이지<select value={target} onChange={(event) => setTarget(event.target.value)}><option value="">페이지 선택</option>{Object.entries(TARGETS).map(([id, item]) => <option key={id} value={id}>{item.label}</option>)}</select></label>
        <div className="advanced-form-actions">
          <button type="button" className="primary" onClick={run} disabled={!target || running}><Play size={15} /> {running ? '수집 중' : '수집 실행'}</button>
        </div>
        <div className="advanced-guard-status"><ShieldAlert size={14} /> 오늘 남은 수집량 {quota}건 · 차단 {blockedSeen ? '확인' : '미확인'} · 수집 {successSeen ? '성공' : '대기'}</div>
      </section>
      <LogPanel logs={logs} empty="페이지를 선택해 수집을 실행하면 단계별 로그가 표시됩니다." />
    </div>
  );
}

function ShapingLab({ finish, feedback }) {
  const [parsed, setParsed] = useState(false);
  const [items, setItems] = useState([]);
  const [combined, setCombined] = useState('');
  const [running, setRunning] = useState(false);
  const RAW = '분석이 끝났습니다. 결과는 다음과 같습니다.\n```json\n{ "keywords": ["배송 지연", "환불 문의", "품질 칭찬"] }\n```';

  const parse = () => {
    setParsed(true);
    feedback('LLM 응답에서 keywords 필드를 추출했습니다. 이제 분배를 실행하세요.', 'success');
  };

  const distribute = async () => {
    if (!parsed || running) return;
    setRunning(true);
    const keywords = ['배송 지연', '환불 문의', '품질 칭찬'];
    setItems([]);
    setCombined('');
    for (let index = 0; index < keywords.length; index += 1) {
      setItems((current) => [...current, `${index + 1}/3 처리 중 · "${keywords[index]}" → 대응 문구 생성`]);
      await sleep(550);
    }
    setCombined('1. 배송 지연: 예상 도착일을 안내했습니다.\n2. 환불 문의: 환불 절차 링크를 전달했습니다.\n3. 품질 칭찬: 감사 인사를 남겼습니다.');
    setRunning(false);
    finish('항목별 처리 결과가 순서대로 이어 붙어 하나의 출력이 되었습니다.');
  };

  return (
    <div className="advanced-shaping-lab">
      <section>
        <span>LLM 응답 원문</span>
        <pre>{RAW}</pre>
        <button type="button" onClick={parse} disabled={parsed}><Braces size={15} /> {parsed ? '파싱 완료' : 'JSON 파싱'}</button>
        {parsed && <div className="advanced-parsed-fields"><code>keywords[0] = 배송 지연</code><code>keywords[1] = 환불 문의</code><code>keywords[2] = 품질 칭찬</code></div>}
      </section>
      <section>
        <span>분배기 · 항목별 처리</span>
        {items.length === 0 ? <p>파싱된 목록을 분배기로 보내면 항목마다 같은 처리 경로가 실행됩니다.</p> : items.map((line) => <p key={line} className="is-item">{line}</p>)}
        {combined && <pre className="advanced-combined-output">{combined}</pre>}
        <button type="button" className="advanced-primary-action" onClick={distribute} disabled={!parsed || running}><Play size={15} /> {running ? '분배 실행 중' : '분배 실행'}</button>
      </section>
    </div>
  );
}

function KakaoLab({ finish, feedback }) {
  const [template, setTemplate] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [logs, setLogs] = useState([]);
  const [rejectedSeen, setRejectedSeen] = useState(false);
  const [running, setRunning] = useState(false);

  const send = async () => {
    if (running) return;
    if (template === 'free') {
      setLogs((current) => [...current, '발송 반려 · 등록되지 않은 문구 — 알림톡은 사전 승인된 템플릿만 발송할 수 있습니다.']);
      setRejectedSeen(true);
      feedback('미등록 문구는 반려됩니다. 승인된 템플릿을 선택하세요.', 'warning');
      return;
    }
    if (template !== 'order') { feedback('템플릿을 먼저 선택하세요.', 'warning'); return; }
    if (!customerName.trim()) { feedback('#{고객명} 변수에 넣을 값을 입력하세요.', 'warning'); return; }
    setRunning(true);
    setLogs((current) => [...current, `템플릿 검증 통과 · 변수 치환: #{고객명} → ${customerName.trim()}`]);
    await sleep(550);
    setLogs((current) => [...current, `알림톡 발송 완료 · "${customerName.trim()}님, 주문하신 상품이 발송되었습니다."`]);
    setRunning(false);
    finish(rejectedSeen
      ? '반려와 정상 발송을 모두 확인했습니다. 알림톡은 승인 템플릿 + 변수 치환으로 발송됩니다.'
      : '승인된 템플릿에 변수를 채워 발송을 완료했습니다.');
  };

  return (
    <div className="advanced-split-layout">
      <section className="advanced-control-panel">
        <div className="advanced-panel-title"><MessageCircle size={17} /><div><strong>카카오 알림톡 노드</strong><span>사전 승인 템플릿 · 변수 치환</span></div></div>
        <label>템플릿<select value={template} onChange={(event) => setTemplate(event.target.value)}><option value="">템플릿 선택</option><option value="order">주문 발송 안내 (승인됨)</option><option value="free">자유 문구 (미등록)</option></select></label>
        {template === 'order' && <div className="advanced-template-preview">#&#123;고객명&#125;님, 주문하신 상품이 발송되었습니다.</div>}
        <label>#&#123;고객명&#125; 변수<input value={customerName} onChange={(event) => setCustomerName(event.target.value)} placeholder="예: 김워크" /></label>
        <div className="advanced-form-actions">
          <button type="button" className="primary" onClick={send} disabled={running}><Send size={15} /> {running ? '발송 중' : '알림톡 발송'}</button>
        </div>
      </section>
      <LogPanel logs={logs} empty="템플릿과 변수를 채워 발송하면 검증·발송 로그가 표시됩니다." />
    </div>
  );
}

function OpenDataLab({ finish, feedback }) {
  const [credential, setCredential] = useState('');
  const [address, setAddress] = useState('세종대로 110');
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const search = async () => {
    if (running) return;
    if (credential !== 'juso') {
      feedback('공공데이터 API는 인증키가 필요합니다. API Center에 저장된 키를 먼저 연결하세요.', 'warning');
      return;
    }
    if (!address.trim()) { feedback('검색할 주소를 입력하세요.', 'warning'); return; }
    setRunning(true);
    setResult({ pending: true });
    await sleep(600);
    setResult({
      road: '서울특별시 중구 세종대로 110',
      jibun: '서울특별시 중구 태평로1가 31',
      zip: '04524',
    });
    setRunning(false);
    finish('인증키를 연결하고 주소를 표준 형식으로 변환했습니다.');
  };

  return (
    <div className="advanced-split-layout">
      <section className="advanced-control-panel">
        <div className="advanced-panel-title"><MapPin size={17} /><div><strong>도로명주소 노드</strong><span>공공데이터 인증키 · 주소 표준화</span></div></div>
        <label>인증키 (API Center)<select value={credential} onChange={(event) => setCredential(event.target.value)}><option value="">연결 안 함</option><option value="juso">juso-search · tutorial_••••7a2f</option></select></label>
        <label>검색할 주소<input value={address} onChange={(event) => setAddress(event.target.value)} placeholder="예: 세종대로 110" /></label>
        <div className="advanced-form-actions">
          <button type="button" className="primary" onClick={search} disabled={running}><Play size={15} /> {running ? '검색 중' : '주소 검색'}</button>
        </div>
      </section>
      <section className="advanced-address-result">
        <span>표준화 결과</span>
        {result?.pending ? <p>주소 검색 중…</p> : result ? (
          <dl>
            <div><dt>도로명</dt><dd>{result.road}</dd></div>
            <div><dt>지번</dt><dd>{result.jibun}</dd></div>
            <div><dt>우편번호</dt><dd>{result.zip}</dd></div>
          </dl>
        ) : <p>인증키를 연결하고 주소를 검색하면 표준화된 결과가 표시됩니다.</p>}
      </section>
    </div>
  );
}

function FormatFillLab({ finish, feedback }) {
  // 프리셋의 빈칸을 채워 문서를 만드는 체험. 출처(정형 데이터 / LLM 해석)를 눈으로 구분하게 한다.
  const FIELDS = [
    { name: 'department', label: '소속', source: 'binding', value: '운영1팀' },
    { name: 'authorName', label: '작성자', source: 'binding', value: '김워크' },
    { name: 'incidentAt', label: '발생 일시', source: 'binding', value: '2026-08-30 14:20' },
    { name: 'summary', label: '사건 개요', source: 'llm' },
    { name: 'prevention', label: '재발 방지 대책', source: 'llm' },
  ];
  const [values, setValues] = useState(() => Object.fromEntries(
    FIELDS.filter((f) => f.source === 'binding').map((f) => [f.name, f.value])));
  const [output, setOutput] = useState('');
  const [generated, setGenerated] = useState(null);
  const [running, setRunning] = useState(false);

  const runLLM = async () => {
    setRunning(true);
    feedback('앞 LLM이 비정형 메모를 해석해 남은 빈칸만 채웁니다…', 'info');
    await sleep(700);
    setValues((current) => ({
      ...current,
      summary: '2026-08-30 14:20경 알람 미작동으로 30분 지각하였습니다.',
      prevention: '알람 이중 설정과 출근 30분 전 알림을 적용하겠습니다.',
    }));
    setRunning(false);
    feedback('빈칸이 모두 채워졌습니다. 출력 형식을 고르고 생성하세요.', 'success');
  };

  const missing = FIELDS.filter((f) => !values[f.name]).map((f) => f.label);

  const generate = async () => {
    if (missing.length) {
      feedback(`필수 빈칸이 비어 있습니다: ${missing.join(', ')} — 실행이 멈추고 빈 문서는 저장되지 않습니다.`, 'warning');
      return;
    }
    if (!output) { feedback('출력 형식을 선택하세요.', 'warning'); return; }
    setRunning(true);
    await sleep(650);
    setGenerated({ name: `시말서.${output}`, output });
    setRunning(false);
    finish(`빈칸 5개를 채워 ${output.toUpperCase()} 문서를 생성했습니다. 완성 파일은 뒤의 발송 노드가 자동 첨부합니다.`);
  };

  return (
    <div className="advanced-split-layout">
      <section className="advanced-control-panel">
        <div className="advanced-panel-title"><FileText size={17} /><div><strong>문서 포맷 노드</strong><span>시말서 · 빈칸 5개</span></div></div>
        <div className="advanced-format-fields">
          {FIELDS.map((field) => (
            <div key={field.name} className={values[field.name] ? 'is-filled' : ''}>
              <span>{field.label}</span>
              <em>{field.source === 'binding' ? '앞 노드 데이터' : 'LLM 해석'}</em>
              <strong>{values[field.name] || '비어 있음'}</strong>
            </div>
          ))}
        </div>
        <button type="button" onClick={runLLM} disabled={running || FIELDS.every((f) => values[f.name])}>
          <Sparkles size={15} /> 남은 빈칸 LLM으로 채우기
        </button>
        <label>출력 형식<select value={output} onChange={(event) => setOutput(event.target.value)}>
          <option value="">형식 선택</option>
          <option value="hwpx">한글 (.hwpx)</option>
          <option value="docx">워드 (.docx)</option>
          <option value="pdf">PDF</option>
          <option value="xlsx">엑셀 (.xlsx)</option>
        </select></label>
        <div className="advanced-form-actions">
          <button type="button" className="primary" onClick={generate} disabled={running}>
            <Play size={15} /> {running ? '생성 중' : '문서 생성'}
          </button>
        </div>
      </section>
      <section className="advanced-address-result">
        <span>생성 결과</span>
        {generated ? (
          <dl>
            <div><dt>파일</dt><dd>{generated.name}</dd></div>
            <div><dt>형식</dt><dd>{generated.output.toUpperCase()}</dd></div>
            <div><dt>첨부</dt><dd>뒤의 이메일·디스코드 노드가 자동 첨부</dd></div>
          </dl>
        ) : <p>빈칸을 채우고 출력 형식을 고르면 완성 파일이 표시됩니다.</p>}
      </section>
    </div>
  );
}

function BindingLab({ finish, feedback }) {
  // 값 연결(데이터 바인딩) 체험. "값을 옮기는 일에는 LLM 을 쓰지 않는다"를 토큰 수로 보여준다.
  const SOURCES = [
    { id: 'n1', label: '웹훅 수신', upstream: true,
      paths: [
        { path: '', preview: '요청 본문 전체(JSON)' },
        { path: 'customer.email', preview: 'buyer@example.com', email: true },
        { path: 'customer.name', preview: '김워크' },
        { path: 'orderId', preview: '1024' },
      ] },
    // 실행 경로상 뒤에 있는 노드 — 고르면 왜 안 되는지 알려준다.
    { id: 'n4', label: '결과 출력 (뒤 노드)', upstream: false, paths: [{ path: '', preview: '아직 실행되지 않음' }] },
  ];
  const FIELDS = [
    { name: 'toEmail', label: '받는 사람', needEmail: true },
    { name: 'subject', label: '제목', needEmail: false },
  ];

  const [bindings, setBindings] = useState({});
  const [open, setOpen] = useState(null);

  const bind = (field, source, candidate) => {
    if (!source.upstream) {
      feedback('실행 순서상 뒤에 있는 노드는 연결할 수 없습니다 — 실행 시점에 그 노드의 결과가 아직 없습니다.', 'warning');
      return;
    }
    const target = FIELDS.find((f) => f.name === field);
    if (target.needEmail && !candidate.email) {
      feedback(`'${candidate.path || '출력 전체'}' 는 이메일 주소가 아닙니다. 받는 사람에는 이메일 값의 경로를 고르세요.`, 'warning');
      return;
    }
    const next = { ...bindings, [field]: { source: source.label, ...candidate } };
    setBindings(next);
    setOpen(null);
    if (Object.keys(next).length === FIELDS.length) {
      finish('두 필드를 모두 앞 노드의 값에 연결했습니다. 값을 옮기는 LLM 노드가 필요 없어져 실행마다 토큰이 들지 않습니다.');
    } else {
      feedback(`${target.label}에 ${source.label}의 ${candidate.path || '출력 전체'} 를 연결했습니다.`, 'success');
    }
  };

  const boundCount = Object.keys(bindings).length;
  const needsLLM = boundCount < FIELDS.length;

  return (
    <div className="advanced-split-layout">
      <section className="advanced-control-panel">
        <div className="advanced-panel-title">
          <Cable size={17} /><div><strong>이메일 발송 노드</strong><span>필드 옆 ⚡ 로 앞 노드 값에 연결</span></div>
        </div>
        <div className="tutorial-binding-fields">
          {FIELDS.map((field) => (
            <div key={field.name} className={bindings[field.name] ? 'is-bound' : ''}>
              <div className="tutorial-binding-head">
                <span>{field.label}</span>
                <button type="button" onClick={() => setOpen(open === field.name ? null : field.name)}>
                  <Zap size={13} /> {bindings[field.name] ? '바꾸기' : '값 연결'}
                </button>
              </div>
              {bindings[field.name] ? (
                <strong className="tutorial-binding-chip">
                  {bindings[field.name].source}
                  {bindings[field.name].path && <code>{bindings[field.name].path}</code>}
                </strong>
              ) : <em>직접 입력하거나 앞 노드 값에 연결</em>}
              {open === field.name && (
                <div className="tutorial-binding-picker">
                  {SOURCES.map((source) => (
                    <div key={source.id}>
                      <span>{source.label}</span>
                      {source.paths.map((candidate) => (
                        <button type="button" key={`${source.id}-${candidate.path}`}
                                onClick={() => bind(field.name, source, candidate)}>
                          <code>{candidate.path || '출력 전체'}</code><small>{candidate.preview}</small>
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
      <section className="advanced-address-result">
        <span>실행 비용</span>
        <dl>
          <div><dt>연결한 필드</dt><dd>{boundCount} / {FIELDS.length}</dd></div>
          <div><dt>값 옮기기용 LLM</dt><dd>{needsLLM ? '1회 필요' : '필요 없음'}</dd></div>
          <div><dt>실행마다 드는 토큰</dt><dd>{needsLLM ? '약 460' : '0'}</dd></div>
        </dl>
        <p>
          {needsLLM
            ? '연결하지 않은 필드는 앞에서 LLM 이 값을 만들어 넘겨야 합니다 — 매 실행 토큰이 들고, 값이 바뀌어 나올 수 있습니다.'
            : '흐름이 웹훅 → 이메일 발송 두 노드로 끝납니다. 값은 실행할 때 그대로 꺼내 쓰므로 결과가 늘 같습니다.'}
        </p>
      </section>
    </div>
  );
}

function LogPanel({ logs, empty }) {
  return <section className="advanced-log-panel"><div><TerminalSquare size={16} /> 실행 로그</div>{logs.length ? logs.map((log, index) => <p key={`${log}-${index}`}><span>{String(index + 1).padStart(2, '0')}</span>{log}</p>) : <small>{empty}</small>}</section>;
}

const SCENARIOS = {
  'trigger-choice': (props) => <ChoiceLab {...props} scenario="trigger-choice" />,
  'schedule-setup': (props) => <ScheduleLab {...props} />,
  'webhook-setup': (props) => <WebhookLab {...props} />,
  'api-basics': (props) => <ApiRequestLab {...props} />,
  'api-center': (props) => <CredentialLab {...props} mode="api" />,
  'api-errors': (props) => <ChoiceLab {...props} scenario="api-errors" />,
  'bot-setup': (props) => <CredentialLab {...props} mode="bot" />,
  'bot-workflow': (props) => <PipelineLab {...props} />,
  'bot-operations': (props) => <BotOperationsLab {...props} />,
  'workflow-evaluation': (props) => <EvaluationLab {...props} />,
  'auto-improvement': (props) => <ImprovementLab {...props} />,
  'cost-readiness': (props) => <ReadinessLab {...props} />,
  'app-components': (props) => <ComponentsLab {...props} />,
  'app-workflow-mapping': (props) => <MappingLab {...props} />,
  'app-playground-deploy': (props) => <BuilderDeployLab {...props} />,
  'data-query': (props) => <QueryLab {...props} />,
  'data-crawler': (props) => <CrawlerLab {...props} />,
  'data-shaping': (props) => <ShapingLab {...props} />,
  'kr-naver': (props) => <ChoiceLab {...props} scenario="kr-naver" />,
  'kr-kakao': (props) => <KakaoLab {...props} />,
  'kr-open-data': (props) => <OpenDataLab {...props} />,
  'data-format': (props) => <FormatFillLab {...props} />,
  'data-binding': (props) => <BindingLab {...props} />,
};

function AdvancedTutorialLab({ lesson, onComplete }) {
  const [resetKey, setResetKey] = useState(0);
  const [notice, setNotice] = useState({ tone: 'info', text: '화면의 목표 작업을 직접 완료하세요. 모든 동작은 연습 환경에서만 처리됩니다.' });
  const completedRef = useRef(false);
  const Scenario = SCENARIOS[lesson.scenario];

  const feedback = (text, tone = 'info') => setNotice({ text, tone });
  const finish = (text) => {
    setNotice({ text, tone: 'success' });
    if (!completedRef.current) {
      completedRef.current = true;
      onComplete();
    }
  };
  const reset = () => {
    completedRef.current = false;
    setResetKey((key) => key + 1);
    setNotice({ tone: 'info', text: '실습을 초기화했습니다. 목표 작업을 다시 진행하세요.' });
  };

  return (
    <section className="advanced-tutorial-lab">
      <header className="advanced-lab-header"><div><span>GUIDED LAB</span><strong>{lesson.title}</strong></div><button type="button" onClick={reset} title="실습 초기화"><RotateCcw size={16} /></button></header>
      <div className="advanced-lab-body" key={resetKey}>{Scenario ? <Scenario finish={finish} feedback={feedback} /> : <div className="advanced-empty-lab"><AlertTriangle size={24} />실습 시나리오를 준비 중입니다.</div>}</div>
      <footer className={`advanced-lab-feedback ${notice.tone}`}>{notice.tone === 'success' ? <Check size={16} /> : notice.tone === 'warning' ? <AlertTriangle size={16} /> : <ChevronRight size={16} />}<span>{notice.text}</span></footer>
    </section>
  );
}

export default AdvancedTutorialLab;
