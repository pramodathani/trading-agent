import { apiClient } from '../api/apiClient';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';
import { useTraders } from '../layout/tradersContext';

const REFRESH_MILLISECONDS = 20000;
const DOLLARS = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
});

/**
 * Which models each trader tries, in order, and how much each was used today.
 * @returns The page.
 */
export function ModelsPage() {
  const traders = useTraders();
  const usage = usePolled(() => apiClient.usage(), REFRESH_MILLISECONDS);
  return (
    <div className="page">
      <div className="page-header">
        <h1>Models and usage</h1>
        <p className="muted">Each trader tries its models in order and falls back when one is unavailable, waiting longer after each failure. Change a trader&apos;s first choice with /model in the chat.</p>
      </div>
      <section className="panel">
        <h2>Model order</h2>
        <div className="card-grid">
          {(traders.document?.traders ?? []).map((trader) => (
            <article key={trader.name} className="mini-card">
              <h3>{trader.name}</h3>
              {trader.models.length === 0 && <p className="muted small">No model: commands only.</p>}
              {trader.models.map((line) => (
                <div key={line} className="mono small">
                  {line}
                </div>
              ))}
              {trader.preferred_model !== null && <p className="muted small">Chosen first with /model: {trader.preferred_model}</p>}
            </article>
          ))}
        </div>
      </section>
      <Loadable data={usage.data} error={usage.error}>
        {(document) => (
          <>
            <section className="panel">
              <h2>Today</h2>
              <p className="muted small">Claude is paid for by the Max subscription; its cost is what the same tokens would cost on the API, as a guide to how fast the limits are used. Local models cost nothing.</p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Trader</th>
                      <th>Model</th>
                      <th className="number">Calls</th>
                      <th className="number">Prompt tokens</th>
                      <th className="number">Cached prompt tokens</th>
                      <th className="number">Answer tokens</th>
                      <th className="number">Claude at API prices</th>
                      <th className="number">Charged</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(document.traders).flatMap(([traderName, backends]) =>
                      Object.entries(backends).map(([backendName, counts]) => (
                        <tr key={`${traderName}-${backendName}`}>
                          <td>{traderName}</td>
                          <td>{backendName}</td>
                          <td className="number">{counts.calls.toLocaleString('en-IN')}</td>
                          <td className="number">{counts.prompt_tokens.toLocaleString('en-IN')}</td>
                          <td className="number">{counts.cache_read_tokens.toLocaleString('en-IN')}</td>
                          <td className="number">{counts.completion_tokens.toLocaleString('en-IN')}</td>
                          <td className="number">{DOLLARS.format(counts.api_equivalent_cost_usd)}</td>
                          <td className="number">{DOLLARS.format(counts.cost_usd ?? 0)}</td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="panel">
              <h2>Subscription limits</h2>
              {Object.keys(document.rate_limits).length === 0 && <p className="muted">No limit report yet. Claude sends one with its answers.</p>}
              {Object.entries(document.rate_limits).map(([backendName, report]) => (
                <p key={backendName}>
                  <strong>{backendName}</strong>: the {String(report.limit ?? '').replaceAll('_', '-')} limit is <strong>{String(report.status ?? '')}</strong>
                  {typeof report.resets_at === 'number' && <span className="muted"> · resets {new Date(report.resets_at * 1000).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>}
                </p>
              ))}
            </section>
          </>
        )}
      </Loadable>
    </div>
  );
}
