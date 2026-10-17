import type { DeskSummary } from '../api/types';
import { SideCard, SideRow } from './SideCard';

/** What the desk card shows. */
interface DeskCardProperties {
  desk: DeskSummary | null;
}

/**
 * The desk's state, its trading mode and its session.
 * @param properties The desk, or null while it loads.
 * @returns The card.
 */
export function DeskCard(properties: DeskCardProperties) {
  const desk = properties.desk;
  if (desk === null) {
    return (
      <SideCard cardId="desk" title="Desk">
        <p className="side-empty">Loading…</p>
      </SideCard>
    );
  }
  let state = desk.state;
  if (desk.paused) {
    state = `${state}, paused`;
  }
  const live = desk.mode === 'live';
  return (
    <SideCard cardId="desk" title="Desk" aside={<span className={live ? 'mode-badge live' : 'mode-badge'}>{live ? 'LIVE' : 'DRY RUN'}</span>}>
      <SideRow label="Name" value={desk.name} />
      <SideRow label="State" value={state} valueClassName={desk.state === 'idle' ? undefined : 'working'} />
      <SideRow label="Waiting triggers" value={desk.queued} />
      <SideRow label="Exchanges this session" value={desk.exchanges} />
      <SideRow label="Session" value={<span className="mono" title={desk.session_id ?? undefined}>{desk.session_id ?? '—'}</span>} />
    </SideCard>
  );
}
