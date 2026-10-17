import { type FormEvent, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { CronJob } from '../api/types';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';
import { useSelectedDesk } from '../layout/selectedDeskStore';
import { formatter } from '../utilities/formatter';

const REFRESH_MILLISECONDS = 15000;

type JobKind = 'agent' | 'command';

/**
 * The chosen desk's schedule: its jobs with their next runs, a form for new jobs, the latest runs, and its price alerts.
 * @returns The page.
 */
export function CronPage() {
  const deskName = useSelectedDesk();
  const jobs = usePolled(() => apiClient.jobs(deskName), REFRESH_MILLISECONDS, deskName);
  const alerts = usePolled(() => apiClient.alerts(deskName), REFRESH_MILLISECONDS, deskName);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /**
   * Runs an action, then shows its outcome and reloads.
   * @param action The request.
   * @param success What to say when it worked.
   */
  async function act(action: () => Promise<unknown>, success: string): Promise<void> {
    setError(null);
    try {
      await action();
      setNotice(success);
      jobs.refresh();
      alerts.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Schedule of {deskName}</h1>
        <p className="muted">Jobs wake the desk with instructions or run a command without a model. Times are India time; trading-day jobs skip weekends and exchange holidays.</p>
      </div>
      {notice !== null && (
        <div className="notice" role="status">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      {error !== null && <p className="error-text">{error}</p>}
      <section className="panel">
        <h2>Jobs</h2>
        <Loadable data={jobs.data} error={jobs.error}>
          {(document) => (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>When</th>
                    <th>Next runs</th>
                    <th>Last run</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {document.jobs.length === 0 && (
                    <tr>
                      <td colSpan={5} className="muted">
                        No jobs.
                      </td>
                    </tr>
                  )}
                  {document.jobs.map((job) => (
                    <JobRow
                      key={job.job_id}
                      job={job}
                      onRun={() => act(() => apiClient.runJob(deskName, job.job_id), `Started ${job.name}. Its result appears on the Activity page.`)}
                      onDelete={() => act(() => apiClient.deleteJob(deskName, job.job_id), `Deleted ${job.name}.`)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Loadable>
      </section>
      <NewJobForm deskName={deskName} onCreated={(name) => act(async () => undefined, `Created ${name}.`)} />
      <section className="panel">
        <h2>Latest runs</h2>
        <Loadable data={jobs.data} error={jobs.error}>
          {(document) => (
            <>
              {document.recent_runs.length === 0 && <p className="muted">No runs yet.</p>}
              {document.recent_runs.slice(0, 25).map((run, index) => (
                <div key={`${run.at}-${index}`} className="run-line small">
                  <span className="mono muted">{formatter.dayTime(run.at)}</span> <strong>{run.name}</strong> {run.outcome}
                  {run.detail && <span className="muted"> · {run.detail}</span>}
                </div>
              ))}
            </>
          )}
        </Loadable>
      </section>
      <section className="panel">
        <h2>Price alerts</h2>
        <p className="muted small">The desk sets these with set_price_alert. Each fires once, wakes the desk, and is removed.</p>
        <Loadable data={alerts.data} error={alerts.error}>
          {(document) => (
            <>
              {document.alerts.length === 0 && <p className="muted">No alerts.</p>}
              {document.alerts.map((alert) => (
                <div key={alert.alert_id} className="alert-line">
                  <span>{alert.description}</span>
                  <span className="muted small">{formatter.dayTime(alert.created_at)}</span>
                  <button type="button" onClick={() => act(() => apiClient.deleteAlert(deskName, alert.alert_id), `Removed the alert on ${alert.symbol}.`)}>
                    Remove
                  </button>
                </div>
              ))}
            </>
          )}
        </Loadable>
      </section>
    </div>
  );
}

/** What one job row shows. */
interface JobRowProperties {
  job: CronJob;
  onRun: () => void;
  onDelete: () => void;
}

/**
 * One job in the table.
 * @param properties The job and its actions.
 * @returns The row.
 */
function JobRow(properties: JobRowProperties) {
  const job = properties.job;
  const builtIn = job.created_by === 'built-in';
  return (
    <tr>
      <td>
        <div>
          <strong>{job.name}</strong> <span className="desk-chip">{builtIn ? 'built in' : job.created_by}</span>
        </div>
        <div className="muted small job-text">
          {job.kind === 'command' ? 'Command: ' : 'Instructions: '}
          <span className={job.kind === 'command' ? 'mono' : ''}>{job.text}</span>
        </div>
      </td>
      <td className="small">
        <span className="mono">{job.schedule ?? job.run_at ?? ''}</span>
        <div className="muted">
          {job.trading_days_only ? 'trading days' : 'every day'}
          {job.market_hours_only ? ', market hours' : ''}
        </div>
      </td>
      <td className="small mono">
        {job.next_runs.length === 0 && <span className="muted">none</span>}
        {job.next_runs.map((moment) => (
          <div key={moment}>{formatter.dayTime(moment)}</div>
        ))}
      </td>
      <td className="small mono">{job.last_run ? formatter.dayTime(job.last_run) : <span className="muted">never</span>}</td>
      <td>
        <span className="button-row">
          <button type="button" onClick={properties.onRun}>
            Run now
          </button>
          {!builtIn && (
            <button className="danger" type="button" onClick={properties.onDelete}>
              Delete
            </button>
          )}
        </span>
      </td>
    </tr>
  );
}

/** What the new job form needs. */
interface NewJobFormProperties {
  deskName: string;
  onCreated: (name: string) => void;
}

/**
 * A form for a new repeating job.
 * @param properties The desk and what to do after creating.
 * @returns The form.
 */
function NewJobForm(properties: NewJobFormProperties) {
  const [name, setName] = useState('');
  const [schedule, setSchedule] = useState('');
  const [kind, setKind] = useState<JobKind>('agent');
  const [text, setText] = useState('');
  const [tradingDaysOnly, setTradingDaysOnly] = useState(true);
  const [marketHoursOnly, setMarketHoursOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = name.trim() && schedule.trim() && text.trim();

  /**
   * Creates the job.
   * @param event The form's submit event.
   */
  async function create(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!ready) {
      return;
    }
    setError(null);
    try {
      await apiClient.createJob(properties.deskName, {
        name: name.trim(),
        schedule: schedule.trim(),
        run_at: null,
        instructions: kind === 'agent' ? text.trim() : null,
        command: kind === 'command' ? text.trim() : null,
        trading_days_only: tradingDaysOnly,
        market_hours_only: marketHoursOnly,
      });
      properties.onCreated(name.trim());
      setName('');
      setSchedule('');
      setText('');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  return (
    <form className="panel job-form" onSubmit={create}>
      <h2>New job</h2>
      <div className="form-grid">
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(change) => setName(change.target.value)} placeholder="Morning gap scan" />
        </label>
        <label className="field">
          <span>Schedule: minute, hour, day of month, month, weekday</span>
          <input className="mono" value={schedule} onChange={(change) => setSchedule(change.target.value)} placeholder="50 8 * * 1-5" />
        </label>
        <label className="field">
          <span>Kind</span>
          <select value={kind} onChange={(change) => setKind(change.target.value as JobKind)}>
            <option value="agent">Wake the desk with instructions</option>
            <option value="command">Run a command, no model</option>
          </select>
        </label>
      </div>
      <label className="field">
        <span>{kind === 'agent' ? 'Instructions for the desk' : 'Shell command, run in the desk sandbox'}</span>
        <textarea rows={3} className={kind === 'command' ? 'mono' : ''} value={text} onChange={(change) => setText(change.target.value)} />
      </label>
      <div className="filters">
        <label className="checkbox">
          <input type="checkbox" checked={tradingDaysOnly} onChange={(change) => setTradingDaysOnly(change.target.checked)} />
          Trading days only
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={marketHoursOnly} onChange={(change) => setMarketHoursOnly(change.target.checked)} />
          Only while NSE equities trade
        </label>
        <span className="spacer" />
        <button className="primary" type="submit" disabled={!ready}>
          Create
        </button>
      </div>
      {error !== null && <p className="error-text">{error}</p>}
    </form>
  );
}
