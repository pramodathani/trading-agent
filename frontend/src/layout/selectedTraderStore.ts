import { useSyncExternalStore } from 'react';

const STORAGE_KEY = 'trading-agent.trader';
const DEFAULT_TRADER = 'general';

type Listener = () => void;

/** Remembers which trader the trader-specific pages show. */
export class SelectedTraderStore {
  private traderName: string;
  private readonly listeners = new Set<Listener>();

  /** Reads the trader chosen earlier. */
  constructor() {
    this.traderName = this.readSaved();
  }

  /**
   * The chosen trader.
   * @returns The trader's name.
   */
  current(): string {
    return this.traderName;
  }

  /**
   * Chooses a trader.
   * @param traderName The trader.
   */
  choose(traderName: string): void {
    if (traderName === this.traderName) {
      return;
    }
    this.traderName = traderName;
    try {
      window.localStorage.setItem(STORAGE_KEY, traderName);
    } catch {
      this.notify();
      return;
    }
    this.notify();
  }

  /**
   * Registers a listener for changes.
   * @param listener Called after every change.
   * @returns A function that removes the listener.
   */
  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /**
   * Reads the saved trader.
   * @returns The saved trader, or main.
   */
  private readSaved(): string {
    try {
      return window.localStorage.getItem(STORAGE_KEY) ?? DEFAULT_TRADER;
    } catch {
      return DEFAULT_TRADER;
    }
  }

  /** Calls every listener. */
  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }
}

export const selectedTraderStore = new SelectedTraderStore();

/**
 * The chosen trader, kept up to date.
 * @returns The trader's name.
 */
export function useSelectedTrader(): string {
  return useSyncExternalStore(
    (listener) => selectedTraderStore.subscribe(listener),
    () => selectedTraderStore.current(),
  );
}
