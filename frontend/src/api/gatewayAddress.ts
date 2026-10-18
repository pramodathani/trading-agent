const STORAGE_KEY = 'trading-agent.gateway-address';

/**
 * Remembers which gateway the page talks to and builds addresses on it.
 *
 * In a browser the page is served by the gateway itself, so the address stays empty and every call goes to the same origin. The Android app carries its own copy of the page, so the user enters the gateway's address once, such as https://desktop.tailnet-name.ts.net.
 */
export class GatewayAddress {
  private address: string;

  /** Reads the address saved earlier, if any. */
  constructor() {
    this.address = this.readSaved();
  }

  /**
   * The gateway's address, or an empty string for the page's own origin.
   * @returns The address, without a trailing slash.
   */
  current(): string {
    return this.address;
  }

  /**
   * Saves a new address.
   * @param address The address the user typed; "https://" is added when no scheme is given.
   * @returns The cleaned address that was saved.
   */
  save(address: string): string {
    this.address = this.clean(address);
    try {
      window.localStorage.setItem(STORAGE_KEY, this.address);
    } catch {
      return this.address;
    }
    return this.address;
  }

  /**
   * Cleans an address the user typed.
   * @param address The typed address.
   * @returns The address with a scheme and without a trailing slash, or an empty string.
   */
  clean(address: string): string {
    let cleaned = address.trim();
    if (!cleaned) {
      return '';
    }
    if (!/^https?:\/\//i.test(cleaned)) {
      cleaned = `https://${cleaned}`;
    }
    while (cleaned.endsWith('/')) {
      cleaned = cleaned.slice(0, -1);
    }
    return cleaned;
  }

  /**
   * The full address of an API path on the gateway.
   * @param path A path starting with "/", such as "/api/desks".
   * @param address The gateway to use instead of the saved one, such as while checking a new address.
   * @returns The address to fetch.
   */
  url(path: string, address: string = this.address): string {
    return `${address}${path}`;
  }

  /**
   * The full WebSocket address of a path on the gateway.
   * @param path A path starting with "/", such as "/ws/events".
   * @returns The ws:// or wss:// address.
   */
  socketUrl(path: string): string {
    if (!this.address) {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      return `${protocol}://${window.location.host}${path}`;
    }
    return `${this.address.replace(/^http/i, 'ws')}${path}`;
  }

  /**
   * Reads the saved address.
   * @returns The address, or an empty string.
   */
  private readSaved(): string {
    try {
      return window.localStorage.getItem(STORAGE_KEY) ?? '';
    } catch {
      return '';
    }
  }
}

export const gatewayAddress = new GatewayAddress();
