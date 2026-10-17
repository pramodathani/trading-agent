import { useEffect, useSyncExternalStore } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router';

import { TokenPage } from './auth/TokenPage';
import { tokenStore } from './auth/tokenStore';
import { AppLayout } from './layout/AppLayout';
import { eventSocket } from './live/eventSocket';
import { ActivityPage } from './pages/ActivityPage';
import { ChatPage } from './pages/ChatPage';
import { DesksPage } from './pages/DesksPage';
import { TradingPage } from './pages/TradingPage';

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
          <Route index element={<Navigate to="/desks" replace />} />
          <Route path="desks" element={<DesksPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="trading" element={<TradingPage />} />
          <Route path="*" element={<Navigate to="/desks" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
