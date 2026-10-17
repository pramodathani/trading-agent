const STORAGE_KEY = 'trading-agent.access-token';

type Listener = () => void;

/** Keeps the gateway's access token in this browser and tells listeners when it changes. */
export class TokenStore {
  private token: string | null;
  private readonly listeners = new Set<Listener>();

  /** Reads the token saved earlier, if any. */
  constructor() {
    this.token = this.readSaved();
  }

  /**
   * The token, or null when none is saved.
   * @returns The token.
   */
  current(): string | null {
    return this.token;
  }

  /**
   * Saves a new token.
   * @param token The token from TRADING_AGENT_GATEWAY_ACCESS_TOKEN in .env.
   */
  save(token: string): void {
    this.token = token;
    try {
      window.localStorage.setItem(STORAGE_KEY, token);
    } catch {
      this.notify();
      return;
    }
    this.notify();
  }

  /** Forgets the token, for example after the gateway refused it. */
  clear(): void {
    this.token = null;
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      this.notify();
      return;
    }
    this.notify();
  }

  /**
   * Registers a listener for token changes.
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
   * Reads the saved token.
   * @returns The token, or null.
   */
  private readSaved(): string | null {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  }

  /** Calls every listener. */
  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }
}

export const tokenStore = new TokenStore();
