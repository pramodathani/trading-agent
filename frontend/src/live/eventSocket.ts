import type { AgentEvent } from '../api/types';
import { gatewayAddress } from '../api/gatewayAddress';
import { tokenStore } from '../auth/tokenStore';

const MOST_EVENTS_KEPT = 3000;
const FIRST_RETRY_MILLISECONDS = 1000;
const LONGEST_RETRY_MILLISECONDS = 15000;
const POLICY_VIOLATION = 1008;

export type ConnectionState = 'connecting' | 'open' | 'closed';

type Listener = () => void;

/** The one connection to the gateway's live event stream, shared by every page. */
export class EventSocket {
  private socket: WebSocket | null = null;
  private events: AgentEvent[] = [];
  private streams: ReadonlyMap<string, string> = new Map();
  private state: ConnectionState = 'closed';
  private retryMilliseconds = FIRST_RETRY_MILLISECONDS;
  private retryTimer: number | null = null;
  private wanted = false;
  private readonly listeners = new Set<Listener>();

  /** Opens the connection, and keeps reopening it after it drops, until stop() is called. */
  start(): void {
    this.wanted = true;
    if (this.socket === null) {
      this.open();
    }
  }

  /** Closes the connection for good, for example when the token is cleared. */
  stop(): void {
    this.wanted = false;
    if (this.retryTimer !== null) {
      window.clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.setState('closed');
  }

  /**
   * The events received since the page opened, oldest first.
   * @returns The events; the same array until a new event arrives.
   */
  received(): AgentEvent[] {
    return this.events;
  }

  /**
   * The text each running turn has streamed so far, before its final answer.
   * @returns The text, keyed by trigger id; the same map until it changes.
   */
  streamingTexts(): ReadonlyMap<string, string> {
    return this.streams;
  }

  /**
   * Whether the connection is open.
   * @returns The connection's state.
   */
  connectionState(): ConnectionState {
    return this.state;
  }

  /**
   * Registers a listener for new events and state changes.
   * @param listener Called after every change.
   * @returns A function that removes the listener.
   */
  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /** Opens one WebSocket and wires its handlers. */
  private open(): void {
    const token = tokenStore.current();
    if (token === null) {
      return;
    }
    const address = gatewayAddress.socketUrl(`/ws/events?token=${encodeURIComponent(token)}`);
    const socket = new WebSocket(address);
    this.socket = socket;
    this.setState('connecting');
    socket.addEventListener('open', () => {
      this.retryMilliseconds = FIRST_RETRY_MILLISECONDS;
      this.setState('open');
    });
    socket.addEventListener('message', (message) => {
      this.receive(message.data as string);
    });
    socket.addEventListener('close', (closing) => {
      this.socket = null;
      this.setState('closed');
      if (closing.code === POLICY_VIOLATION) {
        tokenStore.clear();
        return;
      }
      this.scheduleRetry();
    });
  }

  /**
   * Adds one received event.
   * @param text The event as JSON.
   */
  private receive(text: string): void {
    let event: AgentEvent;
    try {
      event = JSON.parse(text) as AgentEvent;
    } catch {
      return;
    }
    const triggerId = typeof event.payload.trigger_id === 'string' ? event.payload.trigger_id : null;
    if (event.kind === 'text_delta') {
      if (triggerId !== null) {
        const streams = new Map(this.streams);
        streams.set(triggerId, (streams.get(triggerId) ?? '') + String(event.payload.text ?? ''));
        this.streams = streams;
        this.notify();
      }
      return;
    }
    if (triggerId !== null && this.streams.has(triggerId) && (event.kind === 'text' || event.kind === 'tool_call')) {
      const streams = new Map(this.streams);
      streams.delete(triggerId);
      this.streams = streams;
    }
    const events = [
      ...this.events,
      event,
    ];
    if (events.length > MOST_EVENTS_KEPT) {
      events.splice(0, events.length - MOST_EVENTS_KEPT);
    }
    this.events = events;
    this.notify();
  }

  /** Reopens the connection after a growing pause. */
  private scheduleRetry(): void {
    if (!this.wanted) {
      return;
    }
    this.retryTimer = window.setTimeout(() => {
      this.retryTimer = null;
      this.open();
    }, this.retryMilliseconds);
    this.retryMilliseconds = Math.min(this.retryMilliseconds * 2, LONGEST_RETRY_MILLISECONDS);
  }

  /**
   * Records a new connection state.
   * @param state The state.
   */
  private setState(state: ConnectionState): void {
    this.state = state;
    this.notify();
  }

  /** Calls every listener. */
  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }
}

export const eventSocket = new EventSocket();
