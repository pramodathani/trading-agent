import { type FormEvent, useState } from 'react';

import { apiClient } from '../api/apiClient';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';
import { formatter } from '../utilities/formatter';

const REFRESH_MILLISECONDS = 5000;
const STATE_WORDS: Record<string, string> = {
  off: 'Off',
  connecting: 'Connecting…',
  connected: 'Connected',
  failed: 'Cannot reach Telegram',
};

/**
 * The Telegram channel: whether it runs, the chats the desks obey, and the codes waiting for your approval.
 * @returns The page.
 */
export function ChannelsPage() {
  const telegram = usePolled(() => apiClient.telegram(), REFRESH_MILLISECONDS);
  const [code, setCode] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /**
   * Approves a code.
   * @param value The code.
   */
  async function approve(value: string): Promise<void> {
    setError(null);
    try {
      await apiClient.approvePairing(value.trim());
      setNotice('Paired. The bot has told the chat, and now obeys it.');
      setCode('');
      telegram.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Approves the typed code.
   * @param event The form's submit event.
   */
  async function approveTyped(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (code.trim()) {
      await approve(code);
    }
  }

  /**
   * Unpairs a chat.
   * @param chatId The chat.
   */
  async function revoke(chatId: number): Promise<void> {
    setError(null);
    try {
      await apiClient.revokePairing(chatId);
      setNotice('Unpaired. The bot now ignores that chat.');
      telegram.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Channels</h1>
        <p className="muted">Telegram lets you talk to the desks and hear from them on your phone. The bot obeys only chats you approve here.</p>
      </div>
      {notice !== null && (
        <div className="notice" role="status">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      {error !== null && <p className="error-text">{error}</p>}
      <Loadable data={telegram.data} error={telegram.error}>
        {(status) => (
          <>
            <section className="panel">
              <h2>Telegram</h2>
              <p>
                <span className={`state-badge server-${status.state === 'connected' ? 'ready' : status.state}`}>{STATE_WORDS[status.state] ?? status.state}</span>
                {status.username && <span className="mono"> @{status.username}</span>}
              </p>
              {!status.enabled && (
                <p className="muted">
                  Telegram is switched off. Follow <span className="mono">docs/telegram_setup.md</span> to create the bot, then set <span className="mono">enabled = true</span> under <span className="mono">[telegram]</span> in trading_agent.toml and restart.
                </p>
              )}
              {status.enabled && !status.token_present && <p className="error-text">Telegram is enabled, but TRADING_AGENT_TELEGRAM_BOT_TOKEN is not set in .env.</p>}
              {status.error && <p className="error-text small">{status.error}</p>}
              <p className="muted small">
                New chats talk to {status.default_desk}. Pushed to every paired chat: {status.notifications.join(', ').replaceAll('_', ' ')}.
              </p>
            </section>
            <section className="panel">
              <h2>Waiting for approval</h2>
              <p className="muted small">When someone messages the bot, it replies with a code. Approve it only if that someone is you: the chat can then command every desk.</p>
              {status.pending.length === 0 && <p className="muted">No codes waiting.</p>}
              {status.pending.map((pending) => (
                <div key={pending.code} className="alert-line">
                  <span className="mono">{pending.code}</span>
                  <span>
                    {pending.name || '(no name)'} <span className="muted small">chat {pending.chat_id}</span>
                  </span>
                  <span className="muted small">{formatter.dayTime(pending.requested_at)}</span>
                  <span className="spacer" />
                  <button className="primary" type="button" onClick={() => approve(pending.code)}>
                    Approve
                  </button>
                </div>
              ))}
              <form className="filters pairing-form" onSubmit={approveTyped}>
                <input className="mono" value={code} onChange={(change) => setCode(change.target.value)} placeholder="Or type the code from your phone" aria-label="Pairing code" />
                <button type="submit" disabled={!code.trim()}>
                  Approve code
                </button>
              </form>
            </section>
            <section className="panel">
              <h2>Paired chats</h2>
              {status.paired.length === 0 && <p className="muted">No chat is paired yet.</p>}
              {status.paired.map((chat) => (
                <div key={chat.chat_id} className="alert-line">
                  <strong>{chat.name || '(no name)'}</strong>
                  <span className="muted small">chat {chat.chat_id}</span>
                  <span>talks to {chat.desk}</span>
                  <span className="muted small">since {formatter.dayTime(chat.paired_at)}</span>
                  <span className="spacer" />
                  <button className="danger" type="button" onClick={() => revoke(chat.chat_id)}>
                    Unpair
                  </button>
                </div>
              ))}
            </section>
          </>
        )}
      </Loadable>
    </div>
  );
}
