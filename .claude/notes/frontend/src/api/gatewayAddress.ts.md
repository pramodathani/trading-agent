# gatewayAddress.ts

In a desktop browser the page is served by the gateway itself, so every call stays relative and the saved address is empty. The Android app is a Capacitor wrapper that bundles its own copy of the built page and serves it from `https://localhost` on the phone, so relative paths would reach the phone, not the gateway. The user enters the gateway's Tailscale address (served with HTTPS by `tailscale serve`) once on the sign-in page, and every fetch and the WebSocket are built from it.

`clean()` adds `https://` when no scheme is typed, because Tailscale serve always uses HTTPS and an `http://` page call from the `https://localhost` WebView would be blocked as mixed content. The WebSocket address swaps `http` for `ws`, so `https` becomes `wss`.

The address is kept when the token is cleared after a 401, so signing in again only needs the token.
