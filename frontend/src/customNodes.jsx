import React, { useEffect, useLayoutEffect, useState, useCallback, useRef } from 'react';
import { Handle, Position, useUpdateNodeInternals, NodeResizer, useStore } from '@xyflow/react';
import { Shuffle, ChevronDown, ChevronRight } from 'lucide-react';
import { Icon } from './icons';
import axios from 'axios';
import documentFormatsBundle from './generated/documentFormats.json';
import { DatabaseConnectionPanel, DatabaseQueryToolsPanel, useFeatures } from './components/DatabaseQueryPanel';
import { BindingCountBadge, FieldBindingChip, FieldBindingControl } from './components/FieldBindingPicker';
import { bindingCount, bindingOf, isBindableField } from './nodeBindings';
import AttachmentsField from './components/AttachmentsField';
import { getMemoRequiredHeight, MEMO_MIN_NODE_HEIGHT } from './memoSizing';
import { getMemoColorTheme, MEMO_COLOR_OPTIONS } from './memoColors';
import { MEMO_DEFAULT_WIDTH } from './memoNodeDefaults';
import {
  getMemoContentFingerprint,
  getMemoFontSize,
  MEMO_FONT_SIZE_OPTIONS,
  memoContentToPlainText,
  normalizeMemoContent,
} from './memoContent';
import {
  applyMemoInlineFormat,
  clearMemoInlineFormat,
  insertMemoPlainTextAtSelection,
  readMemoContentFromElement,
  renderMemoContentToElement,
} from './memoContentDom';
import {
  getNodeDefinition,
  getNodeDisplay,
  getFieldOptions,
  getFieldDefault,
  isFieldVisible,
  dependentDefaults,
} from './nodeDefinitions';

const calculateNodeCost = (tokens, model, currency) => {
  if (!tokens && tokens !== 0) return '-';

  // Approximate prices per 1M tokens (blended average of input/output for simplicity)
  let pricePer1M = 2.5;
  if (model) {
    if (model.includes('gpt-4o-mini')) pricePer1M = 0.3;
    else if (model.includes('gpt-4o')) pricePer1M = 10.0;
    else if (model.includes('gemini-3.5-flash')) pricePer1M = 0.15;
    else if (model.includes('gemini-1.5-flash') || model.includes('gemini-1.5-flash')) pricePer1M = 0.15;
    else if (model.includes('gemini-1.5-pro')) pricePer1M = 5.0;
    else if (model.includes('claude-3-5-sonnet')) pricePer1M = 9.0;
    else if (model.includes('claude-3-haiku')) pricePer1M = 0.75;
  }

  const usdCost = (tokens / 1000000) * pricePer1M;

  if (currency === 'KRW') {
    const krwRate = Number(localStorage.getItem('krwRate')) || 1400;
    return `₩${Math.round(usdCost * krwRate).toLocaleString()}`;
  }
  return usdCost < 0.0001 ? `$${usdCost.toFixed(6)}` : `$${usdCost.toFixed(4)}`;
};

const ApiKeyInput = ({ id, data, provider, fieldKey = 'apiKey', placeholder = 'API Key' }) => {
  const isApiCenter = data[`${fieldKey}_source`] === 'apicenter';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginTop: '0.5rem', marginBottom: '0.5rem' }}>
      <label>{placeholder}</label>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <select 
          className="nodrag"
          value={data[`${fieldKey}_source`] || 'manual'}
          onChange={(e) => {
            data.onChange(id, `${fieldKey}_source`, e.target.value);
            if (e.target.value === 'apicenter') {
               data.onChange(id, fieldKey, `{{API_CENTER:${provider}}}`);
            } else {
               data.onChange(id, fieldKey, '');
            }
          }}
          style={{ padding: '0.25rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', fontSize: '0.8rem', width: '100%' }}
        >
          <option value="manual">직접 입력 (또는 시스템 환경변수)</option>
          <option value="apicenter">API 센터 연동</option>
        </select>
      </div>
      {!isApiCenter && (
        <input
          type="password"
          className="nodrag"
          value={data[fieldKey] || ''}
          onChange={(e) => data.onChange(id, fieldKey, e.target.value)}
          placeholder="시스템에 저장된 기본 키를 쓰려면 비워두세요"
          style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
        />
      )}
      {isApiCenter && (
        <div style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', border: '1px solid #10b981', fontSize: '0.8rem', textAlign: 'center' }}>
          API 센터에서 안전하게 불러옵니다
        </div>
      )}
    </div>
  );
};




// ── Common hook: tracks expand state and notifies EditorPage via onExpandChange ──
const useNodeExpand = (id, data) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const lastCommandToken = useRef(null);

  // Responds to a global "expand all / collapse all" command broadcast via node data
  useEffect(() => {
    const cmd = data?.expandAllCommand;
    if (!cmd || cmd.token === lastCommandToken.current) return;
    lastCommandToken.current = cmd.token;
    const next = cmd.action === 'expand';
    setIsExpanded(next);
    if (data?.onExpandChange) data.onExpandChange(id, next);
  }, [data?.expandAllCommand, id, data]);

  const toggleExpand = useCallback(() => {
    setIsExpanded(prev => {
      const next = !prev;
      if (data?.onExpandChange) data.onExpandChange(id, next);
      return next;
    });
  }, [id, data]);
  return { isExpanded, toggleExpand };
};

const asText = (value) => (typeof value === 'object' && value !== null
  ? JSON.stringify(value, null, 2)
  : (value ?? ''));

// 노드 안의 일반 입력창도 DraggableTextarea 와 같은 이유로 한글이 지워진다 — 조합 중에는
// 부모 상태가 갱신되지 않는데(EditorPage 의 조합 버퍼), 그 사이 리렌더가 끼면 React 가 DOM 값을
// 옛 값으로 되돌린다. 편집이 시작되면 draft 가 표시의 정본이 되고, blur 하면 부모 값으로 돌아간다.
const NodeTextField = ({ as = 'input', id, fieldKey, value, onChange, ...rest }) => {
  const [draft, setDraft] = useState(null);
  const Tag = as;
  return (
    <Tag
      value={draft ?? (value ?? '')}
      onChange={(e) => { setDraft(e.target.value); onChange(id, fieldKey, e.target.value); }}
      onBlur={() => setDraft(null)}
      {...rest}
    />
  );
};

export const DraggableTextarea = ({ id, fieldKey, value, onChange, placeholder }) => {
  const [isEditing, setIsEditing] = useState(false);
  // 편집 중에는 이 draft 가 화면의 정본이다. 부모(data[fieldKey])를 그대로 쓰면 한글이 깨진다 —
  // IME 조합 중에는 부모 상태를 일부러 갱신하지 않는데(EditorPage 의 조합 버퍼), 그 사이 리렌더가
  // 끼면 React 가 제어 입력의 DOM 값을 옛 값으로 되돌려 조합 중이던 글자를 지운다.
  // 앞 글자가 확정되며 일어나는 리렌더가 바로 다음 글자를 지워서, "안녕하세요"가 "요"만 남았다.
  const [draft, setDraft] = useState('');

  const handleInteraction = (e) => {
    e.stopPropagation();
    setDraft(asText(value));
    setIsEditing(true);
  };

  return isEditing ? (
    <textarea
      className="nodrag"
      value={draft}
      onChange={(e) => { setDraft(e.target.value); onChange(id, fieldKey, e.target.value); }}
      onBlur={() => setIsEditing(false)}
      autoFocus
      placeholder={placeholder || "텍스트를 입력하세요..."}
      style={{ minHeight: '80px', width: '100%', fontSize: window.innerWidth <= 768 ? '16px' : '0.85rem' }}
    />
  ) : (
    <div
      className="nodrag"
      onDoubleClick={window.innerWidth > 768 ? handleInteraction : undefined}
      onClick={window.innerWidth <= 768 ? handleInteraction : undefined}
      style={{
        minHeight: '80px',
        width: '100%',
        padding: '0.5rem',
        border: '1px dashed var(--border-color)',
        borderRadius: '4px',
        backgroundColor: 'var(--btn-active-bg)',
        color: value ? 'var(--text-color)' : 'var(--text-muted)',
        cursor: 'text',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        fontSize: '0.85rem'
      }}
    >
      {asText(value) || "더블클릭하여 수정하세요..."}

    </div>
  );
};

