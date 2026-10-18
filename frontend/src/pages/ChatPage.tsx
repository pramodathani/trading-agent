import { type ClipboardEvent, type DragEvent, type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { AgentEvent, Attachment, DeskCommand } from '../api/types';
import { AttachmentList } from '../components/AttachmentList';
import { MarkdownText } from '../components/MarkdownText';
import { ModelMenu } from '../components/ModelMenu';
import { PictureThumbnail } from '../components/PictureThumbnail';
import { RequestDock } from '../components/requests/RequestDock';
import { RequestSummary } from '../components/requests/RequestSummary';
import { elapsedText, TurnProgress } from '../components/TurnProgress';
import { useCloseOnBack } from '../hooks/useCloseOnBack';
import { useLiveEvents, useStreamingTexts } from '../hooks/useLiveEvents';
import { usePhoneLayout } from '../hooks/usePhoneLayout';
import { usePolled } from '../hooks/usePolled';
import { useDesks } from '../layout/desksContext';
import { useSelectedDesk } from '../layout/selectedDeskStore';
import { SidePanel } from '../sidePanel/SidePanel';
import { sidePanelStore, useSidePanelOpen } from '../sidePanel/sidePanelStore';
import { chatTurnBuilder, type ChatItem, type ChatTurn, type SteeringStep, type ToolStep, type TurnStep } from '../utilities/chatTurnBuilder';
import { eventDescriber } from '../utilities/eventDescriber';
import { eventMerger } from '../utilities/eventMerger';
import { formatter } from '../utilities/formatter';
import { toolDescriber } from '../utilities/toolDescriber';
import { VoiceInput } from '../utilities/voiceInput';

const JOURNAL_LIMIT = 1500;
const BOTTOM_SLACK_PIXELS = 48;
const REQUESTS_REFRESH_MILLISECONDS = 30000;
const REQUEST_EVENT_KINDS = new Set([
  'user_request',
  'user_response',
]);
const ACCEPTED_FILES = '.png,.jpg,.jpeg,.webp,.gif,.pdf,.docx,.xlsx,.csv,.tsv,.txt,.md,.json';
const COMMANDS_REFRESH_MILLISECONDS = 60000;

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
  const panelOpen = useSidePanelOpen();
  const phone = usePhoneLayout();
  useCloseOnBack(phone && panelOpen, closeSidePanel);
  const liveEvents = useLiveEvents();
  const requests = usePolled(() => apiClient.requests('pending'), REQUESTS_REFRESH_MILLISECONDS);
  const commands = usePolled(() => apiClient.deskCommands(deskName), COMMANDS_REFRESH_MILLISECONDS, deskName);
  const refreshRequests = requests.refresh;
  const lastLiveEvent = liveEvents.length > 0 ? liveEvents[liveEvents.length - 1] : null;
  const streams = useStreamingTexts();
  const [loaded, setLoaded] = useState<AgentEvent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const scrollReference = useRef<HTMLDivElement>(null);
  const columnReference = useRef<HTMLDivElement>(null);
  const stuckToBottom = useRef(true);
  const voiceInput = useMemo(() => new VoiceInput(), []);
  const voiceBase = useRef('');
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
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

  const deskEvents = useMemo(() => {
    const deskLive = liveEvents.filter((event) => event.desk === deskName);
    return eventMerger.merge(loaded, deskLive);
  }, [
    loaded,
    liveEvents,
    deskName,
  ]);

  useEffect(() => {
    if (lastLiveEvent !== null && REQUEST_EVENT_KINDS.has(lastLiveEvent.kind)) {
      refreshRequests();
    }
  }, [
    lastLiveEvent,
    refreshRequests,
  ]);

  const deskRequests = (requests.data ?? []).filter((request) => request.desk === deskName);

  const items = useMemo(() => chatTurnBuilder.build(deskEvents), [
    deskEvents,
  ]);

  const lastItemKey = items.length > 0 ? itemKey(items[items.length - 1]) : '';
  const lastTurn = items.length > 0 ? items[items.length - 1] : null;
  const lastSize = lastTurn !== null && lastTurn.type === 'turn' ? lastTurn.steps.length + (lastTurn.answer ?? '').length + (streams.get(lastTurn.triggerId) ?? '').length : 0;

  useEffect(() => {
    stuckToBottom.current = true;
    return () => {
      voiceInput.stop();
    };
  }, [
    deskName,
    voiceInput,
  ]);

  /** Starts turning speech into text in the message box, or stops when already listening. */
  function toggleListening(): void {
    if (listening) {
      voiceInput.stop();
      return;
    }
    setVoiceError(null);
    voiceBase.current = draft.trim();
    setListening(true);
    voiceInput.start({
      onText: (text) => {
        setDraft(voiceBase.current.length > 0 ? `${voiceBase.current} ${text}` : text);
      },
      onEnd: () => setListening(false),
      onError: (message) => setVoiceError(message),
    });
  }

  useEffect(() => {
    if (stuckToBottom.current) {
      scrollToBottom();
    }
  }, [
    lastItemKey,
    lastSize,
    deskName,
  ]);

  useEffect(() => {
    const scroller = scrollReference.current;
    const column = columnReference.current;
    if (scroller === null || column === null) {
      return;
    }
    const observer = new ResizeObserver(() => {
      if (stuckToBottom.current) {
        scrollToBottom();
      }
    });
    observer.observe(scroller);
    observer.observe(column);
    return () => {
      observer.disconnect();
    };
  }, []);

  /** Scrolls the chat to its newest line. */
  function scrollToBottom(): void {
    const scroller = scrollReference.current;
    if (scroller !== null) {
      scroller.scrollTop = scroller.scrollHeight;
    }
  }

  /** Remembers whether the user is reading the newest lines, so the chat follows new ones only then. */
  function handleScroll(): void {
    const scroller = scrollReference.current;
    if (scroller === null) {
      return;
    }
    stuckToBottom.current = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < BOTTOM_SLACK_PIXELS;
  }

  const busy = desk !== null && desk.state !== 'idle';
  const modeWords = desk !== null && desk.mode === 'live' ? 'Live orders' : 'Dry run';
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
    stuckToBottom.current = true;
    voiceInput.stop();
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
    if (event.key === 'Enter' && !event.shiftKey && !phone) {
      event.preventDefault();
      void send();
    }
  }

  const suggestions = draft.startsWith('/') && !draft.includes(' ') ? commandSuggestions(commands.data?.commands ?? [], draft) : [];

  return (
    <div className={panelOpen ? 'chat-page with-panel' : 'chat-page'}>
      <div className="chat-scroll" ref={scrollReference} onScroll={handleScroll}>
        <div className="chat-column" ref={columnReference}>
          <div className="chat-header">
            <h1>Chat with {deskName}</h1>
            {desk !== null && (
              <span className="muted small">
                {desk.state}
                {desk.paused ? ', paused' : ''}
                {desk.queued > 0 ? `, ${desk.queued} waiting` : ''}
              </span>
            )}
          </div>
          <div className="chat-log">
            {loadError !== null && <p className="error-text">Could not read today&apos;s journal: {loadError}</p>}
            {items.length === 0 && loadError === null && <p className="muted">Nothing today yet. Say hello, or try /status.</p>}
            {items.map((item) =>
              item.type === 'turn' ? <TurnView key={itemKey(item)} deskName={deskName} turn={item} streamingText={streams.get(item.triggerId) ?? ''} /> : <LooseEventView key={itemKey(item)} deskName={deskName} event={item.event} />,
            )}
          </div>
        </div>
      </div>
      <div className="composer-area">
        <RequestDock requests={deskRequests} onDone={refreshRequests} />
        <form className={dragging ? 'composer dragging' : 'composer'} onSubmit={send} onDragOver={handleDragOver} onDragLeave={() => setDragging(false)} onDrop={handleDrop}>
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
                <button key={command.name} type="button" title={command.description} onClick={() => setDraft(`${command.name} `)}>
                  {command.name}
                </button>
              ))}
            </div>
          )}
          <div className="composer-row">
            <button type="button" className="icon-button" onClick={() => fileInput.current?.click()} aria-label="Attach files" title="Attach pictures or documents: PNG, JPEG, WebP, GIF, PDF, Word, Excel, CSV, text, Markdown or JSON, up to 20 MB each">
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M8 3v10M3 8h10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
            {phone && desk !== null && <ModelMenu desk={desk} onChanged={desks.refresh} />}
            <textarea
              rows={1}
              value={draft}
              placeholder={composerHint(deskName, busy, phone)}
              title="Enter sends; Shift and Enter adds a line. Drop or paste pictures and documents here."
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
            {busy && (
              <button type="button" className="icon-button stop-button" onClick={stop} aria-label="Stop the running turn" title="Stop the running turn at once">
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.4" />
                  <rect x="5.75" y="5.75" width="4.5" height="4.5" rx="0.8" fill="currentColor" />
                </svg>
              </button>
            )}
            <button
              type="button"
              className={listening ? 'icon-button mic-button listening' : 'icon-button mic-button'}
              onClick={toggleListening}
              disabled={!voiceInput.isSupported()}
              aria-pressed={listening}
              aria-label={listening ? 'Stop voice input' : 'Speak your message'}
              title={voiceInput.isSupported() ? (listening ? 'Listening. Press again to stop.' : 'Speak your message') : 'This browser cannot turn speech into text. Chrome and Edge can.'}
            >
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <rect x="5.75" y="2" width="4.5" height="7.5" rx="2.25" fill="none" stroke="currentColor" strokeWidth="1.4" />
                <path d="M3.5 7.75a4.5 4.5 0 0 0 9 0M8 12.25V14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
            </button>
            {canSend && (
              <button className="primary send-button" type="submit" aria-label="Send">
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M8 13V3M3.5 7.5L8 3l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            )}
          </div>
        </form>
        <div className={phone && !listening ? 'composer-footer hidden' : 'composer-footer'}>
          <span className={listening ? 'composer-hint listening' : 'composer-hint'}>{listening ? 'Listening… press the microphone again to stop' : modeWords}</span>
          <span className="spacer" />
          {!phone && desk !== null && <ModelMenu desk={desk} onChanged={desks.refresh} />}
        </div>
        {voiceError !== null && <p className="error-text small composer-note">{voiceError}</p>}
        {sendError !== null && <p className="error-text small composer-note">{sendError}</p>}
      </div>
      {phone && panelOpen && <div className="sheet-backdrop" onClick={() => sidePanelStore.close()} aria-hidden="true" />}
      {panelOpen && <SidePanel deskName={deskName} desk={desk} events={deskEvents} />}
    </div>
  );
}

