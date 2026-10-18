import { useEffect } from 'react';

import { apiClient } from '../api/apiClient';
import type { AgentEvent, DeskSummary } from '../api/types';
import { usePolled } from '../hooks/usePolled';
import { ContextCard } from './ContextCard';
import { DeskCard } from './DeskCard';
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
  'desk_halt',
  'kill_switch',
]);

/** What the side panel shows. */
interface SidePanelProperties {
  deskName: string;
  desk: DeskSummary | null;
  events: AgentEvent[];
}

/**
 * The column of cards beside the chat, as in Claude Code: the desk, its model, its context window, the money, the orders, the tools and the files it sent.
 * @param properties The desk's name, its summary and today's events for it.
 * @returns The panel.
 */
export function SidePanel(properties: SidePanelProperties) {
  const deskName = properties.deskName;
  const context = usePolled(() => apiClient.deskContext(deskName), CONTEXT_REFRESH_MILLISECONDS, deskName);
  const account = usePolled(() => apiClient.account(), ACCOUNT_REFRESH_MILLISECONDS);
  const deskOrders = usePolled(() => apiClient.deskOrders(), ACCOUNT_REFRESH_MILLISECONDS);
  const servers = usePolled(() => apiClient.mcpServers(), SERVERS_REFRESH_MILLISECONDS);
  const lastEvent = properties.events.length > 0 ? properties.events[properties.events.length - 1] : null;
  const refreshContext = context.refresh;
  const refreshAccount = account.refresh;
  const refreshOrders = deskOrders.refresh;

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
    <aside className="side-panel" aria-label="Desk details">
      <div className="sheet-handle" aria-hidden="true" />
      <DeskCard desk={properties.desk} />
      <ModelCard desk={properties.desk} usage={usage} />
      <ContextCard usage={usage} error={context.error} />
      <FundsCard account={account.data} error={account.error} />
      <ProfitCard deskName={deskName} account={account.data} />
      <OrdersCard deskName={deskName} events={properties.events} openOrders={deskOrders.data?.[deskName] ?? null} account={account.data} />
      <ToolsCard tools={context.data?.tools ?? []} servers={servers.data?.servers ?? null} />
      <OutputsCard deskName={deskName} events={properties.events} />
    </aside>
  );
}
