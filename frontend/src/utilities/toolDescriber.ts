import type { ToolStep } from './chatTurnBuilder';

/** A kind of tool, with the words for one use and for several, in the past tense. */
interface ToolKind {
  one: string;
  many: string;
}

/** What a tool is doing, in words for the activity indicator. */
interface ToolDescription {
  activity: string;
  kind: string;
}

const KINDS: Record<string, ToolKind> = {
  command: {
    one: 'ran a command',
    many: 'ran {count} commands',
  },
  read: {
    one: 'read a file',
    many: 'read {count} files',
  },
  write: {
    one: 'edited a file',
    many: 'edited {count} files',
  },
  picture: {
    one: 'looked at a picture',
    many: 'looked at {count} pictures',
  },
  search: {
    one: 'made a search',
    many: 'made {count} searches',
  },
  web: {
    one: 'read a web page',
    many: 'read {count} web pages',
  },
  browser: {
    one: 'took a browser step',
    many: 'took {count} browser steps',
  },
  quote: {
    one: 'fetched a quote',
    many: 'fetched {count} quotes',
  },
  market: {
    one: 'read market data',
    many: 'read market data {count} times',
  },
  account: {
    one: 'checked the account',
    many: 'checked the account {count} times',
  },
  order: {
    one: 'sent an order action',
    many: 'sent {count} order actions',
  },
  message: {
    one: 'sent a message',
    many: 'sent {count} messages',
  },
  skill: {
    one: 'used a skill',
    many: 'used {count} skills',
  },
  schedule: {
    one: 'changed a schedule or alert',
    many: 'changed {count} schedules or alerts',
  },
  subagent: {
    one: 'delegated a task',
    many: 'delegated {count} tasks',
  },
  tool: {
    one: 'used a tool',
    many: 'used {count} tools',
  },
};

const TOOLS: Record<string, ToolDescription> = {
  bash_run: {
    activity: 'Running a command',
    kind: 'command',
  },
  bash_background: {
    activity: 'Starting a background command',
    kind: 'command',
  },
  bash_check: {
    activity: 'Checking a background command',
    kind: 'command',
  },
  bash_restart: {
    activity: 'Restarting the shell',
    kind: 'command',
  },
  read_file: {
    activity: 'Reading a file',
    kind: 'read',
  },
  write_file: {
    activity: 'Writing a file',
    kind: 'write',
  },
  edit_file: {
    activity: 'Editing a file',
    kind: 'write',
  },
  add_note: {
    activity: 'Writing a note',
    kind: 'write',
  },
  propose_file_change: {
    activity: 'Proposing a file change',
    kind: 'write',
  },
  view_image: {
    activity: 'Looking at a picture',
    kind: 'picture',
  },
  web_search: {
    activity: 'Searching the web',
    kind: 'search',
  },
  search_knowledge: {
    activity: 'Searching the knowledge base',
    kind: 'search',
  },
  search_sessions: {
    activity: 'Searching past sessions',
    kind: 'search',
  },
  search_instruments: {
    activity: 'Looking up instruments',
    kind: 'search',
  },
  tool_search: {
    activity: 'Looking for a tool',
    kind: 'search',
  },
  web_fetch: {
    activity: 'Reading a web page',
    kind: 'web',
  },
  browser_open: {
    activity: 'Opening a page in the browser',
    kind: 'browser',
  },
  browser_snapshot: {
    activity: 'Reading the browser page',
    kind: 'browser',
  },
  browser_click: {
    activity: 'Clicking in the browser',
    kind: 'browser',
  },
  browser_type: {
    activity: 'Typing in the browser',
    kind: 'browser',
  },
  browser_screenshot: {
    activity: 'Taking a browser screenshot',
    kind: 'browser',
  },
  browser_back: {
    activity: 'Going back in the browser',
    kind: 'browser',
  },
  browser_tabs: {
    activity: 'Checking browser tabs',
    kind: 'browser',
  },
  get_quote: {
    activity: 'Fetching a quote',
    kind: 'quote',
  },
  get_candles: {
    activity: 'Reading price candles',
    kind: 'market',
  },
  get_time: {
    activity: 'Checking the time',
    kind: 'market',
  },
  get_portfolio: {
    activity: 'Checking the portfolio',
    kind: 'account',
  },
  get_orders: {
    activity: 'Checking orders',
    kind: 'account',
  },
  place_order: {
    activity: 'Placing an order',
    kind: 'order',
  },
  place_bracket_order: {
    activity: 'Placing a bracket order',
    kind: 'order',
  },
  modify_order: {
    activity: 'Modifying an order',
    kind: 'order',
  },
  cancel_order: {
    activity: 'Cancelling an order',
    kind: 'order',
  },
  flatten_trader: {
    activity: "Closing the trader's positions",
    kind: 'order',
  },
  send_message: {
    activity: 'Sending a message',
    kind: 'message',
  },
  send_image: {
    activity: 'Sending a picture',
    kind: 'message',
  },
  load_skill: {
    activity: 'Loading a skill',
    kind: 'skill',
  },
  skill_create: {
    activity: 'Writing a new skill',
    kind: 'skill',
  },
  skill_patch: {
    activity: 'Updating a skill',
    kind: 'skill',
  },
  skill_archive: {
    activity: 'Archiving a skill',
    kind: 'skill',
  },
  cron_create: {
    activity: 'Scheduling a job',
    kind: 'schedule',
  },
  cron_list: {
    activity: 'Listing scheduled jobs',
    kind: 'schedule',
  },
  cron_delete: {
    activity: 'Removing a scheduled job',
    kind: 'schedule',
  },
  schedule_wakeup: {
    activity: 'Setting a wake-up',
    kind: 'schedule',
  },
  set_price_alert: {
    activity: 'Setting a price alert',
    kind: 'schedule',
  },
  cancel_price_alert: {
    activity: 'Cancelling a price alert',
    kind: 'schedule',
  },
  delegate_task: {
    activity: 'Handing work to a subagent',
    kind: 'subagent',
  },
  call_mcp_tool: {
    activity: 'Using an MCP tool',
    kind: 'tool',
  },
};

