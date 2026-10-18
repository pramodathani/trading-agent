import { Capacitor } from '@capacitor/core';

/** Tells whether the page runs in a desktop or phone browser, or inside the Android app. */
export class Platform {
  /**
   * Whether the page runs inside the Android app rather than a browser.
   * @returns True inside the app.
   */
  isApp(): boolean {
    return Capacitor.isNativePlatform();
  }
}

export const platform = new Platform();
