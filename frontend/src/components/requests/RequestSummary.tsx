import { useState } from 'react';

import type { UserRequest } from '../../api/types';
import { MarkdownText } from '../MarkdownText';

const STATUS_WORDS: Record<string, string> = {
  pending: 'waiting for your answer',
  dismissed: 'you dismissed it',
  expired: 'it expired',
};

/**
 * What stays in the transcript once a desk asked something: each question with your answer, or the plan with your decision, as Claude Code keeps a summary of answered questions.
 * @param properties The request, with its latest status.
 * @returns The summary.
 */
export function RequestSummary(properties: { request: UserRequest }) {
  const request = properties.request;
  if (request.kind === 'plan') {
    return <PlanSummary request={request} />;
  }
  if (request.kind === 'permission') {
    return <PermissionSummary request={request} />;
  }
  const questions = request.content.questions ?? [];
  const answers = request.response?.answers ?? [];
  return (
    <div className="request-summary">
      <div className="request-summary-title">{request.status === 'answered' ? `You answered ${request.desk}'s ${questions.length > 1 ? 'questions' : 'question'}` : `${request.desk} asked you ${questions.length > 1 ? `${questions.length} questions` : 'a question'}`}</div>
      {questions.map((question, index) => {
        const answer = answers[index];
        let answerText = STATUS_WORDS[request.status] ?? '';
        if (answer !== undefined) {
          const parts = [...answer.selected];
          if (answer.other) {
            parts.push(`"${answer.other}"`);
          }
          answerText = parts.join(', ');
        }
        return (
          <div key={question.question} className="request-summary-row">
            <span className="request-summary-question">· {question.question}</span>
            <span className={answer !== undefined ? 'request-summary-answer' : 'request-summary-answer muted'}>→ {answerText}</span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * A plan in the transcript: its title and decision, opening to show the plan.
 * @param properties The plan request.
 * @returns The summary.
 */
function PlanSummary(properties: { request: UserRequest }) {
  const request = properties.request;
  const [open, setOpen] = useState(false);
  let status = STATUS_WORDS[request.status] ?? '';
  let tone = 'muted';
  if (request.status === 'answered' && request.response?.decision === 'approve') {
    status = 'you approved it';
    tone = 'profit';
  } else if (request.status === 'answered') {
    status = 'you asked for changes';
    tone = 'warning-text';
  }
  return (
    <div className="request-summary">
      <button type="button" className={open ? 'tool-group-summary open' : 'tool-group-summary'} aria-expanded={open} onClick={() => setOpen(!open)}>
        Presented a plan: {request.content.title}
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <span className={`request-summary-status ${tone}`}>{status}</span>
      {request.response?.feedback ? <div className="request-summary-feedback">Your feedback: {request.response.feedback}</div> : null}
      {open && (
        <div className="plan-body">
          <MarkdownText text={request.content.plan ?? ''} />
        </div>
      )}
    </div>
  );
}

/**
 * A permission request in the transcript: the tool, your decision, and the call's result when it ran.
 * @param properties The permission request.
 * @returns The summary.
 */
function PermissionSummary(properties: { request: UserRequest }) {
  const request = properties.request;
  const decision = request.response?.decision;
  let status = STATUS_WORDS[request.status] ?? '';
  let tone = 'muted';
  if (decision === 'allow_once') {
    status = 'you allowed it once';
    tone = 'profit';
  } else if (decision === 'always_allow') {
    status = 'you allowed it from now on';
    tone = 'profit';
  } else if (decision === 'deny') {
    status = request.response?.reason ? `you denied it: ${request.response.reason}` : 'you denied it';
    tone = 'loss';
  }
  return (
    <div className="request-summary">
      <div className="request-summary-title">
        Asked permission to run <span className="mono">{request.content.tool_name}</span>
      </div>
      <span className={`request-summary-status ${tone}`}>{status}</span>
      {request.response?.result ? <pre className="request-summary-result">{request.response.result}</pre> : null}
    </div>
  );
}
