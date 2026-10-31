import { useCallback, useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router';

import { apiClient } from '../api/apiClient';
import { tokenStore } from '../auth/tokenStore';
import { useCloseOnBack } from '../hooks/useCloseOnBack';
import { useConnectionState, useLiveEvents } from '../hooks/useLiveEvents';
import { usePolled } from '../hooks/usePolled';
import { sidePanelStore, useSidePanelOpen } from '../sidePanel/sidePanelStore';
import { pushRegistration } from '../utilities/pushRegistration';
import { themeController } from '../utilities/themeController';
import { TraderMenu } from './TraderMenu';
import { TradersContext } from './tradersContext';
import { selectedTraderStore, useSelectedTrader } from './selectedTraderStore';

const TRADERS_REFRESH_MILLISECONDS = 5000;
const APPS_REFRESH_MILLISECONDS = 30000;
const STATE_CHANGING_KINDS = new Set([
  'trigger_received',
  'turn_started',
  'turn_finished',
  'session_started',
  'backend_switch',
  'trader_created',
  'trader_retired',
  'trader_sleeping',
]);
const CONNECTION_WORDS = {
  open: 'Live',
  connecting: 'Connecting…',
  closed: 'Reconnecting…',
};

/**
 * The frame around every page: the sidebar, the header with the trader switcher, and the page itself.
 *
 * On a phone the sidebar becomes a drawer that slides in from the left when the menu button is pressed, as in the Claude app.
 * @returns The layout.
 */
export function AppLayout() {
  const traders = usePolled(() => apiClient.traders(), TRADERS_REFRESH_MILLISECONDS);
  const apps = usePolled(() => apiClient.apps(), APPS_REFRESH_MILLISECONDS);
  const selectedTrader = useSelectedTrader();
  const connection = useConnectionState();
  const events = useLiveEvents();
  const location = useLocation();
  const navigate = useNavigate();
  const panelOpen = useSidePanelOpen();
  const [theme, setTheme] = useState(themeController.current());
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);
  const lastEvent = events.length > 0 ? events[events.length - 1] : null;
  const refreshTraders = traders.refresh;

  useCloseOnBack(drawerOpen, closeDrawer);

  useEffect(() => {
    void pushRegistration.register();
    return pushRegistration.onOpen((traderName) => {
      selectedTraderStore.choose(traderName);
      void navigate('/chat');
    });
  }, [
    navigate,
  ]);

  useEffect(() => {
    setDrawerOpen(false);
  }, [
    location.pathname,
  ]);

  useEffect(() => {
    if (lastEvent !== null && STATE_CHANGING_KINDS.has(lastEvent.kind)) {
      void refreshTraders();
    }
  }, [
    lastEvent,
    refreshTraders,
  ]);

  const traderNames = useMemo(() => {
    const names = [];
    for (const trader of traders.data?.traders ?? []) {
      names.push(trader.name);
    }
    return names;
  }, [
    traders.data,
  ]);

  useEffect(() => {
    if (traderNames.length > 0 && !traderNames.includes(selectedTraderStore.current())) {
      selectedTraderStore.choose(traderNames[0]);
    }
  }, [
    traderNames,
  ]);

  const contextValue = useMemo(
    () => ({
      document: traders.data,
      error: traders.error,
      refresh: refreshTraders,
    }),
    [
      traders.data,
      traders.error,
      refreshTraders,
    ],
  );

  const mode = traders.data?.mode ?? '';

  return (
    <TradersContext.Provider value={contextValue}>
      <div className={drawerOpen ? 'app drawer-open' : 'app'}>
        {drawerOpen && <div className="drawer-backdrop" onClick={closeDrawer} aria-hidden="true" />}
        <nav className="sidebar">
          <div className="brand">
            <img src="/favicon.svg" alt="" />
            trading-agent
          </div>
          <div className="nav-section">Trade</div>
          <NavLink className="nav-link" to="/traders">
            Traders
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
          <button type="button" className="icon-button menu-button" onClick={() => setDrawerOpen(true)} aria-label="Open the menu" title="Open the menu">
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h7" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </button>
          <div className="trader-switcher">
            <span className="muted small">Trader</span>
            <TraderMenu traders={traders.data?.traders ?? []} selectedTrader={selectedTrader} />
          </div>
          {mode && (
            <span className={mode === 'live' ? 'mode-badge live' : 'mode-badge'}>
              <span className="mode-words">{mode === 'live' ? 'LIVE ORDERS' : 'DRY RUN'}</span>
              <span className="mode-words-short">{mode === 'live' ? 'LIVE' : 'DRY'}</span>
            </span>
          )}
          <span className="spacer" />
          {traders.error !== null && <span className="error-text small gateway-error">Gateway: {traders.error}</span>}
          <span className="connection">
            <span className={`connection-dot ${connection}`} title={CONNECTION_WORDS[connection]} />
            <span className="connection-words">{CONNECTION_WORDS[connection]}</span>
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
    </TradersContext.Provider>
  );
}
