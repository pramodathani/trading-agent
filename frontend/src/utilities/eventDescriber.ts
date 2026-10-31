import type { AgentEvent } from '../api/types';
import { formatter } from './formatter';

export type EventTone = 'normal' | 'quiet' | 'good' | 'warning' | 'bad';

/** One event in words: a short title, an optional longer detail, and how much attention it deserves. */
export interface EventDescription {
  title: string;
  detail: string;
  tone: EventTone;
}

const SOURCE_WORDS: Record<string, string> = {
  user_message: 'Message from you',
  cron: 'Woken by a scheduled job',
  heartbeat: 'Heartbeat',
  market_watcher: 'Woken by the market watcher',
  webhook: 'Woken by a webhook',
  rollover: 'Daily rollover',
  compression: 'Context compression',
  subagent: 'Woken by a subagent',
};

const QUIET_KINDS = new Set([
  'turn_started',
  'turn_finished',
  'model_usage',
  'rate_limit',
  'trader_started',
  'trader_sleeping',
  'account_status',
]);

/** Turns gateway events into short sentences for the Activity feed and the chat. */
export class EventDescriber {
  /**
   * Describes one event.
   * @param event The event.
   * @returns Its title, detail and tone.
   */
  describe(event: AgentEvent): EventDescription {
    const payload = event.payload;
    switch (event.kind) {
      case 'trigger_received':
        return this.make(this.sourceWords(payload.source), this.text(payload.text), 'normal');
      case 'turn_started':
        return this.make('Turn started', '', 'quiet');
      case 'turn_finished':
        return this.make('Turn finished', '', 'quiet');
      case 'text':
        if (payload.silent === true) {
          return this.make('Nothing to do', this.text(payload.text), 'quiet');
        }
        return this.make('Answered', this.text(payload.text), 'normal');
      case 'tool_call':
        return this.make(`Calls ${this.text(payload.name)}`, this.json(payload.arguments), 'normal');
      case 'tool_result':
        if (payload.is_error === true) {
          return this.make(`${this.text(payload.name)} failed`, this.text(payload.text), 'warning');
        }
        return this.make(`${this.text(payload.name)} answered`, this.text(payload.text), 'quiet');
      case 'model_usage':
        return this.make(
          `${this.text(payload.backend)} used ${this.number(payload.prompt_tokens)} prompt and ${this.number(payload.completion_tokens)} answer tokens`,
          '',
          'quiet',
        );
      case 'rate_limit':
        return this.make(`${this.text(payload.backend)} ${this.text(payload.limit)} limit: ${this.text(payload.status)}`, '', 'quiet');
      case 'backend_unavailable':
        return this.make(
          `${this.text(payload.backend)} is unavailable; retrying in ${this.number(payload.waiting_seconds)} s`,
          this.text(payload.reason),
          'warning',
        );
      case 'backend_switch':
        if (payload.from === null || payload.from === undefined) {
          return this.make(`Model chosen: ${this.text(payload.to)}`, '', 'quiet');
        }
        return this.make(`Model switched: ${this.text(payload.from)} → ${this.text(payload.to)}`, '', 'warning');
      case 'risk_decision':
        return this.describeRiskDecision(payload);
      case 'kill_switch':
        if (payload.stage === 'fired') {
          return this.make('Kill switch fired', this.text(payload.reason), 'bad');
        }
        return this.make('Kill switch: flatten finished', this.json(payload.outcome), 'bad');
      case 'order':
        return this.describeOrder(payload);
      case 'fill':
        return this.make(
          `Order ${this.text(payload.status).toLowerCase()}: ${this.number(payload.filled_quantity)} at ${formatter.priceText(payload.average_price as number | null)}`,
          this.text(payload.message),
          payload.status === 'REJECTED' ? 'warning' : 'good',
        );
      case 'price_alert':
        return this.make(
          `${this.text(payload.symbol)} at ${formatter.priceText(payload.last_price as number)}, ${this.text(payload.condition)} ${formatter.priceText(payload.price as number)}`,
          this.text(payload.note),
          'warning',
        );
      case 'trader_halt':
        return this.make('Trader halted at its loss limit', this.text(payload.reason), 'bad');
      case 'account_status':
        return this.make(
          `Account ${formatter.money(payload.total_balance as number)}, today ${formatter.signedMoney(payload.day_pnl as number)}`,
          '',
          'quiet',
        );
      case 'session_started':
        if (payload.reason === 'resumed') {
          return this.make(`Session ${this.text(payload.session_id)} resumed after a restart`, '', 'quiet');
        }
        return this.make(`Session ${this.text(payload.session_id)} started`, this.text(payload.reason).replaceAll('_', ' '), 'normal');
      case 'context_compressed':
        return this.make(
          `Conversation compressed from ${this.number(payload.tokens_before)} tokens`,
          `${this.number(payload.messages_summarised)} messages summarised`,
          'normal',
        );
      case 'subagent_started':
        return this.make(`Subagent ${this.text(payload.subagent)} started`, this.text(payload.task), 'normal');
      case 'subagent_finished':
        return this.make(
          `Subagent ${this.text(payload.subagent)} ${this.text(payload.outcome)} in ${this.number(payload.seconds)} s`,
          '',
          'normal',
        );
      case 'cron_fired':
        return this.make(`Scheduled job: ${this.text(payload.name)}`, payload.catching_up === true ? 'catching up a missed run' : '', 'normal');
      case 'cron_result':
        return this.make(`Job ${this.text(payload.name)}: ${this.text(payload.outcome)}`, this.text(payload.text), 'normal');
      case 'message':
        return this.make(payload.urgent === true ? 'Urgent message' : 'Message', this.text(payload.text), payload.urgent === true ? 'warning' : 'normal');
      case 'error':
        return this.make('The turn failed', this.text(payload.error), 'bad');
      case 'steering':
        if (payload.delivered === true) {
          return this.make('Your message was handed to the running turn', '', 'good');
        }
        return this.make('The turn ended before your message reached it, so it is the next turn', '', 'normal');
      case 'channel':
        if (payload.action === 'stranger') {
          return this.make(`Telegram: a chat that is not paired wrote (${this.text(payload.name)}, chat ${this.text(payload.chat_id)})`, this.text(payload.text), 'warning');
        }
        if (payload.action === 'paired') {
          return this.make(`Telegram: paired ${this.text(payload.name)}`, '', 'good');
        }
        return this.make(`Telegram: connected as @${this.text(payload.name)}`, '', 'quiet');
      case 'user_request':
        if (payload.kind === 'plan') {
          return this.make('The trader presented a plan for your approval', this.text((payload.content as Record<string, unknown> | undefined)?.title), 'warning');
        }
        if (payload.kind === 'permission') {
          return this.make('The trader needs your permission', this.text((payload.content as Record<string, unknown> | undefined)?.tool_name), 'warning');
        }
        return this.make('The trader asked you a question', '', 'warning');
      case 'user_response':
        return this.make(payload.status === 'dismissed' ? `You dismissed a ${this.text(payload.kind)}` : `You answered a ${this.text(payload.kind)}`, this.text(payload.title), 'good');
      case 'stopped':
        return this.make('Turn stopped by you', '', 'warning');
      case 'trader_started':
        return this.make('Trader started', '', 'quiet');
      case 'trader_stopped':
        return this.make('Trader stopped', '', 'warning');
      case 'trader_created':
        return this.make('Trader created or restored', this.mandateWords(payload), 'good');
      case 'trader_retired':
        return this.make('Trader retired; its files and memory are kept, and it can be restored', this.mandateWords(payload), 'warning');
      case 'trader_sleeping':
        return this.make('Fell asleep; wakes on the next message, alert, fill or heartbeat', '', 'quiet');
      default:
        return this.make(event.kind.replaceAll('_', ' '), this.json(payload), QUIET_KINDS.has(event.kind) ? 'quiet' : 'normal');
    }
  }

