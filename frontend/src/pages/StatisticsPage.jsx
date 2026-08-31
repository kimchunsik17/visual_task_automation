import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useSearchParams } from 'react-router-dom';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Activity,
  AlertCircle,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  Coins,
  Cpu,
  FlaskConical,
  LayoutTemplate,
  PlayCircle,
  RefreshCw,
} from 'lucide-react';
import { useAuth } from '../AuthContext';
import MainSidebar from '../MainSidebar';
import './StatisticsPage.css';

const TYPE_META = {
  execution: { label: '워크플로우 실행', color: '#8b5cf6', icon: Cpu },
  agent: { label: 'AI 워크플로우 생성', color: '#3b82f6', icon: Bot },
  app_builder: { label: 'App Builder 생성', color: '#ec4899', icon: LayoutTemplate },
  evaluation: { label: '워크플로우 평가', color: '#10b981', icon: FlaskConical },
};

const RANGE_OPTIONS = [
  { value: 'hourly', label: '최근 24시간', title: '시간별' },
  { value: 'weekly', label: '최근 7일', title: '일별' },
  { value: 'monthly', label: '최근 30일', title: '일별' },
  { value: 'yearly', label: '최근 12개월', title: '월별' },
];

const isValidRange = (value) => RANGE_OPTIONS.some((option) => option.value === value);

