const PHONE_QUERY = '(max-width: 760px)';

type Listener = () => void;

/** Tells whether the window is narrow enough for the phone layout, the same width at which the stylesheets switch. */
export class PhoneLayout {
  private readonly query: MediaQueryList | null;

  /** Starts watching the window's width. */
  constructor() {
    this.query = typeof window.matchMedia === 'function' ? window.matchMedia(PHONE_QUERY) : null;
  }

  /**
   * Whether the phone layout is in use.
   * @returns True on a narrow window.
   */
  isActive(): boolean {
    return this.query?.matches ?? false;
  }

  /**
   * Registers a listener for switches between the phone and desktop layouts.
   * @param listener Called after every switch.
   * @returns A function that removes the listener.
   */
  subscribe(listener: Listener): () => void {
    const query = this.query;
    if (query === null) {
      return () => undefined;
    }
    query.addEventListener('change', listener);
    return () => {
      query.removeEventListener('change', listener);
    };
  }
}

export const phoneLayout = new PhoneLayout();