export const StartNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node collapsed start ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-start" size={16} color="#10b981" /> 시작</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body" style={{ textAlign: 'center', padding: '10px' }}>
          <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>시작점</p>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const PromptNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} prompt ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-prompt" size={16} color="#3b82f6" /> 프롬프트</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>사용자 프롬프트</label>
          <DraggableTextarea id={id} fieldKey="userPrompt" value={data.userPrompt} onChange={data.onChange} placeholder="프롬프트를 입력하세요..." />
          {data.isTokenTrackingMode && (
            <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid #3b82f6', borderRadius: '6px', fontSize: '0.75rem', color: '#94a3b8' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                <span>예상 {data.tokenDisplayMode === 'cost' ? '금액' : '토큰'}:</span>
                <span style={{ color: '#60a5fa', fontWeight: 600 }}>{data.predictedTokens ? (data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.predictedTokens.min_tokens, null, data.costCurrency) : data.predictedTokens.min_tokens) : '-'}</span>
              </div>
            </div>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

// ── 정의 기반 필드 렌더러 (ADR-0005) ─────────────────────────────────────
// node_definitions/<type>.json 의 fields 선언을 그대로 그린다. 예전에는 같은 입력 폼이
// 노드마다 JSX로 따로 적혀 있어서, 필드 하나를 고치려면 이 파일과 서버 validator와 LLM
// 카탈로그를 각각 손대야 했고 셋이 어긋나면 "에디터에선 고를 수 있는데 검증에서 막히는"
// 버그가 났다. repeatable 필드(conditionNode 의 rules)는 분기 엣지 Handle 과 묶여 있어
// 아직 각 노드가 직접 그리고, 허용값만 정의에서 읽는다.
const DefinitionField = ({ id, data, nodeType, field }) => {
  const onChange = data.onChange;
  const value = data[field.name];
  const options = field.options || [];
  const isSelect = field.kind === 'select';
  const fallback = field.default ?? options[0]?.value ?? '';
  const selected = isSelect && options.some((option) => option.value === value) ? value : fallback;

  // 저장된 값이 허용 목록에 없으면(예: 모델 목록에서 빠진 옛 모델) 기본값으로 되돌리고
  // data 에도 반영한다 — 화면만 기본값으로 보이고 저장된 값은 옛 값인 상태를 막는다.
  useEffect(() => {
    if (!isSelect || !field.ui?.coerceToDefault) return;
    if (value !== selected && typeof onChange === 'function') {
      onChange(id, field.name, selected);
    }
  }, [isSelect, field.ui?.coerceToDefault, field.name, value, selected, onChange, id]);

  const commit = (next) => onChange && onChange(id, field.name, next);

  if (field.kind === 'secret') {
    return (
      <ApiKeyInput
        id={id}
        data={data}
        provider={field.credential?.provider}
        fieldKey={field.name}
        placeholder={field.label}
      />
    );
  }

  // 첨부 포트(ADR-0018) — 본문과 달리 파일 참조를 담으므로 전용 UI 가 필요하다.
  if (field.kind === 'attachments') {
    return (
      <AttachmentsField
        id={id}
        data={data}
        fieldName={field.name}
        provider={field.ui?.provider}
        help={field.ui?.help}
      />
    );
  }

  if (field.kind === 'checkbox') {
    const inputId = `${id}-${field.name}`;
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
        <input
          type="checkbox"
          id={inputId}
          className="nodrag"
          checked={value || false}
          onChange={(e) => {
            commit(e.target.checked);
            if (!e.target.checked || typeof onChange !== 'function') return;
            // 이 체크박스를 켜야 비로소 드러나는 필드가 비어 있으면 정의의 기본값을 채워준다.
            Object.entries(dependentDefaults(nodeType, field.name, data)).forEach(
              ([name, preset]) => onChange(id, name, preset)
            );
          }}
          style={{ cursor: 'pointer' }}
        />
        <label htmlFor={inputId} style={{ margin: 0, cursor: 'pointer', fontSize: '0.8rem', color: '#cbd5e1' }}>
          {field.label}
        </label>
      </div>
    );
  }

  const label = field.label
    ? <label style={field.ui?.labelColor ? { color: field.ui.labelColor } : undefined}>{field.label}</label>
    : null;

  // 필드 데이터 바인딩(계획 §5) — 값이 앞 노드에서 오면 입력창 대신 소스 칩을 보여준다.
  // 바인딩을 지원하지 않는 필드나 컨텍스트가 없는 화면에서는 아무것도 그리지 않는다.
  const bindable = isBindableField(nodeType, field.name) && Boolean(data?.bindingContext);
  if (bindable && bindingOf(data, field.name)) {
    return (
      <div className="fbind-field">
        {label}
        <FieldBindingChip id={id} data={data} field={field.name} />
        <FieldBindingControl id={id} data={data} nodeType={nodeType} field={field.name} label={field.label} />
      </div>
    );
  }
  const bindingControl = bindable
    ? <FieldBindingControl id={id} data={data} nodeType={nodeType} field={field.name} label={field.label} />
    : null;

  if (field.kind === 'textarea' || field.kind === 'json') {
    return (
      <div className={bindingControl ? 'fbind-field' : undefined}>
        {label}
        {bindingControl}
        <DraggableTextarea
          id={id}
          fieldKey={field.name}
          value={value}
          onChange={onChange}
          placeholder={field.placeholder}
        />
      </div>
    );
  }

  if (isSelect) {
    return (
      <div className={bindingControl ? 'fbind-field' : undefined}>
        {label}
        {bindingControl}
        <select className="nodrag" value={selected} onChange={(e) => commit(e.target.value)}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className={bindingControl ? 'fbind-field' : undefined}>
      {label}
      {bindingControl}
      <input
        type={field.kind === 'number' ? 'number' : 'text'}
        className="nodrag"
        defaultValue={value ?? field.default ?? ''}
        onChange={(e) => commit(field.kind === 'number' ? Number(e.target.value) : e.target.value)}
        placeholder={field.placeholder}
      />
    </div>
  );
};

// 공식 연동 노드(ADR-0008). 헤더도 필드도 전부 정의 파일에서 나오므로, 노드를 추가할 때
// 이 파일에 새로 쓸 JSX 가 사실상 없다 — 아래 한 줄짜리 래퍼가 전부다.
// 실행 결과 배지 (EDITOR_SHORTCUTS §7.2) — 노드 위에서 결과 상태를 보고, 눌러서 Inspector 를 연다.
// 고정 출력(§7.3)으로 대체된 노드는 "실행하지 않았다" 는 사실이 배지로 드러나야 한다.
export const NodeResultBadge = ({ id, data }) => {
  const status = data.executionStatus;
  const pinned = data.isPinnedOutput;
  if (!status && !pinned) return null;
  const label = pinned ? '고정' : status === 'error' ? '오류' : status === 'running' ? '실행 중' : '성공';
  const tone = pinned ? 'pinned' : status === 'error' ? 'error' : status === 'running' ? 'running' : 'success';
  return (
    <button
      type="button"
      className={`node-result-badge ${tone}`}
      title={pinned ? '고정된 출력 — 이 노드는 실행되지 않습니다. 눌러서 검사' : '최근 실행 결과 — 눌러서 입력·출력 검사'}
      onClick={(event) => {
        event.stopPropagation();
        if (data.onInspect) data.onInspect(id);
      }}
    >
      {label}
    </button>
  );
};

/** 입력 포트는 정의 파일의 `inputs` 에서 온다 — 첨부 포트(ADR-0018)처럼 포트가 늘어도
 *  컴포넌트를 고치지 않는다. 본문('in')과 첨부는 세로로 나눠 어디에 잇는지 보이게 한다. */
const ConnectorInputHandles = ({ nodeType }) => {
  const ports = getNodeDefinition(nodeType)?.inputs?.length
    ? getNodeDefinition(nodeType).inputs
    : [{ name: 'in', dataType: 'any' }];
  if (ports.length === 1) {
    return <Handle type="target" position={Position.Left} id={ports[0].name} />;
  }
  return ports.map((port, index) => (
    <Handle
      key={port.name}
      type="target"
      position={Position.Left}
      id={port.name}
      title={port.label || port.name}
      style={{
        top: `${((index + 1) * 100) / (ports.length + 1)}%`,
        background: port.dataType === 'artifact' ? '#f59e0b' : undefined,
      }}
    />
  ));
};

const ConnectorNode = ({ id, data, nodeType, hasInput = true }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const display = getNodeDisplay(nodeType);
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div
      className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} ${data.isAIModified ? 'ai-highlight' : ''}`}
      onClick={handleNodeClick}
      style={{ minWidth: isExpanded ? '250px' : undefined, borderTop: `3px solid ${display.color}` }}
    >
      {hasInput && <ConnectorInputHandles nodeType={nodeType} />}
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Icon name={display.icon} size={16} color={display.color} /> {display.label}
        </div>
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <NodeResultBadge id={id} data={data} />
        <button className="btn-delete" onClick={() => data.onDelete && data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <DefinitionFields id={id} data={data} nodeType={nodeType} />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

// 트리거는 플로우의 시작점이라 들어오는 연결이 없다.
export const YoutubeTriggerNode = (props) => <ConnectorNode {...props} nodeType="youtubeTriggerNode" hasInput={false} />;
export const YoutubeNode = (props) => <ConnectorNode {...props} nodeType="youtubeNode" />;
export const RssTriggerNode = (props) => <ConnectorNode {...props} nodeType="rssTriggerNode" hasInput={false} />;
export const GmailTriggerNode = (props) => <ConnectorNode {...props} nodeType="gmailTriggerNode" hasInput={false} />;
export const GmailNode = (props) => <ConnectorNode {...props} nodeType="gmailNode" />;
export const GoogleDriveNode = (props) => <ConnectorNode {...props} nodeType="googleDriveNode" />;
export const NaverSearchNode = (props) => <ConnectorNode {...props} nodeType="naverSearchNode" />;
export const JusoNode = (props) => <ConnectorNode {...props} nodeType="jusoNode" />;
export const DataGoKrNode = (props) => <ConnectorNode {...props} nodeType="dataGoKrNode" />;
export const NaverSearchTriggerNode = (props) => <ConnectorNode {...props} nodeType="naverSearchTriggerNode" hasInput={false} />;
export const NaverCafeNode = (props) => <ConnectorNode {...props} nodeType="naverCafeNode" />;
// 연동 노드는 아니지만(connector 블록 없음) 화면에서 필요한 것은 같다 — 정의에서 색·아이콘·
// 필드를 읽어 그리고 펼칠 수 있으면 된다. ConnectorNode 는 그 셋만 쓰므로 그대로 재사용한다.
export const HwpxDocumentNode = (props) => <ConnectorNode {...props} nodeType="hwpxDocumentNode" />;

// ── 문서 포맷 노드 (포맷 스튜디오 계획 Phase 1) ─────────────────────────────
// 포맷(프리셋 + 내 라이브러리)을 골라 빈칸 목록을 미리 보여주고, 빈칸 채움 LLM 을 만들 때
// 쓸 축소 JSON Schema(§4.2-b — image 필드 제외)를 복사해 준다. 실행은 결정적(LLM 없음).

let _userFormatsCache = null;
export const invalidateUserFormatsCache = () => {
  _userFormatsCache = null;
  // 열려 있는 FormatNode 들이 목록을 다시 받아오게 한다(스튜디오 저장 직후 적용이 보이도록).
  window.dispatchEvent(new Event('formats-library-changed'));
};
const fetchUserFormats = async () => {
  if (_userFormatsCache) return _userFormatsCache;
  try {
    const token = localStorage.getItem('token');
    const res = await axios.get('/api/formats', { headers: { Authorization: `Bearer ${token}` } });
    _userFormatsCache = res.data.formats || [];
  } catch {
    _userFormatsCache = []; // 미로그인·오류 시 프리셋만
  }
  return _userFormatsCache;
};

export const findFormatSpecById = (formatId) => {
  const preset = (documentFormatsBundle.formats || []).find((f) => f.id === formatId);
  if (preset) return preset;
  const row = (_userFormatsCache || []).find((f) => f.id === formatId);
  return row ? { ...row.spec, id: row.id, name: row.name } : null;
};

const OUTPUT_LABELS = { hwpx: '한/글 (.hwpx)', docx: '워드 (.docx)', pdf: 'PDF', xlsx: '엑셀 (.xlsx)', png: '이미지 (.png)' };
const FIELD_KIND_BADGE = { text: '텍스트', multiline: '긴 글', rows: '표', image: '이미지' };

// 빈칸 채움 LLM 용 축소 스키마 — backend documents/format_spec.fields_json_schema 와 같은 규칙.
export const formatFieldsSchema = (spec) => {
  const properties = {}; const required = [];
  (spec?.fields || []).forEach((field) => {
    if (field.kind === 'image') return; // LLM 이 만들 수 없다
    const description = (field.label || field.name) + (field.description ? ` — ${field.description}` : '');
    properties[field.name] = field.kind === 'rows'
      ? { type: 'array', description: `${description} (각 행은 ${JSON.stringify(field.columns || [])} 순서의 문자열 배열)`, items: { type: 'array', items: { type: 'string' } } }
      : { type: 'string', description };
    if (field.required) required.push(field.name);
  });
  // title 은 OpenAI structured output 의 json_schema.name 이 된다(^[a-zA-Z0-9_-]+$ 만 허용) —
  // 한글 포맷 이름을 그대로 쓰면 400 으로 거부되므로 이름은 description 으로 옮긴다.
  const name = spec?.name || '';
  const safe = Array.from(name).filter((c) => /[a-zA-Z0-9_-]/.test(c)).join('');
  return {
    title: safe || 'FormatValues',
    description: name ? `${name} 포맷의 빈칸 값` : '포맷의 빈칸 값',
    type: 'object', properties, required,
  };
};

export const FormatNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const display = getNodeDisplay('formatNode');
  const [userFormats, setUserFormats] = useState([]);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let on = true;
    const load = () => fetchUserFormats().then((f) => { if (on) setUserFormats(f); });
    load();
    window.addEventListener('formats-library-changed', load);
    return () => { on = false; window.removeEventListener('formats-library-changed', load); };
  }, []);

  const presets = documentFormatsBundle.formats || [];
  const selected = presets.find((f) => f.id === data.formatId)
    || userFormats.map((r) => ({ ...r.spec, id: r.id, name: r.name })).find((f) => f.id === data.formatId)
    || null;
  const allowedOutputs = selected?.output?.allowed || ['hwpx', 'docx', 'pdf', 'xlsx', 'png'];
  // 비워 두면 런타임은 포맷의 output.default 를 쓴다 — 화면도 같은 값을 보여줘야 한다
  // (allowed[0] 를 보여주면 회의록·제안서에서 "hwpx 로 보이는데 docx 가 나오는" 불일치).
  const defaultOutput = (selected?.output?.default && allowedOutputs.includes(selected.output.default))
    ? selected.output.default : allowedOutputs[0];
  const outputValue = data.output || defaultOutput;

  // 바인딩 UI — DefinitionField 와 같은 규칙(칩이면 입력창 대체, ⚡ 는 항상)
  const bindable = Boolean(data?.bindingContext);
  const boundTo = (field) => (bindable ? bindingOf(data, field) : null);
  const bindCtl = (field, label) => (
    bindable ? <FieldBindingControl id={id} data={data} nodeType="formatNode" field={field} label={label} /> : null
  );

  const copySchema = async (event) => {
    event.stopPropagation();
    if (!selected) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(formatFieldsSchema(selected), null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch { /* 클립보드 불가 환경 */ }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} ${data.isAIModified ? 'ai-highlight' : ''}`}
         style={{ minWidth: isExpanded ? '270px' : undefined, borderLeft: `4px solid ${display.color || '#0d9488'}` }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Icon name={display.icon || 'node-file-modifier'} size={16} color={display.color || '#0d9488'} /> 문서 포맷
        </div>
        <NodeResultBadge id={id} data={data} />
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete && data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div className={bindable ? 'fbind-field' : undefined}>
          <label>포맷</label>
          {bindCtl('formatId', '포맷')}
          {boundTo('formatId') ? <FieldBindingChip id={id} data={data} field="formatId" /> : (
          <select className="nodrag" value={data.formatId || ''}
                  onChange={(e) => data.onChange && data.onChange(id, 'formatId', e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-color)', boxSizing: 'border-box' }}>
            <option value="">포맷 선택…</option>
            <optgroup label="프리셋">
              {presets.map((f) => <option key={f.id} value={f.id}>{f.name}{f.layout === 'design' ? ' (디자인)' : ''}</option>)}
            </optgroup>
            {userFormats.length > 0 && (
              <optgroup label="내 포맷">
                {userFormats.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </optgroup>
            )}
          </select>
          )}
          </div>

          <label style={{ marginTop: '0.5rem' }}>출력 형식</label>
          <select className="nodrag" value={outputValue}
                  onChange={(e) => data.onChange && data.onChange(id, 'output', e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-color)', boxSizing: 'border-box' }}>
            {!allowedOutputs.includes(outputValue) && (
              <option value={outputValue} disabled>
                {(OUTPUT_LABELS[outputValue] || outputValue) + ' — 이 포맷은 지원 안 함'}
              </option>
            )}
            {allowedOutputs.map((o) => <option key={o} value={o}>{OUTPUT_LABELS[o] || o}</option>)}
          </select>

          {selected && (
            <div className="format-node-fields nodrag">
              <div className="format-node-fields-head">
                <span>빈칸 {selected.fields?.length || 0}개 — 앞 노드의 값은 아래 <strong>빈칸 값</strong>의 ⚡로 연결하고,
                  문장을 지어내야 하는 칸만 LLM으로 채우세요. 연결이 없으면 직전 노드의 JSON에서 같은 이름 키를 찾습니다.</span>
                <button type="button" onClick={copySchema} title="빈칸 채움 LLM 의 Structured Output 스키마 복사 (이미지 빈칸 제외)">
                  {copied ? '복사됨 ✓' : 'LLM 스키마 복사'}
                </button>
              </div>
              <div className="format-node-field-chips">
                {(selected.fields || []).map((f) => (
                  <span key={f.name} className={f.required ? 'is-required' : ''}
                        title={`${f.name} · ${FIELD_KIND_BADGE[f.kind] || f.kind}${f.required ? ' · 필수' : ''}`}>
                    {f.label || f.name}{f.required ? ' *' : ''}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className={bindable ? 'fbind-field' : undefined}>
            <label style={{ marginTop: '0.5rem' }}>빈칸 값 (JSON, 선택)</label>
            {bindCtl('values', '빈칸 값')}
            {boundTo('values') ? <FieldBindingChip id={id} data={data} field="values" /> : (
              <textarea className="nodrag" defaultValue={data.values || ''} rows={3}
                        onChange={(e) => data.onChange && data.onChange(id, 'values', e.target.value)}
                        placeholder='비우면 직전 노드 출력 사용. 예: {"authorName": "김워크"}' />
            )}
          </div>
          <div className="format-node-actions nodrag">
            <button type="button" onClick={(e) => { e.stopPropagation(); data.onOpenFormatStudio && data.onOpenFormatStudio(id, data.formatId || ''); }}>
              포맷 스튜디오
            </button>
            <button type="button" disabled={!selected || Boolean(boundTo('values'))}
                    title={boundTo('values')
                      ? '빈칸 값이 앞 노드에 연결돼 있습니다 — LLM 을 끼우면 그 값이 무시됩니다. 문장이 필요한 칸만 있을 때 연결을 풀고 쓰세요.'
                      : '이 포맷의 빈칸(이미지 제외)을 채우는 Structured Output llmNode 를 앞에 삽입합니다. 앞 노드의 값으로 채울 수 있는 빈칸이면 ⚡ 연결이 더 싸고 정확합니다.'}
                    onClick={(e) => { e.stopPropagation(); selected && data.onInsertFillLLM && data.onInsertFillLLM(id, selected); }}>
              빈칸 채우기 LLM 삽입
            </button>
          </div>
          <div className={bindable ? 'fbind-field' : undefined}>
            <label style={{ marginTop: '0.5rem' }}>저장 파일 이름 (선택)</label>
            {bindCtl('output_path', '저장 파일 이름')}
            {boundTo('output_path') ? <FieldBindingChip id={id} data={data} field="output_path" /> : (
              <input type="text" className="nodrag" defaultValue={data.output_path || ''}
                     onChange={(e) => data.onChange && data.onChange(id, 'output_path', e.target.value)}
                     placeholder="비우면 포맷 이름으로 자동"
                     style={{ width: '100%', padding: '0.45rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', boxSizing: 'border-box' }} />
            )}
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};

export const DefinitionFields = ({ id, data, nodeType }) => {
  const definition = getNodeDefinition(nodeType);
  if (!definition) return null;
  return (
    <>
      {(definition.fields || [])
        .filter((field) => field.kind !== 'repeatable' && !field.ui?.hidden && isFieldVisible(field, data))
        .map((field) => (
          <DefinitionField key={field.name} id={id} data={data} nodeType={nodeType} field={field} />
        ))}
    </>
  );
};

const LLM_DISPLAY = getNodeDisplay('llmNode');
const HTTP_DISPLAY = getNodeDisplay('httpRequestNode');
const CONDITION_DISPLAY = getNodeDisplay('conditionNode');
const CONDITION_OPERATORS = getFieldOptions('conditionNode', 'rules.operator');
const CONDITION_DEFAULT_OPERATOR = getFieldDefault('conditionNode', 'rules.operator');

export const LLMNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} llm ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name={LLM_DISPLAY.icon} size={16} color={LLM_DISPLAY.color} /> {LLM_DISPLAY.label}</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <DefinitionFields id={id} data={data} nodeType="llmNode" />

          {data.isTokenTrackingMode && (
            <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid #8b5cf6', borderRadius: '6px', fontSize: '0.75rem', color: '#94a3b8' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span>예상 {data.tokenDisplayMode === 'cost' ? '금액' : '토큰'} (최소~최대):</span>
                <span style={{ color: '#a78bfa', fontWeight: 600 }}>
                  {data.predictedTokens ? `${data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.predictedTokens.min_tokens, data.model, data.costCurrency) : data.predictedTokens.min_tokens} ~ ${data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.predictedTokens.max_tokens, data.model, data.costCurrency) : data.predictedTokens.max_tokens}` : '-'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(139, 92, 246, 0.2)', paddingTop: '4px' }}>
                <span>실제 소모:</span>
                <span style={{ color: '#10b981', fontWeight: 600 }}>
                  {data.actualTokens !== null ? (data.tokenDisplayMode === 'cost' ? calculateNodeCost(data.actualTokens.total_tokens || 0, data.model, data.costCurrency) : (data.actualTokens.total_tokens || JSON.stringify(data.actualTokens))) : '-'}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const ValueNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const [isUploading, setIsUploading] = useState(false);
  // 변수 허브(계획 §5-5) — 이름을 붙이면 앞 결과를 이어 붙이지 않고 값 그대로 내보낸다.
  const bindable = Boolean(data?.bindingContext);
  const valueBinding = bindable ? bindingOf(data, 'value') : null;
  const varName = (data.varName || '').trim();

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/upload', formData, {
        // 업로드는 소유자·용량이 기록된다(ADR-0010) — 토큰이 없으면 401 이다.
        headers: { 'Content-Type': 'multipart/form-data', Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      if (response.data.status === 'success') {
        data.onChange(id, 'file_path', response.data.file_path);
        data.onChange(id, 'filename', response.data.filename);
      }
    } catch (error) {
      console.error('File upload failed:', error);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} value ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Icon name="node-value" size={16} color="#ec4899" />
          {varName ? <span title="변수 허브 — 하류 노드가 이 이름으로 값을 가져갑니다">변수 · {varName}</span> : '변수'}
        </div>
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>변수 이름 (선택)</label>
          <input type="text" className="nodrag" defaultValue={data.varName || ''}
                 onChange={(e) => data.onChange(id, 'varName', e.target.value)}
                 placeholder="예: 담당자 이메일"
                 title="이름을 붙이면 앞 결과를 이어 붙이지 않고 값 그대로 내보냅니다 — 여러 노드가 이 값을 가져다 쓰는 허브가 됩니다"
                 style={{ width: '100%', padding: '0.4rem', marginBottom: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', boxSizing: 'border-box' }} />
          <div className={bindable ? 'fbind-field' : undefined}>
          <label>받는 값</label>
          {bindable && <FieldBindingControl id={id} data={data} nodeType="valueNode" field="value" label="값" />}
          {valueBinding ? <FieldBindingChip id={id} data={data} field="value" /> : (
          <>
          {data.filename ? (
            <div style={{ padding: '8px', backgroundColor: 'var(--btn-active-bg)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span title={data.file_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📎 {data.filename}</span>
              <button className="nodrag" onClick={() => { data.onChange(id, 'file_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>✕</button>
            </div>
          ) : (
            <DraggableTextarea id={id} fieldKey="value" value={data.value} onChange={data.onChange} placeholder="Enter a static value..." />
          )}

          {!data.filename && (
            <div style={{ marginTop: '8px' }}>
              <input
                type="file"
                id={`file-upload-${id}`}
                className="nodrag"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
                disabled={isUploading}
              />
              <label htmlFor={`file-upload-${id}`} className="nodrag" style={{ display: 'block', textAlign: 'center', padding: '4px 8px', backgroundColor: '#be185d', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
                {isUploading ? 'Uploading...' : 'Upload File (PDF, Excel, PPT, HWP)'}
              </label>
            </div>
          )}
          </>
          )}
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const OutputNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} output ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-output" size={16} color="#f97316" /> Output</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Final Result</div>
        </div>
      )}

    </div>
  );
};

export const ConditionNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  // Ensure we have a default rules array with stable IDs
  const rules = data.rules && data.rules.length > 0
    ? data.rules
    : [{ id: `${id}_rule_default`, operator: CONDITION_DEFAULT_OPERATOR, value: '' }];
  const updateNodeInternals = useUpdateNodeInternals();

  useEffect(() => {
    updateNodeInternals(id);
  }, [rules.length, id, updateNodeInternals]);

  const addRule = () => {
    const newRules = [...rules, { id: `rule_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`, operator: CONDITION_DEFAULT_OPERATOR, value: '' }];
    data.onChange(id, 'rules', newRules);
  };

  const removeRule = (ruleId) => {
    const newRules = rules.filter(r => r.id !== ruleId);
    data.onChange(id, 'rules', newRules);
  };

  const updateRule = (ruleId, key, value) => {
    const newRules = rules.map(r => r.id === ruleId ? { ...r, [key]: value } : r);
    data.onChange(id, 'rules', newRules);
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} condition ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ width: isExpanded ? '280px' : undefined, position: 'relative', overflow: 'visible' }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Icon name={CONDITION_DISPLAY.icon} size={isExpanded ? 14 : 28} color={CONDITION_DISPLAY.color} />
          {isExpanded ? CONDITION_DISPLAY.label : CONDITION_DISPLAY.collapsedLabel}
        </div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">

          {rules.map((rule, index) => (
            <div key={rule.id} style={{ display: 'flex', alignItems: 'center', marginBottom: '0.5rem', position: 'relative' }}>
              <select
                className="nodrag"
                value={rule.operator}
                onChange={(e) => updateRule(rule.id, 'operator', e.target.value)}
                style={{ width: '35%', padding: '0.25rem', marginRight: '5px', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.75rem' }}
              >
                {CONDITION_OPERATORS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>

              <input
                type="text"
                className="nodrag"
                value={rule.value}
                onChange={(e) => updateRule(rule.id, 'value', e.target.value)}
                placeholder="Value"
                style={{ flex: 1, padding: '0.25rem', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.75rem', minWidth: 0 }}
              />

              <button
                onClick={() => removeRule(rule.id)}
                style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', marginLeft: '5px', padding: '0 5px' }}
                title="Remove Rule"
              >✕</button>
            </div>
          ))}

          <div style={{ display: 'flex', justifyContent: 'center', marginTop: '0.5rem', marginBottom: '1rem' }}>
            <button
              className="nodrag"
              onClick={addRule}
              style={{ background: 'var(--btn-active-bg)', border: '1px dashed var(--border-color)', color: 'var(--text-muted)', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', width: '100%' }}
            >
              + Add Condition
            </button>
          </div>

          <div style={{ position: 'relative', marginTop: '1rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Else (Fallback)</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginRight: '8px' }}>→</span>
          </div>

        </div>
      )}

      {/* ── Handles always rendered outside isExpanded block ── */}
      {rules.map((rule, index) => (
        <Handle
          key={rule.id}
          type="source"
          position={Position.Right}
          id={rule.id}
          style={isExpanded
            ? { right: '-8px', top: `${48 + index * 38}px`, background: '#0ea5e9', zIndex: 20 }
            : {
                right: '-8px',
                top: `${(100 / (rules.length + 2)) * (index + 1)}%`,
                background: '#0ea5e9',
                zIndex: 20
              }
          }
        />
      ))}
      <Handle
        type="source"
        position={Position.Right}
        id="else"
        style={isExpanded
          ? { right: '-8px', bottom: '16px', top: 'auto', background: '#94a3b8', zIndex: 20 }
          : {
              right: '-8px',
              top: `${(100 / (rules.length + 2)) * (rules.length + 1)}%`,
              background: '#94a3b8',
              zIndex: 20
            }
        }
      />


    </div>
  );
};

export const LoopNode = ({ id, data, selected }) => {
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <>
      <NodeResizer minWidth={380} minHeight={280} isVisible={selected} />
      <div
        className={`custom-node loop-node ${isAIModified ? 'ai-highlight' : ''}`}
        onClick={handleNodeClick}
      >
        <Handle
          className="loop-external-handle"
          type="target"
          position={Position.Left}
          id="in"
          style={{ top: '28px' }}
        />
        <div className="loop-node-header">
          <div className="loop-node-title">
            <span><Icon name="node-loop" size={19} /></span>
            <div>
              <small>CONTROL FLOW / CONTAINER</small>
              <strong>{data.label || '반복 컨테이너'}</strong>
            </div>
          </div>
          <label className="loop-iteration-control nodrag" onClick={(event) => event.stopPropagation()}>
            <span>MAX ITERATIONS</span>
            <input
              type="number"
              value={data.maxIterations ?? 5}
              onChange={(event) => data.onChange?.(id, 'maxIterations', Number(event.target.value))}
              min="1"
              max="100"
              aria-label="최대 반복 횟수"
            />
            <em>회</em>
          </label>
          <NodeResultBadge id={id} data={data} />
          <button
            type="button"
            className="btn-delete nodrag"
            onClick={(event) => {
              event.stopPropagation();
              data.onDelete?.(id);
            }}
            aria-label="반복 컨테이너 삭제"
          >✕</button>
        </div>
        <div className="loop-node-workspace">
          <div className="loop-port-card loop-port-entry">
            <span>ENTRY</span>
            <strong>반복 시작</strong>
            <Handle
              className="loop-internal-handle"
              type="source"
              position={Position.Right}
              id="loop_start"
            />
          </div>
          <div className="loop-workspace-hint" aria-hidden="true">
            <span><Icon name="node-loop" size={24} /></span>
            <strong>반복할 노드를 이 영역에 배치하세요</strong>
            <small>목록의 각 항목 또는 지정 횟수만큼 내부 흐름을 실행합니다.</small>
          </div>
          <div className="loop-port-card loop-port-next">
            <span>RETURN</span>
            <strong>다음 반복</strong>
            <Handle
              className="loop-internal-handle"
              type="target"
              position={Position.Left}
              id="loop_next"
            />
          </div>
          <div className="loop-done-port">
            <span><i /> COMPLETE</span>
            <strong>반복 완료</strong>
            <Handle
              className="loop-done-handle"
              type="source"
              position={Position.Right}
              id="done"
            />
          </div>
        </div>
      </div>
    </>
  );
};

export const BreakNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} break break-node special-flow-node ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <div className="special-node-title">
          <span><Icon name="node-break" size={18} /></span>
          <div><strong>{data.label || '반복 종료'}</strong><small>CONTROL / BREAK</small></div>
        </div>
        <button className="btn-delete" onClick={(event) => { event.stopPropagation(); data.onDelete?.(id); }}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div className="special-node-callout danger">
            <span><Icon name="node-break" size={18} /></span>
            <div><strong>현재 반복을 즉시 종료</strong><small>조건이 충족되면 Loop의 완료 경로로 이동합니다.</small></div>
          </div>
        </div>
      )}

    </div>
  );
};

export const PythonNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const target = e.target;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const val = target.value;
      const newValue = val.substring(0, start) + '    ' + val.substring(end);

      data.onChange(id, 'code', newValue);

      // We need to set the cursor position back after the render
      setTimeout(() => {
        target.selectionStart = target.selectionEnd = start + 4;
      }, 0);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} python ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ width: isExpanded ? '300px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-python" size={16} color="#eab308" /> 파이썬</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Input: `input_data`, Output: `output_data`</label>
          <DraggableTextarea id={id} fieldKey="code" value={data.code} onChange={data.onChange} placeholder="output_data = str(input_data) + " />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const TokenizerNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} tokenizer ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ width: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-tokenizer" size={16} color="#14b8a6" /> 토크나이저</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Parsing Method</label>
          <select
            className="nodrag"
            value={data.method || 'extract_text'}
            onChange={(e) => data.onChange(id, 'method', e.target.value)}
            style={{ width: '100%', padding: '0.4rem', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', marginTop: '0.5rem' }}
          >
            <option value="extract_text">Extract All Text</option>
            <option value="chunk_pages">Chunk by Page</option>
          </select>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Supports PDF, PPTX, Excel, HWP/HWPX
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const DistributorNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} distributor distributor-node special-flow-node ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <div className="special-node-title">
          <span><Icon name="node-distributor" size={18} /></span>
          <div><strong>{data.label || '분배기'}</strong><small>FOR EACH / DISTRIBUTE</small></div>
        </div>
        <button className="btn-delete" onClick={(event) => { event.stopPropagation(); data.onDelete?.(id); }}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div className="special-node-callout">
            <span><Icon name="node-distributor" size={18} /></span>
            <div><strong>목록을 개별 항목으로 분배</strong><small>입력 배열의 항목을 하나씩 다음 노드로 전달합니다.</small></div>
          </div>
        </div>
      )}
      {/* 반복 본체로 나가는 선(out)과 **반복이 끝난 뒤** 한 번만 나가는 선(done)은 다르다.
          done 핸들이 없으면 `sourceHandle: "done"` 엣지가 붙을 자리가 없어 **선이 아예
          그려지지 않는다** — 데이터에는 있는데 캔버스에서만 끊겨 보인다(실제로 겪음).
          loopNode 와 같은 이름을 쓴다(node_generators/flow_nodes.py 가 'done' 을 읽는다). */}
      <Handle type="source" position={Position.Right} id="out" style={{ top: '36%' }} />
      <Handle type="source" position={Position.Right} id="done"
              title="반복 완료 후" style={{ top: '68%', background: '#f97316' }} />

    </div>
  );
};

export const FileModifierNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const [isUploading, setIsUploading] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/upload', formData, {
        // 업로드는 소유자·용량이 기록된다(ADR-0010) — 토큰이 없으면 401 이다.
        headers: { 'Content-Type': 'multipart/form-data', Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      if (response.data.status === 'success') {
        data.onChange(id, 'template_path', response.data.file_path);
        data.onChange(id, 'filename', response.data.filename);
      }
    } catch (error) {
      console.error('File upload failed:', error);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} file-modifier ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ width: isExpanded ? '260px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />

      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-file-modifier" size={16} color="#f43f5e" /> 자동 완성</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Template File</label>
          {data.filename ? (
            <div style={{ padding: '8px', backgroundColor: 'var(--btn-active-bg)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span title={data.template_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📎 {data.filename}</span>
              <button className="nodrag" onClick={() => { data.onChange(id, 'template_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>✕</button>
            </div>
          ) : (
            <div style={{ marginBottom: '8px' }}>
              <input
                type="file"
                id={`file-upload-template-${id}`}
                className="nodrag"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
                disabled={isUploading}
              />
              <label htmlFor={`file-upload-template-${id}`} className="nodrag" style={{ display: 'block', textAlign: 'center', padding: '6px', backgroundColor: '#ea580c', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
                {isUploading ? 'Uploading...' : 'Upload Template File'}
              </label>
            </div>
          )}

          <label>Output File Path</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.output_path || ''}
            onChange={(e) => data.onChange(id, 'output_path', e.target.value)}
            placeholder="e.g. output.hwp or output.xlsx"
            style={{ width: '100%', padding: '0.4rem', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', marginBottom: '8px' }}
          />

          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Requires JSON input. Replaces {'{{key}}'} in Excel/PPT and fills 누름틀 in HWP.
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const TemplateAnalyzerNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const [isUploading, setIsUploading] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/upload', formData, {
        // 업로드는 소유자·용량이 기록된다(ADR-0010) — 토큰이 없으면 401 이다.
        headers: { 'Content-Type': 'multipart/form-data', Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      if (response.data.status === 'success') {
        data.onChange(id, 'template_path', response.data.file_path);
        data.onChange(id, 'filename', response.data.filename);
      }
    } catch (error) {
      console.error('File upload failed:', error);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} template-analyzer ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ width: isExpanded ? '260px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-template-analyzer" size={16} color="#8b5cf6" /> 템플릿 분석</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Template File</label>
          {data.filename ? (
            <div style={{ padding: '8px', backgroundColor: 'var(--btn-active-bg)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span title={data.template_path} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📎 {data.filename}</span>
              <button className="nodrag" onClick={() => { data.onChange(id, 'template_path', ''); data.onChange(id, 'filename', ''); }} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>✕</button>
            </div>
          ) : (
            <div style={{ marginBottom: '8px' }}>
              <input
                type="file"
                id={`file-upload-analyzer-${id}`}
                className="nodrag"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
                disabled={isUploading}
              />
              <label htmlFor={`file-upload-analyzer-${id}`} className="nodrag" style={{ display: 'block', textAlign: 'center', padding: '6px', backgroundColor: '#0d9488', color: 'var(--text-color)', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
                {isUploading ? 'Uploading...' : 'Upload Blank Template'}
              </label>
            </div>
          )}

          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            Analyzes the template and extracts placeholders {'{{key}}'} as a JSON schema.
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const DynamicInputNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const [uploading, setUploading] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data', Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      data.onChange(id, 'testValue', res.data.file_path);
    } catch (err) {
      console.error('File upload failed', err);
      alert('파일 업로드에 실패했습니다.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} dynamic-input ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-dynamic-input" size={16} color="#d946ef" /> 동적 입력</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>입력 프롬프트 라벨</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.inputLabel || '사용자 입력을 기다립니다...'}
            onChange={(e) => data.onChange(id, 'inputLabel', e.target.value)}
            placeholder="예: 이름이 무엇인가요?"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          />

          <label>입력 타입</label>
          <select
            className="nodrag"
            value={data.inputType || 'text'}
            onChange={(e) => {
              data.onChange(id, 'inputType', e.target.value);
              data.onChange(id, 'testValue', ''); // Reset test value on type change
            }}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          >
            <option value="text">텍스트 (Text)</option>
            <option value="file">파일 (File)</option>
          </select>

          <label>테스트용 입력값 (에디터 실행용)</label>
          {(data.inputType === 'file') ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <input
                type="file"
                className="nodrag"
                onChange={handleFileUpload}
                disabled={uploading}
                style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}
              />
              {uploading && <span style={{ fontSize: '0.75rem', color: '#fbbf24' }}>업로드 중...</span>}
              {data.testValue && <span style={{ fontSize: '0.75rem', color: '#10b981', wordBreak: 'break-all' }}>업로드 완료: {data.testValue}</span>}
            </div>
          ) : (
            <NodeTextField
              type="text"
              className="nodrag"
              id={id} fieldKey="testValue" value={data.testValue} onChange={data.onChange}
              placeholder="테스트 실행 시 사용할 값"
              style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
            />
          )}

          <label style={{ marginTop: '0.5rem', color: 'var(--text-muted)', fontSize: '0.75rem' }}>* 배포 모드에서 사용자에게 보일 입력 칸입니다.</label>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

const crawlerFieldStyle = {
  width: '100%', padding: '0.5rem', borderRadius: '4px',
  background: 'var(--bg-color)', color: 'var(--text-color)',
  border: '1px solid var(--border-color)',
};

export const WebCrawlerNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} crawler ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-web-crawler" size={16} color="#0ea5e9" /> 웹 크롤러</div>
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>타겟 URL</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.url || ''}
            onChange={(e) => data.onChange(id, 'url', e.target.value)}
            placeholder="https://example.com"
            style={crawlerFieldStyle}
          />
          <label style={{ marginTop: '0.5rem' }}>가져올 내용</label>
          <select
            className="nodrag"
            value={data.output || 'text'}
            onChange={(e) => data.onChange(id, 'output', e.target.value)}
            style={crawlerFieldStyle}
          >
            <option value="text">본문 글 (제목·발행일·본문)</option>
            <option value="structured">전체 정보 (JSON)</option>
            <option value="links">링크 목록만 (JSON)</option>
          </select>
          <label style={{ marginTop: '0.5rem' }}>본문 최대 글자 수</label>
          <input
            type="number"
            className="nodrag"
            min={200}
            max={50000}
            step={500}
            defaultValue={data.maxChars ?? 5000}
            onChange={(e) => data.onChange(id, 'maxChars', e.target.value)}
            style={crawlerFieldStyle}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '0.6rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              className="nodrag"
              checked={data.respectRobots !== false}
              onChange={(e) => data.onChange(id, 'respectRobots', e.target.checked)}
            />
            robots.txt 규칙 지키기
          </label>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '0.4rem', lineHeight: 1.5 }}>
            사이트에 부담을 주지 않도록 같은 사이트에는 하루 요청 수 제한이 걸립니다.
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const EmailNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} email ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" style={{ top: '35%' }} />
      <Handle type="target" position={Position.Left} id="attachments" title="첨부"
              style={{ top: '65%', background: '#f59e0b' }} />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-email" size={16} color="#f43f5e" /> 이메일 발송</div>
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <DefinitionFields id={id} data={data} nodeType="emailNode" />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const KakaoNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} kakao ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-kakao-alimtalk" size={16} color="#facc15" /> 카카오톡 발송</div>
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>* 이전 노드의 결과값이 카카오톡 메시지로 전송됩니다.</p>
          <ApiKeyInput id={id} data={data} provider="kakao_token" fieldKey="accessToken" placeholder="Access Token" />

          <label>수신자 (옵션)</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.receiver || ''}
            onChange={(e) => data.onChange(id, 'receiver', e.target.value)}
            placeholder="나에게 보내기(비워둠) 또는 수신자 uuid"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
          />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const DelayNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} delay ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '180px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-delay" size={16} color="#3b82f6" /> 대기</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <DefinitionFields id={id} data={data} nodeType="delayNode" />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const JsonParserNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} json-parser ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-json-parser" size={16} color="#eab308" /> JSON Parser</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <DefinitionFields id={id} data={data} nodeType="jsonParserNode" />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const MergeNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} merge ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '200px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" style={{ height: '30px', width: isExpanded ? '8px' : undefined, borderRadius: '4px', background: '#ec4899' }} />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-merge" size={16} color="#ec4899" /> 병합</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>병합 방식</label>
          <select
            className="nodrag"
            defaultValue={data.mergeStrategy || 'join_newline'}
            onChange={(e) => data.onChange(id, 'mergeStrategy', e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginTop: '0.5rem' }}
          >
            <option value="join_newline">줄바꿈으로 합치기</option>
            <option value="join_comma">쉼표로 합치기</option>
            <option value="array">JSON 배열로 만들기</option>
          </select>
          <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', color: 'var(--text-muted)' }}>여러 노드를 왼쪽 핸들에 연결하세요.</p>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const HttpRequestNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} http-request ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name={HTTP_DISPLAY.icon} size={16} color={HTTP_DISPLAY.color} /> {HTTP_DISPLAY.label}</div>
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <DefinitionFields id={id} data={data} nodeType="httpRequestNode" />
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const DatabaseNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const features = useFeatures();
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };
  // schema 탐색에서 테이블/컬럼을 눌렀을 때 — 쿼리가 비어 있으면 통째로, 아니면 끝에 덧붙인다.
  const insertSql = (text, mode) => {
    if (!data.onChange) return;
    const current = String(data.query || '');
    if (mode === 'query' && !current.trim()) {
      data.onChange(id, 'query', text);
      return;
    }
    data.onChange(id, 'query', current ? `${current.replace(/\s+$/, '')} ${text}` : text);
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} database ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '250px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-database" size={16} color="#059669" /> 데이터베이스</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body" style={{ minWidth: '320px' }}>
          {/* 접속 문자열은 그래프·수정 이력·로그에 그대로 남는 값이라 노드에 직접 저장하지
              않는다(P0). API 센터의 'Database' 자격증명 reference 만 실행이 허용되고, v2(ADR-0017)에서는
              여러 자격증명 중 하나를 고르고 연결 테스트·schema 탐색·파라미터·Test step 을 여기서 한다. */}
          {features?.database_query_v2 === false ? (
            (data.connectionString || '') === '{{API_CENTER:database}}' ? (
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '0.4rem 0.5rem', marginBottom: '0.5rem', lineHeight: 1.5 }}>
                API 센터의 <b>Database</b> 자격증명을 사용합니다. 접속 문자열은 API 센터에서 등록·변경하세요.
              </div>
            ) : (
              <div style={{ fontSize: '0.72rem', border: '1px solid #f59e0b', borderRadius: '4px', padding: '0.4rem 0.5rem', marginBottom: '0.5rem', lineHeight: 1.5 }}>
                {data.connectionString
                  ? '보안을 위해 노드에 직접 입력한 접속 문자열은 더 이상 실행되지 않습니다.'
                  : '접속 문자열이 설정되지 않았습니다.'}
                <button
                  className="nodrag"
                  onClick={() => data.onChange(id, 'connectionString', '{{API_CENTER:database}}')}
                  style={{ display: 'block', marginTop: '4px', padding: '3px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--btn-active-bg)', color: 'var(--text-color)', cursor: 'pointer', fontSize: '0.72rem' }}
                >
                  API 센터 자격증명 사용
                </button>
              </div>
            )
          ) : (
            <DatabaseConnectionPanel id={id} data={data} onInsertSql={insertSql} />
          )}
          <DefinitionFields id={id} data={data} nodeType="databaseNode" />
          {features?.database_query_v2 !== false && <DatabaseQueryToolsPanel id={id} data={data} />}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const HumanApprovalNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} human-approval ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-human-approval" size={16} color="#f43f5e" /> 사용자 승인</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <DefinitionFields id={id} data={data} nodeType="humanApprovalNode" />
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', margin: '4px 0 8px', lineHeight: 1.5 }}>
            이 노드에 도달하면 실행이 <b>대기</b>로 멈추고 알림이 갑니다(사이트 알림은 항상,
            위 채널은 선택). 직전 노드의 결과(견본)를 확인하고 승인하면 그 지점부터 이어서
            실행됩니다. 자동으로 승인되지 않습니다.
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#10b981', marginBottom: '4px' }}>
            <span>승인 시</span><span>→</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#ef4444' }}>
            <span>거절 시</span><span>→</span>
          </div>
        </div>
      )}
      {/* 승인/거절 분기 핸들 — 백엔드는 sourceHandle 'approved'/'rejected'를 예전부터 지원했지만
          UI에 핸들이 없어 에디터에서 이 분기를 만들 수 없었다(P0). 기존 그래프의 'out' 연결
          (승인 시 진행, 거절 시 중단)은 그대로 동작하도록 핸들을 유지한다. */}
      <Handle type="source" position={Position.Right} id="approved" style={{ top: '30%', background: '#10b981' }} />
      <Handle type="source" position={Position.Right} id="out" style={{ top: '50%', background: '#94a3b8' }} />
      <Handle type="source" position={Position.Right} id="rejected" style={{ top: '70%', background: '#ef4444' }} />

    </div>
  );
};

// 캔버스 주석(스티키 메모). 실행 그래프의 일부가 아니다 — 핸들이 없고, 백엔드 컴파일에서
// 제외되며(graph.py), 고아 노드 검증도 건너뛴다. 큰 그래프에 설명을 남기는 용도(Slice 5).
export const MemoNode = ({ id, data, selected, width, height }) => {
  const [isColorMenuOpen, setIsColorMenuOpen] = useState(false);
  const [contentRevision, setContentRevision] = useState(0);
  const memoRef = useRef(null);
  const editorRef = useRef(null);
  const isComposingRef = useRef(false);
  const isManuallyResizingRef = useRef(false);
  const lastContentFingerprintRef = useRef(null);
  const resizeStartRef = useRef(null);
  const colorTheme = getMemoColorTheme(data.memoColor);
  const fontSize = getMemoFontSize(data.memoFontSize);
  const memoManualHeight = data.memoSize?.height;
  const onMemoAutoResize = data.onMemoAutoResize;
  const onMemoChange = data.onChange;
  const renderedWidth = Math.max(220, Number(width) || Number(data.memoSize?.width) || MEMO_DEFAULT_WIDTH);
  const renderedHeight = Math.max(MEMO_MIN_NODE_HEIGHT, Number(height) || Number(data.memoSize?.height) || MEMO_MIN_NODE_HEIGHT);

  // contentEditable DOM은 React가 매 타이핑마다 다시 그리지 않는다. 이렇게 해야 한글 IME 조합과
  // 커서 위치가 유지된다. Undo/Redo·불러오기처럼 외부 데이터가 실제로 달라졌을 때만 동기화한다.
  useLayoutEffect(() => {
    const normalized = normalizeMemoContent(data.memoContent, data.text || '');
    const fingerprint = getMemoContentFingerprint(normalized);
    if (fingerprint === lastContentFingerprintRef.current) return;
    renderMemoContentToElement(editorRef.current, normalized);
    lastContentFingerprintRef.current = fingerprint;
    setContentRevision((revision) => revision + 1);
  }, [data.memoContent, data.text]);

  const measureMemoHeight = useCallback((manualHeightOverride) => {
    // React Flow가 포인터 이동마다 width/height를 쓰는 동안 자동 높이까지 쓰면 두 치수 변경이
    // 같은 프레임에서 서로를 다시 측정한다. 수동 resize가 끝난 뒤 한 번만 보정한다.
    if (isManuallyResizingRef.current) return;
    const editor = editorRef.current;
    if (!editor) return;
    const contentHeight = Math.max(editor.scrollHeight, 72);
    const naturalHeight = getMemoRequiredHeight({
      contentTop: editor.offsetTop,
      contentHeight,
      bottomPadding: 12,
    });
    const storedManualHeight = Number(memoManualHeight) || MEMO_MIN_NODE_HEIGHT;
    const manualHeight = Number(manualHeightOverride) || storedManualHeight;
    onMemoAutoResize?.(id, Math.max(naturalHeight, manualHeight));
  }, [id, memoManualHeight, onMemoAutoResize]);

  // 내용이 늘면 메모도 늘고, 내용이 줄면 마지막으로 사용자가 지정한 최소 높이까지 되돌아간다.
  // 부모(React Flow) state 변경은 layout effect 안에서 동기 실행하지 않고 다음 frame으로 넘긴다.
  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => measureMemoHeight());
    return () => window.cancelAnimationFrame(frameId);
  }, [contentRevision, fontSize, measureMemoHeight, width]);

  useEffect(() => {
    if (!isColorMenuOpen) return undefined;
    const closeOnOutsidePointer = (event) => {
      if (!memoRef.current?.contains(event.target)) setIsColorMenuOpen(false);
    };
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setIsColorMenuOpen(false);
    };
    document.addEventListener('pointerdown', closeOnOutsidePointer);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isColorMenuOpen]);

  const commitEditorContent = useCallback(() => {
    const nextContent = readMemoContentFromElement(editorRef.current);
    const fingerprint = getMemoContentFingerprint(nextContent);
    lastContentFingerprintRef.current = fingerprint;
    setContentRevision((revision) => revision + 1);
    onMemoChange?.(id, 'memoContent', nextContent);
    // 검색·실행 제외 처리와 이전 버전 호환을 위해 plain text도 함께 유지한다.
    onMemoChange?.(id, 'text', memoContentToPlainText(nextContent));
  }, [id, onMemoChange]);

  const applyFormat = (format) => {
    const changed = format === 'clear'
      ? clearMemoInlineFormat(editorRef.current)
      : applyMemoInlineFormat(editorRef.current, format);
    if (changed) commitEditorContent();
  };

  const handlePlainTextInsertion = (text) => {
    if (insertMemoPlainTextAtSelection(editorRef.current, text)) commitEditorContent();
  };

  const selectColor = (colorId) => {
    data.onChange?.(id, 'memoColor', colorId);
    setIsColorMenuOpen(false);
  };

  return (
    <>
      <NodeResizer
        isVisible={selected}
        minWidth={220}
        minHeight={MEMO_MIN_NODE_HEIGHT}
        maxWidth={720}
        color={colorTheme.accent}
        handleStyle={{ width: 9, height: 9, borderRadius: 3 }}
        onResizeStart={(_event, params) => {
          resizeStartRef.current = {
            width: params.width,
            height: params.height,
            manualHeight: Number(data.memoSize?.height) || MEMO_MIN_NODE_HEIGHT,
          };
        }}
        onResize={() => {
          isManuallyResizingRef.current = true;
        }}
        onResizeEnd={(_event, params) => {
          const start = resizeStartRef.current;
          const manuallyChangedHeight = !start || Math.abs(params.height - start.height) > 1;
          const nextManualHeight = manuallyChangedHeight
            ? Math.round(params.height)
            : start.manualHeight;
          data.onChange?.(id, 'memoSize', {
            width: Math.round(params.width),
            height: Math.max(MEMO_MIN_NODE_HEIGHT, nextManualHeight),
          });
          resizeStartRef.current = null;
          window.requestAnimationFrame(() => {
            isManuallyResizingRef.current = false;
            measureMemoHeight(nextManualHeight);
          });
        }}
      />
      <div
        ref={memoRef}
        className="memo-node"
        style={{
          // auto/100% 사이를 오가면 React Flow의 ResizeObserver가 같은 frame에서 다시 측정한다.
          // 첫 render부터 flow 좌표의 고정 px 치수를 사용해 observer 입력을 안정시킨다.
          width: `${renderedWidth}px`, height: `${renderedHeight}px`, minWidth: '220px', minHeight: `${MEMO_MIN_NODE_HEIGHT}px`,
          padding: '10px 12px 12px', boxSizing: 'border-box', position: 'relative', overflow: 'visible',
          background: colorTheme.background, border: `1px dashed ${colorTheme.border}`,
          borderRadius: '10px', boxShadow: '0 2px 10px rgba(0,0,0,0.12)', transition: 'background 140ms ease, border-color 140ms ease',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
          <span style={{ fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.06em', color: colorTheme.accent }}>MEMO</span>
          <div className="nodrag" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <button
              type="button"
              className="nodrag"
              onClick={(event) => {
                event.stopPropagation();
                setIsColorMenuOpen((isOpen) => !isOpen);
              }}
              style={{
                width: '24px', height: '24px', display: 'grid', placeItems: 'center', padding: 0,
                background: 'transparent', border: 'none', borderRadius: '5px', cursor: 'pointer',
              }}
              aria-label={`메모 색상 변경, 현재 ${colorTheme.label}`}
              aria-expanded={isColorMenuOpen}
              title="메모 색상 변경"
            >
              <span style={{ width: '13px', height: '13px', borderRadius: '50%', background: colorTheme.swatch, boxShadow: '0 0 0 2px rgba(255,255,255,0.16)' }} />
            </button>
            <button
              type="button"
              className="nodrag"
              onClick={(event) => { event.stopPropagation(); data.onDelete?.(id); }}
              style={{ width: '24px', height: '24px', padding: 0, background: 'none', border: 'none', color: colorTheme.accent, cursor: 'pointer', fontSize: '0.8rem', lineHeight: 1, borderRadius: '5px' }}
              aria-label="메모 삭제"
            >✕</button>
          </div>
        </div>
        <div className="memo-format-toolbar nodrag nopan" role="toolbar" aria-label="메모 텍스트 서식">
          <label className="memo-font-size-control" title="전체 글자 크기">
            <span className="sr-only">메모 글자 크기</span>
            <select
              value={fontSize}
              onChange={(event) => data.onChange?.(id, 'memoFontSize', Number(event.target.value))}
              aria-label="메모 글자 크기"
            >
              {MEMO_FONT_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}px</option>)}
            </select>
          </label>
          <span className="memo-format-divider" aria-hidden="true" />
          <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => applyFormat('bold')} aria-label="선택한 글자 굵게" title="선택 영역 굵게"><strong>B</strong></button>
          <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => applyFormat('highlight')} aria-label="선택한 글자 강조" title="선택 영역 형광펜"><span className="memo-highlight-glyph">H</span></button>
          <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => applyFormat('clear')} aria-label="선택한 글자 서식 지우기" title="선택 영역 서식 지우기">Tx</button>
        </div>
        {isColorMenuOpen && (
          <div
            className="nodrag nopan"
            role="group"
            aria-label="메모 색상"
            onPointerDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.stopPropagation();
                setIsColorMenuOpen(false);
              }
            }}
            style={{
              position: 'absolute', zIndex: 30, top: '38px', right: '10px', display: 'flex', gap: '6px',
              padding: '8px', borderRadius: '9px', background: 'var(--card-bg)', border: '1px solid var(--border-color)',
              boxShadow: '0 10px 28px rgba(0,0,0,0.28)',
            }}
          >
            {MEMO_COLOR_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                className="nodrag"
                onClick={(event) => { event.stopPropagation(); selectColor(option.id); }}
                aria-label={option.label}
                aria-pressed={option.id === colorTheme.id}
                title={option.label}
                style={{
                  width: '22px', height: '22px', padding: 0, borderRadius: '50%', cursor: 'pointer',
                  background: option.swatch,
                  border: option.id === colorTheme.id ? '2px solid var(--text-color)' : '2px solid transparent',
                  boxShadow: option.id === colorTheme.id ? `0 0 0 2px ${option.background}` : 'none',
                }}
              />
            ))}
          </div>
        )}
        <div
          ref={editorRef}
          className="memo-rich-editor nodrag nopan"
          contentEditable
          suppressContentEditableWarning
          role="textbox"
          aria-label="메모 내용"
          aria-multiline="true"
          data-placeholder="메모를 입력하세요..."
          onCompositionStart={() => { isComposingRef.current = true; }}
          onCompositionEnd={() => {
            isComposingRef.current = false;
            commitEditorContent();
          }}
          onInput={() => {
            if (isComposingRef.current) {
              setContentRevision((revision) => revision + 1);
            } else {
              commitEditorContent();
            }
          }}
          onBlur={() => {
            if (!isComposingRef.current) commitEditorContent();
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.isComposing) {
              event.preventDefault();
              handlePlainTextInsertion('\n');
            }
          }}
          onPaste={(event) => {
            // 워크플로우 조각 붙여넣기는 EditorPage의 capture handler가 먼저 처리한다.
            if (event.defaultPrevented) return;
            event.preventDefault();
            handlePlainTextInsertion(event.clipboardData?.getData('text/plain') || '');
          }}
          style={{
            minHeight: '72px', background: 'transparent', color: 'var(--text-color)',
            fontSize: `${fontSize}px`, lineHeight: 1.55, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere',
          }}
        />
      </div>
    </>
  );
};

