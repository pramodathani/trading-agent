import { useState } from 'react';
import { useParams } from 'react-router';

import { apiClient } from '../api/apiClient';
import { usePolled } from '../hooks/usePolled';

const REFRESH_MILLISECONDS = 10000;

type UnitAction = 'start' | 'stop' | 'restart';

/**
 * One package's web app: its state and controls on top, and the app's own page below.
 * @returns The page.
 */
export function AppPage() {
  const { packageName = '' } = useParams();
  const apps = usePolled(() => apiClient.apps(), REFRESH_MILLISECONDS, packageName);
  const [working, setWorking] = useState<UnitAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frameKey, setFrameKey] = useState(0);
  const app = apps.data?.find((candidate) => candidate.package === packageName) ?? null;

  /**
   * Starts, stops or restarts the app's unit.
   * @param action The action.
   */
  async function act(action: UnitAction): Promise<void> {
    setWorking(action);
    setError(null);
    try {
      await apiClient.appAction(packageName, action);
      apps.refresh();
      setFrameKey((key) => key + 1);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setWorking(null);
    }
  }

  if (apps.data === null) {
    return <p className="muted">{apps.error ?? 'Loading…'}</p>;
  }
  if (app === null) {
    return <p className="muted">No installed package named {packageName} has an app.</p>;
  }
  const running = app.unit_state?.active_state === 'active';

  return (
    <div className="app-page">
      <div className="app-bar">
        <h1>{app.title}</h1>
        <span className={app.healthy ? 'state-badge server-ready' : 'state-badge server-failed'}>{app.healthy ? 'answers' : `does not answer (${app.health_detail})`}</span>
        {app.unit !== null && (
          <span className="muted small">
            <span className="mono">{app.unit}</span>: {app.unit_state ? `${app.unit_state.active_state} (${app.unit_state.sub_state})` : app.unit_error}
          </span>
        )}
        <span className="spacer" />
        {app.unit !== null && (
          <span className="button-row">
            {!running && (
              <button type="button" disabled={working !== null} onClick={() => act('start')}>
                {working === 'start' ? 'Starting…' : 'Start'}
              </button>
            )}
            {running && (
              <button type="button" disabled={working !== null} onClick={() => act('restart')}>
                {working === 'restart' ? 'Restarting…' : 'Restart'}
              </button>
            )}
            {running && (
              <button className="danger" type="button" disabled={working !== null} onClick={() => act('stop')}>
                {working === 'stop' ? 'Stopping…' : 'Stop'}
              </button>
            )}
          </span>
        )}
        {app.url !== null && (
          <a href={app.url} target="_blank" rel="noreferrer">
            Open in a new tab
          </a>
        )}
      </div>
      {app.error && <p className="error-text">{app.error}</p>}
      {error !== null && <p className="error-text">{error}</p>}
      {app.url !== null && app.open_in === 'frame' && <iframe key={frameKey} className="app-frame" src={app.url} title={app.title} />}
      {app.url !== null && app.open_in === 'tab' && (
        <section className="panel">
          <p>{app.description}</p>
          <p className="muted small">This app opens in its own tab.</p>
        </section>
      )}
    </div>
  );
}
