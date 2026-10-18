import { type FormEvent, useState } from 'react';

import { apiClient } from '../api/apiClient';
import { gatewayAddress } from '../api/gatewayAddress';
import { platform } from '../utilities/platform';
import { tokenStore } from './tokenStore';

/**
 * Asks for the gateway's access token, checks it, and saves it in this browser.
 *
 * Inside the Android app it also asks for the gateway's address, because the app carries its own copy of the page.
 * @returns The page.
 */
export function TokenPage() {
  const inApp = platform.isApp();
  const [address, setAddress] = useState(gatewayAddress.current());
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
    const cleanedAddress = gatewayAddress.clean(address);
    if (!trimmed || (inApp && !cleanedAddress)) {
      return;
    }
    setChecking(true);
    setError(null);
    try {
      if (await apiClient.isAccepted(trimmed, inApp ? cleanedAddress : undefined)) {
        if (inApp) {
          gatewayAddress.save(cleanedAddress);
        }
        tokenStore.save(trimmed);
        return;
      }
      setError('The gateway did not accept this token.');
    } catch {
      setError(inApp ? 'The gateway did not answer. Check the address, that Tailscale is on, and that trading-agent is running.' : 'The gateway did not answer. Is trading-agent running?');
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
        {inApp && (
          <>
            <p>
              Enter the gateway&apos;s address on your Tailscale network, such as <code>https://desktop.tailnet-name.ts.net</code>.
            </p>
            <input
              type="url"
              inputMode="url"
              autoCapitalize="off"
              autoCorrect="off"
              value={address}
              onChange={(change) => setAddress(change.target.value)}
              placeholder="Gateway address"
              aria-label="Gateway address"
            />
          </>
        )}
        <p>
          Paste the gateway&apos;s access token. It is the value of <code>TRADING_AGENT_GATEWAY_ACCESS_TOKEN</code> in the project&apos;s <code>.env</code> file.
        </p>
        <p className="muted small">{inApp ? 'The address and token are kept on this phone only.' : 'The token is kept in this browser only, so you enter it once per browser.'}</p>
        <input
          type="password"
          autoFocus={!inApp}
          value={token}
          onChange={(change) => setToken(change.target.value)}
          placeholder="Access token"
          aria-label="Access token"
        />
        {error !== null && <p className="error-text">{error}</p>}
        <button className="primary" type="submit" disabled={checking || !token.trim() || (inApp && !address.trim())}>
          {checking ? 'Checking…' : 'Continue'}
        </button>
      </form>
    </div>
  );
}
