import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

import { apiClient } from '../api/apiClient';
import type { AgentEvent, Halt, TraderRecord, TraderSummary } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useLiveEvents } from '../hooks/useLiveEvents';
import { usePolled } from '../hooks/usePolled';
import { selectedTraderStore } from '../layout/selectedTraderStore';
import { useTraders } from '../layout/tradersContext';
import { eventDescriber } from '../utilities/eventDescriber';
import { formatter } from '../utilities/formatter';
import { traderStateWords } from '../utilities/traderStateWords';

const ACCOUNT_REFRESH_MILLISECONDS = 15000;
const RECORDS_REFRESH_MILLISECONDS = 30000;
const CONFIGURATION_REFRESH_MILLISECONDS = 300000;
const TRADER_NAME_PATTERN = /^[a-z][a-z0-9_-]{0,199}$/;
const TRADER_NAME_RULE = 'A name uses lower-case letters, digits, hyphens and underscores, starts with a letter, and is at most 200 characters long, such as banknifty-momentum.';
const CHECK_TIME_PATTERN = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;
const HIDDEN_KINDS = new Set([
  'model_usage',
  'rate_limit',
  'turn_finished',
  'account_status',
  'trader_sleeping',
]);
const ROSTER_KINDS = new Set([
  'trader_created',
  'trader_retired',
]);

/**
 * The home page: one card per trader with its mandate, state, model, profit and loss, last activity and controls, a form for a new trader, and the retired traders.
 * @returns The page.
 */
