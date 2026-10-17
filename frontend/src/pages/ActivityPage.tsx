import { useEffect, useMemo, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { AgentEvent } from '../api/types';
import { EventRow } from '../components/EventRow';
import { useLiveEvents } from '../hooks/useLiveEvents';
import { useDesks } from '../layout/desksContext';
import { eventDescriber } from '../utilities/eventDescriber';
import { eventMerger } from '../utilities/eventMerger';

const JOURNAL_LIMIT = 1000;
const MOST_ROWS_SHOWN = 600;
const ALL_DESKS = '';

/**
 * A live feed of every desk's events today, newest first, with filters.
 * @returns The page.
 */
export function ActivityPage() {
  const desks = useDesks();
  const liveEvents = useLiveEvents();
  const [loaded, setLoaded] = useState<AgentEvent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [deskFilter, setDeskFilter] = useState(ALL_DESKS);
  const [showQuiet, setShowQuiet] = useState(false);
  const [search, setSearch] = useState('');
  const deskNames = useMemo(() => (desks.document?.desks ?? []).map((desk) => desk.name), [
    desks.document,
  ]);
  const deskNamesKey = deskNames.join(',');

  useEffect(() => {
    if (!deskNamesKey) {
      return;
    }
    let cancelled = false;
    apiClient
      .allJournals(deskNamesKey.split(','), JOURNAL_LIMIT)
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
    deskNamesKey,
  ]);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const kept = [];
    const merged = eventMerger.merge(loaded, liveEvents);
    for (let index = merged.length - 1; index >= 0 && kept.length < MOST_ROWS_SHOWN; index -= 1) {
      const event = merged[index];
      if (event.kind === 'text_delta') {
        continue;
      }
      if (deskFilter !== ALL_DESKS && event.desk !== deskFilter && event.desk !== null) {
        continue;
      }
      const description = eventDescriber.describe(event);
      if (!showQuiet && description.tone === 'quiet') {
        continue;
      }
      if (needle && !`${description.title} ${description.detail}`.toLowerCase().includes(needle)) {
        continue;
      }
      kept.push(event);
    }
    return kept;
  }, [
    loaded,
    liveEvents,
    deskFilter,
    showQuiet,
    search,
  ]);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Activity</h1>
        <p className="muted">Everything the desks did today, newest first. New events appear as they happen.</p>
      </div>
      <div className="filters">
        <select value={deskFilter} onChange={(change) => setDeskFilter(change.target.value)} aria-label="Desk">
          <option value={ALL_DESKS}>All desks</option>
          {deskNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <input value={search} onChange={(change) => setSearch(change.target.value)} placeholder="Search" aria-label="Search" />
        <label className="checkbox">
          <input type="checkbox" checked={showQuiet} onChange={(change) => setShowQuiet(change.target.checked)} />
          Show routine events (token use, turn start and end, account checks)
        </label>
      </div>
      {loadError !== null && <p className="error-text">Could not read the journals: {loadError}</p>}
      <div className="panel feed">
        {rows.length === 0 && <p className="muted">Nothing matches.</p>}
        {rows.map((event) => (
          <EventRow key={eventMerger.key(event)} event={event} showDesk={deskFilter === ALL_DESKS} />
        ))}
      </div>
    </div>
  );
}
