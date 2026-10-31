import { useState } from 'react';

import { apiClient } from '../../api/apiClient';
import type { UserRequest } from '../../api/types';
import { MarkdownText } from '../MarkdownText';

/** What the plan card shows. */
interface PlanCardProperties {
  request: UserRequest;
  onDone: () => void;
}

/**
 * A trader's plan as Claude Code shows plan approval: the plan in Markdown, then Approve or Keep planning with feedback.
 * @param properties The plan request, and what to call once it is decided or dismissed.
 * @returns The card.
 */
export function PlanCard(properties: PlanCardProperties) {
  const request = properties.request;
  const [feedback, setFeedback] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Sends a decision.
   * @param decision "approve" or "revise".
   */
  async function decide(decision: 'approve' | 'revise'): Promise<void> {
    if (decision === 'revise' && feedback.trim().length === 0) {
      setError('Say what should change, then press Keep planning.');
      return;
    }
    setSending(true);
    setError(null);
    try {
      await apiClient.decidePlan(request.request_id, decision, feedback.trim());
      properties.onDone();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSending(false);
    }
  }

  /** Closes the plan without deciding. */
  async function dismiss(): Promise<void> {
    setSending(true);
    setError(null);
    try {
      await apiClient.dismissRequest(request.request_id);
      properties.onDone();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="request-card plan-card">
      <div className="request-card-top">
        <span className="request-card-from">
          <strong>{request.trader}</strong> presents a plan for your approval
        </span>
        <button type="button" className="icon-button" onClick={() => void dismiss()} disabled={sending} aria-label="Dismiss without deciding" title="Dismiss without deciding; the trader will use its own judgment">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className="question-text">{request.content.title}</div>
      <div className="plan-body">
        <MarkdownText text={request.content.plan ?? ''} />
      </div>
      <textarea className="plan-feedback" rows={2} value={feedback} placeholder="Feedback for the trader: needed for Keep planning, optional with Approve" onChange={(change) => setFeedback(change.target.value)} />
      {error !== null && <p className="error-text small">{error}</p>}
      <div className="request-card-actions">
        <span className="request-card-hint">The trader will not act on the plan until you approve it.</span>
        <button type="button" onClick={() => void decide('revise')} disabled={sending}>
          Keep planning
        </button>
        <button type="button" className="primary" onClick={() => void decide('approve')} disabled={sending}>
          Approve
        </button>
      </div>
    </div>
  );
}
