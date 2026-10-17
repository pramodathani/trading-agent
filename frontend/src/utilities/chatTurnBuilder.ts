import type { AgentEvent } from '../api/types';
import { eventDescriber } from './eventDescriber';

/** One tool call inside a turn, with its result once it arrives. */
export interface ToolStep {
  type: 'tool';
  callId: string;
  name: string;
  argumentsText: string;
  resultText: string | null;
  isError: boolean;
}

/** Any other event inside a turn, such as a risk decision or a model switch. */
export interface EventStep {
  type: 'event';
  event: AgentEvent;
}

export type TurnStep = ToolStep | EventStep;

/** One trigger and everything the desk did about it. */
export interface ChatTurn {
  type: 'turn';
  triggerId: string;
  source: string;
  text: string;
  receivedAt: string;
  started: boolean;
  finished: boolean;
  steps: TurnStep[];
  answer: string | null;
  silent: boolean;
  error: string | null;
  backend: string | null;
}

/** An event that belongs to no turn, such as a fill reported while the desk was idle. */
export interface LooseEvent {
  type: 'loose';
  event: AgentEvent;
}

export type ChatItem = ChatTurn | LooseEvent;

const TURN_LESS_KINDS_SHOWN = new Set([
  'order',
  'risk_decision',
  'fill',
  'price_alert',
  'message',
  'desk_halt',
  'kill_switch',
  'session_started',
  'cron_fired',
  'cron_result',
]);

const STEP_KINDS_SHOWN = new Set([
  'backend_switch',
  'backend_unavailable',
  'risk_decision',
  'order',
  'subagent_started',
  'subagent_finished',
  'context_compressed',
  'message',
]);

/** Groups one desk's events into chat turns, one per trigger. */
export class ChatTurnBuilder {
  /**
   * Builds the chat from a desk's events.
   * @param events The desk's events, oldest first.
   * @returns The turns and loose events, oldest first.
   */
  build(events: AgentEvent[]): ChatItem[] {
    const items: ChatItem[] = [];
    const turns = new Map<string, ChatTurn>();
    let openTurn: ChatTurn | null = null;
    for (const event of events) {
      const triggerId = typeof event.payload.trigger_id === 'string' ? event.payload.trigger_id : null;
      if (event.kind === 'trigger_received' && triggerId !== null) {
        const turn = this.newTurn(event, triggerId);
        turns.set(triggerId, turn);
        items.push(turn);
        continue;
      }
      const turn: ChatTurn | null = triggerId !== null ? turns.get(triggerId) ?? null : openTurn;
      if (turn === null) {
        if (TURN_LESS_KINDS_SHOWN.has(event.kind) && eventDescriber.describe(event).tone !== 'quiet') {
          items.push({
            type: 'loose',
            event,
          });
        }
        continue;
      }
      if (event.kind === 'turn_started') {
        turn.started = true;
        openTurn = turn;
      } else if (event.kind === 'turn_finished') {
        turn.finished = true;
        if (openTurn === turn) {
          openTurn = null;
        }
      } else {
        this.addToTurn(turn, event);
      }
    }
    return items;
  }

  /**
   * Starts a turn from its trigger.
   * @param event The trigger_received event.
   * @param triggerId The trigger's id.
   * @returns The new turn.
   */
  private newTurn(event: AgentEvent, triggerId: string): ChatTurn {
    return {
      type: 'turn',
      triggerId,
      source: String(event.payload.source ?? ''),
      text: String(event.payload.text ?? ''),
      receivedAt: event.created_at,
      started: false,
      finished: false,
      steps: [],
      answer: null,
      silent: false,
      error: null,
      backend: null,
    };
  }

  /**
   * Adds one event to a turn.
   * @param turn The turn.
   * @param event The event.
   */
  private addToTurn(turn: ChatTurn, event: AgentEvent): void {
    const payload = event.payload;
    if (event.kind === 'tool_call') {
      turn.steps.push({
        type: 'tool',
        callId: String(payload.call_id ?? ''),
        name: String(payload.name ?? ''),
        argumentsText: JSON.stringify(payload.arguments ?? {}, null, 2),
        resultText: null,
        isError: false,
      });
      return;
    }
    if (event.kind === 'tool_result') {
      for (const step of turn.steps) {
        if (step.type === 'tool' && step.callId === payload.call_id) {
          step.resultText = String(payload.text ?? '');
          step.isError = payload.is_error === true;
        }
      }
      return;
    }
    if (event.kind === 'text') {
      turn.answer = String(payload.text ?? '');
      turn.silent = payload.silent === true;
      return;
    }
    if (event.kind === 'error') {
      turn.error = String(payload.error ?? '');
      return;
    }
    if (event.kind === 'backend_switch' && typeof payload.to === 'string') {
      turn.backend = payload.to;
      if (payload.from === null || payload.from === undefined) {
        return;
      }
    }
    if (event.kind === 'model_usage' && typeof payload.backend === 'string') {
      turn.backend = payload.backend;
      return;
    }
    if (STEP_KINDS_SHOWN.has(event.kind)) {
      turn.steps.push({
        type: 'event',
        event,
      });
    }
  }
}

export const chatTurnBuilder = new ChatTurnBuilder();
