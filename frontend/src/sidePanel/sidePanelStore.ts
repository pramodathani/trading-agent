import { useSyncExternalStore } from 'react';

const OPEN_KEY = 'trading-agent.side-panel.open';
const COLLAPSED_KEY = 'trading-agent.side-panel.collapsed';
const WIDE_SCREEN_PIXELS = 1100;

type Listener = () => void;

/** Remembers whether the chat page's side panel is shown, and which of its cards are folded. */
export class SidePanelStore {
  private open: boolean;
  private readonly collapsed: Set<string>;
  private readonly listeners = new Set<Listener>();

  /** Reads the choices made earlier; the panel starts open on a wide screen. */
  constructor() {
    this.open = this.readOpen();
    this.collapsed = this.readCollapsed();
  }

  /**
   * Whether the panel is shown.
   * @returns True when it is shown.
   */
  isOpen(): boolean {
    return this.open;
  }

  /** Shows the panel if it is hidden, and hides it if it is shown. */
  toggleOpen(): void {
    this.open = !this.open;
    this.save(OPEN_KEY, this.open ? 'yes' : 'no');
    this.notify();
  }

  /**
   * Whether a card is folded.
   * @param cardId The card's id.
   * @returns True when only its title shows.
   */
  isCollapsed(cardId: string): boolean {
    return this.collapsed.has(cardId);
  }

  /**
   * Folds a card if it is open, and opens it if it is folded.
   * @param cardId The card's id.
   */
  toggleCollapsed(cardId: string): void {
    if (this.collapsed.has(cardId)) {
      this.collapsed.delete(cardId);
    } else {
      this.collapsed.add(cardId);
    }
    this.save(COLLAPSED_KEY, JSON.stringify(Array.from(this.collapsed)));
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
   * Reads whether the panel was shown last time.
   * @returns The saved choice, or true on a wide screen when there is none.
   */
  private readOpen(): boolean {
    try {
      const saved = window.localStorage.getItem(OPEN_KEY);
      if (saved !== null) {
        return saved === 'yes';
      }
    } catch {
      return window.innerWidth >= WIDE_SCREEN_PIXELS;
    }
    return window.innerWidth >= WIDE_SCREEN_PIXELS;
  }

  /**
   * Reads which cards were folded last time.
   * @returns The folded cards' ids.
   */
  private readCollapsed(): Set<string> {
    const folded = new Set<string>();
    try {
      const saved = JSON.parse(window.localStorage.getItem(COLLAPSED_KEY) ?? '[]') as unknown;
      if (Array.isArray(saved)) {
        for (const cardId of saved) {
          folded.add(String(cardId));
        }
      }
    } catch {
      return folded;
    }
    return folded;
  }

  /**
   * Saves one choice, ignoring a browser that refuses storage.
   * @param key The storage key.
   * @param value The value.
   */
  private save(key: string, value: string): void {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      return;
    }
  }

  /** Calls every listener. */
  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }
}

export const sidePanelStore = new SidePanelStore();

/**
 * Whether the side panel is shown, kept up to date.
 * @returns True when it is shown.
 */
export function useSidePanelOpen(): boolean {
  return useSyncExternalStore(
    (listener) => sidePanelStore.subscribe(listener),
    () => sidePanelStore.isOpen(),
  );
}

/**
 * Whether one card is folded, kept up to date.
 * @param cardId The card's id.
 * @returns True when only its title shows.
 */
export function useCardCollapsed(cardId: string): boolean {
  return useSyncExternalStore(
    (listener) => sidePanelStore.subscribe(listener),
    () => sidePanelStore.isCollapsed(cardId),
  );
}
