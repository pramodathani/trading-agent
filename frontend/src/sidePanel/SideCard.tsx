import type { ReactNode } from 'react';

import { sidePanelStore, useCardCollapsed } from './sidePanelStore';

/** What a side card shows. */
interface SideCardProperties {
  cardId: string;
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}

/**
 * One card of the side panel: a title that folds and unfolds it, and its content.
 * @param properties The card's id, title, the text at the right of the title, and its content.
 * @returns The card.
 */
export function SideCard(properties: SideCardProperties) {
  const collapsed = useCardCollapsed(properties.cardId);
  return (
    <section className="side-card">
      <div className="side-card-header">
        <button type="button" className="side-card-title" aria-expanded={!collapsed} onClick={() => sidePanelStore.toggleCollapsed(properties.cardId)}>
          {properties.title}
          <svg className={collapsed ? 'chevron folded' : 'chevron'} viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {properties.aside !== undefined && <span className="side-card-aside">{properties.aside}</span>}
      </div>
      {!collapsed && <div className="side-card-body">{properties.children}</div>}
    </section>
  );
}

/** What a side row shows. */
interface SideRowProperties {
  label: ReactNode;
  value: ReactNode;
  valueClassName?: string;
}

/**
 * One label and value on a line inside a side card.
 * @param properties The label, the value and the value's colour class.
 * @returns The row.
 */
export function SideRow(properties: SideRowProperties) {
  return (
    <div className="side-row">
      <span className="side-row-label">{properties.label}</span>
      <span className={properties.valueClassName === undefined ? 'side-row-value' : `side-row-value ${properties.valueClassName}`}>{properties.value}</span>
    </div>
  );
}
