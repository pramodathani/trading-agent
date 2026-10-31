import { PushNotifications } from '@capacitor/push-notifications';

import { apiClient } from '../api/apiClient';
import { platform } from './platform';

const ANDROID_CHANNEL = 'trading';

type OpenListener = (traderName: string) => void;

/**
 * Registers the Android app for push notifications and reports which trader a tapped notification belongs to.
 *
 * The gateway sends notifications through Firebase Cloud Messaging; each one carries its trader, so a tap opens that trader's chat.
 */
export class PushRegistration {
  private listenersAdded = false;
  private openListener: OpenListener | null = null;
  private waitingTrader: string | null = null;

  /**
   * Asks for permission to show notifications, then registers this phone with the gateway; does nothing in a browser.
   * @returns A message when registration failed, or null.
   */
  async register(): Promise<string | null> {
    if (!platform.isApp()) {
      return null;
    }
    try {
      await this.addListeners();
      let permission = await PushNotifications.checkPermissions();
      if (permission.receive === 'prompt' || permission.receive === 'prompt-with-rationale') {
        permission = await PushNotifications.requestPermissions();
      }
      if (permission.receive !== 'granted') {
        return 'Notifications are not allowed for Trading Agent. Allow them under Settings, Apps, Trading Agent, Notifications.';
      }
      await PushNotifications.createChannel({
        id: ANDROID_CHANNEL,
        name: 'Trading',
        description: 'Fills, halts, alerts and requests from the traders',
        importance: 4,
        visibility: 1,
        vibration: true,
      });
      await PushNotifications.register();
      return null;
    } catch (failure) {
      return `Could not register for notifications: ${failure instanceof Error ? failure.message : String(failure)}`;
    }
  }

  /**
   * Sets what happens when a notification is tapped; a tap that arrived before this was set is passed on at once.
   * @param listener Receives the trader's name.
   * @returns A function that removes the listener.
   */
  onOpen(listener: OpenListener): () => void {
    this.openListener = listener;
    if (this.waitingTrader !== null) {
      const traderName = this.waitingTrader;
      this.waitingTrader = null;
      listener(traderName);
    }
    return () => {
      if (this.openListener === listener) {
        this.openListener = null;
      }
    };
  }

  /** Listens for the phone's Firebase token and for taps on notifications, once. */
  private async addListeners(): Promise<void> {
    if (this.listenersAdded) {
      return;
    }
    this.listenersAdded = true;
    await PushNotifications.addListener('registration', (token) => {
      void apiClient.registerDevice(token.value, this.phoneName()).catch(() => undefined);
    });
    await PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      const data = action.notification.data as Record<string, string> | undefined;
      const traderName = data?.trader ?? '';
      if (!traderName) {
        return;
      }
      if (this.openListener !== null) {
        this.openListener(traderName);
        return;
      }
      this.waitingTrader = traderName;
    });
  }

  /**
   * A name for this phone, from the model in the browser's user agent, such as "Android SM-M536B".
   * @returns The name.
   */
  private phoneName(): string {
    const match = /Android [\d.]+; ([^;)]+)/.exec(navigator.userAgent);
    if (match === null) {
      return 'Android phone';
    }
    const model = match[1].split(' Build/')[0].trim();
    return model ? `Android ${model}` : 'Android phone';
  }
}

export const pushRegistration = new PushRegistration();
