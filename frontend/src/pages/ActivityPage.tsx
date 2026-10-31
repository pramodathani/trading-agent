import { useEffect, useMemo, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { AgentEvent } from '../api/types';
import { EventRow } from '../components/EventRow';
import { useLiveEvents } from '../hooks/useLiveEvents';
import { useTraders } from '../layout/tradersContext';
import { eventDescriber } from '../utilities/eventDescriber';
import { eventMerger } from '../utilities/eventMerger';

const JOURNAL_LIMIT = 1000;
const MOST_ROWS_SHOWN = 600;
const ALL_TRADERS = '';

/**
 * A live feed of every trader's events today, newest first, with filters.
 * @returns The page.
 */
export function ActivityPage() {
  const traders = useTraders();
  const liveEvents = useLiveEvents();
  const [loaded, setLoaded] = useState<AgentEvent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [traderFilter, setTraderFilter] = useState(ALL_TRADERS);
  const [showQuiet, setShowQuiet] = useState(false);
  const [search, setSearch] = useState('');
  const traderNames = useMemo(() => (traders.document?.traders ?? []).map((trader) => trader.name), [
    traders.document,
  ]);
  const traderNamesKey = traderNames.join(',');

  useEffect(() => {
    if (!traderNamesKey) {
      return;
    }
    let cancelled = false;
    apiClient
      .allJournals(traderNamesKey.split(','), JOURNAL_LIMIT)
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
    traderNamesKey,
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
      if (traderFilter !== ALL_TRADERS && event.trader !== traderFilter && event.trader !== null) {
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
    traderFilter,
    showQuiet,
    search,
  ]);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Activity</h1>
        <p className="muted">Everything the traders did today, newest first. New events appear as they happen.</p>
      </div>
      <div className="filters">
        <select value={traderFilter} onChange={(change) => setTraderFilter(change.target.value)} aria-label="Trader">
          <option value={ALL_TRADERS}>All traders</option>
          {traderNames.map((name) => (
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
          <EventRow key={eventMerger.key(event)} event={event} showTrader={traderFilter === ALL_TRADERS} />
        ))}
      </div>
    </div>
  );
}
