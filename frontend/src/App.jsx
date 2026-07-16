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
import CustomAlert from './CustomAlert';

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
        <Route path="/" element={<MainPage />} />
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/editor/:projectId?" element={<EditorPage />} />
        <Route path="/project/:projectId/runs" element={<ProjectRunsPage />} />
        <Route path="/app/:shareToken" element={<AppRunnerPage />} />
        <Route path="/viewer/:projectId" element={<AppViewerPage />} />
        <Route path="/apicenter" element={<ApiCenterPage />} />
        <Route path="/webhooks" element={<WebhookManagerPage />} />
        <Route path="/bots" element={<BotManagerPage />} />
        <Route path="/scheduler" element={<SchedulerPage />} />
        <Route path="/statistics" element={<StatisticsPage />} />
      </Routes>
      <CustomAlert />
    </Router>
  );
}

export default App;

