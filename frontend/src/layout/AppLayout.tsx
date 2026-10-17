import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router';

import { apiClient } from '../api/apiClient';
import { tokenStore } from '../auth/tokenStore';
import { useConnectionState, useLiveEvents } from '../hooks/useLiveEvents';
import { usePolled } from '../hooks/usePolled';
import { sidePanelStore, useSidePanelOpen } from '../sidePanel/sidePanelStore';
import { themeController } from '../utilities/themeController';
import { DeskMenu } from './DeskMenu';
import { DesksContext } from './desksContext';
import { selectedDeskStore, useSelectedDesk } from './selectedDeskStore';

const DESKS_REFRESH_MILLISECONDS = 5000;
const APPS_REFRESH_MILLISECONDS = 30000;
const STATE_CHANGING_KINDS = new Set([
  'trigger_received',
  'turn_started',
  'turn_finished',
  'session_started',
  'backend_switch',
]);
const CONNECTION_WORDS = {
  open: 'Live',
  connecting: 'Connecting…',
  closed: 'Reconnecting…',
};

/**
 * The frame around every page: the sidebar, the header with the desk switcher, and the page itself.
 * @returns The layout.
 */
export function AppLayout() {
  const desks = usePolled(() => apiClient.desks(), DESKS_REFRESH_MILLISECONDS);
  const apps = usePolled(() => apiClient.apps(), APPS_REFRESH_MILLISECONDS);
  const selectedDesk = useSelectedDesk();
  const connection = useConnectionState();
  const events = useLiveEvents();
  const location = useLocation();
  const panelOpen = useSidePanelOpen();
  const [theme, setTheme] = useState(themeController.current());
  const lastEvent = events.length > 0 ? events[events.length - 1] : null;
  const refreshDesks = desks.refresh;

  useEffect(() => {
    if (lastEvent !== null && STATE_CHANGING_KINDS.has(lastEvent.kind)) {
      refreshDesks();
    }
  }, [
    lastEvent,
    refreshDesks,
  ]);

  const deskNames = useMemo(() => {
    const names = [];
    for (const desk of desks.data?.desks ?? []) {
      names.push(desk.name);
    }
    return names;
  }, [
    desks.data,
  ]);

  useEffect(() => {
    if (deskNames.length > 0 && !deskNames.includes(selectedDesk)) {
      selectedDeskStore.choose(deskNames[0]);
    }
  }, [
    deskNames,
    selectedDesk,
  ]);

  const contextValue = useMemo(
    () => ({
      document: desks.data,
      error: desks.error,
      refresh: refreshDesks,
    }),
    [
      desks.data,
      desks.error,
      refreshDesks,
    ],
  );

  const mode = desks.data?.mode ?? '';

  return (
    <DesksContext.Provider value={contextValue}>
      <div className="app">
        <nav className="sidebar">
          <div className="brand">
            <img src="/favicon.svg" alt="" />
            trading-agent
          </div>
          <div className="nav-section">Trade</div>
          <NavLink className="nav-link" to="/desks">
            Desks
          </NavLink>
          <NavLink className="nav-link" to="/chat">
            Chat
          </NavLink>
          <NavLink className="nav-link" to="/activity">
            Activity
          </NavLink>
          <NavLink className="nav-link" to="/trading">
            Trading
          </NavLink>
          <div className="nav-section">Memory</div>
          <NavLink className="nav-link" to="/sessions">
            Sessions
          </NavLink>
          <NavLink className="nav-link" to="/files">
            Files
          </NavLink>
          <NavLink className="nav-link" to="/checkpoints">
            Checkpoints
          </NavLink>
          <div className="nav-section">Automation</div>
          <NavLink className="nav-link" to="/cron">
            Schedule
          </NavLink>
          <NavLink className="nav-link" to="/skills">
            Skills
          </NavLink>
          <NavLink className="nav-link" to="/extensions">
            Extensions
          </NavLink>
          <div className="nav-section">System</div>
          <NavLink className="nav-link" to="/models">
            Models
          </NavLink>
          <NavLink className="nav-link" to="/channels">
            Channels
          </NavLink>
          <NavLink className="nav-link" to="/settings">
            Settings
          </NavLink>
          {(apps.data ?? []).length > 0 && <div className="nav-section">Apps</div>}
          {(apps.data ?? []).map((app) => (
            <NavLink key={app.package} className="nav-link app-link" to={`/apps/${app.package}`} title={app.description}>
              <span className={app.healthy ? 'health-dot up' : 'health-dot down'} />
              {app.title}
            </NavLink>
          ))}
          <div className="sidebar-footer">
            <button
              type="button"
              onClick={() => setTheme(themeController.toggle())}
            >
              {theme === 'dark' ? 'Light theme' : 'Dark theme'}
            </button>
            <button type="button" onClick={() => tokenStore.clear()}>
              Forget token
            </button>
          </div>
        </nav>
        <header className="header">
          <div className="desk-switcher">
            <span className="muted small">Desk</span>
            <DeskMenu desks={desks.data?.desks ?? []} selectedDesk={selectedDesk} />
          </div>
          {mode && (
            <span className={mode === 'live' ? 'mode-badge live' : 'mode-badge'}>
              {mode === 'live' ? 'LIVE ORDERS' : 'DRY RUN'}
            </span>
          )}
          <span className="spacer" />
          {desks.error !== null && <span className="error-text small">Gateway: {desks.error}</span>}
          <span className="connection">
            <span className={`connection-dot ${connection}`} />
            {CONNECTION_WORDS[connection]}
          </span>
          {location.pathname === '/chat' && (
            <button
              type="button"
              className={panelOpen ? 'icon-button pressed' : 'icon-button'}
              onClick={() => sidePanelStore.toggleOpen()}
              aria-pressed={panelOpen}
              aria-label={panelOpen ? 'Hide the details panel' : 'Show the details panel'}
              title={panelOpen ? 'Hide the details panel' : 'Show the details panel'}
            >
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <rect x="2" y="2.5" width="12" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3" />
                <path d="M10 2.5v11" stroke="currentColor" strokeWidth="1.3" />
              </svg>
            </button>
          )}
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </DesksContext.Provider>
  );
}
