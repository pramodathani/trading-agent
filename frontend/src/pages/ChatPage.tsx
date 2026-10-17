import { type ClipboardEvent, type DragEvent, type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { AgentEvent, Attachment } from '../api/types';
import { AttachmentList } from '../components/AttachmentList';
import { useLiveEvents, useStreamingTexts } from '../hooks/useLiveEvents';
import { useDesks } from '../layout/desksContext';
import { useSelectedDesk } from '../layout/selectedDeskStore';
import { chatTurnBuilder, type ChatItem, type ChatTurn, type SteeringStep, type ToolStep } from '../utilities/chatTurnBuilder';
import { eventDescriber } from '../utilities/eventDescriber';
import { eventMerger } from '../utilities/eventMerger';
import { formatter } from '../utilities/formatter';

const JOURNAL_LIMIT = 1500;
const ACCEPTED_FILES = '.png,.jpg,.jpeg,.webp,.gif,.pdf,.docx,.xlsx,.csv,.tsv,.txt,.md,.json';
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

/** A file added to the message being written, uploaded at once. */
interface PendingFile {
  localId: string;
  fileName: string;
  status: 'uploading' | 'ready' | 'failed';
  attachment: Attachment | null;
  error: string | null;
  previewAddress: string | null;
}

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
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const bottomReference = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const pendingReference = useRef<PendingFile[]>([]);
  pendingReference.current = pending;
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

  useEffect(() => {
    return () => {
      for (const item of pendingReference.current) {
        if (item.previewAddress !== null) {
          URL.revokeObjectURL(item.previewAddress);
        }
      }
      setPending([]);
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

  const readyFiles = pending.filter((item) => item.status === 'ready');
  const uploading = pending.some((item) => item.status === 'uploading');
  const canSend = !sending && !uploading && (draft.trim().length > 0 || readyFiles.length > 0);

  /**
   * Changes one pending file.
   * @param localId The file's id on this page.
   * @param changes The fields to change.
   */
  function updatePending(localId: string, changes: Partial<PendingFile>): void {
    setPending((current) => current.map((item) => (item.localId === localId ? { ...item, ...changes } : item)));
  }

  /**
   * Adds files to the message and uploads each at once.
   * @param files The files chosen, dropped or pasted.
   */
  function addFiles(files: File[]): void {
    for (const file of files) {
      const localId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const previewAddress = file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
      setPending((current) => [
        ...current,
        {
          localId,
          fileName: file.name || 'pasted picture',
          status: 'uploading',
          attachment: null,
          error: null,
          previewAddress,
        },
      ]);
      apiClient.uploadAttachment(deskName, file).then(
        (attachment) => updatePending(localId, { status: 'ready', attachment }),
        (failure: unknown) => updatePending(localId, { status: 'failed', error: failure instanceof Error ? failure.message : String(failure) }),
      );
    }
  }

  /**
   * Takes a file off the message.
   * @param localId The file's id on this page.
   */
  function removePending(localId: string): void {
    const item = pending.find((candidate) => candidate.localId === localId);
    if (item?.previewAddress) {
      URL.revokeObjectURL(item.previewAddress);
    }
    setPending((current) => current.filter((candidate) => candidate.localId !== localId));
  }

  /** Empties the list of files once they are sent. */
  function clearPending(): void {
    for (const item of pending) {
      if (item.previewAddress !== null) {
        URL.revokeObjectURL(item.previewAddress);
      }
    }
    setPending([]);
  }

  /**
   * Adds pictures pasted into the message box.
   * @param event The paste event.
   */
  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>): void {
    const files = Array.from(event.clipboardData.files);
    if (files.length > 0) {
      event.preventDefault();
      addFiles(files);
    }
  }

  /**
   * Shows that files can be dropped while they are dragged over the box.
   * @param event The drag event.
   */
  function handleDragOver(event: DragEvent<HTMLFormElement>): void {
    if (event.dataTransfer.types.includes('Files')) {
      event.preventDefault();
      setDragging(true);
    }
  }

  /**
   * Adds files dropped on the box.
   * @param event The drop event.
   */
  function handleDrop(event: DragEvent<HTMLFormElement>): void {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  }

  /**
   * Sends the draft and its files to the desk.
   * @param event The form's submit event, if any.
   */
  async function send(event?: FormEvent): Promise<void> {
    event?.preventDefault();
    const text = draft.trim();
    if (!canSend) {
      return;
    }
    setSending(true);
    setSendError(null);
    try {
      const attachmentIds = readyFiles.map((item) => (item.attachment as Attachment).attachment_id);
      await apiClient.sendMessage(deskName, text, attachmentIds);
      setDraft('');
      clearPending();
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
          item.type === 'turn' ? <TurnView key={itemKey(item)} deskName={deskName} turn={item} streamingText={streams.get(item.triggerId) ?? ''} /> : <LooseEventView key={itemKey(item)} event={item.event} />,
        )}
        <div ref={bottomReference} />
      </div>
      <form className={dragging ? 'chat-input dragging' : 'chat-input'} onSubmit={send} onDragOver={handleDragOver} onDragLeave={() => setDragging(false)} onDrop={handleDrop}>
        {pending.length > 0 && (
          <div className="pending-files">
            {pending.map((item) => (
              <span key={item.localId} className={`pending-file ${item.status}`} title={item.error ?? item.fileName}>
                {item.previewAddress !== null ? <img src={item.previewAddress} alt="" /> : <span className="attachment-badge">{item.fileName.split('.').pop()?.toUpperCase() ?? 'FILE'}</span>}
                <span className="pending-file-name">{item.fileName}</span>
                <span className="small muted">{pendingStatus(item)}</span>
                <button type="button" className="pending-remove" onClick={() => removePending(item.localId)} aria-label={`Remove ${item.fileName}`}>
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
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
          placeholder={`Message ${deskName}, or type / for commands. Enter sends; Shift and Enter adds a line. Drop or paste pictures and documents here.`}
          onChange={(change) => setDraft(change.target.value)}
          onKeyDown={handleKey}
          onPaste={handlePaste}
        />
        <input
          ref={fileInput}
          type="file"
          multiple
          accept={ACCEPTED_FILES}
          hidden
          onChange={(change) => {
            addFiles(Array.from(change.target.files ?? []));
            change.target.value = '';
          }}
        />
        <span className="button-row">
          <button type="button" onClick={() => fileInput.current?.click()} title="Attach pictures or documents: PNG, JPEG, WebP, GIF, PDF, Word, Excel, CSV, text, Markdown or JSON, up to 20 MB each">
            Attach
          </button>
          {desk !== null && desk.state !== 'idle' && (
            <button className="danger" type="button" onClick={stop} title="Cancel the running turn at once">
              Stop
            </button>
          )}
          <button className="primary" type="submit" disabled={!canSend}>
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
 * Describes where a pending file's upload has got to.
 * @param item The file.
 * @returns A short status word.
 */
function pendingStatus(item: PendingFile): string {
  if (item.status === 'uploading') {
    return 'uploading…';
  }
  if (item.status === 'failed') {
    return `not attached: ${item.error ?? 'the upload failed'}`;
  }
  if (item.attachment !== null && item.attachment.kind === 'document' && item.attachment.text_characters === null) {
    return `attached, but ${item.attachment.problem || 'its text cannot be read'}`;
  }
  return 'ready';
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
  deskName: string;
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
        {turn.text.length > 0 && <pre>{turn.text}</pre>}
        <AttachmentList deskName={properties.deskName} attachments={turn.attachments} />
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
