import { useState } from 'react';

import { apiClient } from '../api/apiClient';
import { usePolled } from '../hooks/usePolled';
import { formatter } from '../utilities/formatter';

const REFRESH_MILLISECONDS = 30000;

/**
 * The standing permissions given with "Always allow", each with a button to revoke it so the trader asks again.
 * @returns The panel.
 */
export function PermissionGrantsPanel() {
  const grants = usePolled(() => apiClient.permissionGrants(), REFRESH_MILLISECONDS);
  const [error, setError] = useState<string | null>(null);

  /**
   * Revokes one grant.
   * @param trader The trader.
   * @param toolName The tool.
   */
  async function revoke(trader: string, toolName: string): Promise<void> {
    setError(null);
    try {
      await apiClient.revokePermission(trader, toolName);
      grants.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  const list = grants.data ?? [];
  return (
    <section className="panel">
      <h2>Standing permissions</h2>
      <p className="muted small">The tools in [approvals] tools ask for your permission each time, unless you chose &quot;Always allow&quot; for a trader. Revoke one to make that trader ask again.</p>
      {grants.error !== null && <p className="error-text small">{grants.error}</p>}
      {error !== null && <p className="error-text small">{error}</p>}
      {grants.data !== null && list.length === 0 && <p className="muted small">None. Every covered action asks first.</p>}
      {list.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Trader</th>
              <th>Tool</th>
              <th>Allowed since</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((grant) => (
              <tr key={`${grant.trader}/${grant.tool_name}`}>
                <td>{grant.trader}</td>
                <td className="mono">{grant.tool_name}</td>
                <td>{formatter.dayTime(grant.granted_at)}</td>
                <td className="number">
                  <button type="button" className="danger" onClick={() => void revoke(grant.trader, grant.tool_name)}>
                    Revoke
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
