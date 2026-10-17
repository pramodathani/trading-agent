import type { AgentEvent, Attachment, UserRequest } from '../api/types';
import { eventDescriber } from './eventDescriber';

/** One tool call inside a turn, with its result once it arrives. */
export interface ToolStep {
  type: 'tool';
  callId: string;
  name: string;
  argumentsText: string;
  resultText: string | null;
  isError: boolean;
  picturePath: string | null;
}

/** Any other event inside a turn, such as a risk decision or a model switch. */
export interface EventStep {
  type: 'event';
  event: AgentEvent;
}

/** A message the user sent while this turn was running. */
export interface SteeringStep {
  type: 'steering';
  message: ChatTurn;
}

/** A question, plan or permission request the desk made during the turn, with its latest status. */
export interface RequestStep {
  type: 'request';
  request: UserRequest;
}

export type TurnStep = ToolStep | EventStep | SteeringStep | RequestStep;

/** One trigger and everything the desk did about it. */
export interface ChatTurn {
  type: 'turn';
  triggerId: string;
  source: string;
  text: string;
  attachments: Attachment[];
  receivedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  started: boolean;
  finished: boolean;
  steps: TurnStep[];
  answer: string | null;
  silent: boolean;
  error: string | null;
  backend: string | null;
  steeringInto: string | null;
  steeringOutcome: 'waiting' | 'delivered' | 'queued' | null;
  stopped: boolean;
  requestId: string | null;
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
    const shown = new Set<string>();
    const turns = new Map<string, ChatTurn>();
    let openTurn: ChatTurn | null = null;
    const requestSteps = new Map<string, RequestStep>();
    for (const event of events) {
      if (event.kind === 'user_response') {
        const step = requestSteps.get(String(event.payload.request_id ?? ''));
        if (step !== undefined) {
          step.request = {
            ...step.request,
            status: event.payload.status as UserRequest['status'],
            response: (event.payload.response as UserRequest['response']) ?? null,
            responded_via: typeof event.payload.via === 'string' ? event.payload.via : null,
          };
        }
        continue;
      }
      const triggerId = typeof event.payload.trigger_id === 'string' ? event.payload.trigger_id : null;
      if (event.kind === 'trigger_received' && triggerId !== null) {
        const turn = this.newTurn(event, triggerId);
        turns.set(triggerId, turn);
        const running = turn.steeringInto !== null ? turns.get(turn.steeringInto) : undefined;
        if (running !== undefined) {
          running.steps.push({
            type: 'steering',
            message: turn,
          });
        } else {
          items.push(turn);
          shown.add(triggerId);
        }
        continue;
      }
      if (event.kind === 'turn_started' && triggerId !== null && !shown.has(triggerId)) {
        const queuedMessage = turns.get(triggerId);
        if (queuedMessage !== undefined) {
          items.push(queuedMessage);
          shown.add(triggerId);
        }
      }
      const turn: ChatTurn | null = triggerId !== null ? turns.get(triggerId) ?? null : openTurn;
      if (event.kind === 'user_request') {
        const step: RequestStep = {
          type: 'request',
          request: event.payload as unknown as UserRequest,
        };
        requestSteps.set(step.request.request_id, step);
        if (turn !== null) {
          turn.steps.push(step);
        }
        continue;
      }
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
        turn.startedAt = event.created_at;
        openTurn = turn;
      } else if (event.kind === 'turn_finished') {
        turn.finished = true;
        turn.finishedAt = event.created_at;
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
      attachments: Array.isArray(event.payload.attachments) ? (event.payload.attachments as Attachment[]) : [],
      receivedAt: event.created_at,
      startedAt: null,
      finishedAt: null,
      started: false,
      finished: false,
      steps: [],
      answer: null,
      silent: false,
      error: null,
      backend: null,
      steeringInto: typeof event.payload.steering_into === 'string' ? event.payload.steering_into : null,
      steeringOutcome: typeof event.payload.steering_into === 'string' ? 'waiting' : null,
      stopped: false,
      requestId: typeof event.payload.request_id === 'string' ? event.payload.request_id : null,
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
        picturePath: null,
      });
      return;
    }
    if (event.kind === 'tool_result') {
      for (const step of turn.steps) {
        if (step.type === 'tool' && step.callId === payload.call_id) {
          step.resultText = String(payload.text ?? '');
          step.isError = payload.is_error === true;
          step.picturePath = typeof payload.picture_path === 'string' ? payload.picture_path : null;
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
    if (event.kind === 'steering') {
      turn.steeringOutcome = payload.delivered === true ? 'delivered' : 'queued';
      return;
    }
    if (event.kind === 'stopped') {
      turn.stopped = true;
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
