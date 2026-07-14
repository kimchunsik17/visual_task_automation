import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import MainPage from './pages/MainPage';
import EditorPage from './pages/EditorPage';
import WorkflowsPage from './pages/WorkflowsPage';
import TemplatesPage from './pages/TemplatesPage';
import SettingsPage from './pages/SettingsPage';
import AppRunnerPage from './pages/AppRunnerPage';
import BotManagerPage from './pages/BotManagerPage';
import StatisticsPage from './pages/StatisticsPage';
import ProjectRunsPage from './pages/ProjectRunsPage';

function App() {
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
        <Route path="/bots" element={<BotManagerPage />} />
        <Route path="/statistics" element={<StatisticsPage />} />
      </Routes>
    </Router>
  );
}

export default App;

