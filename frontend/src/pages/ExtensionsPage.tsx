import { apiClient } from '../api/apiClient';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';

const REFRESH_MILLISECONDS = 15000;

/**
 * What the desks can reach beyond their own tools: subagents, MCP servers and installed packages.
 * @returns The page.
 */
export function ExtensionsPage() {
  const subagents = usePolled(() => apiClient.subagents(), REFRESH_MILLISECONDS);
  const servers = usePolled(() => apiClient.mcpServers(), REFRESH_MILLISECONDS);
  const packages = usePolled(() => apiClient.packages(), REFRESH_MILLISECONDS);
  return (
    <div className="page">
      <div className="page-header">
        <h1>Extensions</h1>
        <p className="muted">Shared by every desk. Install and remove them with the trading-agent command, which shows what each brings before it is added.</p>
      </div>
      <section className="panel">
        <h2>Subagents</h2>
        <p className="muted small">Helpers a desk hands one task to with delegate_task. They cannot place orders unless their definition lists an order tool, and cannot start subagents of their own.</p>
        <Loadable data={subagents.data} error={subagents.error}>
          {(document) => (
            <>
              <div className="card-grid">
                {document.subagents.map((subagent) => (
                  <article key={subagent.name} className="mini-card">
                    <h3 className="mono">{subagent.name}</h3>
                    <p className="small">{subagent.description}</p>
                    <p className="muted small">
                      {subagent.maximum_turns} rounds at most, {subagent.timeout_seconds} s · models: {subagent.models?.join(', ') ?? "the desk's"}
                    </p>
                    <p className="muted small">Tools: {subagent.tools?.join(', ') ?? 'the default read-only set'}</p>
                  </article>
                ))}
              </div>
              {document.broken.map((broken) => (
                <p key={broken.path} className="error-text small">
                  {broken.path}: {broken.error}
                </p>
              ))}
            </>
          )}
        </Loadable>
      </section>
      <section className="panel">
        <h2>MCP servers</h2>
        <p className="muted small">Listed in mcp_servers.json. Their tools are named in the prompt and loaded with tool_search when a desk needs one.</p>
        <Loadable data={servers.data} error={servers.error}>
          {(document) => (
            <>
              {document.servers.length === 0 && <p className="muted">No MCP servers are configured.</p>}
              {document.servers.map((server) => (
                <div key={server.name} className="server-line">
                  <span className={`state-badge server-${server.state}`}>{server.state}</span> <strong>{server.name}</strong> <span className="muted small">{server.type}</span>
                  {server.error && <span className="error-text small"> {server.error}</span>}
                  {server.tools.length > 0 && <div className="mono small muted">{server.tools.join(', ')}</div>}
                </div>
              ))}
            </>
          )}
        </Loadable>
      </section>
      <section className="panel">
        <h2>Packages</h2>
        <Loadable data={packages.data} error={packages.error}>
          {(document) => (
            <>
              {document.packages.length === 0 && <p className="muted">No packages are installed.</p>}
              {document.packages.map((entry) => (
                <article key={entry.name} className="mini-card">
                  <h3>
                    {entry.name} <span className="muted small">{entry.version}</span>
                  </h3>
                  <p className="small">{entry.description}</p>
                  <p className="muted small">
                    Skills: {entry.skills.join(', ') || 'none'} · agents: {entry.agents.join(', ') || 'none'} · MCP: {entry.mcp_servers.join(', ') || 'none'} · hooks: {entry.hooks.join(', ') || 'none'}
                    {entry.has_app ? ' · has an app' : ''}
                  </p>
                </article>
              ))}
            </>
          )}
        </Loadable>
      </section>
    </div>
  );
}
