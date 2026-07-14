import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import MainSidebar from '../MainSidebar';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart, BarChart as RechartsBarChart, Bar } from 'recharts';
import { BarChart, Activity, Database, Clock } from 'lucide-react';
import './MainPage.css';

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
      const usdCost = (tokens / 1000000) * 2.5; // 평균 $2.5 / 1M tokens
      return costCurrency === 'KRW' ? `₩${Math.round(usdCost * 1400).toLocaleString()}` : `$${usdCost.toFixed(4)}`;
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
                style={{ background: 'transparent', border: 'none', color: 'var(--text-color)', fontSize: '0.9rem', outline: 'none', cursor: 'pointer' }}
              >
                <option value="hourly">일간 (시간별)</option>
                <option value="weekly">주간 (일별)</option>
                <option value="monthly">월간 (일별)</option>
                <option value="yearly">연간 (월별)</option>
              </select>
            </div>
          </div>

          {loading ? (
            <div className="loading-state">
              <p>통계 데이터를 불러오는 중...</p>
            </div>
          ) : stats ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
                <div style={{ background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--card-shadow)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', color: 'var(--text-muted)' }}>
                    <Activity size={20} color="#3b82f6" />
                    <h3 style={{ margin: 0, fontSize: '1.1rem' }}>총 누적 사용량</h3>
                  </div>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#60a5fa' }}>
                    {formatTokenDisplay(stats.total_used)}
                  </div>
                  <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    현재까지 워크플로우를 통해 소모된 {tokenDisplayMode === 'cost' ? '비용입니다.' : '총 토큰입니다.'}
                  </p>
                </div>

                <div style={{ background: 'var(--card-bg)', padding: '1.5rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--card-shadow)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', color: 'var(--text-muted)' }}>
                    <Database size={20} color="#10b981" />
                    <h3 style={{ margin: 0, fontSize: '1.1rem' }}>잔여 {tokenDisplayMode === 'cost' ? '잔액' : '토큰'}</h3>
                  </div>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#34d399' }}>
                    {formatTokenDisplay(stats.remaining)}
                  </div>
                  <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    보유하신 {tokenDisplayMode === 'cost' ? '잔액' : '토큰'}입니다.
                  </p>
                </div>
              </div>

              <div style={{ background: 'var(--card-bg)', padding: '2rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--card-shadow)' }}>
                <h3 style={{ margin: '0 0 1.5rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {timeRange === 'hourly' ? '최근 24시간 추이' : 
                   timeRange === 'monthly' ? '최근 30일 추이' : 
                   timeRange === 'yearly' ? '최근 12개월 추이' : '최근 7일 추이'}
                </h3>
                <div style={{ width: '100%', height: '400px' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={stats.chart_data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.8}/>
                          <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                      <XAxis dataKey="date" stroke="var(--text-muted)" tick={{fill: 'var(--text-muted)'}} />
                      <YAxis 
                        stroke="var(--text-muted)" 
                        tick={{fill: 'var(--text-muted)'}} 
                        tickFormatter={(value) => {
                          if (tokenDisplayMode === 'cost') {
                            const usdCost = (value / 1000000) * 2.5;
                            return costCurrency === 'KRW' ? `₩${Math.round(usdCost * 1400).toLocaleString()}` : `$${usdCost.toFixed(2)}`;
                          }
                          return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value;
                        }} 
                      />
                      <Tooltip 
                        contentStyle={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-color)' }}
                        formatter={(value) => [formatTokenDisplay(value), tokenDisplayMode === 'cost' ? '사용 금액' : '사용 토큰']}
                        labelStyle={{ color: 'var(--text-color)', fontWeight: 'bold', marginBottom: '0.5rem' }}
                        labelFormatter={(label, payload) => {
                          if (payload && payload.length > 0) {
                            return payload[0].payload.fullDate;
                          }
                          return label;
                        }}
                      />
                      <Area type="monotone" dataKey="tokens" stroke="#8b5cf6" strokeWidth={3} fillOpacity={1} fill="url(#colorTokens)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {stats.project_usage && stats.project_usage.length > 0 && (
                <div style={{ background: 'var(--card-bg)', padding: '2rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--card-shadow)', marginTop: '2rem' }}>
                  <h3 style={{ margin: '0 0 1.5rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    프로젝트별 토큰 사용량
                  </h3>
                  <div style={{ width: '100%', height: '300px' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <RechartsBarChart data={stats.project_usage} margin={{ top: 10, right: 30, left: 0, bottom: 0 }} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" horizontal={false} />
                        <XAxis type="number" stroke="var(--text-muted)" tick={{fill: 'var(--text-muted)'}} />
                        <YAxis type="category" dataKey="title" width={150} stroke="var(--text-muted)" tick={{fill: 'var(--text-muted)'}} />
                        <Tooltip 
                          contentStyle={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-color)' }}
                          formatter={(value) => [formatTokenDisplay(value), tokenDisplayMode === 'cost' ? '사용 금액' : '사용 토큰']}
                        />
                        <Bar dataKey="tokens" fill="#10b981" radius={[0, 4, 4, 0]} />
                      </RechartsBarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">
              <p>표시할 데이터가 없습니다.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default StatisticsPage;
