import { type PluginListenerHandle, registerPlugin } from '@capacitor/core';

import type { VoiceInputListener } from './voiceInput';

/** The app's own speech plugin, SpeechInputPlugin.java in the Android project. */
interface SpeechInputPlugin {
  start(options: { language: string }): Promise<void>;
  stop(): Promise<void>;
  addListener(eventName: 'partial' | 'final', listener: (data: { text: string }) => void): Promise<PluginListenerHandle>;
  addListener(eventName: 'error', listener: (data: { message: string }) => void): Promise<PluginListenerHandle>;
  addListener(eventName: 'end', listener: () => void): Promise<PluginListenerHandle>;
}

const SpeechInput = registerPlugin<SpeechInputPlugin>('SpeechInput');

/** Turns speech into text inside the Android app with the phone's own speech recognition, as the Claude app's microphone does. */
export class AndroidVoiceInput {
  private handles: PluginListenerHandle[] = [];
  private listener: VoiceInputListener | null = null;

  /**
   * Whether speech can be recognised; the app always offers it, and start reports a phone without a speech service.
   * @returns True.
   */
  isSupported(): boolean {
    return true;
  }

  /**
   * Asks for the microphone if needed, then listens until stop is called or the phone hears a pause.
   * @param listener Receives the text heard so far, the end and any error.
   */
  start(listener: VoiceInputListener): void {
    void this.listen(listener);
  }

  /** Stops listening; the phone then reports its final text and the end. */
  stop(): void {
    void SpeechInput.stop().catch(() => this.finish());
  }

  /**
   * Does the work of start.
   * @param listener Receives the text heard so far, the end and any error.
   */
  private async listen(listener: VoiceInputListener): Promise<void> {
    await this.finish();
    this.listener = listener;
    this.handles.push(
      await SpeechInput.addListener('partial', (data) => {
        listener.onText(data.text.trim());
      }),
    );
    this.handles.push(
      await SpeechInput.addListener('final', (data) => {
        if (data.text) {
          listener.onText(data.text.trim());
        }
      }),
    );
    this.handles.push(
      await SpeechInput.addListener('error', (data) => {
        listener.onError(data.message);
      }),
    );
    this.handles.push(
      await SpeechInput.addListener('end', () => {
        void this.finish();
      }),
    );
    try {
      await SpeechInput.start({ language: navigator.language || 'en-IN' });
    } catch (failure) {
      listener.onError(failure instanceof Error ? failure.message : String(failure));
      await this.finish();
    }
  }

  /** Removes the event listeners and reports the end once. */
  private async finish(): Promise<void> {
    const handles = this.handles;
    this.handles = [];
    for (const handle of handles) {
      await handle.remove();
    }
    const listener = this.listener;
    this.listener = null;
    listener?.onEnd();
  }
}
