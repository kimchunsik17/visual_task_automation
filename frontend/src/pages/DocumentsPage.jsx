import { useEffect, useMemo, useState } from 'react';
import SectionTabs from '../components/SectionTabs';
import { TUTORIAL_SECTION_TABS } from '../navigation';
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Boxes,
  AlertCircle,
  Command,
  ExternalLink,
  GitBranch,
  LayoutGrid,
  Search,
  Sparkles,
  Zap,
} from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import MainSidebar from '../MainSidebar';
import { Icon as NodeIcon } from '../icons';
import { EDITOR_NODE_CATALOG, NODE_CATEGORY_LABELS, getEditorNodeMeta } from '../editorNodeCatalog';
import { NodeDefinitions } from '../nodeDefinitions';
import { NodeRegistry } from '../nodeRegistry';
import { getNodeDoc } from '../nodeDocumentation';
import { bindableFields } from '../nodeBindings';
import bindableBundle from '../generated/bindableFields.json';
import { WORKFLOW_PATTERNS, getWorkflowPattern, patternNodeTypes, patternsUsingNode } from '../workflowPatterns';
import TemplateFlowPreview from '../components/TemplateFlowPreview';
import { EDITOR_COMMAND_DOCUMENTATION, EDITOR_CONVENIENCE_FEATURES } from '../editorDocumentation';
import { formatEditorShortcut } from '../editorCommands';
import './MainPage.css';
import './DocumentsPage.css';

const SECTION_ITEMS = [
  { id: 'overview', label: '에디터 시작하기', icon: Sparkles },
  { id: 'shortcuts', label: '키보드 단축키', icon: Command },
  { id: 'nodes', label: '노드 카탈로그', icon: Boxes },
  { id: 'patterns', label: '디자인 패턴', icon: GitBranch },
  { id: 'binding', label: '값 연결 (데이터 바인딩)', icon: Zap },
];

// 바인딩 가능한 노드·필드는 백엔드 node_bindings.BINDABLE_FIELDS 번들에서 파생한다 —
// 여기에 손으로 적으면 지원 필드가 늘 때 문서만 옛 목록을 들고 있게 된다.
const BINDABLE_ENTRIES = Object.entries(bindableBundle.fields || {})
  .map(([type, fields]) => ({ type, fields, meta: getEditorNodeMeta(type) }))
  .sort((a, b) => a.meta.label.localeCompare(b.meta.label, 'ko'));

const KIND_LABELS = {
  trigger: '시작 노드',
  container: '컨테이너',
  annotation: '주석',
  node: '일반 노드',
};

const FIELD_KIND_LABELS = {
  text: '텍스트',
  textarea: '여러 줄',
  select: '선택',
  number: '숫자',
  checkbox: '켜기/끄기',
  secret: '비밀값',
  password: '비밀값',
  json: 'JSON',
  repeatable: '목록',
  attachments: '첨부',
};

const normalize = (value) => String(value || '').trim().toLocaleLowerCase('ko');

// 노드의 필드 명세 — 정의(NodeDefinitions)가 정본, 없으면 레지스트리, 그것도 없으면
// 문서(extraFields). 설명 문구는 nodeDocumentation 의 fields[name] 이 얹힌다.
const getNodeFieldSpecs = (type) => {
  const doc = getNodeDoc(type);
  const definition = NodeDefinitions[type];
  if (definition?.fields?.length) {
    return definition.fields.map((field) => ({
      name: field.name,
      label: field.label || field.name,
      kind: field.kind,
      options: (field.options || []).map((option) => option.label || String(option.value)),
      defaultValue: field.default,
      required: (field.validation || []).some((rule) => rule.rule === 'required'),
      description: doc?.fields?.[field.name] || '',
    }));
  }
  const registry = NodeRegistry[type];
  if (registry?.fields?.length) {
    return registry.fields.map((field) => ({
      name: field.name,
      label: field.label || field.name,
      kind: field.type,
      options: (field.options || []).map((option) => option.label || String(option.value)),
      defaultValue: undefined,
      required: false,
      description: doc?.fields?.[field.name] || '',
    }));
  }
  return (doc?.extraFields || []).map((field) => ({
    name: field.name,
    label: field.label || field.name,
    kind: field.kind,
    options: [],
    defaultValue: undefined,
    required: false,
    description: field.description || '',
  }));
};

