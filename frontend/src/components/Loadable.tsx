import type { ReactNode } from 'react';

/** What a loadable section shows. */
export interface LoadableProperties<Answer> {
  data: Answer | null;
  error: string | null;
  children: (data: Answer) => ReactNode;
}

/**
 * Shows a loading line, an error, or the loaded content.
 * @param properties The answer, the error and how to draw the answer.
 * @returns The section.
 */
export function Loadable<Answer>(properties: LoadableProperties<Answer>) {
  if (properties.error !== null && properties.data === null) {
    return <p className="error-text">{properties.error}</p>;
  }
  if (properties.data === null) {
    return <p className="muted">Loading…</p>;
  }
  return <>{properties.children(properties.data)}</>;
}
