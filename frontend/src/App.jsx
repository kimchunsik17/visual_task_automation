import {BrowserRouter as Router, Routes, Route, Navigate, useLocation} from 'react-router-dom';
import { useEffect } from 'react';
import axios from 'axios';
import MainPage from './pages/MainPage';
import EditorPage from './pages/EditorPage';
import WorkflowsPage from './pages/WorkflowsPage';
import TemplatesPage from './pages/TemplatesPage';
import TemplateDetailPage from './pages/TemplateDetailPage';
import CommunityQnaPage from './pages/CommunityQnaPage';
import MessagesPage from './pages/MessagesPage';
import SettingsPage from './pages/SettingsPage';
import AppRunnerPage from './pages/AppRunnerPage';
import BotManagerPage from './pages/BotManagerPage';
import StatisticsPage from './pages/StatisticsPage';
import ProjectRunsPage from './pages/ProjectRunsPage';
import SchedulerPage from './pages/SchedulerPage';
import ApprovalInboxPage from './pages/ApprovalInboxPage';
import WebhookManagerPage from './pages/WebhookManagerPage';
import AppViewerPage from './pages/AppViewerPage';
import ApiCenterPage from './pages/ApiCenterPage';
import PatchNotesPage from './pages/PatchNotesPage';
import CustomAlert from './CustomAlert';
import CustomConfirm from './CustomConfirm';
import RequireAuth from './RequireAuth';
import AdminRoute from './AdminRoute';
import AdminPage from './pages/AdminPage';
import IntroPage from './pages/IntroPage';
import { ErrorBoundary } from './ErrorBoundary';
import { useAuth } from './AuthContext';
import AppBuilderPage from './pages/AppBuilderPage';
import CustomAppViewerPage from './pages/CustomAppViewerPage';
import CustomAppsDashboardPage from './pages/CustomAppsDashboardPage';
import TutorialPage from './pages/TutorialPage';
import DocumentsPage from './pages/DocumentsPage';
import FormatsPage from './pages/FormatsPage';
import OperationsOverviewPage from './pages/OperationsOverviewPage';

// 구 URL → 새 IA 경로 (쿼리·해시 보존, replace 이동 — IA 계획 §2)
const LegacyRedirect = ({ to }) => {
  const location = useLocation();
  return <Navigate replace to={`${to}${location.search}${location.hash}`} />;
};
import MilestoneCelebrationHost from './MilestoneCelebration';

function RootRoute() {
  const { user } = useAuth();
  return user ? <MainPage /> : <IntroPage />;
}

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
      {/* 라우트 렌더링 중 터진 오류가 흰 화면으로 끝나지 않게 <Routes> 바깥에서 감싼다 */}
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<RootRoute />} />
          <Route path="/intro" element={<IntroPage />} />
          <Route path="/workflows" element={<RequireAuth><WorkflowsPage /></RequireAuth>} />
          <Route path="/community/templates" element={<RequireAuth><TemplatesPage /></RequireAuth>} />
          <Route path="/community/templates/:slug" element={<RequireAuth><TemplateDetailPage /></RequireAuth>} />
          <Route path="/messages" element={<RequireAuth><MessagesPage /></RequireAuth>} />
          <Route path="/community/qna" element={<RequireAuth><CommunityQnaPage /></RequireAuth>} />
          <Route path="/community/qna/new" element={<RequireAuth><CommunityQnaPage view="new" /></RequireAuth>} />
          <Route path="/community/qna/:postId" element={<RequireAuth><CommunityQnaPage view="detail" /></RequireAuth>} />
          <Route path="/templates" element={<LegacyRedirect to="/community/templates" />} />
          <Route path="/tutorial" element={<RequireAuth><TutorialPage /></RequireAuth>} />
          <Route path="/tutorial/:trackId" element={<RequireAuth><TutorialPage /></RequireAuth>} />
          <Route path="/formats" element={<RequireAuth><FormatsPage /></RequireAuth>} />
          <Route path="/documents" element={<RequireAuth><DocumentsPage /></RequireAuth>} />
          <Route path="/documents/nodes/:nodeType" element={<RequireAuth><DocumentsPage /></RequireAuth>} />
          <Route path="/documents/patterns/:patternId" element={<RequireAuth><DocumentsPage /></RequireAuth>} />
          <Route path="/settings" element={<LegacyRedirect to="/settings/profile" />} />
          <Route path="/settings/api-center" element={<RequireAuth><ApiCenterPage /></RequireAuth>} />
          <Route path="/settings/:tab" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/admin" element={<AdminRoute><AdminPage view="overview" /></AdminRoute>} />
          <Route path="/admin/moderation" element={<RequireAuth><AdminPage view="moderation" /></RequireAuth>} />
          <Route path="/admin/users" element={<AdminRoute><AdminPage view="users" /></AdminRoute>} />
          <Route path="/admin/llm" element={<AdminRoute><AdminPage view="llm" /></AdminRoute>} />
          <Route path="/admin/feedback" element={<AdminRoute><AdminPage view="feedback" /></AdminRoute>} />
          <Route path="/moderation" element={<RequireAuth><LegacyRedirect to="/admin/moderation" /></RequireAuth>} />
          <Route path="/patch-notes" element={<RequireAuth><PatchNotesPage /></RequireAuth>} />
          <Route path="/editor/:projectId?" element={<RequireAuth><EditorPage /></RequireAuth>} />
          <Route path="/project/:projectId/runs" element={<RequireAuth><ProjectRunsPage /></RequireAuth>} />
          {/* 공유 링크 — 계정 없이도 열람/실행 가능해야 하므로 로그인 강제에서 제외 */}
          <Route path="/app/:shareToken" element={<AppRunnerPage />} />
          <Route path="/viewer/:projectId" element={<AppViewerPage />} />
          <Route path="/apicenter" element={<LegacyRedirect to="/settings/api-center" />} />
          <Route path="/operations" element={<RequireAuth><OperationsOverviewPage /></RequireAuth>} />
          <Route path="/operations/webhooks" element={<RequireAuth><WebhookManagerPage /></RequireAuth>} />
          <Route path="/operations/bots" element={<RequireAuth><BotManagerPage /></RequireAuth>} />
          <Route path="/operations/schedules" element={<RequireAuth><SchedulerPage /></RequireAuth>} />
          <Route path="/webhooks" element={<LegacyRedirect to="/operations/webhooks" />} />
          <Route path="/bots" element={<LegacyRedirect to="/operations/bots" />} />
          <Route path="/scheduler" element={<LegacyRedirect to="/operations/schedules" />} />
          <Route path="/approvals" element={<RequireAuth><ApprovalInboxPage /></RequireAuth>} />
          <Route path="/statistics" element={<RequireAuth><StatisticsPage /></RequireAuth>} />
          <Route path="/custom-apps" element={<RequireAuth><CustomAppsDashboardPage /></RequireAuth>} />
          <Route path="/app-builder/:appId?" element={<RequireAuth><AppBuilderPage /></RequireAuth>} />
          <Route path="/custom-app/:appId" element={<CustomAppViewerPage />} />
        </Routes>
      </ErrorBoundary>
      <CustomAlert />
      <CustomConfirm />
      <MilestoneCelebrationHost />
    </Router>
  );
}

export default App;
