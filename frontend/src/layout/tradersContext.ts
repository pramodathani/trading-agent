import { createContext, useContext } from 'react';

import type { TradersDocument } from '../api/types';

/** The traders' latest state, shared by the layout with every page. */
export interface TradersContextValue {
  document: TradersDocument | null;
  error: string | null;
  refresh: () => void;
}

export const TradersContext = createContext<TradersContextValue>({
  document: null,
  error: null,
  refresh: () => undefined,
});

/**
 * The traders' latest state.
 * @returns The traders document, its error and a refresh function.
 */
export function useTraders(): TradersContextValue {
  return useContext(TradersContext);
}
