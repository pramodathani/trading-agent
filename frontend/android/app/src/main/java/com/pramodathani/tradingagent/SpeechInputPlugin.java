package com.pramodathani.tradingagent;

import android.Manifest;
import android.content.Intent;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import java.util.ArrayList;

/**
 * Turns speech into text with Android's own speech recognizer and reports every stage to the page.
 *
 * Events sent to the page: "partial" and "final" with the text heard, "error" with a message, and "end" exactly once per listening session.
 */
@CapacitorPlugin(
    name = "SpeechInput",
    permissions = {
        @Permission(alias = "microphone", strings = { Manifest.permission.RECORD_AUDIO })
    }
)
public class SpeechInputPlugin extends Plugin {

    private SpeechRecognizer recognizer;
    private boolean ended = true;

    /**
     * Starts listening after making sure the microphone may be used.
     *
     * @param call The page's call, with an optional "language" such as "en-IN".
     */
    @PluginMethod
    public void start(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            requestPermissionForAlias("microphone", call, "afterMicrophonePermission");
            return;
        }
        beginListening(call);
    }

    /**
     * Stops listening; the recognizer then sends its final text and the end.
     *
     * @param call The page's call.
     */
    @PluginMethod
    public void stop(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            if (recognizer != null) {
                recognizer.stopListening();
            }
            call.resolve();
        });
    }

    /**
     * Continues a start call once the user has answered the microphone question.
     *
     * @param call The start call.
     */
    @PermissionCallback
    private void afterMicrophonePermission(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            call.reject("The app was not allowed to use the microphone. Allow it under Settings, Apps, Trading Agent, Permissions.");
            return;
        }
        beginListening(call);
    }

    /**
     * Creates the recognizer on the main thread and starts it.
     *
     * @param call The start call, resolved once listening has begun.
     */
    private void beginListening(PluginCall call) {
        String language = call.getString("language", "en-IN");
        getActivity().runOnUiThread(() -> {
            if (!SpeechRecognizer.isRecognitionAvailable(getContext())) {
                call.reject("This phone has no speech recognition service. Installing the Google app adds one.");
                return;
            }
            closeRecognizer();
            recognizer = SpeechRecognizer.createSpeechRecognizer(getContext());
            recognizer.setRecognitionListener(new Listener());
            Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, language);
            intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
            intent.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getActivity().getPackageName());
            ended = false;
            recognizer.startListening(intent);
            call.resolve();
        });
    }

    /**
     * Sends the end to the page once and frees the recognizer.
     */
    private void finish() {
        if (ended) {
            return;
        }
        ended = true;
        notifyListeners("end", new JSObject());
        closeRecognizer();
    }

    /**
     * Frees the recognizer, if there is one.
     */
    private void closeRecognizer() {
        if (recognizer != null) {
            recognizer.destroy();
            recognizer = null;
        }
    }

    /**
     * Frees the recognizer when the app closes.
     */
    @Override
    protected void handleOnDestroy() {
        closeRecognizer();
    }

    /**
     * Reads the first recognized text from a recognizer bundle.
     *
     * @param results The bundle from onPartialResults or onResults.
     * @return The text, or an empty string.
     */
    private static String firstText(Bundle results) {
        if (results == null) {
            return "";
        }
        ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        if (matches == null || matches.isEmpty() || matches.get(0) == null) {
            return "";
        }
        return matches.get(0);
    }

    /**
     * Explains a recognizer error code in plain words.
     *
     * @param error The code from SpeechRecognizer.
     * @return The explanation.
     */
    private static String describe(int error) {
        switch (error) {
            case SpeechRecognizer.ERROR_NO_MATCH:
            case SpeechRecognizer.ERROR_SPEECH_TIMEOUT:
                return "No speech was heard.";
            case SpeechRecognizer.ERROR_AUDIO:
                return "The microphone could not be read.";
            case SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS:
                return "The app was not allowed to use the microphone.";
            case SpeechRecognizer.ERROR_NETWORK:
            case SpeechRecognizer.ERROR_NETWORK_TIMEOUT:
                return "The speech service could not be reached.";
            case SpeechRecognizer.ERROR_RECOGNIZER_BUSY:
                return "The speech service is busy. Try again in a moment.";
            default:
                return "Speech recognition failed (code " + error + ").";
        }
    }

    /**
     * Receives the recognizer's callbacks and passes them to the page.
     */
    private class Listener implements RecognitionListener {

        /** {@inheritDoc} */
        @Override
        public void onReadyForSpeech(Bundle params) {}

        /** {@inheritDoc} */
        @Override
        public void onBeginningOfSpeech() {}

        /** {@inheritDoc} */
        @Override
        public void onRmsChanged(float rmsdB) {}

        /** {@inheritDoc} */
        @Override
        public void onBufferReceived(byte[] buffer) {}

        /** {@inheritDoc} */
        @Override
        public void onEndOfSpeech() {}

        /** {@inheritDoc} */
        @Override
        public void onError(int error) {
            JSObject data = new JSObject();
            data.put("message", describe(error));
            notifyListeners("error", data);
            finish();
        }

        /** {@inheritDoc} */
        @Override
        public void onResults(Bundle results) {
            JSObject data = new JSObject();
            data.put("text", firstText(results));
            notifyListeners("final", data);
            finish();
        }

        /** {@inheritDoc} */
        @Override
        public void onPartialResults(Bundle partialResults) {
            String text = firstText(partialResults);
            if (text.isEmpty()) {
                return;
            }
            JSObject data = new JSObject();
            data.put("text", text);
            notifyListeners("partial", data);
        }

        /** {@inheritDoc} */
        @Override
        public void onEvent(int eventType, Bundle params) {}
    }
}
