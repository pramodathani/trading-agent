import type { ContextCategory, ContextUsage } from '../api/types';
import { formatter } from '../utilities/formatter';
import { SideCard } from './SideCard';

const FREE_SPACE = 'Free space';
const SWATCHES: Record<string, string> = {
  Messages: 'var(--color-swatch-blue)',
  'System tools': 'var(--color-swatch-orange)',
  Tools: 'var(--color-swatch-orange)',
  'Memory files': 'var(--color-swatch-green)',
  'Autocompact buffer': 'var(--color-swatch-dark)',
  [FREE_SPACE]: 'var(--color-swatch-free)',
};

/** What the context card shows. */
interface ContextCardProperties {
  usage: ContextUsage | null;
  error: string | null;
}

/**
 * How full the model's context window is: the share used, a bar, and one row per category, as Claude Code shows it.
 * @param properties The latest snapshot and the latest error.
 * @returns The card.
 */
export function ContextCard(properties: ContextCardProperties) {
  const usage = properties.usage;
  if (usage === null) {
    return (
      <SideCard cardId="context" title="Context">
        {properties.error !== null ? <p className="side-empty error-text">{properties.error}</p> : <p className="side-empty">Shown after the trader's next turn.</p>}
      </SideCard>
    );
  }
  const window = usage.context_window;
  const loaded: ContextCategory[] = [];
  const deferred: ContextCategory[] = [];
  for (const category of usage.categories) {
    if (category.deferred) {
      deferred.push(category);
    } else {
      loaded.push(category);
    }
  }
  const used = formatter.share(usage.total_tokens, window).replace('.0%', '%');
  return (
    <SideCard cardId="context" title="Context" aside={usage.measured ? undefined : 'estimated'}>
      <div className="context-summary">
        <span>{used} used</span>
        <span className="muted">
          {formatter.tokenCount(usage.total_tokens)} / {formatter.tokenCount(window)}
        </span>
      </div>
      <div className="context-bar" role="img" aria-label={`${used} of the context window used`}>
        {loaded
          .filter((category) => category.name !== FREE_SPACE && category.tokens > 0)
          .map((category) => (
            <span
              key={category.name}
              style={{
                width: `${(100 * category.tokens) / Math.max(window, 1)}%`,
                background: swatchOf(category),
              }}
            />
          ))}
      </div>
      <div className="context-rows">
        {loaded.map((category) => (
          <ContextRow key={category.name} category={category} window={window} />
        ))}
      </div>
      {deferred.length > 0 && (
        <div className="context-rows deferred">
          {deferred.map((category) => (
            <ContextRow key={category.name} category={category} window={window} />
          ))}
        </div>
      )}
      <p className="side-note">
        {usage.backend} · {usage.measured ? 'measured by Claude Code' : 'estimated from the conversation'} at {formatter.time(usage.recorded_at)}
      </p>
    </SideCard>
  );
}

/**
 * One category: its colour, name, tokens and share of the window.
 * @param properties The category and the window's size.
 * @returns The row.
 */
function ContextRow(properties: { category: ContextCategory; window: number }) {
  const category = properties.category;
  return (
    <div className="context-row">
      <span className="swatch" style={{ background: swatchOf(category) }} />
      <span className="context-name">{category.name}</span>
      <span className="context-tokens">{formatter.tokenCount(category.tokens)}</span>
      <span className="context-share">{category.deferred ? '—' : formatter.share(category.tokens, properties.window)}</span>
    </div>
  );
}

/**
 * The colour a category is drawn in.
 * @param category The category.
 * @returns A CSS colour.
 */
function swatchOf(category: ContextCategory): string {
  if (category.deferred) {
    return 'var(--color-swatch-dark)';
  }
  return SWATCHES[category.name] ?? 'var(--color-swatch-grey)';
}
