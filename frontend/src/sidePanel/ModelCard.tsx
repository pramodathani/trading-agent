import type { ContextUsage, TraderSummary } from '../api/types';
import { SideCard, SideRow } from './SideCard';

/** What the model card shows. */
interface ModelCardProperties {
  trader: TraderSummary | null;
  usage: ContextUsage | null;
}

/**
 * Which model answers the trader, and the order its backends are tried in.
 * @param properties The trader and its latest context snapshot.
 * @returns The card.
 */
export function ModelCard(properties: ModelCardProperties) {
  const trader = properties.trader;
  const usage = properties.usage;
  if (trader === null) {
    return null;
  }
  const answering = trader.last_model ?? trader.preferred_model ?? '—';
  return (
    <SideCard cardId="model" title="Model">
      <SideRow label="Answered last" value={answering} />
      {usage !== null && usage.model.length > 0 && <SideRow label="Model" value={<span className="mono">{usage.model}</span>} />}
      <SideRow label="Preferred" value={trader.preferred_model ?? 'configured order'} />
      {trader.models.length > 0 && (
        <ol className="side-list">
          {trader.models.map((line) => (
            <li key={line}>{line.replace(/^\d+\.\s*/, '')}</li>
          ))}
        </ol>
      )}
    </SideCard>
  );
}