  /**
   * Names what woke a trader.
   * @param source The trigger's source.
   * @returns Plain words, such as "Message from you".
   */
  sourceWords(source: unknown): string {
    const key = this.text(source);
    return SOURCE_WORDS[key] ?? `Woken by ${key.replaceAll('_', ' ')}`;
  }

  /**
   * Describes a risk engine decision.
   * @param payload The event's payload.
   * @returns The description.
   */
  private describeRiskDecision(payload: Record<string, unknown>): EventDescription {
    const order = this.text(payload.order);
    if (payload.approved === true) {
      return this.make(`Risk engine approved: ${order}`, '', 'good');
    }
    const reasons = Array.isArray(payload.reasons) ? payload.reasons.join(' ') : '';
    return this.make(`Risk engine refused: ${order}`, reasons, 'warning');
  }

  /**
   * Describes an order action.
   * @param payload The event's payload.
   * @returns The description.
   */
  private describeOrder(payload: Record<string, unknown>): EventDescription {
    const mode = payload.dry_run === true ? ' (dry run)' : '';
    const title = `Order ${this.text(payload.action)}: ${this.text(payload.kind)}${mode}`;
    const lines = [];
    if (typeof payload.order === 'string') {
      lines.push(payload.order);
    }
    if (Array.isArray(payload.steps)) {
      lines.push(...payload.steps.map(String));
    }
    if (typeof payload.reason === 'string') {
      lines.push(`Reason: ${payload.reason}`);
    }
    return this.make(title, lines.join('\n'), 'good');
  }

  /**
   * Builds a description.
   * @param title The title.
   * @param detail The detail.
   * @param tone The tone.
   * @returns The description.
   */
  private make(title: string, detail: string, tone: EventTone): EventDescription {
    return {
      title,
      detail,
      tone,
    };
  }

  /**
   * Describes a trader's mandate from a creation or retirement payload.
   * @param payload The event's payload.
   * @returns Such as "Mandate: ...", or an empty string when it has none.
   */
  private mandateWords(payload: Record<string, unknown>): string {
    const mandate = this.text(payload.mandate).trim();
    if (!mandate) {
      return '';
    }
    return `Mandate: ${mandate}`;
  }

  /**
   * Turns a payload value into text.
   * @param value The value.
   * @returns The text, or an empty string for a missing value.
   */
  private text(value: unknown): string {
    if (value === null || value === undefined) {
      return '';
    }
    return String(value);
  }

  /**
   * Formats a payload number.
   * @param value The value.
   * @returns The number with thousands separators, or "?" when missing.
   */
  private number(value: unknown): string {
    if (typeof value !== 'number') {
      return '?';
    }
    return value.toLocaleString('en-IN');
  }

  /**
   * Turns a payload value into indented JSON.
   * @param value The value.
   * @returns The JSON, or an empty string for an empty object.
   */
  private json(value: unknown): string {
    if (value === null || value === undefined) {
      return '';
    }
    if (typeof value === 'object' && Object.keys(value).length === 0) {
      return '';
    }
    return JSON.stringify(value, null, 2);
  }
}

export const eventDescriber = new EventDescriber();
