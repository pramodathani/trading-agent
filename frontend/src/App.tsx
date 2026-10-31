import { useEffect, useSyncExternalStore } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router';

import { TokenPage } from './auth/TokenPage';
import { tokenStore } from './auth/tokenStore';
import { AppLayout } from './layout/AppLayout';
import { eventSocket } from './live/eventSocket';
import { ActivityPage } from './pages/ActivityPage';
import { AppPage } from './pages/AppPage';
import { ChannelsPage } from './pages/ChannelsPage';
import { ChatPage } from './pages/ChatPage';
import { CheckpointsPage } from './pages/CheckpointsPage';
import { CronPage } from './pages/CronPage';
import { TradersPage } from './pages/TradersPage';
import { ExtensionsPage } from './pages/ExtensionsPage';
import { FilesPage } from './pages/FilesPage';
import { ModelsPage } from './pages/ModelsPage';
import { SessionsPage } from './pages/SessionsPage';
import { SettingsPage } from './pages/SettingsPage';
import { SkillsPage } from './pages/SkillsPage';
import { TradingPage } from './pages/TradingPage';
import { platform } from './utilities/platform';

/**
 * The application root: asks for the token when there is none, and otherwise shows the pages.
 * @returns The application.
 */
export function App() {
  const token = useSyncExternalStore(
    (listener) => tokenStore.subscribe(listener),
    () => tokenStore.current(),
  );

  useEffect(() => {
    if (token === null) {
      eventSocket.stop();
      return;
    }
    eventSocket.start();
  }, [
    token,
  ]);

  if (token === null) {
    return <TokenPage />;
  }
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to={platform.isApp() ? '/chat' : '/traders'} replace />} />
          <Route path="traders" element={<TradersPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="trading" element={<TradingPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="files" element={<FilesPage />} />
          <Route path="checkpoints" element={<CheckpointsPage />} />
          <Route path="cron" element={<CronPage />} />
          <Route path="skills" element={<SkillsPage />} />
          <Route path="extensions" element={<ExtensionsPage />} />
          <Route path="models" element={<ModelsPage />} />
          <Route path="channels" element={<ChannelsPage />} />
          <Route path="apps/:packageName" element={<AppPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/traders" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
