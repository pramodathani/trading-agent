import type { AccountDocument, AgentEvent, TraderOrder } from '../api/types';
import { SideCard, SideRow } from './SideCard';

/** What the orders card shows. */
interface OrdersCardProperties {
  traderName: string;
  events: AgentEvent[];
  openOrders: TraderOrder[] | null;
  account: AccountDocument | null;
}

/**
 * How many orders the trader placed today, how many are open, how many filled, and how many positions it holds.
 * @param properties The trader, today's events, its open orders and the account.
 * @returns The card.
 */
export function OrdersCard(properties: OrdersCardProperties) {
  let placed = 0;
  let cancelled = 0;
  let trades = 0;
  for (const event of properties.events) {
    if (event.kind === 'order' && event.payload.action === 'placed') {
      placed += 1;
    }
    if (event.kind === 'order' && event.payload.action === 'cancelled') {
      cancelled += 1;
    }
    if (event.kind === 'fill' && Number(event.payload.filled_quantity ?? 0) > 0) {
      trades += 1;
    }
  }
  let positions: number | string = '—';
  if (properties.account !== null) {
    positions = properties.account.owners.filter((owner) => owner.trader === properties.traderName).length;
  }
  return (
    <SideCard cardId="orders" title="Orders and trades" aside="today">
      <SideRow label="Orders placed" value={placed} />
      <SideRow label="Orders cancelled" value={cancelled} />
      <SideRow label="Trades (fills)" value={trades} />
      <SideRow label="Open orders" value={properties.openOrders === null ? '—' : properties.openOrders.length} />
      <SideRow label="Stocks held" value={positions} />
    </SideCard>
  );
}
