import type { TraderSummary } from '../api/types';

const SHORT_WORDS: Record<string, string> = {
  idle: 'idle',
  busy: 'busy',
  sleeping: 'sleeping',
  waiting: 'waiting',
  stopped: 'stopped',
};

const EXPLANATIONS: Record<string, string> = {
  sleeping: 'sleeping — wakes on the next message, alert, fill or heartbeat',
  waiting: 'waiting for a turn slot',
};

const WORKING_STATES = new Set([
  'busy',
  'waiting',
]);

/** Puts a trader's state into words the same way on every page. */
export class TraderStateWords {
  /**
   * A short name for a state, for badges and menus.
   * @param state The state the gateway reports, such as "sleeping".
   * @returns Such as "sleeping" or "waiting".
   */
  short(state: string): string {
    return SHORT_WORDS[state] ?? state;
  }

  /**
   * A state in a few plain words, saying what it means for the user where that is not obvious.
   * @param state The state the gateway reports.
   * @returns Such as "sleeping — wakes on the next message, alert, fill or heartbeat".
   */
  explained(state: string): string {
    return EXPLANATIONS[state] ?? this.short(state);
  }

  /**
   * An explanation for states that need one.
   * @param state The state the gateway reports.
   * @returns The explanation, or null for states whose name says enough.
   */
  explanation(state: string): string | null {
    return EXPLANATIONS[state] ?? null;
  }

  /**
   * Whether the trader has a turn running or waiting to start, so a new message steers it and Stop applies.
   * @param state The state the gateway reports.
   * @returns True while busy or waiting for a turn slot.
   */
  isWorking(state: string): boolean {
    return WORKING_STATES.has(state);
  }

  /**
   * A trader's whole state in words, with its pause.
   * @param trader The trader.
   * @returns Such as "sleeping — wakes on the next message, alert, fill or heartbeat, paused".
   */
  describe(trader: TraderSummary): string {
    const words = this.explained(trader.state);
    if (trader.paused) {
      return `${words}, paused`;
    }
    return words;
  }
}

export const traderStateWords = new TraderStateWords();