export function TradersPage() {
  const traders = useTraders();
  const account = usePolled(() => apiClient.account(), ACCOUNT_REFRESH_MILLISECONDS);
  const records = usePolled(() => apiClient.traderRecords(), RECORDS_REFRESH_MILLISECONDS);
  const events = useLiveEvents();
  const navigate = useNavigate();
  const [flattening, setFlattening] = useState<string | null>(null);
  const [retiring, setRetiring] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const lastEvent = events.length > 0 ? events[events.length - 1] : null;
  const refreshRecords = records.refresh;

  useEffect(() => {
    if (lastEvent !== null && ROSTER_KINDS.has(lastEvent.kind)) {
      void refreshRecords();
    }
  }, [
    lastEvent,
    refreshRecords,
  ]);

  const lastEventByTrader = useMemo(() => {
    const latest = new Map<string, AgentEvent>();
    for (const event of events) {
      if (event.trader !== null && !HIDDEN_KINDS.has(event.kind)) {
        latest.set(event.trader, event);
      }
    }
    return latest;
  }, [
    events,
  ]);

  const recordByName = useMemo(() => {
    const byName = new Map<string, TraderRecord>();
    for (const record of records.data?.records ?? []) {
      byName.set(record.name, record);
    }
    return byName;
  }, [
    records.data,
  ]);

  const retiredRecords = useMemo(() => {
    const retired = [];
    for (const record of records.data?.records ?? []) {
      if (record.retired) {
        retired.push(record);
      }
    }
    return retired;
  }, [
    records.data,
  ]);

  /**
   * Pauses or resumes a trader.
   * @param trader The trader.
   */
  async function togglePause(trader: TraderSummary): Promise<void> {
    try {
      if (trader.paused) {
        await apiClient.resume(trader.name);
      } else {
        await apiClient.pause(trader.name);
      }
      void traders.refresh();
    } catch (failure) {
      setNotice(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Flattens a trader and shows the tool's report.
   * @param traderName The trader.
   * @param reason Why.
   */
  async function flatten(traderName: string, reason: string): Promise<void> {
    const result = await apiClient.flatten(traderName, reason);
    setNotice(`${traderName}: ${result.text}`);
    void account.refresh();
  }

  /**
   * Retires a trader, then reads the lists again.
   * @param traderName The trader.
   */
  async function retire(traderName: string): Promise<void> {
    await apiClient.retireTrader(traderName);
    await Promise.all([
      traders.refresh(),
      refreshRecords(),
    ]);
  }

  /**
   * Brings a retired trader back, then reads the lists again.
   * @param traderName The trader.
   */
  async function restore(traderName: string): Promise<void> {
    setRestoring(traderName);
    try {
      await apiClient.restoreTrader(traderName);
      await Promise.all([
        traders.refresh(),
        refreshRecords(),
      ]);
    } catch (failure) {
      setNotice(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setRestoring(null);
    }
  }

  /**
   * Shows a new trader's chat once the lists know about it, so its introduction can be watched as it arrives.
   * @param traderName The new trader.
   */
  async function openNewTrader(traderName: string): Promise<void> {
    await Promise.all([
      traders.refresh(),
      refreshRecords(),
    ]);
    setFormOpen(false);
    selectedTraderStore.choose(traderName);
    void navigate('/chat');
  }

  if (traders.document === null) {
    return <p className="muted">{traders.error ?? 'Loading the traders…'}</p>;
  }

  const runningTraders = traders.document.traders;
  const canRetire = runningTraders.length > 1;

  return (
    <div className="page">
      <div className="page-header traders-header">
        <div className="traders-heading">
          <h1>Traders</h1>
          <p className="muted">Each trader is its own agent with its own mandate, persona, models, schedule and memory. All of them share one risk engine.</p>
        </div>
        {!formOpen && (
          <button className="primary new-trader-button" type="button" onClick={() => setFormOpen(true)}>
            New trader
          </button>
        )}
      </div>
      {account.data !== null && (
        <div className="summary-strip">
          <div>
            <span className="muted small">Account balance</span>
            <strong>{formatter.money(account.data.total_balance)}</strong>
          </div>
          <div>
            <span className="muted small">Today</span>
            <strong className={formatter.pnlClass(account.data.day_pnl)}>{formatter.signedMoney(account.data.day_pnl)}</strong>
          </div>
          <div>
            <span className="muted small">This week</span>
            <strong className={formatter.pnlClass(account.data.week_pnl)}>{formatter.signedMoney(account.data.week_pnl)}</strong>
          </div>
          <div>
            <span className="muted small">Open positions</span>
            <strong>{account.data.positions.length}</strong>
          </div>
        </div>
      )}
      {account.error !== null && <p className="error-text small">Account: {account.error}</p>}
      {notice !== null && (
        <div className="notice" role="status">
          <pre>{notice}</pre>
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      {formOpen && <NewTraderForm onCreated={openNewTrader} onCancel={() => setFormOpen(false)} />}
      <div className="trader-grid">
        {runningTraders.map((trader) => (
          <TraderCard
            key={trader.name}
            trader={trader}
            record={recordByName.get(trader.name) ?? null}
            pnl={account.data?.trader_pnl[trader.name] ?? null}
            halts={(account.data?.halts ?? []).filter((halt) => halt.scope === trader.name || halt.scope === 'account')}
            lastEvent={lastEventByTrader.get(trader.name) ?? null}
            canRetire={canRetire}
            onTogglePause={() => togglePause(trader)}
            onFlatten={() => setFlattening(trader.name)}
            onRetire={() => setRetiring(trader.name)}
          />
        ))}
      </div>
      {retiredRecords.length > 0 && (
        <section className="panel retired-traders">
          <h2>Retired traders</h2>
          <p className="muted small">A retired trader does not run, but its files, memory and journal are kept. Restoring it brings it back with its sessions.</p>
          <ul className="retired-list">
            {retiredRecords.map((record) => (
              <li key={record.name} className="retired-item">
                <div className="retired-text">
                  <strong className="trader-name-text">{record.name}</strong>
                  {record.created_at && <span className="muted small"> created {formatter.dayTime(record.created_at)}</span>}
                  {record.mandate && <p className="trader-mandate small">{record.mandate}</p>}
                </div>
                <button type="button" onClick={() => restore(record.name)} disabled={restoring !== null}>
                  {restoring === record.name ? 'Restoring…' : 'Restore'}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {records.error !== null && <p className="error-text small">Could not read the traders&apos; records: {records.error}</p>}
      {flattening !== null && (
        <ConfirmDialog
          title={`Flatten the ${flattening} trader`}
          explanation="This cancels the trader's open orders and closes its positions through its own flatten_trader tool, so the risk engine and the journal see it. Other traders are not touched."
          confirmLabel="Flatten"
          onConfirm={(reason) => flatten(flattening, reason)}
          onClose={() => setFlattening(null)}
        />
      )}
      {retiring !== null && (
        <ConfirmDialog
          title={`Retire ${retiring}?`}
          explanation={`${retiring} stops: it no longer answers messages, runs its schedule or receives heartbeats, alerts and fills. A trader that still owns positions or has open orders cannot be retired, so flatten it first. Its files, memory and journal stay in its folder, and you can restore it at any time from Retired traders on this page.`}
          confirmLabel="Retire"
          askReason={false}
          onConfirm={async () => retire(retiring)}
          onClose={() => setRetiring(null)}
        />
      )}
    </div>
  );
}

/** What one trader card shows. */
interface TraderCardProperties {
  trader: TraderSummary;
  record: TraderRecord | null;
  pnl: number | null;
  halts: Halt[];
  lastEvent: AgentEvent | null;
  canRetire: boolean;
  onTogglePause: () => void;
  onFlatten: () => void;
  onRetire: () => void;
}

/**
 * One trader's card.
 * @param properties The trader, its record and its controls.
 * @returns The card.
 */
function TraderCard(properties: TraderCardProperties) {
  const navigate = useNavigate();
  const trader = properties.trader;
  const record = properties.record;
  const working = traderStateWords.isWorking(trader.state);
  const stateExplanation = traderStateWords.explanation(trader.state);
  const lastEvent = properties.lastEvent;

  /** Opens the chat with this trader. */
  function openChat(): void {
    selectedTraderStore.choose(trader.name);
    void navigate('/chat');
  }

  return (
    <article className={working ? 'trader-card busy' : 'trader-card'}>
      <header className="trader-card-header">
        <h2 className="trader-name-text">{trader.name}</h2>
        <span className={`state-badge state-${trader.state}`} title={traderStateWords.explained(trader.state)}>
          {traderStateWords.short(trader.state)}
        </span>
        {trader.paused && <span className="state-badge paused">paused</span>}
        {trader.queued > 0 && <span className="muted small">{trader.queued} waiting</span>}
      </header>
      {stateExplanation !== null && <div className="small muted">{stateExplanation}</div>}
      {record !== null && record.mandate && (
        <div className="trader-mandate-block">
          <span className="muted small">Mandate</span>
          <p className="trader-mandate" title={record.mandate}>
            {record.mandate}
          </p>
          <span className="small muted">{scheduleWords(record)}</span>
        </div>
      )}
      <div className="trader-pnl">
        <span className="muted small">Today</span>
        <strong className={formatter.pnlClass(properties.pnl)}>{properties.pnl === null ? 'no trades' : formatter.signedMoney(properties.pnl)}</strong>
      </div>
      {properties.halts.map((halt) => (
        <p key={`${halt.scope}-${halt.until_date}`} className="halt-line">
          Halted until {halt.until_date}: {halt.reason}
        </p>
      ))}
      <div className="trader-models">
        <span className="muted small">Models, in the order tried</span>
        {trader.models.length === 0 && <span className="small">No model: commands only</span>}
        {trader.models.map((line) => (
          <span key={line} className="mono">
            {line}
          </span>
        ))}
      </div>
      <div className="small muted">
        Session <span className="mono">{trader.session_id ?? '—'}</span>, {trader.exchanges} {trader.exchanges === 1 ? 'exchange' : 'exchanges'}
      </div>
      <div className="trader-last-event small">
        {lastEvent === null ? (
          <span className="muted">Nothing since this page opened.</span>
        ) : (
          <>
            <span className="mono muted">{formatter.time(lastEvent.created_at)}</span> {eventDescriber.describe(lastEvent).title}
          </>
        )}
      </div>
      <footer className="trader-card-buttons">
        <button className="primary" type="button" onClick={openChat}>
          Chat
        </button>
        <button type="button" onClick={properties.onTogglePause}>
          {trader.paused ? 'Resume' : 'Pause'}
        </button>
        <button className="danger" type="button" onClick={properties.onFlatten}>
          Flatten
        </button>
        {properties.canRetire && (
          <>
            <span className="spacer" />
            <button className="danger" type="button" onClick={properties.onRetire}>
              Retire
            </button>
          </>
        )}
      </footer>
    </article>
  );
}

/**
 * A trader's heartbeat and scheduled checks in one line.
 * @param record The trader's record.
 * @returns Such as "Heartbeat every 10 min; checks at 09:05, 15:05".
 */
function scheduleWords(record: TraderRecord): string {
  let heartbeat = 'No heartbeat';
  if (record.heartbeat_minutes !== null) {
    heartbeat = `Heartbeat every ${record.heartbeat_minutes} min`;
  }
  if (record.scheduled_checks.length === 0) {
    return `${heartbeat}; no scheduled checks`;
  }
  return `${heartbeat}; checks at ${record.scheduled_checks.join(', ')}`;
}

/** The backends the form offers, and the ones a new trader gets by default. */
interface BackendChoices {
  names: string[];
  defaults: string[];
}

/**
 * Reads the backends and the [traders] defaults from the configuration.
 * @param configuration The configuration, as GET /api/configuration gives it.
 * @returns Every backend, the defaults first in their order, and the defaults.
 */
function backendChoices(configuration: Record<string, unknown> | null): BackendChoices {
  if (configuration === null) {
    return {
      names: [],
      defaults: [],
    };
  }
  const backends = (configuration.backends ?? {}) as Record<string, unknown>;
  const traderDefaults = (configuration.traders ?? {}) as Record<string, unknown>;
  const defaults = ((traderDefaults.backend_order ?? []) as string[]).filter((name) => name in backends);
  const names = [...defaults];
  for (const name of Object.keys(backends).sort()) {
    if (!names.includes(name)) {
      names.push(name);
    }
  }
  return {
    names,
    defaults,
  };
}

/** What the new trader form needs. */
interface NewTraderFormProperties {
  onCreated: (traderName: string) => Promise<void>;
  onCancel: () => void;
}

/**
 * A form that creates a trader; the gateway starts it at once and asks it to introduce itself.
 * @param properties What to do after creating or on cancel.
 * @returns The form.
 */
function NewTraderForm(properties: NewTraderFormProperties) {
  const configuration = usePolled(() => apiClient.configuration(), CONFIGURATION_REFRESH_MILLISECONDS);
  const choices = useMemo(
    () => backendChoices(configuration.data),
    [
      configuration.data,
    ],
  );
  const [name, setName] = useState('');
  const [mandate, setMandate] = useState('');
  const [chosenModels, setChosenModels] = useState<string[] | null>(null);
  const [heartbeat, setHeartbeat] = useState('');
  const [checks, setChecks] = useState('');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const models = chosenModels ?? choices.defaults;
  const trimmedName = name.trim();
  const nameProblem = trimmedName && !TRADER_NAME_PATTERN.test(trimmedName) ? TRADER_NAME_RULE : null;
  const checkTimes: string[] = [];
  for (const part of checks.split(',')) {
    if (part.trim()) {
      checkTimes.push(part.trim());
    }
  }
  const badCheck = checkTimes.find((time) => !CHECK_TIME_PATTERN.test(time));
  const checksProblem = badCheck === undefined ? null : `${badCheck} is not a time like 09:15; use 24-hour HH:MM, separated by commas.`;
  const heartbeatNumber = heartbeat.trim() === '' ? null : Number(heartbeat);
  let heartbeatProblem = null;
  if (heartbeatNumber !== null && (!Number.isInteger(heartbeatNumber) || heartbeatNumber < 0 || heartbeatNumber > 240)) {
    heartbeatProblem = 'The heartbeat is a whole number of minutes from 0 (none) to 240.';
  }
  const ready = Boolean(trimmedName) && nameProblem === null && Boolean(mandate.trim()) && checksProblem === null && heartbeatProblem === null && !working;

  /**
   * Ticks or unticks one model; the ticked ones are tried in the order shown.
   * @param backendName The backend.
   */
  function toggleModel(backendName: string): void {
    const ticked = new Set(models);
    if (ticked.has(backendName)) {
      ticked.delete(backendName);
    } else {
      ticked.add(backendName);
    }
    setChosenModels(choices.names.filter((choice) => ticked.has(choice)));
  }

  /**
   * Creates the trader and hands its name on.
   * @param event The form's submit event.
   */
  async function create(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!ready) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      await apiClient.createTrader({
        name: trimmedName,
        mandate: mandate.trim(),
        backend_order: models,
        heartbeat_minutes: heartbeatNumber,
        scheduled_checks: checkTimes,
        introduce: true,
      });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      setWorking(false);
      return;
    }
    await properties.onCreated(trimmedName);
  }

  return (
    <form className="panel job-form new-trader-form" onSubmit={create}>
      <h2>New trader</h2>
      <p className="muted small">
        The trader starts at once, restates its mandate in its chat, and proposes a fuller Persona.md and its own limits for you to accept. Until you add limits of its own to TradingRules.md, it may trade within the account-wide limits.
      </p>
      <label className="field">
        <span>Name</span>
        <input
          className="mono"
          value={name}
          onChange={(change) => setName(change.target.value)}
          placeholder="banknifty-momentum"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={200}
          autoFocus
        />
        {nameProblem !== null && <span className="error-text">{nameProblem}</span>}
      </label>
      <label className="field">
        <span>Mandate: what the trader trades and how</span>
        <textarea
          rows={4}
          value={mandate}
          onChange={(change) => setMandate(change.target.value)}
          placeholder="Intraday momentum in Bank Nifty options, buying only, with a stop on every trade and flat by 15:15."
        />
      </label>
      <fieldset className="field model-choices">
        <legend>Models, tried in the order shown</legend>
        {configuration.data === null && <span className="muted small">{configuration.error ?? 'Loading the models…'}</span>}
        <div className="model-choice-list">
          {choices.names.map((backendName) => (
            <label key={backendName} className="model-choice">
              <input type="checkbox" checked={models.includes(backendName)} onChange={() => toggleModel(backendName)} />
              <span className="mono">{backendName}</span>
            </label>
          ))}
        </div>
        {configuration.data !== null && models.length === 0 && <span className="muted small">No model ticked: the trader gets the default models.</span>}
      </fieldset>
      <div className="form-grid">
        <label className="field">
          <span>Heartbeat, in minutes while the market is open (empty for the default, 0 for none)</span>
          <input inputMode="numeric" value={heartbeat} onChange={(change) => setHeartbeat(change.target.value)} placeholder="10" />
          {heartbeatProblem !== null && <span className="error-text">{heartbeatProblem}</span>}
        </label>
        <label className="field">
          <span>Scheduled checks, India time on trading days (optional)</span>
          <input className="mono" value={checks} onChange={(change) => setChecks(change.target.value)} placeholder="09:10, 15:05" />
          {checksProblem !== null && <span className="error-text">{checksProblem}</span>}
        </label>
      </div>
      {error !== null && <p className="error-text">{error}</p>}
      <div className="dialog-buttons">
        <button type="button" onClick={properties.onCancel} disabled={working}>
          Cancel
        </button>
        <button className="primary" type="submit" disabled={!ready}>
          {working ? 'Creating…' : 'Create trader'}
        </button>
      </div>
    </form>
  );
}
