import type { AgentEvent } from '../api/types';
import { eventDescriber } from '../utilities/eventDescriber';
import { formatter } from '../utilities/formatter';

const LONG_DETAIL_CHARACTERS = 160;

/** What one feed row shows. */
export interface EventRowProperties {
  event: AgentEvent;
  showDesk: boolean;
}

/**
 * One event in the activity feed: its time, desk and description, with a long detail folded away.
 * @param properties The event and whether to show its desk.
 * @returns The row.
 */
export function EventRow(properties: EventRowProperties) {
  const description = eventDescriber.describe(properties.event);
  const detail = description.detail;
  const isLong = detail.length > LONG_DETAIL_CHARACTERS || detail.includes('\n');
  return (
    <div className={`event-row tone-${description.tone}${properties.showDesk ? ' with-desk' : ''}`}>
      <span className="event-time mono">{formatter.time(properties.event.created_at)}</span>
      {properties.showDesk && <span className="desk-chip">{properties.event.desk ?? 'account'}</span>}
      <div className="event-body">
        <div className="event-title">{description.title}</div>
        {detail && !isLong && <div className="event-detail">{detail}</div>}
        {detail && isLong && (
          <details>
            <summary className="muted small">{detail.slice(0, LONG_DETAIL_CHARACTERS).replaceAll('\n', ' ')}…</summary>
            <pre>{detail}</pre>
          </details>
        )}
      </div>
    </div>
  );
}
