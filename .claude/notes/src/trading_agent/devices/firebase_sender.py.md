# firebase_sender.py

Uses Firebase Cloud Messaging's HTTP v1 API directly with `httpx`, rather than the much larger `firebase-admin` package; the only new dependency is `google-auth[requests]` (pinned to 2.59.1, released 2026-09-30; 2.62.0 was under two weeks old when chosen), which turns the service-account key into a short-lived OAuth token. The token refresh is a blocking `requests` call, so it runs in `asyncio.to_thread` behind a lock.

The key file (`TRADING_AGENT_FIREBASE_SERVICE_ACCOUNT_FILE`) lives at `~/.config/trading-agent/firebase-service-account.json`, mode 600, outside the repository. It is a real secret: anyone holding it can send notifications to the app. The project id is read from the key, so `[push]` needs no project setting. The Firebase project is `trading-agent-d3ad6`.

Notifications go to Android channel `trading`, which the app creates with high importance (`pushRegistration.ts`), so they pop up and make a sound. Their title and text pass through Google's servers.
