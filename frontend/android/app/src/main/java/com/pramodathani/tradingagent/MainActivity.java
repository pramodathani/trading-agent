package com.pramodathani.tradingagent;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

/**
 * The app's only screen: Capacitor's web view showing the trading-agent page, with the app's own plugins registered.
 */
public class MainActivity extends BridgeActivity {

    /**
     * Registers the app's own plugins before Capacitor starts.
     *
     * @param savedInstanceState The state Android saved, if the screen is being recreated.
     */
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(SpeechInputPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