function StatisticsPage() {
  const { user, token } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [timeRange, setTimeRange] = useState(() => {
    const requestedRange = searchParams.get('range');
    return isValidRange(requestedRange) ? requestedRange : 'weekly';
  });
  const [displayMode, setDisplayMode] = useState(() => localStorage.getItem('tokenDisplayMode') || 'tokens');
  const [projectVisibility, setProjectVisibility] = useState(() => ({
    unassigned: localStorage.getItem('statisticsIncludeUnassigned') !== 'false',
    deleted: localStorage.getItem('statisticsIncludeDeleted') !== 'false',
  }));
  const requestSequence = useRef(0);

  const currency = localStorage.getItem('costCurrency') || 'USD';
  const timezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Seoul',
    [],
  );

  useEffect(() => {
    if (!user || !token) {
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    const sequence = ++requestSequence.current;

    const fetchStats = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await axios.get('/api/statistics/v2', {
          params: { time_range: timeRange, timezone },
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (sequence === requestSequence.current) setStats(response.data);
      } catch (requestError) {
        if (axios.isCancel(requestError) || requestError.code === 'ERR_CANCELED') return;
        if (sequence === requestSequence.current) {
          setError(requestError.response?.data?.detail || '통계 데이터를 불러오지 못했습니다.');
          setStats(null);
        }
      } finally {
        if (sequence === requestSequence.current) setLoading(false);
      }
    };

    fetchStats();
    return () => controller.abort();
  }, [refreshKey, timeRange, timezone, token, user]);

  const setRange = (nextRange) => {
    setTimeRange(nextRange);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('range', nextRange);
    setSearchParams(nextParams, { replace: true });
  };

  const setUsageDisplayMode = (mode) => {
    localStorage.setItem('tokenDisplayMode', mode);
    setDisplayMode(mode);
  };

  const setProjectCategoryVisibility = (category, included) => {
    const storageKey = category === 'unassigned'
      ? 'statisticsIncludeUnassigned'
      : 'statisticsIncludeDeleted';
    localStorage.setItem(storageKey, String(included));
    setProjectVisibility((current) => ({ ...current, [category]: included }));
  };

  const formatUsage = (tokens, options = {}) => {
    const normalized = Number(tokens || 0);
    if (displayMode === 'cost') {
      const usdCost = (normalized / 1_000_000) * 2.5;
      if (currency === 'KRW') {
        const krwRate = Number(localStorage.getItem('krwRate')) || 1400;
        return `₩${Math.round(usdCost * krwRate).toLocaleString()}`;
      }
      if (options.compact) return `$${usdCost.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
      return usdCost < 0.0001 ? `$${usdCost.toFixed(6)}` : `$${usdCost.toFixed(4)}`;
    }
    if (options.compact) {
      return Intl.NumberFormat('ko-KR', { notation: 'compact', maximumFractionDigits: 1 }).format(normalized);
    }
    return normalized.toLocaleString();
  };

  if (!user) {
    return (
      <div className="main-page-layout">
        <MainSidebar />
        <main className="statistics-main statistics-auth-state">
          <AlertCircle size={24} />
          <h1>로그인이 필요합니다</h1>
          <p>통계를 보려면 먼저 로그인해주세요.</p>
        </main>
      </div>
    );
  }

  const rangeMeta = RANGE_OPTIONS.find((option) => option.value === timeRange) || RANGE_OPTIONS[1];
  const summary = stats?.summary || {};
  const usageByType = stats?.usage_by_type || {};
  const breakdownTotal = Object.values(usageByType).reduce((sum, value) => sum + Number(value || 0), 0);
  const hasUsage = Boolean(stats?.meta?.has_usage);
  const allProjectUsage = stats?.project_usage || [];
  const visibleProjectUsage = allProjectUsage.filter((project) => {
    if (project.project_id === null) return projectVisibility.unassigned;
    if (project.project_id === -1) return projectVisibility.deleted;
    return true;
  });
  const generatedAt = stats?.meta?.generated_at
    ? new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit' }).format(new Date(stats.meta.generated_at))
    : null;

  const changeLabel = summary.change_rate == null
    ? '이전 기간 비교 없음'
    : `${summary.change_rate > 0 ? '+' : ''}${(summary.change_rate * 100).toFixed(1)}%`;

  const kpis = [
    { label: displayMode === 'cost' ? '기간 추정 비용' : '기간 사용량', value: formatUsage(summary.period_tokens), detail: changeLabel, icon: Activity, tone: 'blue' },
    { label: '현재 잔여 토큰', value: Number(summary.remaining_tokens || 0).toLocaleString(), detail: '현재 계정 잔액', icon: Coins, tone: 'green' },
    { label: '워크플로우 실행', value: `${Number(summary.execution_count || 0).toLocaleString()}회`, detail: rangeMeta.label, icon: PlayCircle, tone: 'violet' },
    { label: '실행 성공률', value: summary.success_rate == null ? '-' : `${(summary.success_rate * 100).toFixed(1)}%`, detail: summary.success_rate == null ? '실행 기록 없음' : '워크플로우 실행 기준', icon: CheckCircle2, tone: 'teal' },
  ];

  return (
    <div className="main-page-layout statistics-layout">
      <MainSidebar />
      <main className="main-page-content statistics-main">
        <div className="statistics-content">
          <header className="statistics-page-header">
            <div className="statistics-heading">
              <div className="statistics-title-row">
                <BarChart3 size={23} aria-hidden="true" />
                <h1>사용 통계</h1>
              </div>
              <p>선택한 기간의 토큰 사용과 워크플로우 실행 상태를 확인하세요.</p>
              <div className="statistics-meta-line">
                <span>{stats?.period?.timezone || timezone}</span>
                {generatedAt && <span>마지막 갱신 {generatedAt}</span>}
                {displayMode === 'cost' && <span>평균 단가 기반 추정치</span>}
              </div>
            </div>

            <div className="statistics-toolbar">
              <div className="statistics-segmented" role="group" aria-label="사용량 표시 단위">
                <button type="button" className={displayMode === 'tokens' ? 'active' : ''} onClick={() => setUsageDisplayMode('tokens')}>토큰</button>
                <button type="button" className={displayMode === 'cost' ? 'active' : ''} onClick={() => setUsageDisplayMode('cost')}>비용</button>
              </div>
              <label className="statistics-range-field">
                <Clock3 size={16} aria-hidden="true" />
                <span className="statistics-sr-only">조회 기간</span>
                <select value={timeRange} onChange={(event) => setRange(event.target.value)}>
                  {RANGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <button
                type="button"
                className="statistics-icon-button"
                onClick={() => setRefreshKey((key) => key + 1)}
                aria-label="통계 새로고침"
                title="새로고침"
                disabled={loading}
              >
                <RefreshCw size={17} className={loading ? 'spinning' : ''} />
              </button>
            </div>
          </header>

          {loading ? (
            <StatisticsLoading />
          ) : error ? (
            <section className="statistics-state-panel" role="alert">
              <span className="statistics-state-icon error"><AlertCircle size={24} /></span>
              <h2>통계를 불러오지 못했습니다</h2>
              <p>{typeof error === 'string' ? error : '잠시 후 다시 시도해주세요.'}</p>
              <button type="button" onClick={() => setRefreshKey((key) => key + 1)}><RefreshCw size={16} /> 다시 시도</button>
            </section>
          ) : (
            <>
              <section className="statistics-kpi-grid" aria-label="기간 요약">
                {kpis.map((kpi) => {
                  const Icon = kpi.icon;
                  return (
                    <article key={kpi.label} className={`statistics-kpi statistics-kpi-${kpi.tone}`}>
                      <div className="statistics-kpi-label"><Icon size={16} /> {kpi.label}</div>
                      <strong>{kpi.value}</strong>
                      <span>{kpi.detail}</span>
                    </article>
                  );
                })}
              </section>

              {!hasUsage ? (
                <section className="statistics-state-panel statistics-empty-state">
                  <span className="statistics-state-icon"><BarChart3 size={24} /></span>
                  <h2>선택한 기간의 사용 기록이 없습니다</h2>
                  <p>다른 기간을 선택하거나 워크플로우를 실행하면 사용 추이가 표시됩니다.</p>
                </section>
              ) : (
                <>
                  <div className="statistics-analysis-grid">
                    <section className="statistics-panel statistics-trend-panel">
                      <div className="statistics-panel-header">
                        <div><h2>{rangeMeta.label} 사용 추이</h2><p>{rangeMeta.title} 사용량</p></div>
                        <div className="statistics-chart-legend" aria-label="차트 범례">
                          {Object.entries(TYPE_META).map(([key, meta]) => <span key={key}><i style={{ background: meta.color }} />{meta.label}</span>)}
                        </div>
                      </div>
                      <div className="statistics-chart" role="img" aria-label={`${rangeMeta.label} 기능별 사용량 영역 차트`}>
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={stats.chart_data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }} accessibilityLayer>
                            <defs>
                              {Object.entries(TYPE_META).map(([key, meta]) => (
                                <linearGradient key={key} id={`statistics_${key}`} x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor={meta.color} stopOpacity={0.48} />
                                  <stop offset="95%" stopColor={meta.color} stopOpacity={0.04} />
                                </linearGradient>
                              ))}
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                            <XAxis dataKey="date" stroke="var(--text-muted)" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} tickLine={false} axisLine={false} />
                            <YAxis stroke="var(--text-muted)" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} tickLine={false} axisLine={false} width={52} tickFormatter={(value) => formatUsage(value, { compact: true })} />
                            <Tooltip
                              contentStyle={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-color)' }}
                              formatter={(value, name) => [formatUsage(value), TYPE_META[name]?.label || name]}
                              labelFormatter={(label, payload) => payload?.[0]?.payload?.fullDate || label}
                              labelStyle={{ color: 'var(--text-color)', fontWeight: 600, marginBottom: '6px' }}
                            />
                            {Object.entries(TYPE_META).map(([key, meta]) => <Area key={key} type="monotone" dataKey={key} stackId="usage" stroke={meta.color} fill={`url(#statistics_${key})`} strokeWidth={2} />)}
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                      <UsageDataTable rows={stats.chart_data} formatUsage={formatUsage} />
                    </section>

                    <section className="statistics-panel statistics-breakdown-panel">
                      <div className="statistics-panel-header"><div><h2>기능별 사용량</h2><p>{rangeMeta.label} 기준</p></div></div>
                      <div className="statistics-breakdown-list">
                        {Object.entries(TYPE_META).map(([key, meta]) => {
                          const value = Number(usageByType[key] || 0);
                          const percentage = breakdownTotal ? (value / breakdownTotal) * 100 : 0;
                          const Icon = meta.icon;
                          return (
                            <div className="statistics-breakdown-row" key={key}>
                              <div className="statistics-breakdown-info">
                                <span className="statistics-type-icon" style={{ color: meta.color }}><Icon size={15} /></span>
                                <span>{meta.label}</span><strong>{formatUsage(value)}</strong>
                              </div>
                              <div className="statistics-progress-track" aria-label={`${meta.label} ${percentage.toFixed(1)}%`}><span style={{ width: `${percentage}%`, background: meta.color }} /></div>
                              <small>{percentage.toFixed(1)}%</small>
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  </div>

                  <section className="statistics-panel statistics-project-panel">
                    <div className="statistics-panel-header">
                      <div><h2>프로젝트별 사용량</h2><p>선택 기간 내 사용량이 많은 순서</p></div>
                      <div className="statistics-project-filters" role="group" aria-label="프로젝트 사용량 포함 항목">
                        <label>
                          <input
                            type="checkbox"
                            checked={projectVisibility.unassigned}
                            onChange={(event) => setProjectCategoryVisibility('unassigned', event.target.checked)}
                          />
                          <span>미지정 프로젝트 포함</span>
                        </label>
                        <label>
                          <input
                            type="checkbox"
                            checked={projectVisibility.deleted}
                            onChange={(event) => setProjectCategoryVisibility('deleted', event.target.checked)}
                          />
                          <span>삭제된 프로젝트 포함</span>
                        </label>
                      </div>
                    </div>
                    {visibleProjectUsage.length ? (
                      <div className="statistics-project-list">
                        {visibleProjectUsage.map((project) => {
                          const share = summary.period_tokens ? (project.tokens / summary.period_tokens) * 100 : 0;
                          return (
                            <div className="statistics-project-row" key={project.project_id ?? 'unassigned'}>
                              <div className="statistics-project-copy"><strong title={project.title}>{project.title}</strong><span>{share.toFixed(1)}%</span></div>
                              <div className="statistics-project-meter"><span style={{ width: `${Math.min(share, 100)}%` }} /></div>
                              <strong className="statistics-project-value">{formatUsage(project.tokens)}</strong>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="statistics-inline-empty">
                        {allProjectUsage.length ? '현재 포함 조건에 표시할 프로젝트가 없습니다.' : '프로젝트에 연결된 사용 기록이 없습니다.'}
                      </p>
                    )}
                  </section>
                </>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function StatisticsLoading() {
  return (
    <div className="statistics-loading" aria-live="polite" aria-label="통계 데이터를 불러오는 중">
      <div className="statistics-kpi-grid">{[0, 1, 2, 3].map((key) => <div key={key} className="statistics-skeleton statistics-kpi-skeleton" />)}</div>
      <div className="statistics-skeleton statistics-chart-skeleton" />
    </div>
  );
}

function UsageDataTable({ rows, formatUsage }) {
  return (
    <details className="statistics-data-details">
      <summary>데이터 표 보기</summary>
      <div className="statistics-table-scroll">
        <table>
          <thead><tr><th>기간</th>{Object.values(TYPE_META).map((meta) => <th key={meta.label}>{meta.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.fullDate}><td>{row.fullDate}</td>{Object.keys(TYPE_META).map((key) => <td key={key}>{formatUsage(row[key])}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export default StatisticsPage;
