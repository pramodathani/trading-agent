# voiceInput.ts

Voice input uses the browser's own Web Speech API (`SpeechRecognition`, which Chrome and Edge expose as `webkitSpeechRecognition`). Firefox and Safari do not offer it, so the microphone button is disabled there with a title saying why.

In Chrome the audio is sent to Google's speech service to be turned into text; nothing goes through the gateway. A fully local alternative would be to record the audio in the page and transcribe it on the gateway with a local Whisper model, which this first version does not do.

Recognition runs with interim results, so the message box fills in as the user speaks; the text already in the box when listening started is kept in front. Sending a message, switching desks or pressing the button again stops listening. The browser asks once for permission to use the microphone; 127.0.0.1 counts as a secure origin, so it works without HTTPS.
