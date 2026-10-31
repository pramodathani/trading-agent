import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

import { apiClient } from '../api/apiClient';
import type { AgentEvent, TraderSummary, Halt } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useLiveEvents } from '../hooks/useLiveEvents';
import { usePolled } from '../hooks/usePolled';
import { useTraders } from '../layout/tradersContext';
import { selectedTraderStore } from '../layout/selectedTraderStore';
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
 * The home page: one card per trader with its state, model, profit and loss, last activity and controls.
 * @returns The page.
 */
export function TradersPage() {
  const traders = useTraders();
  const account = usePolled(() => apiClient.account(), ACCOUNT_REFRESH_MILLISECONDS);
  const events = useLiveEvents();
  const [flattening, setFlattening] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const lastEventByTrader = useMemo(() => {
    const latest = new Map<string, AgentEvent>();
    for (const event of events) {
      if (event.trader !== null && !HIDDEN_KINDS.has(event.kind)) {
        latest.set(event.trader, event);
      }
    }
    return latest;
  }, [
    events,
  ]);

  /**
   * Pauses or resumes a trader.
   * @param trader The trader.
   */
  async function togglePause(trader: TraderSummary): Promise<void> {
    try {
      if (trader.paused) {
        await apiClient.resume(trader.name);
      } else {
        await apiClient.pause(trader.name);
      }
      traders.refresh();
    } catch (failure) {
      setNotice(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Flattens a trader and shows the tool's report.
   * @param traderName The trader.
   * @param reason Why.
   */
  async function flatten(traderName: string, reason: string): Promise<void> {
    const result = await apiClient.flatten(traderName, reason);
    setNotice(`${traderName}: ${result.text}`);
    account.refresh();
  }

  if (traders.document === null) {
    return <p className="muted">{traders.error ?? 'Loading the traders…'}</p>;
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Traders</h1>
        <p className="muted">Each trader is its own agent with its own persona, models, schedule and memory. All of them share one risk engine.</p>
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
      <div className="trader-grid">
        {traders.document.traders.map((trader) => (
          <TraderCard
            key={trader.name}
            trader={trader}
            pnl={account.data?.trader_pnl[trader.name] ?? null}
            halts={(account.data?.halts ?? []).filter((halt) => halt.scope === trader.name || halt.scope === 'account')}
            lastEvent={lastEventByTrader.get(trader.name) ?? null}
            onTogglePause={() => togglePause(trader)}
            onFlatten={() => setFlattening(trader.name)}
          />
        ))}
      </div>
      {flattening !== null && (
        <ConfirmDialog
          title={`Flatten the ${flattening} trader`}
          explanation="This cancels the trader's open orders and closes its positions through its own flatten_trader tool, so the risk engine and the journal see it. Other traders are not touched."
          confirmLabel="Flatten"
          onConfirm={(reason) => flatten(flattening, reason)}
          onClose={() => setFlattening(null)}
        />
      )}
    </div>
  );
}

/** What one trader card shows. */
interface TraderCardProperties {
  trader: TraderSummary;
  pnl: number | null;
  halts: Halt[];
  lastEvent: AgentEvent | null;
  onTogglePause: () => void;
  onFlatten: () => void;
}

/**
 * One trader's card.
 * @param properties The trader and its controls.
 * @returns The card.
 */
function TraderCard(properties: TraderCardProperties) {
  const navigate = useNavigate();
  const trader = properties.trader;
  const busy = trader.state !== 'idle';
  const lastEvent = properties.lastEvent;

  /** Opens the chat with this trader. */
  function openChat(): void {
    selectedTraderStore.choose(trader.name);
    navigate('/chat');
  }

  return (
    <article className={busy ? 'trader-card busy' : 'trader-card'}>
      <header className="trader-card-header">
        <h2>{trader.name}</h2>
        <span className={`state-badge state-${trader.state}`}>{trader.state}</span>
        {trader.paused && <span className="state-badge paused">paused</span>}
        {trader.queued > 0 && <span className="muted small">{trader.queued} waiting</span>}
      </header>
      <div className="trader-pnl">
        <span className="muted small">Today</span>
        <strong className={formatter.pnlClass(properties.pnl)}>{properties.pnl === null ? 'no trades' : formatter.signedMoney(properties.pnl)}</strong>
      </div>
      {properties.halts.map((halt) => (
        <p key={`${halt.scope}-${halt.until_date}`} className="halt-line">
          Halted until {halt.until_date}: {halt.reason}
        </p>
      ))}
      <div className="trader-models">
        <span className="muted small">Models, in the order tried</span>
        {trader.models.length === 0 && <span className="small">No model: commands only</span>}
        {trader.models.map((line) => (
          <span key={line} className="mono">
            {line}
          </span>
        ))}
      </div>
      <div className="small muted">
        Session <span className="mono">{trader.session_id ?? '—'}</span>, {trader.exchanges} {trader.exchanges === 1 ? 'exchange' : 'exchanges'}
      </div>
      <div className="trader-last-event small">
        {lastEvent === null ? (
          <span className="muted">Nothing since this page opened.</span>
        ) : (
          <>
            <span className="mono muted">{formatter.time(lastEvent.created_at)}</span> {eventDescriber.describe(lastEvent).title}
          </>
        )}
      </div>
      <footer className="trader-card-buttons">
        <button className="primary" type="button" onClick={openChat}>
          Chat
        </button>
        <button type="button" onClick={properties.onTogglePause}>
          {trader.paused ? 'Resume' : 'Pause'}
        </button>
        <button className="danger" type="button" onClick={properties.onFlatten}>
          Flatten
        </button>
      </footer>
    </article>
  );
}
