# androidVoiceInput.ts

The Android app's counterpart to `voiceInput.ts` (the browser's Web Speech API, which Android's WebView does not provide). It is its own class with the same three methods (`isSupported`, `start`, `stop`), and `ChatPage` picks one with `platform.isApp()`, in keeping with one self-contained class per case. It talks to the in-repo `SpeechInput` plugin; see the note for `SpeechInputPlugin.java` for why the community plugin was dropped.

Android's recognizer is not continuous: it stops after a pause, unlike the desktop page's `continuous = true`. Each `partial` event carries the whole utterance so far, which `ChatPage` appends to whatever was in the box before listening began.
