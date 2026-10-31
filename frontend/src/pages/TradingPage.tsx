import { useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { TraderOrder } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { usePolled } from '../hooks/usePolled';
import { useTraders } from '../layout/tradersContext';
import { formatter } from '../utilities/formatter';

const ACCOUNT_REFRESH_MILLISECONDS = 10000;

/**
 * The account and each trader's share of it: profit and loss, positions, stock ownership, halts, orders and the kill switch.
 * @returns The page.
 */
export function TradingPage() {
  const traders = useTraders();
  const account = usePolled(() => apiClient.account(), ACCOUNT_REFRESH_MILLISECONDS);
  const traderOrders = usePolled(() => apiClient.traderOrders(), ACCOUNT_REFRESH_MILLISECONDS);
  const [brokerOrders, setBrokerOrders] = useState<Record<string, unknown>[] | null>(null);
  const [brokerError, setBrokerError] = useState<string | null>(null);
  const [killing, setKilling] = useState(false);
  const [killReport, setKillReport] = useState<string | null>(null);
  const mode = traders.document?.mode ?? 'dry_run';

  /** Reads UBI's own order book. */
  async function loadBrokerOrders(): Promise<void> {
    setBrokerError(null);
    try {
      const document = await apiClient.brokerOrders();
      setBrokerOrders(document.orders ?? []);
    } catch (failure) {
      setBrokerError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Fires the kill switch.
   * @param reason Why.
   */
  async function kill(reason: string): Promise<void> {
    const report = await apiClient.kill(reason);
    setKillReport(JSON.stringify(report, null, 2));
    account.refresh();
  }

  const ownerByInstrument = new Map<string, string>();
  for (const owner of account.data?.owners ?? []) {
    ownerByInstrument.set(owner.instrument_id, owner.trader);
  }
  const openOrders: TraderOrder[] = [];
  for (const orders of Object.values(traderOrders.data ?? {})) {
    openOrders.push(...orders);
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Trading</h1>
        <p className="muted">The account as the risk engine sees it. Orders are {mode === 'live' ? 'live' : 'dry runs'}.</p>
      </div>
      {account.error !== null && <p className="error-text">Account: {account.error}</p>}
      {account.data !== null && (
        <>
          <div className="summary-strip">
            <div>
              <span className="muted small">Balance</span>
              <strong>{formatter.money(account.data.total_balance)}</strong>
            </div>
            <div>
              <span className="muted small">Margin in use</span>
              <strong>{formatter.money(account.data.margin_utilized)}</strong>
            </div>
            <div>
              <span className="muted small">Today</span>
              <strong className={formatter.pnlClass(account.data.day_pnl)}>{formatter.signedMoney(account.data.day_pnl)}</strong>
            </div>
            <div>
              <span className="muted small">This week</span>
              <strong className={formatter.pnlClass(account.data.week_pnl)}>{formatter.signedMoney(account.data.week_pnl)}</strong>
            </div>
          </div>
          <div className="two-columns">
            <section className="panel">
              <h2>Each trader today</h2>
              <table>
                <thead>
                  <tr>
                    <th>Trader</th>
                    <th className="number">Profit or loss</th>
                    <th>Stocks owned</th>
                  </tr>
                </thead>
                <tbody>
                  {(traders.document?.traders ?? []).map((trader) => (
                    <tr key={trader.name}>
                      <td>{trader.name}</td>
                      <td className={`number ${formatter.pnlClass(account.data?.trader_pnl[trader.name])}`}>{formatter.signedMoney(account.data?.trader_pnl[trader.name] ?? 0)}</td>
                      <td>
                        {(account.data?.owners ?? [])
                          .filter((owner) => owner.trader === trader.name)
                          .map((owner) => owner.symbol)
                          .join(', ') || <span className="muted">none</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="panel">
              <h2>Halts in force</h2>
              {account.data.halts.length === 0 && <p className="muted">None. Every trader may trade within its limits.</p>}
              {account.data.halts.map((halt) => (
                <p key={`${halt.scope}-${halt.until_date}`} className="halt-line">
                  <strong>{halt.scope}</strong> until {halt.until_date}: {halt.reason}
                </p>
              ))}
            </section>
          </div>
          <section className="panel">
            <h2>Positions</h2>
            {account.data.positions.length === 0 ? (
              <p className="muted">No open positions.</p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Product</th>
                      <th>Trader</th>
                      <th className="number">Quantity</th>
                      <th className="number">Last price</th>
                      <th className="number">Today</th>
                    </tr>
                  </thead>
                  <tbody>
                    {account.data.positions.map((position) => (
                      <tr key={`${position.instrument_id}-${position.product}`}>
                        <td>{position.symbol}</td>
                        <td>{position.product}</td>
                        <td>{ownerByInstrument.get(position.instrument_id) ?? <span className="muted">yours</span>}</td>
                        <td className="number">{position.quantity}</td>
                        <td className="number">{formatter.priceText(position.last_price)}</td>
                        <td className={`number ${formatter.pnlClass(position.day_pnl)}`}>{formatter.signedMoney(position.day_pnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
      <section className="panel">
        <h2>Traders&apos; open orders</h2>
        {traderOrders.error !== null && <p className="error-text">{traderOrders.error}</p>}
        {openOrders.length === 0 ? (
          <p className="muted">No trader has an open order.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Placed</th>
                  <th>Trader</th>
                  <th>Order</th>
                  <th>Product</th>
                  <th className="number">Price</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {openOrders.map((order) => (
                  <tr key={order.record_id}>
                    <td className="mono">{formatter.dayTime(order.placed_at)}</td>
                    <td>{order.trader}</td>
                    <td>
                      {order.transaction_type} {order.quantity} {order.symbol} <span className="muted small">({order.kind})</span>
                    </td>
                    <td>{order.product}</td>
                    <td className="number">{formatter.priceText(order.price)}</td>
                    <td>
                      {order.state}
                      {order.dry_run ? <span className="muted small"> · dry run</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel">
        <h2>UBI&apos;s order book</h2>
        <p className="muted small">Every order UBI knows about today, including your own. It is read only when you ask.</p>
        <button type="button" onClick={loadBrokerOrders}>
          {brokerOrders === null ? 'Load' : 'Reload'}
        </button>
        {brokerError !== null && <p className="error-text">{brokerError}</p>}
        {brokerOrders !== null && brokerOrders.length === 0 && <p className="muted">UBI has no orders today.</p>}
        {brokerOrders !== null && brokerOrders.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Status</th>
                  <th className="number">Filled</th>
                  <th className="number">Average price</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {brokerOrders.map((order, index) => (
                  <tr key={String(order.order_id ?? index)}>
                    <td className="mono">{String(order.order_id ?? order.engine_parent_id ?? '')}</td>
                    <td>{String(order.status ?? '')}</td>
                    <td className="number">{String(order.filled_quantity ?? '')}</td>
                    <td className="number">{formatter.priceText(order.average_price as number | null)}</td>
                    <td className="small">{String(order.status_message ?? '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel kill-panel">
        <h2>Kill switch</h2>
        <p>
          Halts every trader until tomorrow and asks UBI to flatten the whole account: open orders are cancelled and positions closed. It is the same switch the daily loss limit fires.
          {mode !== 'live' && ' In dry_run mode, the flatten is a dry run.'}
        </p>
        <button className="danger solid" type="button" onClick={() => setKilling(true)}>
          Fire the kill switch
        </button>
        {killReport !== null && <pre className="small">{killReport}</pre>}
      </section>
      {killing && (
        <ConfirmDialog
          title="Fire the kill switch"
          explanation="Every trader stops trading until tomorrow, and the whole account is flattened. This cannot be undone from here."
          confirmLabel="Fire"
          requiredWord="FLATTEN"
          onConfirm={kill}
          onClose={() => setKilling(false)}
        />
      )}
    </div>
  );
}
