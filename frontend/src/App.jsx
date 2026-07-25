import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import axios from 'axios';
import MainPage from './pages/MainPage';
import EditorPage from './pages/EditorPage';
import WorkflowsPage from './pages/WorkflowsPage';
import TemplatesPage from './pages/TemplatesPage';
import SettingsPage from './pages/SettingsPage';
import AppRunnerPage from './pages/AppRunnerPage';
import BotManagerPage from './pages/BotManagerPage';
import StatisticsPage from './pages/StatisticsPage';
import ProjectRunsPage from './pages/ProjectRunsPage';
import SchedulerPage from './pages/SchedulerPage';
import WebhookManagerPage from './pages/WebhookManagerPage';
import AppViewerPage from './pages/AppViewerPage';
import ApiCenterPage from './pages/ApiCenterPage';
import PatchNotesPage from './pages/PatchNotesPage';
import CustomAlert from './CustomAlert';
import CustomConfirm from './CustomConfirm';
import RequireAuth from './RequireAuth';

function App() {
  useEffect(() => {
    const fetchExchangeRate = async () => {
      try {
        const res = await axios.get('/api/exchange-rate');
        if (res.data?.krw_rate) {
          localStorage.setItem('krwRate', res.data.krw_rate);
        }
      } catch (err) {
        console.error('Failed to fetch exchange rate:', err);
      }
    };
    fetchExchangeRate();
  }, []);

  return (
    <Router>
      <Routes>
        <Route path="/" element={<RequireAuth><MainPage /></RequireAuth>} />
        <Route path="/workflows" element={<RequireAuth><WorkflowsPage /></RequireAuth>} />
        <Route path="/templates" element={<RequireAuth><TemplatesPage /></RequireAuth>} />
        <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
        <Route path="/patch-notes" element={<RequireAuth><PatchNotesPage /></RequireAuth>} />
        <Route path="/editor/:projectId?" element={<RequireAuth><EditorPage /></RequireAuth>} />
        <Route path="/project/:projectId/runs" element={<RequireAuth><ProjectRunsPage /></RequireAuth>} />
        {/* 공유 링크 — 계정 없이도 열람/실행 가능해야 하므로 로그인 강제에서 제외 */}
        <Route path="/app/:shareToken" element={<AppRunnerPage />} />
        <Route path="/viewer/:projectId" element={<AppViewerPage />} />
        <Route path="/apicenter" element={<RequireAuth><ApiCenterPage /></RequireAuth>} />
        <Route path="/webhooks" element={<RequireAuth><WebhookManagerPage /></RequireAuth>} />
        <Route path="/bots" element={<RequireAuth><BotManagerPage /></RequireAuth>} />
        <Route path="/scheduler" element={<RequireAuth><SchedulerPage /></RequireAuth>} />
        <Route path="/statistics" element={<RequireAuth><StatisticsPage /></RequireAuth>} />
      </Routes>
      <CustomAlert />
      <CustomConfirm />
    </Router>
  );
}

export default App;

