import type { TraderSummary } from '../api/types';
import { traderStateWords } from '../utilities/traderStateWords';
import { SideCard, SideRow } from './SideCard';

/** What the trader card shows. */
interface TraderCardProperties {
  trader: TraderSummary | null;
}

/**
 * The trader's state, its trading mode and its session.
 * @param properties The trader, or null while it loads.
 * @returns The card.
 */
export function TraderCard(properties: TraderCardProperties) {
  const trader = properties.trader;
  if (trader === null) {
    return (
      <SideCard cardId="trader" title="Trader">
        <p className="side-empty">Loading…</p>
      </SideCard>
    );
  }
  const live = trader.mode === 'live';
  return (
    <SideCard cardId="trader" title="Trader" aside={<span className={live ? 'mode-badge live' : 'mode-badge'}>{live ? 'LIVE' : 'DRY RUN'}</span>}>
      <SideRow label="Name" value={trader.name} />
      <SideRow label="State" value={traderStateWords.describe(trader)} valueClassName={traderStateWords.isWorking(trader.state) ? 'working' : undefined} />
      <SideRow label="Waiting triggers" value={trader.queued} />
      <SideRow label="Exchanges this session" value={trader.exchanges} />
      <SideRow label="Session" value={<span className="mono" title={trader.session_id ?? undefined}>{trader.session_id ?? '—'}</span>} />
    </SideCard>
  );
}
