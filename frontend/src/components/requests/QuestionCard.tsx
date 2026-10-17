import { type KeyboardEvent, useEffect, useRef, useState } from 'react';

import { apiClient } from '../../api/apiClient';
import type { QuestionAnswer, RequestQuestion, UserRequest } from '../../api/types';
import { MarkdownText } from '../MarkdownText';

/** What the user has chosen so far for one question. */
interface Draft {
  selected: string[];
  other: string;
}

/** What the question card shows. */
interface QuestionCardProperties {
  request: UserRequest;
  onDone: () => void;
}

/**
 * A desk's questions as Claude Code shows them: a tab per question when there are several, numbered options with descriptions, check boxes for multiple choice, an Other box, a preview beside the options, and a review step before sending.
 * @param properties The question request, and what to call once it is answered or dismissed.
 * @returns The card.
 */
export function QuestionCard(properties: QuestionCardProperties) {
  const request = properties.request;
  const questions = request.content.questions ?? [];
  const many = questions.length > 1;
  const [tab, setTab] = useState(0);
  const [drafts, setDrafts] = useState<Draft[]>(() => questions.map(() => ({ selected: [], other: '' })));
  const [highlighted, setHighlighted] = useState(0);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cardReference = useRef<HTMLDivElement>(null);
  const reviewing = many && tab === questions.length;
  const question: RequestQuestion | null = reviewing ? null : questions[tab];

  useEffect(() => {
    cardReference.current?.focus();
  }, [
    request.request_id,
  ]);

  useEffect(() => {
    setHighlighted(0);
  }, [
    tab,
  ]);

  /**
   * Whether a question has an answer.
   * @param index The question's position.
   * @returns True when an option is chosen or Other has text.
   */
  function isAnswered(index: number): boolean {
    const draft = drafts[index];
    return draft.selected.length > 0 || draft.other.trim().length > 0;
  }

  /**
   * Replaces the draft of one question.
   * @param index The question's position.
   * @param draft The new draft.
   */
  function setDraft(index: number, draft: Draft): void {
    setDrafts((current) => current.map((item, position) => (position === index ? draft : item)));
  }

  /**
   * Chooses an option: toggles it for multiple choice; for single choice selects it and moves on, sending at once when it is the only question.
   * @param label The option's label.
   */
  function choose(label: string): void {
    if (question === null) {
      return;
    }
    const draft = drafts[tab];
    if (question.multi_select) {
      const selected = draft.selected.includes(label) ? draft.selected.filter((item) => item !== label) : [...draft.selected, label];
      setDraft(tab, { ...draft, selected });
      return;
    }
    const next = { selected: [label], other: '' };
    setDraft(tab, next);
    if (!many) {
      void submit([next]);
      return;
    }
    setTab(tab + 1);
  }

  /**
   * Sends the answers.
   * @param finalDrafts The drafts to send, when they were just changed and the state has not caught up yet.
   */
  async function submit(finalDrafts: Draft[] = drafts): Promise<void> {
    setSending(true);
    setError(null);
    try {
      const answers: QuestionAnswer[] = finalDrafts.map((draft) => ({ selected: draft.selected, other: draft.other.trim() }));
      await apiClient.answerQuestions(request.request_id, answers);
      properties.onDone();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSending(false);
    }
  }

  /** Closes the questions without answering; the desk is told to use its own judgment. */
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

  /**
   * Keyboard control as in Claude Code: arrows move, numbers and Enter choose, Tab and the side arrows switch questions.
   * @param event The key event.
   */
  function handleKey(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.target instanceof HTMLInputElement || question === null) {
      return;
    }
    const count = question.options.length + 1;
    const number = Number.parseInt(event.key, 10);
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlighted((index) => (index + 1) % count);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlighted((index) => (index - 1 + count) % count);
    } else if (event.key === 'Enter' && highlighted < question.options.length) {
      event.preventDefault();
      choose(question.options[highlighted].label);
    } else if (number >= 1 && number <= question.options.length) {
      event.preventDefault();
      setHighlighted(number - 1);
      choose(question.options[number - 1].label);
    } else if (many && (event.key === 'ArrowRight' || (event.key === 'Tab' && !event.shiftKey))) {
      event.preventDefault();
      setTab(Math.min(tab + 1, questions.length));
    } else if (many && (event.key === 'ArrowLeft' || (event.key === 'Tab' && event.shiftKey))) {
      event.preventDefault();
      setTab(Math.max(tab - 1, 0));
    }
  }

  const allAnswered = questions.every((_, index) => isAnswered(index));
  const highlightedOption = question !== null && highlighted < question.options.length ? question.options[highlighted] : null;
  const hasPreview = question !== null && question.options.some((option) => option.preview);

  return (
    <div className="request-card question-card" ref={cardReference} tabIndex={-1} onKeyDown={handleKey}>
      <div className="request-card-top">
        <span className="request-card-from">
          <strong>{request.desk}</strong> asks you {many ? `${questions.length} questions` : 'a question'}
        </span>
        <button type="button" className="icon-button" onClick={() => void dismiss()} disabled={sending} aria-label="Dismiss without answering" title="Dismiss without answering; the desk will use its own judgment">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      {many && (
        <div className="question-tabs" role="tablist">
          {questions.map((item, index) => (
            <button key={item.question} type="button" role="tab" aria-selected={tab === index} className={tab === index ? 'question-tab active' : 'question-tab'} onClick={() => setTab(index)}>
              {isAnswered(index) ? <CheckMark /> : <span className="question-tab-dot" />}
              {item.header}
            </button>
          ))}
          <button type="button" role="tab" aria-selected={reviewing} className={reviewing ? 'question-tab active' : 'question-tab'} onClick={() => setTab(questions.length)}>
            Submit
          </button>
        </div>
      )}
      {question !== null && (
        <>
          {!many && <span className="question-chip">{question.header}</span>}
          <div className="question-text">{question.question}</div>
          {question.multi_select && <div className="question-hint">Choose all that apply.</div>}
          <div className={hasPreview ? 'question-body with-preview' : 'question-body'}>
            <ul className="question-options" role={question.multi_select ? 'group' : 'listbox'}>
              {question.options.map((option, index) => {
                const chosen = drafts[tab].selected.includes(option.label);
                let className = 'question-option';
                if (chosen) {
                  className = `${className} chosen`;
                }
                if (index === highlighted) {
                  className = `${className} highlighted`;
                }
                return (
                  <li key={option.label} className={className} role="option" aria-selected={chosen} onMouseEnter={() => setHighlighted(index)} onClick={() => choose(option.label)}>
                    {question.multi_select ? <span className={chosen ? 'option-box checked' : 'option-box'}>{chosen && <CheckMark />}</span> : <span className="option-key">{index + 1}</span>}
                    <span className="option-text">
                      <span className="option-label">{option.label}</span>
                      <span className="option-description">{option.description}</span>
                    </span>
                    {!question.multi_select && chosen && <CheckMark />}
                  </li>
                );
              })}
              <li className={highlighted === question.options.length ? 'question-option other highlighted' : 'question-option other'} onMouseEnter={() => setHighlighted(question.options.length)}>
                <span className="option-key">{question.options.length + 1}</span>
                <input
                  className="option-other"
                  value={drafts[tab].other}
                  placeholder="Other: type your own answer"
                  onFocus={() => setHighlighted(question.options.length)}
                  onChange={(change) => setDraft(tab, { selected: question.multi_select ? drafts[tab].selected : [], other: change.target.value })}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && drafts[tab].other.trim().length > 0) {
                      event.preventDefault();
                      if (!many) {
                        void submit();
                      } else {
                        setTab(tab + 1);
                      }
                    }
                  }}
                />
              </li>
            </ul>
            {hasPreview && (
              <div className="question-preview">
                {highlightedOption?.preview ? <MarkdownText text={highlightedOption.preview} /> : <span className="muted small">No preview for this choice.</span>}
              </div>
            )}
          </div>
        </>
      )}
      {reviewing && (
        <div className="question-review">
          <div className="question-text">Review your answers</div>
          {questions.map((item, index) => (
            <div key={item.question} className="question-review-row">
              <span className="muted">{item.question}</span>
              <span>{answerText(drafts[index]) || <span className="error-text">Not answered yet</span>}</span>
            </div>
          ))}
        </div>
      )}
      {error !== null && <p className="error-text small">{error}</p>}
      <div className="request-card-actions">
        <span className="request-card-hint">{question !== null ? '↑↓ to move · number or Enter to choose' : ''}{many && question !== null ? ' · Tab for the next question' : ''}</span>
        {(question === null || question.multi_select || many || drafts[tab].other.trim().length > 0) && (
          <button
            type="button"
            className="primary"
            disabled={sending || (reviewing ? !allAnswered : !isAnswered(tab))}
            onClick={() => {
              if (!many || reviewing) {
                void submit();
              } else {
                setTab(tab + 1);
              }
            }}
          >
            {!many || reviewing ? 'Submit' : 'Next'}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * One answer in words, for the review step.
 * @param draft The answer.
 * @returns The chosen labels and the Other text, joined.
 */
function answerText(draft: Draft): string {
  const parts = [...draft.selected];
  if (draft.other.trim().length > 0) {
    parts.push(`"${draft.other.trim()}"`);
  }
  return parts.join(', ');
}

/**
 * A small tick.
 * @returns The icon.
 */
function CheckMark() {
  return (
    <svg className="check-mark" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
