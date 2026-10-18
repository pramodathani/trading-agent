# capacitor.config.ts

- `appId` `com.pramodathani.tradingagent` is the Android package name; Firebase's `google-services.json` is tied to it, so changing it means re-registering the app in Firebase.
- `webDir` `dist` is Vite's output; `npm run android:sync` builds it and copies it into `android/app/src/main/assets/public` (ignored by git).
- `SystemBars.insetsHandling: 'css'` with `initialViewportFitValueHint: 'cover'` draws the page edge to edge and fills `env(safe-area-inset-*)`, which `phone.css` uses to keep the header below the status bar and the composer above the gesture bar.
- `Keyboard.resizeOnFullScreen` makes the WebView shrink when the keyboard opens even though the app is edge to edge, so the composer stays above the keyboard.
- `allowMixedContent: false`: the bundled page is `https://localhost`, and the gateway is reached over HTTPS through `tailscale serve`, so there is never a reason to load plain HTTP from it.

The app icon and splash were drawn from the web page's favicon (the orange rising line on #1e2129) at `frontend/assets/`, and `npx @capacitor/assets@3.0.5 generate --android` made every density into `android/app/src/main/res`. The app is called Trading Agent with its own icon; only the Claude app's layout is borrowed, not its name or logo.
