import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import MainSidebar from '../MainSidebar';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart, BarChart as RechartsBarChart, Bar, PieChart, Pie, Cell, Legend } from 'recharts';
import { BarChart, Activity, Database, Clock, Cpu, Bot } from 'lucide-react';
import './MainPage.css';

const TYPE_COLORS = {
  execution:  '#8b5cf6',
  agent:      '#3b82f6',
  evaluation: '#10b981',
};

const TYPE_LABELS = {
  execution:  '워크플로우 실행',
  agent:      'AI 생성(챗봇)',
  evaluation: '평가',
};

function StatisticsPage() {
  const { user, token } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('weekly');
  
  const tokenDisplayMode = localStorage.getItem('tokenDisplayMode') || 'tokens';
  const costCurrency = localStorage.getItem('costCurrency') || 'USD';
  
  const formatTokenDisplay = (tokens) => {
    if (!tokens && tokens !== 0) return '-';
    if (tokenDisplayMode === 'cost') {
      const usdCost = (tokens / 1000000) * 2.5;
      const krwRate = Number(localStorage.getItem('krwRate')) || 1400;
      return costCurrency === 'KRW' ? `${Math.round(usdCost * krwRate).toLocaleString()}` : `$${usdCost.toFixed(4)}`;
    }
    return tokens.toLocaleString();
  };

  useEffect(() => {
    if (user && token) {
      fetchStats();
    } else {
      setLoading(false);
    }
  }, [user, token, timeRange]);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`/api/statistics?time_range=${timeRange}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setStats(res.data);
    } catch (error) {
      console.error('Failed to fetch statistics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!user) {
    return (
      <div className="main-page-layout">
        <MainSidebar />
        <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
          <div className="content-area centered" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
            <h2>로그인이 필요합니다</h2>
            <p>통계를 보려면 먼저 로그인해주세요.</p>
          </div>
        </div>
      </div>
    );
  }

  const hasData = stats && (stats.total_used > 0 || (stats.chart_data && stats.chart_data.length > 0));

  const pieData = stats?.usage_by_type
    ? Object.entries(stats.usage_by_type)
        .filter(([, v]) => v > 0)
        .map(([key, value]) => ({ name: TYPE_LABELS[key], value, color: TYPE_COLORS[key], key }))
    : [];

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="content-area" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
          <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h1 className="page-title"><BarChart className="title-icon" /> 사용 통계</h1>
              <p className="page-subtitle">워크플로우 실행 및 토큰 사용 현황을 확인하세요.</p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--card-bg)', padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <Clock size={16} color="var(--text-muted)" />
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                style={{ background: 'var(--card-bg)', border: 'none', color: 'var(--text-color)', fontSize: '0.9rem', outline: 'none', cursor: 'pointer' }}
              >
                <option value="hourly">일간 (시간별)</option>
                <option value="weekly">주간 (일별)</option>
                <option value="monthly">월간 (일별)</option>
                <option value="yearly">연간 (월별)</option>
              </select>
            </div>
          </div>

          {loading ? (
            <div className="loading-state"><p>통계 데이터를 불러오는 중...</p></div>
          ) : hasData ? (
            <>
              {/* 상단 요약 카드 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                {[
                  { label: '총 누적 사용량', value: stats.total_used, color: '#60a5fa', accent: '#3b82f6', icon: <Activity size={16} color="#3b82f6" />, sub: tokenDisplayMode==='cost'?'누적 비용':'누적 토큰', leftBorder: false },
                  { label: `잔여 ${tokenDisplayMode==='cost'?'잔액':'토큰'}`, value: stats.remaining, color: '#34d399', accent: '#10b981', icon: <Database size={16} color="#10b981" />, sub: '보유 잔여량', leftBorder: false },
                  { label: '워크플로우 실행', value: stats.usage_by_type?.execution||0, color: '#a78bfa', accent: '#8b5cf6', icon: <Cpu size={16} color="#8b5cf6" />, sub: '실행 노드 소모량', leftBorder: '#8b5cf6' },
                  { label: 'AI 생성 (챗봇)', value: stats.usage_by_type?.agent||0, color: '#60a5fa', accent: '#3b82f6', icon: <Bot size={16} color="#3b82f6" />, sub: '워크플로우 생성·수정', leftBorder: '#3b82f6' },
                  { label: '평가', value: stats.usage_by_type?.evaluation||0, color: '#34d399', accent: '#10b981', icon: <span style={{fontSize:'0.9rem'}}>🧪</span>, sub: '워크플로우 품질 평가', leftBorder: '#10b981' },
                ].map((card, i) => (
                  <div key={i} style={{ background: 'var(--card-bg)', padding: '1.25rem 1.25rem', borderRadius: '12px', border: '1px solid var(--border-color)', borderLeft: card.leftBorder ? `3px solid ${card.leftBorder}` : undefined, boxShadow: 'var(--card-shadow)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem' }}>
                      {card.icon}
                      <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>{card.label}</span>
                    </div>
                    <div style={{ fontSize: '1.6rem', fontWeight: 700, color: card.color }}>{formatTokenDisplay(card.value)}</div>
                    <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--text-muted)' }}>{card.sub}</p>
                  </div>
                ))}
              </div>

              {/* 스택 영역 차트 + 도넛 */}
              <div style={{ display: 'grid', gridTemplateColumns: pieData.length > 0 ? '1fr 310px' : '1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
                <div style={{ background: 'var(--card-bg)', padding: '2rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--card-shadow)' }}>
                  <h3 style={{ margin: '0 0 1.5rem 0', color: 'var(--text-color)' }}>
                    {timeRange==='hourly'?'최근 24시간 추이':timeRange==='monthly'?'최근 30일 추이':timeRange==='yearly'?'최근 12개월 추이':'최근 7일 추이'}
                  </h3>
                  <div style={{ width: '100%', height: '300px' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={stats.chart_data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                        <defs>
                          {Object.entries(TYPE_COLORS).map(([key, color]) => (
                            <linearGradient key={key} id={`g_${key}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor={color} stopOpacity={0.7}/>
                              <stop offset="95%" stopColor={color} stopOpacity={0}/>
                            </linearGradient>
                          ))}
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                        <XAxis dataKey="date" stroke="var(--text-muted)" tick={{fill:'var(--text-muted)'}} />
                        <YAxis stroke="var(--text-muted)" tick={{fill:'var(--text-muted)'}}
                          tickFormatter={(v) => v>=1000?`${(v/1000).toFixed(1)}k`:v}
                        />
                        <Tooltip
                          contentStyle={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-color)' }}
                          formatter={(value, name) => [formatTokenDisplay(value), {execution:'워크플로우 실행',agent:'AI 생성',evaluation:'평가'}[name]||name]}
                          labelFormatter={(label, payload) => payload?.[0]?.payload?.fullDate||label}
                          labelStyle={{ color: 'var(--text-color)', fontWeight: 'bold', marginBottom: '0.4rem' }}
                        />
                        <Legend formatter={(v) => ({execution:'워크플로우 실행',agent:'AI 생성',evaluation:'평가'}[v]||v)} />
                        <Area type="monotone" dataKey="execution" stackId="1" stroke={TYPE_COLORS.execution} fill="url(#g_execution)" strokeWidth={2} />
                        <Area type="monotone" dataKey="agent" stackId="1" stroke={TYPE_COLORS.agent} fill="url(#g_agent)" strokeWidth={2} />
                        <Area type="monotone" dataKey="evaluation" stackId="1" stroke={TYPE_COLORS.evaluation} fill="url(#g_evaluation)" strokeWidth={2} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {pieData.length > 0 && (
                  <div style={{ background: 'var(--card-bg)', padding: '2rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--card-shadow)', display:'flex', flexDirection:'column' }}>
                    <h3 style={{ margin: '0 0 0.75rem 0', color: 'var(--text-color)' }}>용도별 비율</h3>
                    <div style={{ flex: 1, display:'flex', alignItems:'center', justifyContent:'center' }}>
                      <PieChart width={210} height={210}>
                        <Pie data={pieData} cx="50%" cy="50%" innerRadius={58} outerRadius={90} paddingAngle={3} dataKey="value">
                          {pieData.map((entry) => <Cell key={entry.key} fill={entry.color} />)}
                        </Pie>
                        <Tooltip
                          contentStyle={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-color)' }}
                          formatter={(v) => [formatTokenDisplay(v)]}
                        />
                      </PieChart>
                    </div>
                    <div style={{ display:'flex', flexDirection:'column', gap:'0.5rem', marginTop:'0.5rem' }}>
                      {pieData.map(d => (
                        <div key={d.key} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', fontSize:'0.8rem' }}>
                          <div style={{ display:'flex', alignItems:'center', gap:'0.4rem' }}>
                            <div style={{ width:8, height:8, borderRadius:'50%', background:d.color }} />
                            <span style={{ color:'var(--text-muted)' }}>{d.name}</span>
                          </div>
                          <span style={{ fontWeight:600, color:'var(--text-color)' }}>
                            {formatTokenDisplay(d.value)}{' '}
                            <span style={{ color:'var(--text-muted)', fontWeight:400 }}>
                              ({stats.total_used > 0 ? Math.round(d.value/stats.total_used*100) : 0}%)
                            </span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {stats.project_usage && stats.project_usage.length > 0 && (
                <div style={{ background: 'var(--card-bg)', padding: '2rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--card-shadow)' }}>
                  <h3 style={{ margin: '0 0 1.5rem 0' }}>프로젝트별 토큰 사용량</h3>
                  <div style={{ width: '100%', height: '300px' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <RechartsBarChart data={stats.project_usage} margin={{ top: 10, right: 30, left: 0, bottom: 0 }} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" horizontal={false} />
                        <XAxis type="number" stroke="var(--text-muted)" tick={{fill:'var(--text-muted)'}} />
                        <YAxis type="category" dataKey="title" width={150} stroke="var(--text-muted)" tick={{fill:'var(--text-muted)'}} />
                        <Tooltip
                          contentStyle={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-color)' }}
                          formatter={(value) => [formatTokenDisplay(value), tokenDisplayMode==='cost'?'사용 금액':'사용 토큰']}
                        />
                        <Bar dataKey="tokens" fill="#10b981" radius={[0, 4, 4, 0]} />
                      </RechartsBarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div style={{ textAlign:'center', padding:'4rem 2rem', background:'var(--card-bg)', borderRadius:'16px', border:'1px solid var(--border-color)', marginTop:'1rem' }}>
              <div style={{ fontSize:'4rem', marginBottom:'1.5rem', lineHeight:1 }}>📊</div>
              <h3 style={{ margin:'0 0 0.75rem 0', color:'var(--text-color)', fontSize:'1.3rem', fontWeight:700 }}>아직 사용 기록이 없습니다</h3>
              <p style={{ color:'var(--text-muted)', margin:'0 0 2rem 0', fontSize:'0.95rem', lineHeight:1.6, maxWidth:'360px', marginLeft:'auto', marginRight:'auto' }}>
                워크플로우를 실행하면 이곳에 토큰 사용량과 실행 추이가 기록됩니다.
              </p>
              <div style={{ display:'flex', justifyContent:'center', gap:'1rem', flexWrap:'wrap' }}>
                <div style={{ background:'var(--btn-active-bg)', borderRadius:'10px', padding:'1rem 1.5rem', minWidth:'140px' }}>
                  <div style={{ fontSize:'1.5rem', fontWeight:700, color:'#60a5fa' }}>0</div>
                  <div style={{ color:'var(--text-muted)', fontSize:'0.8rem', marginTop:'0.25rem' }}>총 사용 토큰</div>
                </div>
                <div style={{ background:'var(--btn-active-bg)', borderRadius:'10px', padding:'1rem 1.5rem', minWidth:'140px' }}>
                  <div style={{ fontSize:'1.5rem', fontWeight:700, color:'#34d399' }}>{stats?.remaining?.toLocaleString()||'-'}</div>
                  <div style={{ color:'var(--text-muted)', fontSize:'0.8rem', marginTop:'0.25rem' }}>잔여 토큰</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default StatisticsPage;
