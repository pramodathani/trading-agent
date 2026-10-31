import { apiClient } from '../api/apiClient';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';
import { useSelectedTrader } from '../layout/selectedTraderStore';
import { formatter } from '../utilities/formatter';

const REFRESH_MILLISECONDS = 30000;
const ORIGIN_WORDS: Record<string, string> = {
  installed: 'yours',
  agent: 'written by the trader',
};

/**
 * The chosen trader's skills: the ones it can use, with how often they helped, and the ones hidden for a missing program or variable.
 * @returns The page.
 */
export function SkillsPage() {
  const traderName = useSelectedTrader();
  const skills = usePolled(() => apiClient.skills(traderName), REFRESH_MILLISECONDS, traderName);
  return (
    <div className="page">
      <div className="page-header">
        <h1>Skills of {traderName}</h1>
        <p className="muted">A skill is a written procedure the trader loads when a task matches it. The trader writes its own after complex work; the curator archives those it stops using.</p>
      </div>
      <Loadable data={skills.data} error={skills.error}>
        {(document) => (
          <>
            <section className="panel">
              <h2>Usable</h2>
              {document.available.length === 0 ? (
                <p className="muted">No skills yet. Import one with trading-agent skills import, or let the trader write its own.</p>
              ) : (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Skill</th>
                        <th>From</th>
                        <th className="number">Uses</th>
                        <th className="number">With trouble</th>
                        <th>Last used</th>
                      </tr>
                    </thead>
                    <tbody>
                      {document.available.map((skill) => (
                        <tr key={skill.name}>
                          <td className="wrap">
                            <div className="mono">{skill.name}</div>
                            <div className="muted small">{skill.description}</div>
                          </td>
                          <td>{ORIGIN_WORDS[skill.origin] ?? skill.origin}</td>
                          <td className="number">{skill.uses}</td>
                          <td className="number">{skill.troubled_uses}</td>
                          <td className="small">{skill.last_used ? formatter.dayTime(skill.last_used) : <span className="muted">never</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
            {document.hidden.length > 0 && (
              <section className="panel">
                <h2>Hidden</h2>
                <p className="muted small">These need a program or an environment variable this machine does not have, so the trader is not offered them.</p>
                {document.hidden.map((skill) => (
                  <p key={skill.name}>
                    <span className="mono">{skill.name}</span> <span className="muted">needs {skill.missing.join(', ')}</span>
                  </p>
                ))}
              </section>
            )}
          </>
        )}
      </Loadable>
    </div>
  );
}
