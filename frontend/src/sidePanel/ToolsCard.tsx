import type { McpServerEntry } from '../api/types';
import { SideCard } from './SideCard';

/** What the tools card shows. */
interface ToolsCardProperties {
  tools: string[];
  servers: McpServerEntry[] | null;
}

/**
 * The desk's own tools and the MCP servers it can reach, each list folded until opened.
 * @param properties The tool names and the MCP servers.
 * @returns The card.
 */
export function ToolsCard(properties: ToolsCardProperties) {
  const servers = properties.servers ?? [];
  let serverTools = 0;
  for (const server of servers) {
    serverTools += server.tools.length;
  }
  return (
    <SideCard cardId="tools" title="Tools" aside={properties.tools.length + serverTools}>
      <details className="side-fold">
        <summary>
          <span>Desk tools</span>
          <span className="side-row-value">{properties.tools.length}</span>
        </summary>
        <ul className="side-list mono">
          {properties.tools.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      </details>
      <details className="side-fold">
        <summary>
          <span>MCP servers</span>
          <span className="side-row-value">{properties.servers === null ? '—' : servers.length}</span>
        </summary>
        <ul className="side-list">
          {servers.map((server) => (
            <li key={server.name} title={server.error || undefined}>
              <span className={server.state === 'ready' ? 'health-dot up' : 'health-dot down'} />
              <span className="mono">{server.name}</span>
              <span className="muted">
                {server.tools.length} {server.tools.length === 1 ? 'tool' : 'tools'}
              </span>
            </li>
          ))}
          {properties.servers !== null && servers.length === 0 && <li className="muted">None configured</li>}
        </ul>
      </details>
    </SideCard>
  );
}
