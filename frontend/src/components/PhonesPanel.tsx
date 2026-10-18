import { useState } from 'react';

import { apiClient } from '../api/apiClient';
import { usePolled } from '../hooks/usePolled';
import { formatter } from '../utilities/formatter';
import { platform } from '../utilities/platform';
import { pushRegistration } from '../utilities/pushRegistration';

const REFRESH_MILLISECONDS = 30000;

/**
 * The phones running the Android app that receive push notifications, each with buttons to send a test and to remove it.
 * @returns The panel.
 */
export function PhonesPanel() {
  const devices = usePolled(() => apiClient.devices(), REFRESH_MILLISECONDS);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /**
   * Runs one action and refreshes the list.
   * @param action The action.
   */
  async function act(action: () => Promise<string | null>): Promise<void> {
    setMessage(null);
    setError(null);
    try {
      setMessage(await action());
      devices.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Sends a test notification to one phone.
   * @param deviceId The phone.
   * @returns What happened.
   */
  async function test(deviceId: string): Promise<string> {
    const answer = await apiClient.testDevice(deviceId);
    return answer.sent ? 'Test notification sent.' : 'Firebase did not accept the test notification. The gateway log says why.';
  }

  /**
   * Removes one phone.
   * @param deviceId The phone.
   * @returns What happened.
   */
  async function remove(deviceId: string): Promise<string> {
    const removed = await apiClient.removeDevice(deviceId);
    return `${removed.name} will get no more notifications.`;
  }

  /**
   * Registers this phone again, for example after allowing notifications.
   * @returns What happened.
   */
  async function registerThisPhone(): Promise<string> {
    const problem = await pushRegistration.register();
    if (problem !== null) {
      throw new Error(problem);
    }
    return 'This phone asked the gateway to send it notifications.';
  }

  const document = devices.data;
  const list = document?.devices ?? [];
  return (
    <section className="panel">
      <h2>Phones</h2>
      <p className="muted small">Phones running the Trading Agent app get push notifications for the kinds in [push] notifications, through Google&apos;s Firebase service.</p>
      {devices.error !== null && <p className="error-text small">{devices.error}</p>}
      {document !== null && !document.enabled && <p className="small">{document.problem}</p>}
      {message !== null && <p className="small">{message}</p>}
      {error !== null && <p className="error-text small">{error}</p>}
      {document !== null && list.length === 0 && <p className="muted small">No phone is registered. Sign in from the Android app and allow notifications.</p>}
      {list.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Phone</th>
                <th>Registered</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.map((device) => (
                <tr key={device.device_id}>
                  <td>{device.name}</td>
                  <td>{formatter.dayTime(device.registered_at)}</td>
                  <td className="number">
                    <span className="button-row">
                      <button type="button" disabled={!document?.enabled} onClick={() => void act(() => test(device.device_id))}>
                        Send test
                      </button>
                      <button type="button" className="danger" onClick={() => void act(() => remove(device.device_id))}>
                        Remove
                      </button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {platform.isApp() && (
        <p>
          <button type="button" onClick={() => void act(registerThisPhone)}>
            Register this phone again
          </button>
        </p>
      )}
    </section>
  );
}
