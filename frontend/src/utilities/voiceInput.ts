/** One recognised alternative, as the browser's speech recognition gives it. */
interface RecognitionAlternative {
  transcript: string;
}

/** The alternatives for one stretch of speech. */
interface RecognitionResult {
  readonly length: number;
  readonly isFinal: boolean;
  [index: number]: RecognitionAlternative;
}

/** Every stretch of speech heard since listening started. */
interface RecognitionResultList {
  readonly length: number;
  [index: number]: RecognitionResult;
}

/** The event the browser fires as it hears more. */
interface RecognitionEvent {
  results: RecognitionResultList;
}

/** The event the browser fires when recognition fails. */
interface RecognitionErrorEvent {
  error: string;
}

/** The part of the browser's SpeechRecognition object this page uses. */
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

type RecognitionConstructor = new () => Recognition;

/** What the voice input reports back to the page. */
export interface VoiceInputListener {
  onText: (text: string) => void;
  onEnd: () => void;
  onError: (message: string) => void;
}

const ERROR_WORDS: Record<string, string> = {
  'not-allowed': 'The browser was not allowed to use the microphone.',
  'service-not-allowed': 'The browser was not allowed to use the microphone.',
  'no-speech': 'No speech was heard.',
  'audio-capture': 'No microphone was found.',
  network: "The browser's speech service could not be reached.",
};

/** Turns speech into text with the browser's own speech recognition (Chrome and Edge). */
export class VoiceInput {
  private recognition: Recognition | null = null;

  /**
   * Whether this browser can recognise speech.
   * @returns True in Chrome and Edge.
   */
  isSupported(): boolean {
    return this.recognitionClass() !== null;
  }

  /**
   * Starts listening; the text heard so far is reported after every change, until stop is called or the browser stops.
   * @param listener Receives the text, the end and any error.
   */
  start(listener: VoiceInputListener): void {
    const RecognitionClass = this.recognitionClass();
    if (RecognitionClass === null) {
      listener.onError('This browser cannot turn speech into text. Chrome and Edge can.');
      listener.onEnd();
      return;
    }
    this.stop();
    const recognition = new RecognitionClass();
    recognition.lang = navigator.language || 'en-IN';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      const pieces: string[] = [];
      for (let index = 0; index < event.results.length; index += 1) {
        pieces.push(event.results[index][0].transcript);
      }
      listener.onText(pieces.join('').trim());
    };
    recognition.onerror = (event) => {
      if (event.error !== 'aborted') {
        listener.onError(ERROR_WORDS[event.error] ?? `Speech recognition failed: ${event.error}`);
      }
    };
    recognition.onend = () => {
      if (this.recognition === recognition) {
        this.recognition = null;
      }
      listener.onEnd();
    };
    this.recognition = recognition;
    recognition.start();
  }

  /** Stops listening; the browser then reports its last text and the end. */
  stop(): void {
    if (this.recognition !== null) {
      this.recognition.stop();
    }
  }

  /**
   * The browser's speech recognition class, under its standard or its Chrome name.
   * @returns The class, or null when the browser has none.
   */
  private recognitionClass(): RecognitionConstructor | null {
    const holder = window as unknown as Record<string, RecognitionConstructor | undefined>;
    return holder.SpeechRecognition ?? holder.webkitSpeechRecognition ?? null;
  }
}
