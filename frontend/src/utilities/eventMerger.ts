import type { AgentEvent } from '../api/types';

/** Joins events read from the journal with events received live, dropping the ones that appear in both. */
export class EventMerger {
  /**
   * Merges two lists of events.
   * @param loaded Events read from the journal, oldest first.
   * @param live Events received live, oldest first.
   * @returns Every distinct event, oldest first.
   */
  merge(loaded: AgentEvent[], live: AgentEvent[]): AgentEvent[] {
    const seen = new Set<string>();
    const merged = [];
    for (const event of [
      ...loaded,
      ...live,
    ]) {
      const key = this.key(event);
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      merged.push(event);
    }
    merged.sort((first, second) => first.created_at.localeCompare(second.created_at));
    return merged;
  }

  /**
   * A key that is the same for the journal's copy and the live copy of one event.
   * @param event The event.
   * @returns The key.
   */
  key(event: AgentEvent): string {
    const callId = typeof event.payload.call_id === 'string' ? event.payload.call_id : '';
    return `${event.created_at}|${event.kind}|${event.desk ?? ''}|${callId}`;
  }
}

export const eventMerger = new EventMerger();
