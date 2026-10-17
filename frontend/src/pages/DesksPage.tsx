import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

import { apiClient } from '../api/apiClient';
import type { AgentEvent, DeskSummary, Halt } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useLiveEvents } from '../hooks/useLiveEvents';
import { usePolled } from '../hooks/usePolled';
import { useDesks } from '../layout/desksContext';
import { selectedDeskStore } from '../layout/selectedDeskStore';
import { eventDescriber } from '../utilities/eventDescriber';
import { formatter } from '../utilities/formatter';

const ACCOUNT_REFRESH_MILLISECONDS = 15000;
const HIDDEN_KINDS = new Set([
  'model_usage',
  'rate_limit',
  'turn_finished',
  'account_status',
]);

/**
 * The home page: one card per desk with its state, model, profit and loss, last activity and controls.
 * @returns The page.
 */
export function DesksPage() {
  const desks = useDesks();
  const account = usePolled(() => apiClient.account(), ACCOUNT_REFRESH_MILLISECONDS);
  const events = useLiveEvents();
  const [flattening, setFlattening] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const lastEventByDesk = useMemo(() => {
    const latest = new Map<string, AgentEvent>();
    for (const event of events) {
      if (event.desk !== null && !HIDDEN_KINDS.has(event.kind)) {
        latest.set(event.desk, event);
      }
    }
    return latest;
  }, [
    events,
  ]);

  /**
   * Pauses or resumes a desk.
   * @param desk The desk.
   */
  async function togglePause(desk: DeskSummary): Promise<void> {
    try {
      if (desk.paused) {
        await apiClient.resume(desk.name);
      } else {
        await apiClient.pause(desk.name);
      }
      desks.refresh();
    } catch (failure) {
      setNotice(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Flattens a desk and shows the tool's report.
   * @param deskName The desk.
   * @param reason Why.
   */
  async function flatten(deskName: string, reason: string): Promise<void> {
    const result = await apiClient.flatten(deskName, reason);
    setNotice(`${deskName}: ${result.text}`);
    account.refresh();
  }

  if (desks.document === null) {
    return <p className="muted">{desks.error ?? 'Loading the desks…'}</p>;
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Desks</h1>
        <p className="muted">Each desk is its own agent with its own persona, models, schedule and memory. All of them share one risk engine.</p>
      </div>
      {account.data !== null && (
        <div className="summary-strip">
          <div>
            <span className="muted small">Account balance</span>
            <strong>{formatter.money(account.data.total_balance)}</strong>
          </div>
          <div>
            <span className="muted small">Today</span>
            <strong className={formatter.pnlClass(account.data.day_pnl)}>{formatter.signedMoney(account.data.day_pnl)}</strong>
          </div>
          <div>
            <span className="muted small">This week</span>
            <strong className={formatter.pnlClass(account.data.week_pnl)}>{formatter.signedMoney(account.data.week_pnl)}</strong>
          </div>
          <div>
            <span className="muted small">Open positions</span>
            <strong>{account.data.positions.length}</strong>
          </div>
        </div>
      )}
      {account.error !== null && <p className="error-text small">Account: {account.error}</p>}
      {notice !== null && (
        <div className="notice" role="status">
          <pre>{notice}</pre>
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      <div className="desk-grid">
        {desks.document.desks.map((desk) => (
          <DeskCard
            key={desk.name}
            desk={desk}
            pnl={account.data?.desk_pnl[desk.name] ?? null}
            halts={(account.data?.halts ?? []).filter((halt) => halt.scope === desk.name || halt.scope === 'account')}
            lastEvent={lastEventByDesk.get(desk.name) ?? null}
            onTogglePause={() => togglePause(desk)}
            onFlatten={() => setFlattening(desk.name)}
          />
        ))}
      </div>
      {flattening !== null && (
        <ConfirmDialog
          title={`Flatten the ${flattening} desk`}
          explanation="This cancels the desk's open orders and closes its positions through its own flatten_desk tool, so the risk engine and the journal see it. Other desks are not touched."
          confirmLabel="Flatten"
          onConfirm={(reason) => flatten(flattening, reason)}
          onClose={() => setFlattening(null)}
        />
      )}
    </div>
  );
}

/** What one desk card shows. */
interface DeskCardProperties {
  desk: DeskSummary;
  pnl: number | null;
  halts: Halt[];
  lastEvent: AgentEvent | null;
  onTogglePause: () => void;
  onFlatten: () => void;
}

/**
 * One desk's card.
 * @param properties The desk and its controls.
 * @returns The card.
 */
function DeskCard(properties: DeskCardProperties) {
  const navigate = useNavigate();
  const desk = properties.desk;
  const busy = desk.state !== 'idle';
  const lastEvent = properties.lastEvent;

  /** Opens the chat with this desk. */
  function openChat(): void {
    selectedDeskStore.choose(desk.name);
    navigate('/chat');
  }

  return (
    <article className={busy ? 'desk-card busy' : 'desk-card'}>
      <header className="desk-card-header">
        <h2>{desk.name}</h2>
        <span className={`state-badge state-${desk.state}`}>{desk.state}</span>
        {desk.paused && <span className="state-badge paused">paused</span>}
        {desk.queued > 0 && <span className="muted small">{desk.queued} waiting</span>}
      </header>
      <div className="desk-pnl">
        <span className="muted small">Today</span>
        <strong className={formatter.pnlClass(properties.pnl)}>{properties.pnl === null ? 'no trades' : formatter.signedMoney(properties.pnl)}</strong>
      </div>
      {properties.halts.map((halt) => (
        <p key={`${halt.scope}-${halt.until_date}`} className="halt-line">
          Halted until {halt.until_date}: {halt.reason}
        </p>
      ))}
      <div className="desk-models">
        <span className="muted small">Models, in the order tried</span>
        {desk.models.length === 0 && <span className="small">No model: commands only</span>}
        {desk.models.map((line) => (
          <span key={line} className="mono">
            {line}
          </span>
        ))}
      </div>
      <div className="small muted">
        Session <span className="mono">{desk.session_id ?? '—'}</span>, {desk.exchanges} {desk.exchanges === 1 ? 'exchange' : 'exchanges'}
      </div>
      <div className="desk-last-event small">
        {lastEvent === null ? (
          <span className="muted">Nothing since this page opened.</span>
        ) : (
          <>
            <span className="mono muted">{formatter.time(lastEvent.created_at)}</span> {eventDescriber.describe(lastEvent).title}
          </>
        )}
      </div>
      <footer className="desk-card-buttons">
        <button className="primary" type="button" onClick={openChat}>
          Chat
        </button>
        <button type="button" onClick={properties.onTogglePause}>
          {desk.paused ? 'Resume' : 'Pause'}
        </button>
        <button className="danger" type="button" onClick={properties.onFlatten}>
          Flatten
        </button>
      </footer>
    </article>
  );
}
