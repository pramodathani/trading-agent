import { type KeyboardEvent, useEffect, useRef, useState } from 'react';

import { apiClient } from '../../api/apiClient';
import type { UserRequest } from '../../api/types';
import { MarkdownText } from '../MarkdownText';

const TICK_MILLISECONDS = 1000;

/** What the permission card shows. */
interface PermissionCardProperties {
  request: UserRequest;
  onDone: () => void;
}

/**
 * A held tool call as Claude Code asks for permission: the tool and its arguments, then "Do you want to proceed?" with Yes, Yes and don't ask again, and No with a reason, and the time left before it lapses.
 * @param properties The permission request, and what to call once it is decided.
 * @returns The card.
 */
export function PermissionCard(properties: PermissionCardProperties) {
  const request = properties.request;
  const toolName = request.content.tool_name ?? 'a tool';
  const [highlighted, setHighlighted] = useState(0);
  const [reason, setReason] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const cardReference = useRef<HTMLDivElement>(null);

  useEffect(() => {
    cardReference.current?.focus();
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MILLISECONDS);
    return () => {
      window.clearInterval(timer);
    };
  }, [
    request.request_id,
  ]);

  const secondsLeft = request.expires_at === null ? null : Math.max(0, Math.floor((Date.parse(request.expires_at) - now) / 1000));
  const lapsed = secondsLeft === 0;

  /**
   * Sends the decision.
   * @param decision "allow_once", "always_allow" or "deny".
   */
  async function decide(decision: 'allow_once' | 'always_allow' | 'deny'): Promise<void> {
    setSending(true);
    setError(null);
    try {
      await apiClient.decidePermission(request.request_id, decision, reason.trim());
      properties.onDone();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSending(false);
    }
  }

  /**
   * Keyboard control as in Claude Code: arrows move, 1 to 3 or Enter choose.
   * @param event The key event.
   */
  function handleKey(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.target instanceof HTMLInputElement || sending || lapsed) {
      return;
    }
    const choices: ('allow_once' | 'always_allow' | 'deny')[] = [
      'allow_once',
      'always_allow',
      'deny',
    ];
    const number = Number.parseInt(event.key, 10);
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlighted((index) => (index + 1) % 3);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlighted((index) => (index + 2) % 3);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      void decide(choices[highlighted]);
    } else if (number >= 1 && number <= 3) {
      event.preventDefault();
      void decide(choices[number - 1]);
    }
  }

  /**
   * The class of one choice row.
   * @param index The row's position.
   * @returns The class names.
   */
  function rowClass(index: number): string {
    return index === highlighted ? 'question-option highlighted' : 'question-option';
  }

  return (
    <div className="request-card permission-card" ref={cardReference} tabIndex={-1} onKeyDown={handleKey}>
      <div className="request-card-top">
        <span className="request-card-from">
          <strong>{request.trader}</strong> needs your permission
        </span>
        {secondsLeft !== null && <span className={secondsLeft < 60 ? 'permission-timer urgent' : 'permission-timer'}>{lapsed ? 'lapsed' : `lapses in ${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')}`}</span>}
      </div>
      <div className="question-text">
        Run <span className="mono permission-tool">{toolName}</span>?
      </div>
      <MarkdownText text={'```json\n' + JSON.stringify(request.content.arguments ?? {}, null, 2) + '\n```'} />
      <div className="question-text permission-question">Do you want to proceed?</div>
      <ul className="question-options">
        <li className={rowClass(0)} onMouseEnter={() => setHighlighted(0)} onClick={() => !sending && !lapsed && void decide('allow_once')}>
          <span className="option-key">1</span>
          <span className="option-text">
            <span className="option-label">Yes</span>
            <span className="option-description">Run this call once, through the risk engine as usual.</span>
          </span>
        </li>
        <li className={rowClass(1)} onMouseEnter={() => setHighlighted(1)} onClick={() => !sending && !lapsed && void decide('always_allow')}>
          <span className="option-key">2</span>
          <span className="option-text">
            <span className="option-label">
              Yes, and don&apos;t ask again for <span className="mono">{toolName}</span> on {request.trader}
            </span>
            <span className="option-description">Saved until you revoke it on the Settings page.</span>
          </span>
        </li>
        <li className={`${rowClass(2)} other`} onMouseEnter={() => setHighlighted(2)}>
          <span className="option-key">3</span>
          <span className="option-text">
            <span className="option-label">No, and tell the trader why</span>
            <input
              className="option-other"
              value={reason}
              placeholder="Optional reason, then press Enter or Deny"
              onChange={(change) => setReason(change.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void decide('deny');
                }
              }}
            />
          </span>
        </li>
      </ul>
      {error !== null && <p className="error-text small">{error}</p>}
      <div className="request-card-actions">
        <span className="request-card-hint">↑↓ to move · 1–3 or Enter to choose</span>
        <button type="button" className="danger" onClick={() => void decide('deny')} disabled={sending || lapsed}>
          Deny
        </button>
        <button type="button" className="primary" onClick={() => void decide('allow_once')} disabled={sending || lapsed}>
          Allow once
        </button>
      </div>
    </div>
  );
}
