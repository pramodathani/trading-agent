# SpeechInputPlugin.java

The app's own Capacitor plugin over Android's `SpeechRecognizer`, registered in `MainActivity.onCreate` before `super.onCreate`.

The plan first used `@capacitor-community/speech-recognition` 7.0.1. It built on Capacitor 8, but on the phone the microphone stayed red forever. Its Android code has two faults: with partial results on, `onError` (no match, speech timeout) only rejects a call that was already resolved and sends no "stopped" event, so the page never learns that listening ended; and `stop()` never resolves its call. Its last release was June 2025, so the plan's fallback, a small in-repo plugin, was built instead.

The contract with the page (`frontend/src/utilities/androidVoiceInput.ts`):

- `start({language})` asks for RECORD_AUDIO through the "microphone" permission alias if needed, then resolves once listening has begun.
- Events: `partial` and `final` carry `text`; `error` carries a plain-language `message`; `end` is sent exactly once per session, whatever ended it (the `ended` flag guards it). That guarantee is the whole point: the page always gets its mic button back.
- `stop()` calls `stopListening()`, after which the recognizer delivers its final result and the end.

`SpeechRecognizer` must be created and used on the main thread, hence `runOnUiThread`. On the user's Samsung phone the recognizer is Google's speech service, so audio is processed by Google, the same as the Web Speech API on the desktop page.
