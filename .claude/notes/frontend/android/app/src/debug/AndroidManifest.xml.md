# Debug-only network security config

Android blocks cleartext (`http://`) traffic for apps targeting API 28 and later; the WebView reports it as `net::ERR_CLEARTEXT_NOT_PERMITTED`. Normal use goes over HTTPS through `tailscale serve`, so release builds keep that block.

For testing over USB, `adb reverse tcp:8121 tcp:8121` makes the phone's `localhost:8121` reach a test gateway on the computer, and the app signs in to `http://localhost:8121`. This manifest overlay and `res/xml/network_security_config.xml` exist only in the `debug` source set, and they allow cleartext to `localhost` alone, so a debug build can do that and a release build cannot. `adb reverse` rules are dropped when the app is reinstalled, so set it again after each `npm run android:install`.
