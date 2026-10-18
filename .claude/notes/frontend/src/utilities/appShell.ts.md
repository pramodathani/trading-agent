# appShell.ts

Runs only inside the Android app (it returns at once in a browser).

- **Back button:** Capacitor's `App` plugin reports Android's back button. The newest drawer or sheet registered in `backButton` closes first; otherwise the page goes back in history; on the chat page (the app's home) the app is minimised with `App.minimizeApp()` rather than closed, so the live connection and the page's state survive, the way the Claude app behaves.
- **System bars:** Capacitor 8's built-in `SystemBars` sets light icons on the dark theme and dark icons on the light theme. A `MutationObserver` on `data-theme` follows the theme toggle without `themeController` needing to know about the app. The separate `@capacitor/status-bar` plugin was installed at first and then removed, because `SystemBars` in `@capacitor/core` does the same job.
