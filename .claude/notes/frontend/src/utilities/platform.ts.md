# platform.ts

A thin wrapper over `Capacitor.isNativePlatform()`, so components ask one question ("are we inside the Android app?") without importing Capacitor themselves. In a browser `@capacitor/core` reports the "web" platform and every app-only branch is skipped, so the desktop page behaves as before.
