import { apiClient } from '../api/apiClient';
import { Loadable } from '../components/Loadable';
import { PermissionGrantsPanel } from '../components/PermissionGrantsPanel';
import { PhonesPanel } from '../components/PhonesPanel';
import { usePolled } from '../hooks/usePolled';

const REFRESH_MILLISECONDS = 60000;

/**
 * The standing permissions, and the configuration the gateway runs with, read-only, with every known secret masked.
 * @returns The page.
 */
export function SettingsPage() {
  const configuration = usePolled(() => apiClient.configuration(), REFRESH_MILLISECONDS);
  return (
    <div className="page">
      <div className="page-header">
        <h1>Settings</h1>
        <p className="muted">
          This is trading_agent.toml as the gateway read it at start, with defaults filled in. Edit the file and restart the gateway to change it. Secrets live in .env and are never shown.
        </p>
      </div>
      <PermissionGrantsPanel />
      <PhonesPanel />
      <Loadable data={configuration.data} error={configuration.error}>
        {(document) => (
          <>
            {Object.entries(document).map(([section, value]) => (
              <section key={section} className="panel">
                <h2 className="mono">{section}</h2>
                <pre className="small">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>
              </section>
            ))}
          </>
        )}
      </Loadable>
    </div>
  );
}
