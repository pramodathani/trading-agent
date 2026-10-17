import type { ContextUsage, DeskSummary } from '../api/types';
import { SideCard, SideRow } from './SideCard';

/** What the model card shows. */
interface ModelCardProperties {
  desk: DeskSummary | null;
  usage: ContextUsage | null;
}

/**
 * Which model answers the desk, and the order its backends are tried in.
 * @param properties The desk and its latest context snapshot.
 * @returns The card.
 */
export function ModelCard(properties: ModelCardProperties) {
  const desk = properties.desk;
  const usage = properties.usage;
  if (desk === null) {
    return null;
  }
  const answering = desk.last_model ?? desk.preferred_model ?? '—';
  return (
    <SideCard cardId="model" title="Model">
      <SideRow label="Answered last" value={answering} />
      {usage !== null && usage.model.length > 0 && <SideRow label="Model" value={<span className="mono">{usage.model}</span>} />}
      <SideRow label="Preferred" value={desk.preferred_model ?? 'configured order'} />
      {desk.models.length > 0 && (
        <ol className="side-list">
          {desk.models.map((line) => (
            <li key={line}>{line.replace(/^\d+\.\s*/, '')}</li>
          ))}
        </ol>
      )}
    </SideCard>
  );
}