import { NodeRegistry } from './nodeRegistry';
import { Settings } from 'lucide-react';

export const DynamicNode = ({ id, data, type }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const meta = NodeRegistry[type] || {};
  // NodeDefinition으로 이전한 노드(slackNode, posterGeneratorNode 등)는 정의가 필드의
  // 정본이다 — 레지스트리 meta는 헤더(라벨·아이콘·색)만 공급한다.
  const hasDefinition = Boolean(getNodeDefinition(type));
  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ borderLeft: `4px solid ${meta.color || '#3b82f6'}` }}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {meta.icon ? <Icon name={meta.icon} size={16} color={meta.color || '#3b82f6'} /> : <Settings size={16} color={meta.color || '#3b82f6'} />}
          {meta.label || 'Task'}
        </div>
        <NodeResultBadge id={id} data={data} />
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete && data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          {hasDefinition && <DefinitionFields id={id} data={data} nodeType={type} />}
          {!hasDefinition && meta.fields?.map(f => (
            <div key={f.name}>
              <label>{f.label}</label>
              {f.type === 'textarea' ? (
                <textarea
                  className="nodrag"
                  defaultValue={data[f.name] || ''}
                  onChange={(e) => data.onChange && data.onChange(id, f.name, e.target.value)}
                  placeholder={f.placeholder}
                />
              ) : f.type === 'select' ? (
                <select
                  className="nodrag"
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-color)', boxSizing: 'border-box' }}
                  defaultValue={data[f.name] || f.options?.[0]?.value || ''}
                  onChange={(e) => data.onChange && data.onChange(id, f.name, e.target.value)}
                >
                  {f.options?.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type={f.type}
                  className="nodrag"
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border-color)', background: 'var(--bg-color)', color: 'var(--text-color)', boxSizing: 'border-box' }}
                  defaultValue={data[f.name] ?? ''}
                  onChange={(e) => data.onChange && data.onChange(id, f.name, f.type === 'number' ? Number(e.target.value) : e.target.value)}
                  placeholder={f.placeholder}
                />
              )}
            </div>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

const MULTI_AGENT_MODE_META = {
  supervisor: {
    label: '감독자 위임',
    shortLabel: 'SUPERVISOR',
    description: '감독 에이전트가 작업을 분석하고 적합한 전문가에게 위임합니다.',
  },
  group_chat: {
    label: '그룹 토론',
    shortLabel: 'GROUP CHAT',
    description: '여러 에이전트가 정해진 라운드 동안 의견을 교환해 결론을 만듭니다.',
  },
  tool_agent: {
    label: '도구 실행',
    shortLabel: 'TOOL AGENT',
    description: '에이전트가 연결된 도구를 선택하고 필요한 작업을 순서대로 수행합니다.',
  },
};

export const MultiAgentNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const mode = data.mode || 'supervisor';
  const modeMeta = MULTI_AGENT_MODE_META[mode] || MULTI_AGENT_MODE_META.supervisor;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} multi-agent-node ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle className="multi-agent-tools-handle" type="target" position={Position.Top} id="tools" />
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" onClick={toggleExpand}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <div className="special-node-title multi-agent-title">
          <span><Icon name="node-multi-agent" size={19} /></span>
          <div>
            <strong>{data.label || '멀티 에이전트'}</strong>
            <small>{modeMeta.shortLabel} / ORCHESTRATION</small>
          </div>
        </div>
        <span className="multi-agent-tools-label">TOOLS IN <i>↑</i></span>
        <NodeResultBadge id={id} data={data} />
        <button className="btn-delete" onClick={(event) => { event.stopPropagation(); data.onDelete?.(id); }}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div className="multi-agent-network" aria-hidden="true">
            <div className="multi-agent-orbit"><i /><i /><i /><span><Icon name="node-multi-agent" size={20} /></span></div>
            <div><small>ACTIVE STRATEGY</small><strong>{modeMeta.label}</strong><p>{modeMeta.description}</p></div>
          </div>

          <div className="special-node-field">
            <label htmlFor={`multi-agent-mode-${id}`}>에이전트 작동 방식</label>
            <select
              id={`multi-agent-mode-${id}`}
              className="nodrag"
              value={mode}
              onChange={(event) => data.onChange?.(id, 'mode', event.target.value)}
            >
              <option value="supervisor">감독자 위임</option>
              <option value="group_chat">그룹 토론</option>
              <option value="tool_agent">도구 실행 에이전트</option>
            </select>
          </div>

          {mode === 'supervisor' && (
            <div className="special-node-field">
              <label>감독자 지침</label>
              <DraggableTextarea id={id} fieldKey="supervisorPrompt" value={data.supervisorPrompt} onChange={data.onChange} placeholder="System prompt for supervisor..." />
            </div>
          )}

          {mode === 'group_chat' && (
            <div className="special-node-field multi-agent-rounds">
              <label htmlFor={`multi-agent-rounds-${id}`}>최대 토론 라운드</label>
              <input
                id={`multi-agent-rounds-${id}`}
                type="number"
                className="nodrag"
                value={data.maxRounds ?? 3}
                onChange={(event) => data.onChange?.(id, 'maxRounds', Number(event.target.value))}
                min="1"
                max="20"
              />
              <span>ROUNDS</span>
            </div>
          )}

          {mode === 'tool_agent' && (
            <div className="special-node-field">
              <label>에이전트 지침</label>
              <DraggableTextarea id={id} fieldKey="agentPrompt" value={data.agentPrompt} onChange={data.onChange} placeholder="System prompt for tool agent..." />
            </div>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

const SCHEDULE_WEEKDAY_LABELS = ['일', '월', '화', '수', '목', '금', '토'];

// cron 표현식("0 7 * * *" 같은)을 사람이 이해하기 쉬운 매일/매주/매월 선택지로 최대한 되짚어본다.
// 이 세 패턴에 안 맞는(초 단위, 범위/목록 등 복잡한) 표현식이면 '직접 입력' 모드로 빠져서 원본을 그대로 보여준다.
function parseScheduleCron(expr) {
  if (!expr) return { mode: 'daily', hour: 7, minute: 0, weekday: 1, day: 1 };
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return { mode: 'custom', hour: 7, minute: 0, weekday: 1, day: 1 };
  const [min, hour, dom, mon, dow] = parts;
  const isNum = (v) => /^\d+$/.test(v);
  if (isNum(min) && isNum(hour)) {
    if (dom === '*' && mon === '*' && dow === '*') {
      return { mode: 'daily', hour: Number(hour), minute: Number(min), weekday: 1, day: 1 };
    }
    if (dom === '*' && mon === '*' && isNum(dow)) {
      return { mode: 'weekly', hour: Number(hour), minute: Number(min), weekday: Number(dow), day: 1 };
    }
    if (mon === '*' && dow === '*' && isNum(dom)) {
      return { mode: 'monthly', hour: Number(hour), minute: Number(min), weekday: 1, day: Number(dom) };
    }
  }
  return { mode: 'custom', hour: 7, minute: 0, weekday: 1, day: 1 };
}

function buildScheduleCron(mode, hour, minute, weekday, day) {
  if (mode === 'weekly') return `${minute} ${hour} * * ${weekday}`;
  if (mode === 'monthly') return `${minute} ${hour} ${day} * *`;
  return `${minute} ${hour} * * *`; // daily
}

export const ScheduleNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  const parsed = parseScheduleCron(data.cronExpression);
  const [mode, setMode] = useState(parsed.mode);

  const applyChange = (nextMode, overrides = {}) => {
    setMode(nextMode);
    if (nextMode === 'custom') return; // 직접 입력 모드는 아래 텍스트 필드가 그대로 처리
    const hour = overrides.hour ?? parsed.hour;
    const minute = overrides.minute ?? parsed.minute;
    const weekday = overrides.weekday ?? parsed.weekday;
    const day = overrides.day ?? parsed.day;
    data.onChange(id, 'cronExpression', buildScheduleCron(nextMode, hour, minute, weekday, day));
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} schedule ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '240px' : undefined }}>
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-schedule" size={16} color="#8b5cf6" /> 스케줄 시작</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <div className="input-group">
            <label>반복 주기</label>
            <select className="nodrag" value={mode} onChange={(e) => applyChange(e.target.value)}>
              <option value="daily">매일</option>
              <option value="weekly">매주</option>
              <option value="monthly">매월</option>
              <option value="custom">직접 입력 (cron)</option>
            </select>
          </div>

          {mode === 'weekly' && (
            <div className="input-group">
              <label>요일</label>
              <select className="nodrag" value={parsed.weekday} onChange={(e) => applyChange('weekly', { weekday: Number(e.target.value) })}>
                {SCHEDULE_WEEKDAY_LABELS.map((label, idx) => (
                  <option key={idx} value={idx}>{label}요일</option>
                ))}
              </select>
            </div>
          )}

          {mode === 'monthly' && (
            <div className="input-group">
              <label>날짜</label>
              <select className="nodrag" value={parsed.day} onChange={(e) => applyChange('monthly', { day: Number(e.target.value) })}>
                {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>{d}일</option>
                ))}
              </select>
            </div>
          )}

          {mode !== 'custom' ? (
            <div className="input-group">
              <label>시각</label>
              <input
                type="time"
                className="nodrag"
                value={`${String(parsed.hour).padStart(2, '0')}:${String(parsed.minute).padStart(2, '0')}`}
                onChange={(e) => {
                  const [h, m] = e.target.value.split(':').map(Number);
                  applyChange(mode, { hour: h, minute: m });
                }}
              />
            </div>
          ) : (
            <div className="input-group">
              <label>Cron 표현식</label>
              <input
                type="text"
                className="nodrag"
                value={data.cronExpression || ''}
                onChange={(e) => data.onChange(id, 'cronExpression', e.target.value)}
                placeholder="0 7 * * *"
              />
              <small style={{ display: 'block', marginTop: '4px', color: 'var(--text-muted)' }}>분 시 일 월 요일 순서 (예: 0 7 * * * → 매일 오전 7시)</small>
            </div>
          )}

          {data.cronExpression && (
            <small style={{ display: 'block', marginTop: '8px', color: 'var(--text-muted)' }}>
              현재 설정: {data.cronExpression}
            </small>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

// 정의 기반 노드다(ADR-0005). 입력 포트·필드·문구는 node_definitions/discordNode.json 이 정본이라
// 여기서는 껍데기만 그린다 — 예전에는 필드 세 개를 손으로 배치해서, 정의 파일과 화면이 갈라졌다.
const DISCORD_DISPLAY = getNodeDisplay('discordNode');

export const DiscordNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} discord ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <ConnectorInputHandles nodeType="discordNode" />
      {/* 나가는 핸들이 없으면 이 노드 **뒤로 잇는 선이 아예 그려지지 않는다** —
          데이터에 엣지가 있어도 화면에서는 끊긴 것처럼 보인다(실제로 겪음). */}
      <Handle type="source" position={Position.Right} id="out" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name={DISCORD_DISPLAY.icon} size={16} color={DISCORD_DISPLAY.color} /> {DISCORD_DISPLAY.label}</div>
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <DefinitionFields id={id} data={data} nodeType="discordNode" />
        </div>
      )}

    </div>
  );
};

