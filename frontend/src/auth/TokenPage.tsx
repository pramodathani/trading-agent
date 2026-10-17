import { type FormEvent, useState } from 'react';

import { apiClient } from '../api/apiClient';
import { tokenStore } from './tokenStore';

/**
 * Asks for the gateway's access token, checks it, and saves it in this browser.
 * @returns The page.
 */
export function TokenPage() {
  const [token, setToken] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Checks and saves the token.
   * @param event The form's submit event.
   */
  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    const trimmed = token.trim();
    if (!trimmed) {
      return;
    }
    setChecking(true);
    setError(null);
    try {
      if (await apiClient.isAccepted(trimmed)) {
        tokenStore.save(trimmed);
        return;
      }
      setError('The gateway did not accept this token.');
    } catch {
      setError('The gateway did not answer. Is trading-agent running?');
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="token-page">
      <form className="token-card panel" onSubmit={handleSubmit}>
        <div className="brand">
          <img src="/favicon.svg" alt="" />
          trading-agent
        </div>
        <p>
          Paste the gateway&apos;s access token. It is the value of <code>TRADING_AGENT_GATEWAY_ACCESS_TOKEN</code> in the project&apos;s <code>.env</code> file.
        </p>
        <p className="muted small">The token is kept in this browser only, so you enter it once per browser.</p>
        <input
          type="password"
          autoFocus
          value={token}
          onChange={(change) => setToken(change.target.value)}
          placeholder="Access token"
          aria-label="Access token"
        />
        {error !== null && <p className="error-text">{error}</p>}
        <button className="primary" type="submit" disabled={checking || !token.trim()}>
          {checking ? 'Checking…' : 'Continue'}
        </button>
      </form>
    </div>
  );
}