const DETAIL_KEYS = [
  'command',
  'symbol',
  'query',
  'keywords',
  'path',
  'file_path',
  'url',
  'skill_name',
  'tool_name',
  'name',
];
const DETAIL_LENGTH = 48;

/** Describes tool calls in plain words: what one is doing now, and a summary of several once done. */
export class ToolDescriber {
  /**
   * What a running tool is doing.
   * @param step The tool call.
   * @returns Such as "Fetching a quote".
   */
  activity(step: ToolStep): string {
    return TOOLS[this.baseName(step.name)]?.activity ?? `Using ${step.name}`;
  }

  /**
   * The most telling argument of a tool call, shortened.
   * @param step The tool call.
   * @returns Such as "RELIANCE" or "ls -la", or an empty string when there is none.
   */
  detail(step: ToolStep): string {
    let parsed: unknown;
    try {
      parsed = JSON.parse(step.argumentsText);
    } catch {
      return '';
    }
    if (parsed === null || typeof parsed !== 'object') {
      return '';
    }
    const values = parsed as Record<string, unknown>;
    for (const key of DETAIL_KEYS) {
      const value = values[key];
      if (typeof value === 'string' && value.trim().length > 0) {
        const line = value.trim().split('\n')[0];
        return line.length > DETAIL_LENGTH ? `${line.slice(0, DETAIL_LENGTH - 1)}…` : line;
      }
    }
    return '';
  }

  /**
   * One line summing up several tool calls, as Claude Code does.
   * @param steps The tool calls, in order.
   * @returns Such as "Fetched 2 quotes, ran a command (1 failed), used a tool".
   */
  summary(steps: ToolStep[]): string {
    const order: string[] = [];
    const counts = new Map<string, number>();
    const failures = new Map<string, number>();
    for (const step of steps) {
      const kind = TOOLS[this.baseName(step.name)]?.kind ?? 'tool';
      if (!counts.has(kind)) {
        order.push(kind);
      }
      counts.set(kind, (counts.get(kind) ?? 0) + 1);
      if (step.isError) {
        failures.set(kind, (failures.get(kind) ?? 0) + 1);
      }
    }
    const parts: string[] = [];
    for (const kind of order) {
      const count = counts.get(kind) ?? 0;
      const words = KINDS[kind];
      let part = count === 1 ? words.one : words.many.replace('{count}', String(count));
      const failed = failures.get(kind) ?? 0;
      if (failed > 0) {
        part = `${part} (${failed} failed)`;
      }
      parts.push(part);
    }
    const sentence = parts.join(', ');
    return sentence.charAt(0).toUpperCase() + sentence.slice(1);
  }

  /**
   * A tool's own name without the prefix Claude Code adds to tools served over MCP.
   * @param name The name as the event gives it.
   * @returns Such as "get_quote" for "mcp__trading_agent__get_quote".
   */
  private baseName(name: string): string {
    const parts = name.split('__');
    return parts[parts.length - 1];
  }
}

export const toolDescriber = new ToolDescriber();
