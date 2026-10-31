import { useEffect } from 'react';

import { apiClient } from '../api/apiClient';
import type { AgentEvent, TraderSummary } from '../api/types';
import { usePolled } from '../hooks/usePolled';
import { ContextCard } from './ContextCard';
import { TraderCard } from './TraderCard';
import { FundsCard } from './FundsCard';
import { ModelCard } from './ModelCard';
import { OrdersCard } from './OrdersCard';
import { OutputsCard } from './OutputsCard';
import { ProfitCard } from './ProfitCard';
import { ToolsCard } from './ToolsCard';

const ACCOUNT_REFRESH_MILLISECONDS = 15000;
const CONTEXT_REFRESH_MILLISECONDS = 20000;
const SERVERS_REFRESH_MILLISECONDS = 60000;
const CONTEXT_CHANGING_KINDS = new Set([
  'turn_finished',
  'context_compressed',
  'session_started',
  'backend_switch',
]);
const ACCOUNT_CHANGING_KINDS = new Set([
  'order',
  'fill',
  'trader_halt',
  'kill_switch',
]);

/** What the side panel shows. */
interface SidePanelProperties {
  traderName: string;
  trader: TraderSummary | null;
  events: AgentEvent[];
}

/**
 * The column of cards beside the chat, as in Claude Code: the trader, its model, its context window, the money, the orders, the tools and the files it sent.
 * @param properties The trader's name, its summary and today's events for it.
 * @returns The panel.
 */
export function SidePanel(properties: SidePanelProperties) {
  const traderName = properties.traderName;
  const context = usePolled(() => apiClient.traderContext(traderName), CONTEXT_REFRESH_MILLISECONDS, traderName);
  const account = usePolled(() => apiClient.account(), ACCOUNT_REFRESH_MILLISECONDS);
  const traderOrders = usePolled(() => apiClient.traderOrders(), ACCOUNT_REFRESH_MILLISECONDS);
  const servers = usePolled(() => apiClient.mcpServers(), SERVERS_REFRESH_MILLISECONDS);
  const lastEvent = properties.events.length > 0 ? properties.events[properties.events.length - 1] : null;
  const refreshContext = context.refresh;
  const refreshAccount = account.refresh;
  const refreshOrders = traderOrders.refresh;

  useEffect(() => {
    if (lastEvent === null) {
      return;
    }
    if (CONTEXT_CHANGING_KINDS.has(lastEvent.kind)) {
      refreshContext();
    }
    if (ACCOUNT_CHANGING_KINDS.has(lastEvent.kind)) {
      refreshAccount();
      refreshOrders();
    }
  }, [
    lastEvent,
    refreshContext,
    refreshAccount,
    refreshOrders,
  ]);

  const usage = context.data?.usage ?? null;
  return (
    <aside className="side-panel" aria-label="Trader details">
      <div className="sheet-handle" aria-hidden="true" />
      <TraderCard trader={properties.trader} />
      <ModelCard trader={properties.trader} usage={usage} />
      <ContextCard usage={usage} error={context.error} />
      <FundsCard account={account.data} error={account.error} />
      <ProfitCard traderName={traderName} account={account.data} />
      <OrdersCard traderName={traderName} events={properties.events} openOrders={traderOrders.data?.[traderName] ?? null} account={account.data} />
      <ToolsCard tools={context.data?.tools ?? []} servers={servers.data?.servers ?? null} />
      <OutputsCard traderName={traderName} events={properties.events} />
    </aside>
  );
}
