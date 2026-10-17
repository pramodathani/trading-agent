import { createContext, useContext } from 'react';

import type { DesksDocument } from '../api/types';

/** The desks' latest state, shared by the layout with every page. */
export interface DesksContextValue {
  document: DesksDocument | null;
  error: string | null;
  refresh: () => void;
}

export const DesksContext = createContext<DesksContextValue>({
  document: null,
  error: null,
  refresh: () => undefined,
});

/**
 * The desks' latest state.
 * @returns The desks document, its error and a refresh function.
 */
export function useDesks(): DesksContextValue {
  return useContext(DesksContext);
}