const formatDefault = (value) => {
  if (value === undefined || value === null || value === '') return null;
  if (typeof value === 'object') return null; // 첨부 기본값 등 — 표에 보여줄 가치가 없다
  if (typeof value === 'boolean') return value ? '켬' : '끔';
  return String(value);
};

function NodeCard({ node, onOpen }) {
  const doc = getNodeDoc(node.type);
  const fieldCount = getNodeFieldSpecs(node.type).length;
  return (
    <button type="button" className="documents-node-card" onClick={() => onOpen(node.type)}>
      <div className="documents-node-header">
        <span className="documents-node-glyph" style={{ '--node-color': node.color }}>
          {node.icon ? <NodeIcon name={node.icon} size={17} /> : <Boxes size={17} />}
        </span>
        <div><h3>{node.label}</h3><code>{node.type}</code></div>
        <span className="documents-node-kind">{KIND_LABELS[node.kind] || KIND_LABELS.node}</span>
      </div>
      <p className="documents-node-summary">{doc?.summary || '설명이 준비 중입니다.'}</p>
      <div className="documents-node-meta">
        <span>{fieldCount > 0 ? `설정 필드 ${fieldCount}개` : '별도 설정 없음'}</span>
        <span className="documents-node-open">자세히 <ArrowUpRight size={13} /></span>
      </div>
    </button>
  );
}

