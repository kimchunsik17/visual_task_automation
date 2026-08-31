// 실행 오류 카드 (ADR-0016 ERROR-4.1) — category 아이콘, userMessage, code, 해결 동작, 요청 ID.
//
// 서버의 NodeError v1 객체 하나를 그린다. 재시도 버튼은 retryable 이면서 effectState 가 안전할
// 때만 켠다 — Discord/이메일 발송처럼 "보냈는지 모르는" 실패를 다시 보내면 두 번 갈 수 있다.
import { AlertCircle, Bug, Copy, Database, FileWarning, History, KeyRound, Plug, Send, RotateCcw } from 'lucide-react';
import { canRetry, effectStateLabel, getCategoryMeta, getResolution, isLegacyError } from '../nodeErrors';

// safeDetails 는 서버가 "사용자에게 보여도 되는 값"만 골라 담은 것이다(코드별 허용 목록).
// 그런데 화면에 한 번도 그려지지 않아서, "연결한 값의 출처 노드가 실행되지 않았습니다" 같은
// 문구만 남고 **어느 필드·어느 노드·어떤 경로**인지는 알 수 없었다. 아는 키는 한국어 라벨로,
// 모르는 키는 키 이름 그대로 보여준다(빠뜨리는 것보다 낫다).
const DETAIL_LABELS = {
  field: '필드',
  sourceNodeId: '값의 출처',
  path: '경로',
  formatId: '포맷',
  missingFields: '빈 필수 항목',
  artifactId: '파일',
  provider: '제공자',
  providerName: '제공자',
  service: '서비스',
  status: '응답 상태',
  dialect: 'DB 종류',
  targets: '대상',
  targetCount: '대상 수',
  scope: '범위',
  phase: '단계',
  reason: '사유',
  label: '이름',
  nodeType: '노드 종류',
  line: '줄',
  limit: '상한',
  limitKind: '상한 종류',
  timeoutSeconds: '제한 시간(초)',
  expected: '기대값',
  allowed: '허용값',
  output: '출력',
};

const formatDetailValue = (value) => {
  if (Array.isArray(value)) return value.join(', ');
  if (value && typeof value === 'object') return JSON.stringify(value);
  if (value === '') return '(전체)';
  return String(value);
};

const ICONS = {
  'key-round': KeyRound,
  'alert-circle': AlertCircle,
  'file-warning': FileWarning,
  database: Database,
  send: Send,
  plug: Plug,
  history: History,
  bug: Bug,
};

export default function NodeErrorCard({
  error,
  nodeId,
  nodeType,
  onFocusNode,
  onFocusField,
  onRetry,
  onNavigate,
  compact = false,
}) {
  if (!error) return null;
  const category = getCategoryMeta(error.category);
  const Icon = ICONS[category.icon] || Bug;
  const resolution = getResolution(error);
  // field 는 이미 해결 버튼 라벨에 나오므로 중복해서 싣지 않는다.
  const details = Object.entries(error.safeDetails || {})
    .filter(([key, value]) => value !== null && value !== undefined && !(key === 'field' && resolution.kind === 'focus_field'));
  const retryAllowed = canRetry(error);
  const legacy = isLegacyError(error);
  const copyRequestId = () => navigator.clipboard?.writeText(error.requestId || '');

  const actions = [];
  if (resolution.kind === 'navigate' && resolution.target && onNavigate) {
    actions.push(
      <button key="nav" type="button" className="btn-secondary exec-btn" onClick={() => onNavigate(resolution.target)}>
        {resolution.label}
      </button>,
    );
  }
  if (resolution.kind === 'focus_field' && nodeId && (onFocusField || onFocusNode)) {
    actions.push(
      <button key="field" type="button" className="btn-secondary exec-btn" onClick={() => (onFocusField || onFocusNode)(nodeId, error.field)}>
        {resolution.label}{error.field ? ` (${error.field})` : ''}
      </button>,
    );
  }
  // 커뮤니티로 가는 길 (ADR-0021 COMMUNITY-3). **막힌 그 자리가 질문이 시작되는 자리다** —
  // 오류를 보고 커뮤니티를 따로 찾아가게 하면 대부분 그냥 포기한다.
  // 넘기는 것은 NodeError 의 공개 payload 뿐이다(요청 id·내부 기록은 따라가지 않는다).
  if (error.code && !legacy) {
    const excerpt = encodeURIComponent(JSON.stringify({
      code: error.code, category: error.category,
      effectState: error.effectState, userMessage: error.userMessage,
    }));
    actions.push(
      <a key="qna-search" className="btn-secondary exec-btn" href={`/community/qna?error_code=${error.code}`}
         title="같은 오류를 겪은 다른 사람의 질문을 먼저 봅니다">
        비슷한 질문 보기
      </a>,
      <a key="qna-ask" className="btn-secondary exec-btn"
         href={`/community/qna/new?error=${excerpt}&node_type=${encodeURIComponent(nodeType || '')}`}
         title="이 오류를 붙여 질문을 올립니다">
        질문 올리기
      </a>,
    );
  }
  if ((resolution.kind === 'retry' || error.retryable) && nodeId && onRetry) {
    actions.push(
      <button
        key="retry"
        type="button"
        className="btn-secondary exec-btn"
        disabled={!retryAllowed}
        title={retryAllowed ? '이 노드부터 다시 실행' : `자동 재시도 불가 — ${effectStateLabel(error.effectState)}`}
        onClick={() => retryAllowed && onRetry(nodeId)}
      >
        <RotateCcw size={13} /> {resolution.kind === 'retry' ? resolution.label : '다시 시도'}
      </button>,
    );
  }

  return (
    <div className={`exec-error-card ${compact ? 'compact' : ''}`} role="alert">
      <div className="exec-error-head">
        <span className={`exec-error-icon cat-${error.category || 'runtime'}`} aria-hidden="true">
          <Icon size={15} />
        </span>
        <div className="exec-error-body">
          <div className="exec-error-title">
            <span className="exec-error-category">{category.label}</span>
            {nodeId && (
              <button type="button" className="exec-link" onClick={() => onFocusNode && onFocusNode(nodeId)}>
                {nodeId}{nodeType ? <span className="muted"> ({nodeType})</span> : null}
              </button>
            )}
            {legacy && <span className="exec-badge warning" title="아직 구조화 오류로 이전되지 않은 노드의 문구입니다">legacy</span>}
          </div>
          <div className="exec-error-message">{error.userMessage}</div>
          <div className="exec-error-meta">
            <code className="exec-error-code">{error.code}</code>
            {error.effectState && error.effectState !== 'not_applicable' && (
              <span className={`exec-error-effect ${error.effectState}`}>{effectStateLabel(error.effectState)}</span>
            )}
            {error.retryAfterMs ? <span>재시도 대기 {Math.ceil(error.retryAfterMs / 1000)}초</span> : null}
            {error.requestId && (
              <button type="button" className="exec-link muted" onClick={copyRequestId} title="요청 ID 복사 — 문의할 때 알려주세요">
                <Copy size={11} /> {error.requestId}
              </button>
            )}
          </div>
          {details.length > 0 && (
            <dl className="exec-error-details">
              {details.map(([key, value]) => (
                <div key={key}>
                  <dt>{DETAIL_LABELS[key] || key}</dt>
                  <dd>{formatDetailValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
          {resolution.kind === 'manual' && <div className="exec-error-hint">{resolution.label}</div>}
        </div>
      </div>
      {actions.length > 0 && <div className="exec-error-actions">{actions}</div>}
    </div>
  );
}
