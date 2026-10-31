import { type FormEvent, useEffect, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { Exchange, SearchHit } from '../api/types';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';
import { useSelectedTrader } from '../layout/selectedTraderStore';
import { formatter } from '../utilities/formatter';

const REFRESH_MILLISECONDS = 30000;

/**
 * The chosen trader's memory: its sessions, daily summaries and notes, and a search over all of them.
 * @returns The page.
 */
export function SessionsPage() {
  const traderName = useSelectedTrader();
  const sessions = usePolled(() => apiClient.sessions(traderName), REFRESH_MILLISECONDS, traderName);
  const summaries = usePolled(() => apiClient.summaries(traderName), REFRESH_MILLISECONDS, traderName);
  const notes = usePolled(() => apiClient.notes(traderName), REFRESH_MILLISECONDS, traderName);
  const [openSession, setOpenSession] = useState<string | null>(null);
  const [exchanges, setExchanges] = useState<Exchange[] | null>(null);
  const [keywords, setKeywords] = useState('');
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [everyWord, setEveryWord] = useState(true);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    setOpenSession(null);
    setHits(null);
  }, [
    traderName,
  ]);

  useEffect(() => {
    if (openSession === null) {
      setExchanges(null);
      return;
    }
    let cancelled = false;
    apiClient
      .session(traderName, openSession)
      .then((document) => {
        if (!cancelled) {
          setExchanges(document.exchanges);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setExchanges([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    traderName,
    openSession,
  ]);

  /**
   * Runs a search.
   * @param event The form's submit event.
   */
  async function search(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!keywords.trim()) {
      return;
    }
    setSearchError(null);
    try {
      const result = await apiClient.search(traderName, keywords.trim());
      setHits(result.hits);
      setEveryWord(result.matched_every_word);
    } catch (failure) {
      setSearchError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Sessions of {traderName}</h1>
        <p className="muted">What the trader said and remembered: one session per trading day, the summary written at each rollover, and its notes.</p>
      </div>
      <section className="panel">
        <h2>Search the trader&apos;s memory</h2>
        <form className="filters" onSubmit={search}>
          <input value={keywords} onChange={(change) => setKeywords(change.target.value)} placeholder="For example: NIFTY gap down" aria-label="Keywords" />
          <button className="primary" type="submit" disabled={!keywords.trim()}>
            Search
          </button>
        </form>
        {searchError !== null && <p className="error-text">{searchError}</p>}
        {hits !== null && (
          <div className="search-hits">
            {!everyWord && hits.length > 0 && <p className="muted small">No result holds every word, so these hold some of them.</p>}
            {hits.length === 0 && <p className="muted">Nothing found.</p>}
            {hits.map((hit, index) => (
              <div key={`${hit.day}-${index}`} className="search-hit">
                <span className="mono muted">{hit.day}</span> <span className="trader-chip">{hit.kind}</span>
                <pre>{hit.snippet}</pre>
              </div>
            ))}
          </div>
        )}
      </section>
      <div className="two-columns sessions-layout">
        <section className="panel">
          <h2>Sessions</h2>
          <Loadable data={sessions.data} error={sessions.error}>
            {(document) => (
              <div className="session-list">
                {document.sessions.length === 0 && <p className="muted">No sessions yet.</p>}
                {document.sessions.map((entry) => (
                  <button
                    key={entry.session_id}
                    type="button"
                    className={entry.session_id === openSession ? 'list-item selected' : 'list-item'}
                    onClick={() => setOpenSession(entry.session_id)}
                  >
                    <span className="mono">{entry.session_id}</span>
                    <span className="muted small">
                      {entry.exchanges} {entry.exchanges === 1 ? 'exchange' : 'exchanges'}
                      {entry.session_id === document.current ? ' · current' : ''}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Loadable>
        </section>
        <section className="panel">
          <h2>{openSession === null ? 'Choose a session' : `Session ${openSession}`}</h2>
          {openSession !== null && exchanges === null && <p className="muted">Loading…</p>}
          {exchanges !== null && exchanges.length === 0 && <p className="muted">This session has no finished exchanges.</p>}
          {exchanges?.map((exchange, index) => (
            <div key={`${exchange.finished_at}-${index}`} className="exchange">
              <div className="muted small">
                {formatter.dayTime(exchange.finished_at)} · {exchange.backend_name || 'no model'}
              </div>
              <pre className="exchange-question">{exchange.trigger_text}</pre>
              <pre>{exchange.answer}</pre>
            </div>
          ))}
        </section>
      </div>
      <section className="panel">
        <h2>Daily summaries</h2>
        <Loadable data={summaries.data} error={summaries.error}>
          {(document) => (
            <>
              {document.summaries.length === 0 && <p className="muted">No summaries yet. One is written at each rollover after the close.</p>}
              {document.summaries.map((summary) => (
                <details key={summary.date} className="folded">
                  <summary>{summary.date}</summary>
                  <pre>{summary.text}</pre>
                </details>
              ))}
            </>
          )}
        </Loadable>
      </section>
      <section className="panel">
        <h2>Notes</h2>
        <p className="muted small">The one to three lessons the trader writes after its turns; they are folded into Memory.md at the close.</p>
        <Loadable data={notes.data} error={notes.error}>
          {(document) => (
            <>
              {document.notes.length === 0 && <p className="muted">No notes yet.</p>}
              {document.notes.map((file) => (
                <details key={file.file} className="folded">
                  <summary className="mono">{file.file}</summary>
                  <pre>{file.text}</pre>
                </details>
              ))}
            </>
          )}
        </Loadable>
      </section>
    </div>
  );
}