/**
 * The grey hint in the empty message box.
 * @param deskName The desk being talked to.
 * @param busy Whether the desk is in the middle of a turn.
 * @param phone Whether the phone layout is in use, where Enter adds a line and the send button sends.
 * @returns The hint.
 */
function composerHint(deskName: string, busy: boolean, phone: boolean): string {
  if (phone) {
    return busy ? `Steer ${deskName} at its next tool call` : `Message ${deskName}`;
  }
  return busy ? `Enter to hand a message to ${deskName} at its next tool call` : 'Enter to send, Shift+Enter for a new line, / for commands';
}

/** Hides the side panel. */
function closeSidePanel(): void {
  sidePanelStore.close();
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
  const inProgress = !turn.finished && !turn.stopped && turn.error === null && (turn.started || turn.steeringOutcome === null);
  let finishedStatus = status;
  if (turn.startedAt !== null && turn.finishedAt !== null) {
    const seconds = Math.max(0, Math.round((Date.parse(turn.finishedAt) - Date.parse(turn.startedAt)) / 1000));
    finishedStatus = `${status} · ${elapsedText(seconds)}`;
  }
  const showStream = turn.answer === null && !turn.finished && properties.streamingText.length > 0;
  return (
    <section className="turn">
      {turn.requestId !== null ? (
        <div className="answer-note" title={turn.text}>
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4 3v5a2 2 0 0 0 2 2h7M10 7l3 3-3 3" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Your response went to the desk <span className="mono">{formatter.time(turn.receivedAt)}</span>
        </div>
      ) : (
        <div className={fromUser ? 'bubble user' : 'bubble trigger'}>
          <div className="bubble-meta">
            <span>{fromUser ? 'You' : eventDescriber.sourceWords(turn.source)}</span>
            <span className="mono">{formatter.time(turn.receivedAt)}</span>
          </div>
          {turn.text.length > 0 && <pre>{turn.text}</pre>}
          <AttachmentList deskName={properties.deskName} attachments={turn.attachments} />
        </div>
      )}
      {turn.steps.length > 0 && (
        <div className="steps">
          {stepSegments(turn.steps).map((segment, index) => {
            if (segment.type === 'tools') {
              return <ToolGroup key={segment.steps[0].callId || index} deskName={properties.deskName} steps={segment.steps} />;
            }
            const step = segment.step;
            if (step.type === 'steering') {
              return <SteeringView key={step.message.triggerId} step={step} />;
            }
            if (step.type === 'tool') {
              return null;
            }
            if (step.type === 'request') {
              return <RequestSummary key={step.request.request_id} request={step.request} />;
            }
            if (step.event.kind === 'message') {
              return <DeskMessageView key={eventMerger.key(step.event)} deskName={properties.deskName} event={step.event} />;
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
          <MarkdownText text={properties.streamingText} />
        </div>
      )}
      {turn.answer !== null && (
        <div className={turn.silent ? 'bubble answer silent' : 'bubble answer'}>
          <div className="bubble-meta">
            <span>{turn.silent ? 'Nothing to do' : 'Desk'}</span>
          </div>
          <MarkdownText text={turn.answer} />
        </div>
      )}
      {turn.error !== null && <div className="bubble failed">The turn failed: {turn.error}</div>}
      {inProgress ? <TurnProgress turn={turn} streamingText={properties.streamingText} /> : <div className="turn-status muted small">{finishedStatus}</div>}
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

/** A run of tool calls shown as one folded line, or any other step shown on its own. */
type StepSegment = { type: 'tools'; steps: ToolStep[] } | { type: 'single'; step: TurnStep };

/**
 * Groups a turn's steps so that tool calls in a row become one segment.
 * @param steps The turn's steps, in order.
 * @returns The segments, in order.
 */
function stepSegments(steps: TurnStep[]): StepSegment[] {
  const segments: StepSegment[] = [];
  for (const step of steps) {
    const last = segments.length > 0 ? segments[segments.length - 1] : null;
    if (step.type === 'tool' && last !== null && last.type === 'tools') {
      last.steps.push(step);
    } else if (step.type === 'tool') {
      segments.push({
        type: 'tools',
        steps: [
          step,
        ],
      });
    } else {
      segments.push({
        type: 'single',
        step,
      });
    }
  }
  return segments;
}

/**
 * Tool calls in a row, folded into one summary line as Claude Code shows them; pictures the tools showed the model stay visible.
 * @param properties The desk and the tool calls.
 * @returns The group.
 */
function ToolGroup(properties: { deskName: string; steps: ToolStep[] }) {
  const [open, setOpen] = useState(false);
  const steps = properties.steps;
  const pictures = steps.filter((step) => step.picturePath !== null);
  return (
    <div className="tool-group">
      <button type="button" className={open ? 'tool-group-summary open' : 'tool-group-summary'} aria-expanded={open} onClick={() => setOpen(!open)}>
        {toolDescriber.summary(steps)}
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="tool-group-body">
          {steps.map((step, index) => (
            <ToolCard key={step.callId || index} deskName={properties.deskName} step={step} />
          ))}
        </div>
      )}
      {!open &&
        pictures.map((step) => (
          <div key={step.callId} className="tool-card-picture">
            <PictureThumbnail fileName={step.picturePath as string} loadKey={`${properties.deskName}/${step.picturePath}`} load={() => apiClient.deskPicture(properties.deskName, step.picturePath as string)} />
          </div>
        ))}
    </div>
  );
}

/**
 * One tool call, folded, with its arguments and result inside, and any picture it showed the model beneath.
 * @param properties The desk and the step.
 * @returns The card.
 */
function ToolCard(properties: { deskName: string; step: ToolStep }) {
  const step = properties.step;
  const deskName = properties.deskName;
  const picturePath = step.picturePath;
  let state = 'running…';
  if (step.resultText !== null) {
    state = step.isError ? 'failed' : 'done';
  }
  return (
    <div className="tool-step">
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
      {picturePath !== null && (
        <div className="tool-card-picture">
          <PictureThumbnail fileName={picturePath} loadKey={`${deskName}/${picturePath}`} load={() => apiClient.deskPicture(deskName, picturePath)} />
        </div>
      )}
    </div>
  );
}

/**
 * A message the desk sent with send_message or send_image: its text and any pictures, shown large.
 * @param properties The desk and the message event.
 * @returns The bubble.
 */
function DeskMessageView(properties: { deskName: string; event: AgentEvent }) {
  const payload = properties.event.payload;
  const text = typeof payload.text === 'string' ? payload.text : '';
  const attachments = Array.isArray(payload.attachments) ? (payload.attachments as Attachment[]) : [];
  const urgent = payload.urgent === true;
  let label = 'Message from the desk';
  if (attachments.length > 0) {
    label = 'Picture from the desk';
  }
  if (urgent) {
    label = 'Urgent message from the desk';
  }
  return (
    <div className={urgent ? 'bubble answer desk-message urgent' : 'bubble answer desk-message'}>
      <div className="bubble-meta">
        <span>{label}</span>
        <span className="mono">{formatter.time(properties.event.created_at)}</span>
      </div>
      {text.length > 0 && <MarkdownText text={text} />}
      <AttachmentList deskName={properties.deskName} attachments={attachments} large />
    </div>
  );
}

/**
 * An event that happened outside any turn.
 * @param properties The desk and the event.
 * @returns A one-line view, or a message bubble for a message the desk sent.
 */
function LooseEventView(properties: { deskName: string; event: AgentEvent }) {
  if (properties.event.kind === 'message') {
    return <DeskMessageView deskName={properties.deskName} event={properties.event} />;
  }
  const description = eventDescriber.describe(properties.event);
  return (
    <div className={`loose-event tone-${description.tone}`}>
      <span className="mono muted">{formatter.time(properties.event.created_at)}</span> {description.title}
      {description.detail && <pre className="muted small">{description.detail}</pre>}
    </div>
  );
}

/**
 * The commands whose names start with what the user has typed, each name once.
 * @param commands The desk's commands and skills, as GET /api/desks/{desk}/commands lists them.
 * @param draft What the user has typed, such as "/st".
 * @returns The matching entries, in the desk's order.
 */
function commandSuggestions(commands: DeskCommand[], draft: string): DeskCommand[] {
  const seen = new Set<string>();
  const matches: DeskCommand[] = [];
  for (const command of commands) {
    if (seen.has(command.name) || !command.name.startsWith(draft)) {
      continue;
    }
    seen.add(command.name);
    matches.push(command);
  }
  return matches;
}
