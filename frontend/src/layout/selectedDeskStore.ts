import { useSyncExternalStore } from 'react';

const STORAGE_KEY = 'trading-agent.desk';
const DEFAULT_DESK = 'general';

type Listener = () => void;

/** Remembers which desk the desk-specific pages show. */
export class SelectedDeskStore {
  private deskName: string;
  private readonly listeners = new Set<Listener>();

  /** Reads the desk chosen earlier. */
  constructor() {
    this.deskName = this.readSaved();
  }

  /**
   * The chosen desk.
   * @returns The desk's name.
   */
  current(): string {
    return this.deskName;
  }

  /**
   * Chooses a desk.
   * @param deskName The desk.
   */
  choose(deskName: string): void {
    if (deskName === this.deskName) {
      return;
    }
    this.deskName = deskName;
    try {
      window.localStorage.setItem(STORAGE_KEY, deskName);
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
   * Reads the saved desk.
   * @returns The saved desk, or main.
   */
  private readSaved(): string {
    try {
      return window.localStorage.getItem(STORAGE_KEY) ?? DEFAULT_DESK;
    } catch {
      return DEFAULT_DESK;
    }
  }

  /** Calls every listener. */
  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }
}

export const selectedDeskStore = new SelectedDeskStore();

/**
 * The chosen desk, kept up to date.
 * @returns The desk's name.
 */
export function useSelectedDesk(): string {
  return useSyncExternalStore(
    (listener) => selectedDeskStore.subscribe(listener),
    () => selectedDeskStore.current(),
  );
}