function NodeDetail({ nodeType, onBack, onOpen, onOpenPattern, onOpenBinding }) {
  const usedInPatterns = patternsUsingNode(nodeType);
  const meta = getEditorNodeMeta(nodeType);
  const doc = getNodeDoc(nodeType);
  const fields = getNodeFieldSpecs(nodeType);
  const related = (doc?.related || [])
    .map((type) => getEditorNodeMeta(type))
    .filter((item) => item.label !== item.type); // 카탈로그에 없는 타입은 링크하지 않는다

  return (
    <>
      <button type="button" className="documents-node-back" onClick={onBack}>
        <ArrowLeft size={15} /> 노드 카탈로그
      </button>

      <header className="documents-node-hero">
        <span className="documents-node-glyph is-large" style={{ '--node-color': meta.color }}>
          {meta.icon ? <NodeIcon name={meta.icon} size={26} /> : <Boxes size={26} />}
        </span>
        <div>
          <div className="documents-node-hero-badges">
            <span>{meta.categoryLabel}</span>
            <span>{KIND_LABELS[meta.kind] || KIND_LABELS.node}</span>
          </div>
          <h2>{meta.label}</h2>
          <code>{meta.type}</code>
        </div>
      </header>

      {doc ? (
        <>
          <p className="documents-node-lede">{doc.summary}</p>

          <section className="documents-node-section">
            <h3>동작</h3>
            {doc.details.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
          </section>

          {doc.io && (
            <section className="documents-node-section documents-node-io" aria-label="입출력">
              <div><strong>입력</strong><p>{doc.io.input}</p></div>
              <div><strong>출력</strong><p>{doc.io.output}</p></div>
            </section>
          )}

          {doc.usage?.length > 0 && (
            <section className="documents-node-section">
              <h3>이런 요청에 쓰세요</h3>
              <ul>{doc.usage.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          )}

          {fields.length > 0 && (
            <section className="documents-node-section">
              <h3>설정 필드</h3>
              <div className="documents-field-table">
                {fields.map((field) => (
                  <div key={field.name} className="documents-field-row">
                    <div className="documents-field-name">
                      <code>{field.name}</code>
                      <span>{field.label}{field.required && <em title="필수">*</em>}</span>
                    </div>
                    <div className="documents-field-kind">
                      <span>{FIELD_KIND_LABELS[field.kind] || field.kind}</span>
                      {formatDefault(field.defaultValue) && <small>기본 {formatDefault(field.defaultValue)}</small>}
                    </div>
                    <div className="documents-field-desc">
                      {field.description && <p>{field.description}</p>}
                      {field.options.length > 0 && (
                        <div className="documents-field-options">
                          {field.options.map((option) => <code key={option}>{option}</code>)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {bindableFields(nodeType).length > 0 && (
            <section className="documents-node-section documents-node-binding">
              <h3><Zap size={15} /> 값 연결할 수 있는 필드</h3>
              <p>
                아래 필드는 값을 직접 입력하는 대신 <strong>앞 노드의 출력값에 연결</strong>할 수 있습니다.
                에디터에서 필드 오른쪽 위 <Zap size={12} /> 를 누르세요 — LLM 이나 JSON 파서를 끼우지 않아도 됩니다.
              </p>
              <div className="documents-node-binding-fields">
                {bindableFields(nodeType).map((field) => <code key={field}>{field}</code>)}
              </div>
              <button type="button" className="documents-inline-link" onClick={onOpenBinding}>
                값 연결 문서 보기 <ArrowUpRight size={14} />
              </button>
            </section>
          )}

          {doc.tips?.length > 0 && (
            <section className="documents-node-section documents-node-tips">
              <h3><AlertCircle size={15} /> 주의사항</h3>
              <ul>{doc.tips.map((tip) => <li key={tip}>{tip}</li>)}</ul>
            </section>
          )}

          {related.length > 0 && (
            <section className="documents-node-section">
              <h3>관련 노드</h3>
              <div className="documents-node-related">
                {related.map((item) => (
                  <button type="button" key={item.type} onClick={() => onOpen(item.type)}>
                    <span className="documents-node-glyph" style={{ '--node-color': item.color }}>
                      {item.icon ? <NodeIcon name={item.icon} size={14} /> : <Boxes size={14} />}
                    </span>
                    {item.label}
                  </button>
                ))}
              </div>
            </section>
          )}

          {usedInPatterns.length > 0 && (
            <section className="documents-node-section">
              <h3>이 노드가 쓰이는 패턴</h3>
              <div className="documents-node-related">
                {usedInPatterns.map((pattern) => (
                  <button type="button" key={pattern.id} onClick={() => onOpenPattern(pattern.id)}>
                    <span className="documents-node-glyph" style={{ '--node-color': '#60a5fa' }}><GitBranch size={14} /></span>
                    {pattern.title}
                  </button>
                ))}
              </div>
            </section>
          )}
        </>
      ) : (
        <p className="documents-empty">이 노드의 문서가 아직 준비되지 않았습니다.</p>
      )}
    </>
  );
}

function PatternCard({ pattern, onOpen, onOpenNode }) {
  const types = patternNodeTypes(pattern);
  return (
    <button type="button" className="documents-node-card documents-pattern-card" onClick={() => onOpen(pattern.id)}>
      <div className="documents-node-header">
        <span className="documents-node-glyph" style={{ '--node-color': '#60a5fa' }}><GitBranch size={17} /></span>
        <div><h3>{pattern.title}</h3><code>{types.length}개 노드 조합</code></div>
      </div>
      <p className="documents-node-summary">{pattern.summary}</p>
      <div className="documents-pattern-chain" aria-hidden="true">
        {types.slice(0, 6).map((type) => {
          const meta = getEditorNodeMeta(type);
          return (
            <span key={type} className="documents-node-glyph" style={{ '--node-color': meta.color }} title={meta.label}>
              {meta.icon ? <NodeIcon name={meta.icon} size={13} /> : <Boxes size={13} />}
            </span>
          );
        })}
        <span className="documents-node-open">자세히 <ArrowUpRight size={13} /></span>
      </div>
    </button>
  );
}

function PatternDetail({ patternId, onBack, onOpenNode, onOpenPattern }) {
  const pattern = getWorkflowPattern(patternId);
  if (!pattern) {
    return (
      <>
        <button type="button" className="documents-node-back" onClick={onBack}><ArrowLeft size={15} /> 디자인 패턴</button>
        <p className="documents-empty">해당 패턴을 찾을 수 없습니다.</p>
      </>
    );
  }
  const types = patternNodeTypes(pattern);
  const outline = {
    nodes: pattern.graph.nodes.map((node) => ({ id: node.id, type: node.type, x: node.x, y: node.y })),
    edges: pattern.graph.edges.map((edge) => ({ source: edge.source, target: edge.target, handle: edge.handle })),
  };
  const siblings = WORKFLOW_PATTERNS.filter((item) => item.id !== pattern.id
    && patternNodeTypes(item).some((type) => types.includes(type) && !['startNode', 'outputNode', 'promptNode', 'llmNode'].includes(type)));

  return (
    <>
      <button type="button" className="documents-node-back" onClick={onBack}>
        <ArrowLeft size={15} /> 디자인 패턴
      </button>

      <header className="documents-node-hero">
        <span className="documents-node-glyph is-large" style={{ '--node-color': '#60a5fa' }}><GitBranch size={26} /></span>
        <div>
          <div className="documents-node-hero-badges"><span>디자인 패턴</span><span>{types.length}개 노드</span></div>
          <h2>{pattern.title}</h2>
          <code>{pattern.id}</code>
        </div>
      </header>

      <p className="documents-node-lede">{pattern.summary}</p>

      <section className="documents-node-section">
        <h3>구조</h3>
        <div className="documents-pattern-preview"><TemplateFlowPreview outline={outline} /></div>
      </section>

      <section className="documents-node-section">
        <h3>이런 요청에 쓰세요</h3>
        <ul>{pattern.when.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <section className="documents-node-section documents-node-tips">
        <h3><AlertCircle size={15} /> 주의사항</h3>
        <ul>{pattern.cautions.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <section className="documents-node-section">
        <h3>사용 노드</h3>
        <div className="documents-node-related">
          {types.map((type) => {
            const meta = getEditorNodeMeta(type);
            return (
              <button type="button" key={type} onClick={() => onOpenNode(type)}>
                <span className="documents-node-glyph" style={{ '--node-color': meta.color }}>
                  {meta.icon ? <NodeIcon name={meta.icon} size={14} /> : <Boxes size={14} />}
                </span>
                {meta.label}
              </button>
            );
          })}
        </div>
      </section>

      {siblings.length > 0 && (
        <section className="documents-node-section">
          <h3>관련 패턴</h3>
          <div className="documents-node-related">
            {siblings.map((item) => (
              <button type="button" key={item.id} onClick={() => onOpenPattern(item.id)}>
                <span className="documents-node-glyph" style={{ '--node-color': '#60a5fa' }}><GitBranch size={14} /></span>
                {item.title}
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="documents-callout">
        <Sparkles size={20} />
        <div>
          <strong>이 패턴은 AI 생성에도 쓰입니다</strong>
          <p>홈 화면·에디터의 AI 생성이 같은 패턴 정의를 참고해 워크플로우 골격을 잡습니다. 요청이 위 상황과 맞으면 이 구조로 생성될 확률이 높습니다.</p>
        </div>
      </div>
    </>
  );
}

export default function DocumentsPage() {
  const navigate = useNavigate();
  const { nodeType, patternId } = useParams();
  const [activeSection, setActiveSection] = useState(nodeType ? 'nodes' : patternId ? 'patterns' : 'overview');
  const [query, setQuery] = useState('');
  const normalizedQuery = normalize(query);

  // 상세 URL로 직접 들어온 경우 목차를 해당 섹션으로 맞춘다.
  useEffect(() => {
    if (nodeType) setActiveSection('nodes');
    else if (patternId) setActiveSection('patterns');
  }, [nodeType, patternId]);

  const shortcutGroups = useMemo(() => {
    const filtered = EDITOR_COMMAND_DOCUMENTATION.filter((command) => {
      const shortcutText = command.shortcuts.map((shortcut) => formatEditorShortcut(shortcut)).join(' ');
      return normalize(`${command.label} ${command.category} ${shortcutText}`).includes(normalizedQuery);
    });
    return Object.entries(filtered.reduce((groups, command) => {
      groups[command.category] = [...(groups[command.category] || []), command];
      return groups;
    }, {}));
  }, [normalizedQuery]);

  const nodeGroups = useMemo(() => {
    const filtered = EDITOR_NODE_CATALOG.filter((node) => normalize([
      node.label,
      node.type,
      node.categoryLabel,
      getNodeDoc(node.type)?.summary || '',
    ].join(' ')).includes(normalizedQuery));
    return Object.keys(NODE_CATEGORY_LABELS)
      .map((categoryId) => ({
        id: categoryId,
        label: NODE_CATEGORY_LABELS[categoryId],
        nodes: filtered.filter((node) => node.category === categoryId),
      }))
      .filter((group) => group.nodes.length > 0);
  }, [normalizedQuery]);

  const totalFiltered = nodeGroups.reduce((sum, group) => sum + group.nodes.length, 0);

  const setSection = (section) => {
    if (nodeType || patternId) navigate('/documents');
    setActiveSection(section);
    setQuery('');
  };

  // 스크롤은 window가 아니라 .main-page-content(overflow-y: auto)에서 일어난다.
  const resetScroll = () => document.querySelector('.documents-page-content')?.scrollTo(0, 0);

  const openNode = (type) => {
    navigate(`/documents/nodes/${type}`);
    resetScroll();
  };

  const openPattern = (id) => {
    navigate(`/documents/patterns/${id}`);
    resetScroll();
  };

  return (
    <div className="main-page-layout documents-page">
      <MainSidebar />
      <main className="main-page-content documents-page-content">
        <SectionTabs ariaLabel="튜토리얼 섹션" tabs={TUTORIAL_SECTION_TABS} />
        <div className="documents-container">
          <header className="documents-hero">
            <div className="documents-eyebrow"><BookOpen size={15} /> WorkFlow AI Documents</div>
            <h1>제품 문서</h1>
            <p>워크플로우를 더 빠르게 만드는 에디터 기능과 노드별 정보를 한곳에서 확인하세요.</p>
          </header>

          <div className="documents-layout">
            <aside className="documents-local-nav" aria-label="문서 목차">
              <span className="documents-nav-label">에디터 문서</span>
              {SECTION_ITEMS.map(({ id, label, icon: SectionIcon }) => (
                <button
                  key={id}
                  type="button"
                  className={activeSection === id ? 'active' : ''}
                  onClick={() => setSection(id)}
                >
                  <SectionIcon size={17} />
                  <span>{label}</span>
                </button>
              ))}
            </aside>

            <article className="documents-article">
              {activeSection === 'overview' && (
                <>
                  <div className="documents-section-heading">
                    <div>
                      <span className="documents-kicker">EDITOR GUIDE</span>
                      <h2>에디터 시작하기</h2>
                      <p>최근 추가된 빠른 편집 기능을 활용하면 캔버스 이동과 반복 작업을 줄일 수 있습니다.</p>
                    </div>
                    <button type="button" className="documents-primary-action" onClick={() => navigate('/editor')}>
                      에디터 열기 <ExternalLink size={16} />
                    </button>
                  </div>

                  <div className="documents-stats">
                    <button type="button" onClick={() => setSection('shortcuts')}>
                      <Command size={19} /><strong>{EDITOR_COMMAND_DOCUMENTATION.length}</strong><span>단축키 명령</span>
                    </button>
                    <button type="button" onClick={() => setSection('nodes')}>
                      <Boxes size={19} /><strong>{EDITOR_NODE_CATALOG.length}</strong><span>사용 가능 노드</span>
                    </button>
                    <div>
                      <LayoutGrid size={19} /><strong>{Object.keys(NODE_CATEGORY_LABELS).length}</strong><span>노드 카테고리</span>
                    </div>
                  </div>

                  <section className="documents-feature-grid" aria-label="에디터 편의 기능">
                    {EDITOR_CONVENIENCE_FEATURES.map((feature, index) => (
                      <div className="documents-feature-card" key={feature.title}>
                        <span>{String(index + 1).padStart(2, '0')}</span>
                        <h3>{feature.title}</h3>
                        <p>{feature.description}</p>
                      </div>
                    ))}
                  </section>

                  <div className="documents-callout">
                    <Command size={20} />
                    <div>
                      <strong>어디서 시작할지 모르겠다면</strong>
                      <p><kbd>{formatEditorShortcut({ mod: true, key: 'k' })}</kbd>로 명령 팔레트를 열어 사용 가능한 작업을 검색해 보세요.</p>
                    </div>
                  </div>
                </>
              )}

              {activeSection === 'shortcuts' && (
                <>
                  <div className="documents-section-heading">
                    <div>
                      <span className="documents-kicker">KEYBOARD</span>
                      <h2>키보드 단축키</h2>
                      <p>운영체제에 맞는 보조 키가 자동으로 표시됩니다. 입력창을 편집할 때는 캔버스 단축키가 실행되지 않습니다.</p>
                    </div>
                  </div>
                  <label className="documents-search">
                    <Search size={18} />
                    <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="명령 또는 단축키 검색" />
                  </label>
                  <div className="documents-shortcut-groups">
                    {shortcutGroups.map(([category, commands]) => (
                      <section key={category} className="documents-shortcut-group">
                        <h3>{category}</h3>
                        <div>
                          {commands.map((command) => (
                            <div className="documents-shortcut-row" key={command.id}>
                              <span>{command.label}</span>
                              <div>
                                {command.shortcuts.map((shortcut, index) => (
                                  <kbd key={`${command.id}-${index}`}>{formatEditorShortcut(shortcut)}</kbd>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </section>
                    ))}
                    {shortcutGroups.length === 0 && <p className="documents-empty">일치하는 단축키가 없습니다.</p>}
                  </div>
                </>
              )}

              {activeSection === 'nodes' && nodeType && (
                <NodeDetail nodeType={nodeType} onBack={() => navigate('/documents')} onOpen={openNode}
                            onOpenPattern={openPattern} onOpenBinding={() => setSection('binding')} />
              )}

              {activeSection === 'patterns' && patternId && (
                <PatternDetail patternId={patternId} onBack={() => navigate('/documents')} onOpenNode={openNode} onOpenPattern={openPattern} />
              )}

              {activeSection === 'patterns' && !patternId && (
                <>
                  <div className="documents-section-heading">
                    <div>
                      <span className="documents-kicker">DESIGN PATTERNS</span>
                      <h2>디자인 패턴</h2>
                      <p>자주 쓰는 검증된 노드 조합입니다. AI 생성도 같은 패턴 정의를 참고해 워크플로우 골격을 잡습니다.</p>
                    </div>
                    <span className="documents-result-count">{WORKFLOW_PATTERNS.length}개 패턴</span>
                  </div>
                  <div className="documents-node-grid documents-pattern-grid">
                    {WORKFLOW_PATTERNS.map((pattern) => (
                      <PatternCard key={pattern.id} pattern={pattern} onOpen={openPattern} onOpenNode={openNode} />
                    ))}
                  </div>
                </>
              )}

              {activeSection === 'binding' && (
                <>
                  <div className="documents-section-heading">
                    <div>
                      <span className="documents-kicker">DATA BINDING</span>
                      <h2>값 연결 (데이터 바인딩)</h2>
                      <p>앞 노드의 출력값을 다음 노드의 입력 필드에 직접 꽂습니다. 값을 옮기려고 LLM 노드나 JSON 파서를 끼울 필요가 없습니다.</p>
                    </div>
                    <button type="button" className="documents-primary-action" onClick={() => navigate('/editor')}>
                      에디터에서 써보기 <ExternalLink size={16} />
                    </button>
                  </div>

                  <div className="documents-callout">
                    <Zap size={20} />
                    <div>
                      <strong>왜 쓰나요</strong>
                      <p>
                        값을 옮기는 일에 LLM 을 쓰면 값이 바뀌어 나올 수 있고(환각), 실행마다 토큰이 듭니다.
                        값 연결은 실행할 때 그 노드의 결과에서 값을 그대로 꺼내므로 <strong>LLM 호출이 0회</strong>고 결과가 늘 같습니다.
                      </p>
                    </div>
                  </div>

                  <section className="documents-feature-grid" aria-label="값 연결 사용법">
                    {[
                      { title: '필드에서 ⚡ 누르기', description: '노드를 펼치고 필드 오른쪽 위의 번개 버튼을 누르면 앞에 연결된 노드들이 나옵니다. 캔버스에 선은 생기지 않습니다.' },
                      { title: '경로 고르기', description: '한 번 실행한 워크플로우라면 그 노드의 실제 결과에서 경로와 값을 미리 보고 고를 수 있습니다. 실행 전이라면 “출력 전체”만 연결됩니다.' },
                      { title: '연결된 필드는 칩으로', description: '값이 어디서 오는지 필드 자리에 그대로 보입니다. × 를 누르면 연결이 풀리고 다시 입력창이 됩니다.' },
                      { title: 'D 로 데이터 레이어', description: '연결을 한눈에 보려면 D 를 누르세요. 얇은 점선으로 모든 연결이 보이고, 필드마다 입력 포트가 열려 선을 그어 연결할 수도 있습니다.' },
                      { title: '접힌 노드는 배지', description: '접힌 노드에는 포트를 그리지 않고 연결 개수만 ⇣N 으로 알립니다. 노드가 많아도 캔버스가 포트로 뒤덮이지 않습니다.' },
                      { title: '같은 값을 여러 곳에 쓸 때', description: '변수 노드에 이름을 붙여 값을 한 번 받고, 다른 노드들은 그 변수 노드를 연결하세요. 값이 바뀌면 한 곳만 고치면 됩니다.' },
                    ].map((feature, index) => (
                      <div className="documents-feature-card" key={feature.title}>
                        <span>{String(index + 1).padStart(2, '0')}</span>
                        <h3>{feature.title}</h3>
                        <p>{feature.description}</p>
                      </div>
                    ))}
                  </section>

                  <section className="documents-node-section">
                    <h3>값 연결을 받을 수 있는 필드</h3>
                    <p className="documents-section-note">
                      아래 목록에 없는 필드에는 연결할 수 없습니다 — 실행 코드가 그 값을 만들 때 미리 굳혀 넣기 때문입니다.
                      목록에 없는 필드에 연결하면 조용히 무시되지 않고 검증에서 막힙니다.
                    </p>
                    <div className="documents-binding-table">
                      {BINDABLE_ENTRIES.map(({ type, fields, meta }) => (
                        <div className="documents-binding-row" key={type}>
                          <button type="button" className="documents-binding-node" onClick={() => openNode(type)}>
                            <span className="documents-node-glyph" style={{ '--node-color': meta.color }}>
                              {meta.icon ? <NodeIcon name={meta.icon} size={14} /> : <Boxes size={14} />}
                            </span>
                            {meta.label}
                          </button>
                          <div className="documents-binding-fields">
                            {fields.map((field) => <code key={field}>{field}</code>)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="documents-node-section documents-node-tips">
                    <h3><AlertCircle size={15} /> 주의사항</h3>
                    <ul>
                      <li>연결할 수 있는 것은 <strong>실행 순서상 앞선 노드</strong>뿐입니다. 조건 분기의 반대편 노드를 연결하면 실행 시점에 값이 없어 오류가 납니다.</li>
                      <li>경로는 짐작하지 말고 한 번 실행한 뒤 실제 값에서 고르세요. 없는 경로를 연결하면 실행이 그 자리에서 멈춥니다.</li>
                      <li>연결된 필드는 값이 비어 있어도 필수 검사를 통과합니다 — 값이 실행할 때 들어오기 때문입니다.</li>
                      <li>실행 흐름을 잇는 연결선은 그대로 필요합니다. 값 연결은 그 위에 얹히는 것이고, 실행 순서를 대신하지 않습니다.</li>
                    </ul>
                  </section>
                </>
              )}

              {activeSection === 'nodes' && !nodeType && (
                <>
                  <div className="documents-section-heading">
                    <div>
                      <span className="documents-kicker">NODE REFERENCE</span>
                      <h2>노드 카탈로그</h2>
                      <p>노드를 눌러 동작·설정 필드·주의사항이 담긴 상세 문서를 확인하세요.</p>
                    </div>
                    <span className="documents-result-count">{totalFiltered}개 노드</span>
                  </div>
                  <label className="documents-search">
                    <Search size={18} />
                    <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="노드 이름, 타입 또는 설명 검색" />
                  </label>
                  {nodeGroups.map((group) => (
                    <section key={group.id} className="documents-node-group" aria-label={group.label}>
                      <h3>{group.label} <span>{group.nodes.length}</span></h3>
                      <div className="documents-node-grid">
                        {group.nodes.map((node) => <NodeCard key={node.type} node={node} onOpen={openNode} />)}
                      </div>
                    </section>
                  ))}
                  {totalFiltered === 0 && <p className="documents-empty">조건에 맞는 노드가 없습니다.</p>}
                </>
              )}
            </article>
          </div>
        </div>
      </main>
    </div>
  );
}
