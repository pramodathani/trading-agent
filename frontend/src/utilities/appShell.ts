import { App } from '@capacitor/app';
import { SystemBars, SystemBarsStyle } from '@capacitor/core';

import { backButton } from './backButton';
import { platform } from './platform';

const HOME_PATHS = new Set([
  '/',
  '/chat',
]);

/** Connects the page to the Android app around it: the back button and the colours of the status and navigation bars. */
export class AppShell {
  private started = false;

  /** Starts listening to the app; does nothing in a browser. */
  start(): void {
    if (!platform.isApp() || this.started) {
      return;
    }
    this.started = true;
    void App.addListener('backButton', () => {
      this.goBack();
    });
    this.matchTheme();
    const observer = new MutationObserver(() => {
      this.matchTheme();
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: [
        'data-theme',
      ],
    });
  }

  /** Closes the newest drawer or sheet, otherwise goes back a page, and from the chat puts the app in the background like the Claude app. */
  private goBack(): void {
    if (backButton.closeNewest()) {
      return;
    }
    if (HOME_PATHS.has(window.location.pathname) || window.history.length <= 1) {
      void App.minimizeApp();
      return;
    }
    window.history.back();
  }

  /** Makes the status and navigation bar icons light on the dark theme and dark on the light theme. */
  private matchTheme(): void {
    const dark = document.documentElement.dataset.theme !== 'light';
    void SystemBars.setStyle({
      style: dark ? SystemBarsStyle.Dark : SystemBarsStyle.Light,
    });
  }
}

export const appShell = new AppShell();