export const DiscordTriggerNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} discord ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-discord-trigger" size={16} color="#5865F2" /> 디스코드 수신</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <ApiKeyInput id={id} data={data} provider="discord" fieldKey="botToken" placeholder="Bot Token" />
          <small style={{ display: 'block', marginTop: '4px', color: 'var(--text-muted)' }}>
            DM을 보내거나 봇을 멘션하면 그 메시지로 워크플로우가 시작됩니다. 상단의 "라이브 시작"을
            켜야 실제로 메시지를 기다립니다.
          </small>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const TelegramNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} telegram ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      {/* 나가는 핸들이 없으면 이 노드 **뒤로 잇는 선이 아예 그려지지 않는다** —
          데이터에 엣지가 있어도 화면에서는 끊긴 것처럼 보인다(실제로 겪음). */}
      <Handle type="source" position={Position.Right} id="out" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-telegram-send" size={16} color="#26A5E4" /> 텔레그램 발송</div>
        {!isExpanded && <BindingCountBadge count={bindingCount(data)} />}
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <ApiKeyInput id={id} data={data} provider="telegram" fieldKey="botToken" placeholder="Bot Token" />
          <div className="input-group">
            <label>Chat ID</label>
            <input
              type="text"
              className="nodrag"
              value={data.chatId || ''}
              onChange={(e) => data.onChange(id, 'chatId', e.target.value)}
              placeholder="예: 123456789 또는 @channel_username"
            />
          </div>
        </div>
      )}

    </div>
  );
};

