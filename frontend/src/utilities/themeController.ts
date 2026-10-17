const STORAGE_KEY = 'trading-agent.theme';

export type Theme = 'dark' | 'light';

/** Applies and remembers the colour theme, dark unless the user chose light. */
export class ThemeController {
  /** Applies the theme saved earlier. */
  applyStoredChoice(): void {
    this.apply(this.stored());
  }

  /**
   * The theme in use.
   * @returns "dark" or "light".
   */
  current(): Theme {
    return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
  }

  /**
   * Switches to the other theme and remembers it.
   * @returns The new theme.
   */
  toggle(): Theme {
    const next: Theme = this.current() === 'dark' ? 'light' : 'dark';
    this.apply(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      return next;
    }
    return next;
  }

  /**
   * Sets the theme on the page.
   * @param theme The theme.
   */
  private apply(theme: Theme): void {
    document.documentElement.dataset.theme = theme;
  }

  /**
   * Reads the saved theme.
   * @returns The saved theme, or dark.
   */
  private stored(): Theme {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  }
}

export const themeController = new ThemeController();
