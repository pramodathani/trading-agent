import { apiClient } from '../api/apiClient';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';
import { useDesks } from '../layout/desksContext';

const REFRESH_MILLISECONDS = 20000;
const DOLLARS = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
});

/**
 * Which models each desk tries, in order, and how much each was used today.
 * @returns The page.
 */
export function ModelsPage() {
  const desks = useDesks();
  const usage = usePolled(() => apiClient.usage(), REFRESH_MILLISECONDS);
  return (
    <div className="page">
      <div className="page-header">
        <h1>Models and usage</h1>
        <p className="muted">Each desk tries its models in order and falls back when one is unavailable, waiting longer after each failure. Change a desk&apos;s first choice with /model in the chat.</p>
      </div>
      <section className="panel">
        <h2>Model order</h2>
        <div className="card-grid">
          {(desks.document?.desks ?? []).map((desk) => (
            <article key={desk.name} className="mini-card">
              <h3>{desk.name}</h3>
              {desk.models.length === 0 && <p className="muted small">No model: commands only.</p>}
              {desk.models.map((line) => (
                <div key={line} className="mono small">
                  {line}
                </div>
              ))}
              {desk.preferred_model !== null && <p className="muted small">Chosen first with /model: {desk.preferred_model}</p>}
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
                      <th>Desk</th>
                      <th>Model</th>
                      <th className="number">Calls</th>
                      <th className="number">Prompt tokens</th>
                      <th className="number">Cached prompt tokens</th>
                      <th className="number">Answer tokens</th>
                      <th className="number">API-equivalent cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(document.desks).flatMap(([deskName, backends]) =>
                      Object.entries(backends).map(([backendName, counts]) => (
                        <tr key={`${deskName}-${backendName}`}>
                          <td>{deskName}</td>
                          <td>{backendName}</td>
                          <td className="number">{counts.calls.toLocaleString('en-IN')}</td>
                          <td className="number">{counts.prompt_tokens.toLocaleString('en-IN')}</td>
                          <td className="number">{counts.cache_read_tokens.toLocaleString('en-IN')}</td>
                          <td className="number">{counts.completion_tokens.toLocaleString('en-IN')}</td>
                          <td className="number">{DOLLARS.format(counts.api_equivalent_cost_usd)}</td>
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