export const TelegramTriggerNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} telegram ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-telegram-trigger" size={16} color="#26A5E4" /> 텔레그램 수신</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <ApiKeyInput id={id} data={data} provider="telegram" fieldKey="botToken" placeholder="Bot Token" />
          <small style={{ display: 'block', marginTop: '4px', color: 'var(--text-muted)' }}>
            봇에게 메시지를 보내면 그 메시지로 워크플로우가 시작됩니다. 상단의 "라이브 시작"을
            켜야 실제로 메시지를 기다립니다.
          </small>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />

    </div>
  );
};

export const NotionNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };
  const mode = data.mode || 'create';

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} notion ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '240px' : undefined }}>
      <Handle type="target" position={Position.Left} id="in" />
      {/* 나가는 핸들이 없으면 이 노드 **뒤로 잇는 선이 아예 그려지지 않는다** —
          데이터에 엣지가 있어도 화면에서는 끊긴 것처럼 보인다(실제로 겪음). */}
      <Handle type="source" position={Position.Right} id="out" />
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-notion" size={16} color="#9B9B9B" /> Notion</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <ApiKeyInput id={id} data={data} provider="notion" fieldKey="token" placeholder="Internal Integration Token" />
          <div className="input-group">
            <label>동작</label>
            <select
              className="nodrag"
              value={mode}
              onChange={(e) => data.onChange(id, 'mode', e.target.value)}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
            >
              <option value="create">페이지 생성</option>
              <option value="query">데이터베이스 조회</option>
            </select>
          </div>
          <div className="input-group">
            <label>데이터베이스 ID</label>
            <input
              type="text"
              className="nodrag"
              value={data.databaseId || ''}
              onChange={(e) => data.onChange(id, 'databaseId', e.target.value)}
              placeholder="Notion 데이터베이스 URL에 있는 ID"
            />
          </div>
          {mode === 'create' && (
            <div className="input-group">
              <label>등록할 속성 (JSON, 선택 — 비우면 직전 노드 출력 사용)</label>
              <NodeTextField
                as="textarea"
                className="nodrag"
                id={id} fieldKey="properties" value={data.properties} onChange={data.onChange}
                placeholder='{"이름": {"title": [{"text": {"content": "..."}}]}}'
                style={{ width: '100%', minHeight: '60px', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
};


export const WebhookNode = ({ id, data }) => {
  const { isExpanded, toggleExpand } = useNodeExpand(id, data);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} webhook-node ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick} style={{ minWidth: isExpanded ? '220px' : undefined }}>
      <div className="node-header" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Icon name="node-webhook" size={16} color="#0ea5e9" /> {data.label || '웹훅 수신'}</div>
        <button className="btn-delete" onClick={() => data.onDelete(id)}>✕</button>
      </div>
      {isExpanded && (
        <div className="node-body">
          <label>Webhook URL (경로)</label>
          <input
            type="text"
            className="nodrag"
            defaultValue={data.webhookUrl || '/webhook/your-endpoint'}
            onChange={(e) => data.onChange(id, 'webhookUrl', e.target.value)}
            placeholder="/webhook/my-trigger"
            style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-color)', color: 'var(--text-color)', border: '1px solid var(--border-color)', marginBottom: '0.5rem' }}
          />
          <div style={{fontSize: '11px', color: '#666', marginTop: '4px'}}>
            이 URL로 POST 요청이 오면 플로우가 시작됩니다.
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};
