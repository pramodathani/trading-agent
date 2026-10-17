import { type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { AgentEvent } from '../api/types';
import { useLiveEvents, useStreamingTexts } from '../hooks/useLiveEvents';
import { useDesks } from '../layout/desksContext';
import { useSelectedDesk } from '../layout/selectedDeskStore';
import { chatTurnBuilder, type ChatItem, type ChatTurn, type SteeringStep, type ToolStep } from '../utilities/chatTurnBuilder';
import { eventDescriber } from '../utilities/eventDescriber';
import { eventMerger } from '../utilities/eventMerger';
import { formatter } from '../utilities/formatter';

const JOURNAL_LIMIT = 1500;
const SLASH_COMMANDS = [
  '/status',
  '/usage',
  '/model',
  '/compact',
  '/new',
  '/rollover',
  '/pause',
  '/resume',
  '/help',
];

/**
 * Talk to the chosen desk: today's turns with every tool call, live updates, and a box to send messages and slash commands.
 * @returns The page.
 */
export function ChatPage() {
  const deskName = useSelectedDesk();
  const desks = useDesks();
  const liveEvents = useLiveEvents();
  const streams = useStreamingTexts();
  const [loaded, setLoaded] = useState<AgentEvent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const bottomReference = useRef<HTMLDivElement>(null);
  const desk = desks.document?.desks.find((candidate) => candidate.name === deskName) ?? null;

  useEffect(() => {
    let cancelled = false;
    setLoaded([]);
    setLoadError(null);
    apiClient
      .deskJournal(deskName, JOURNAL_LIMIT)
      .then((document) => {
        if (!cancelled) {
          setLoaded(document.events);
        }
      })
      .catch((failure: unknown) => {
        if (!cancelled) {
          setLoadError(failure instanceof Error ? failure.message : String(failure));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    deskName,
  ]);

  const items = useMemo(() => {
    const deskLive = liveEvents.filter((event) => event.desk === deskName);
    return chatTurnBuilder.build(eventMerger.merge(loaded, deskLive));
  }, [
    loaded,
    liveEvents,
    deskName,
  ]);

  const lastItemKey = items.length > 0 ? itemKey(items[items.length - 1]) : '';
  const lastTurn = items.length > 0 ? items[items.length - 1] : null;
  const lastSize = lastTurn !== null && lastTurn.type === 'turn' ? lastTurn.steps.length + (lastTurn.answer ?? '').length + (streams.get(lastTurn.triggerId) ?? '').length : 0;

  useEffect(() => {
    bottomReference.current?.scrollIntoView({
      block: 'end',
    });
  }, [
    lastItemKey,
    lastSize,
    deskName,
  ]);

  /**
   * Sends the draft to the desk.
   * @param event The form's submit event, if any.
   */
  async function send(event?: FormEvent): Promise<void> {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || sending) {
      return;
    }
    setSending(true);
    setSendError(null);
    try {
      await apiClient.sendMessage(deskName, text);
      setDraft('');
    } catch (failure) {
      setSendError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSending(false);
    }
  }

  /** Stops the desk's running turn. */
  async function stop(): Promise<void> {
    setSendError(null);
    try {
      await apiClient.sendMessage(deskName, '/stop');
    } catch (failure) {
      setSendError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Sends on Enter; Shift and Enter starts a new line.
   * @param event The key event.
   */
  function handleKey(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  const suggestions = draft.startsWith('/') && !draft.includes(' ') ? SLASH_COMMANDS.filter((command) => command.startsWith(draft)) : [];

  return (
    <div className="chat-page">
      <div className="chat-header">
        <h1>Chat with {deskName}</h1>
        {desk !== null && (
          <span className="muted small">
            {desk.state}
            {desk.paused ? ', paused' : ''}
            {desk.queued > 0 ? `, ${desk.queued} waiting` : ''} · session <span className="mono">{desk.session_id ?? '—'}</span>
          </span>
        )}
      </div>
      <div className="chat-log">
        {loadError !== null && <p className="error-text">Could not read today&apos;s journal: {loadError}</p>}
        {items.length === 0 && loadError === null && <p className="muted">Nothing today yet. Say hello, or try /status.</p>}
        {items.map((item) =>
          item.type === 'turn' ? <TurnView key={itemKey(item)} turn={item} streamingText={streams.get(item.triggerId) ?? ''} /> : <LooseEventView key={itemKey(item)} event={item.event} />,
        )}
        <div ref={bottomReference} />
      </div>
      <form className="chat-input" onSubmit={send}>
        {suggestions.length > 0 && (
          <div className="slash-suggestions">
            {suggestions.map((command) => (
              <button key={command} type="button" onClick={() => setDraft(`${command} `)}>
                {command}
              </button>
            ))}
          </div>
        )}
        <textarea
          rows={2}
          value={draft}
          placeholder={`Message ${deskName}, or type / for commands. Enter sends; Shift and Enter adds a line.`}
          onChange={(change) => setDraft(change.target.value)}
          onKeyDown={handleKey}
        />
        <span className="button-row">
          {desk !== null && desk.state !== 'idle' && (
            <button className="danger" type="button" onClick={stop} title="Cancel the running turn at once">
              Stop
            </button>
          )}
          <button className="primary" type="submit" disabled={sending || !draft.trim()}>
            Send
          </button>
        </span>
        {sendError !== null && <p className="error-text small">{sendError}</p>}
        {desk !== null && desk.state !== 'idle' && <p className="muted small">The desk is working. A message you send now is handed to it at its next tool call; if the turn ends first, it becomes the next turn.</p>}
      </form>
    </div>
  );
}

/**
 * A stable key for a chat item.
 * @param item The item.
 * @returns The key.
 */
function itemKey(item: ChatItem): string {
  if (item.type === 'turn') {
    return item.triggerId;
  }
  return eventMerger.key(item.event);
}

/**
 * Describes where a turn has got to.
 * @param turn The turn.
 * @returns A short status line.
 */
function turnStatus(turn: ChatTurn): string {
  if (turn.stopped) {
    return 'stopped by you';
  }
  if (turn.finished) {
    return turn.backend !== null ? `answered by ${turn.backend}` : 'finished';
  }
  if (turn.started) {
    return 'working…';
  }
  if (turn.steeringOutcome === 'waiting') {
    return 'waiting for the running turn to pick it up at its next tool call';
  }
  if (turn.steeringOutcome === 'delivered') {
    return 'handed to the running turn';
  }
  if (turn.steeringOutcome === 'queued') {
    return 'the running turn ended first, so this is the next turn';
  }
  return 'waiting in the queue';
}

/** What a turn view shows. */
interface TurnViewProperties {
  turn: ChatTurn;
  streamingText: string;
}

/**
 * One turn: what woke the desk, its steps, the text it is writing, and its answer.
 * @param properties The turn and its streamed text.
 * @returns The turn's view.
 */
function TurnView(properties: TurnViewProperties) {
  const turn = properties.turn;
  const fromUser = turn.source === 'user_message';
  const status = turnStatus(turn);
  const showStream = turn.answer === null && !turn.finished && properties.streamingText.length > 0;
  return (
    <section className="turn">
      <div className={fromUser ? 'bubble user' : 'bubble trigger'}>
        <div className="bubble-meta">
          <span>{fromUser ? 'You' : eventDescriber.sourceWords(turn.source)}</span>
          <span className="mono">{formatter.time(turn.receivedAt)}</span>
        </div>
        <pre>{turn.text}</pre>
      </div>
      {turn.steps.length > 0 && (
        <div className="steps">
          {turn.steps.map((step, index) => {
            if (step.type === 'tool') {
              return <ToolCard key={step.callId || index} step={step} />;
            }
            if (step.type === 'steering') {
              return <SteeringView key={step.message.triggerId} step={step} />;
            }
            return (
              <div key={eventMerger.key(step.event)} className={`step-line tone-${eventDescriber.describe(step.event).tone}`}>
                {eventDescriber.describe(step.event).title}
              </div>
            );
          })}
        </div>
      )}
      {showStream && (
        <div className="bubble answer streaming">
          <div className="bubble-meta">
            <span>Writing…</span>
          </div>
          <pre>{properties.streamingText}</pre>
        </div>
      )}
      {turn.answer !== null && (
        <div className={turn.silent ? 'bubble answer silent' : 'bubble answer'}>
          <div className="bubble-meta">
            <span>{turn.silent ? 'Nothing to do' : 'Desk'}</span>
          </div>
          <pre>{turn.answer}</pre>
        </div>
      )}
      {turn.error !== null && <div className="bubble failed">The turn failed: {turn.error}</div>}
      <div className={turn.finished || turn.steeringOutcome === 'delivered' ? 'turn-status muted small' : 'turn-status working small'}>{status}</div>
    </section>
  );
}

/**
 * A message the user sent while the turn was running, at the point it arrived.
 * @param properties The steering step.
 * @returns The view.
 */
function SteeringView(properties: { step: SteeringStep }) {
  const message = properties.step.message;
  return (
    <div className="steering-message">
      <div className="bubble-meta">
        <span>You, while it worked</span>
        <span className="mono">{formatter.time(message.receivedAt)}</span>
      </div>
      <pre>{message.text}</pre>
      <div className="muted small">{turnStatus(message)}</div>
    </div>
  );
}

/**
 * One tool call, folded, with its arguments and result inside.
 * @param properties The step.
 * @returns The card.
 */
function ToolCard(properties: { step: ToolStep }) {
  const step = properties.step;
  let state = 'running…';
  if (step.resultText !== null) {
    state = step.isError ? 'failed' : 'done';
  }
  return (
    <details className={step.isError ? 'tool-card failed' : 'tool-card'}>
      <summary>
        <span className="mono">{step.name}</span>
        <span className="muted small">{state}</span>
      </summary>
      <div className="tool-card-body">
        <span className="muted small">Arguments</span>
        <pre>{step.argumentsText}</pre>
        {step.resultText !== null && (
          <>
            <span className="muted small">Result</span>
            <pre>{step.resultText}</pre>
          </>
        )}
      </div>
    </details>
  );
}

/**
 * An event that happened outside any turn.
 * @param properties The event.
 * @returns A one-line view.
 */
function LooseEventView(properties: { event: AgentEvent }) {
  const description = eventDescriber.describe(properties.event);
  return (
    <div className={`loose-event tone-${description.tone}`}>
      <span className="mono muted">{formatter.time(properties.event.created_at)}</span> {description.title}
      {description.detail && <pre className="muted small">{description.detail}</pre>}
    </div>
  );
}
