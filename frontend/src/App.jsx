import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import MainPage from './pages/MainPage';
import EditorPage from './pages/EditorPage';
import WorkflowsPage from './pages/WorkflowsPage';
import TemplatesPage from './pages/TemplatesPage';
import SettingsPage from './pages/SettingsPage';
import AppViewerPage from './pages/AppViewerPage';
import BotManagerPage from './pages/BotManagerPage';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<MainPage />} />
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/editor/:projectId?" element={<EditorPage />} />
        <Route path="/app/:projectId" element={<AppViewerPage />} />
        <Route path="/bots" element={<BotManagerPage />} />
      </Routes>
    </Router>
  );
}

export default App;
