# push_channel.py

The Android app's notification worker, modelled on `TelegramChannel._event_loop` and `_forward`: one more background worker in `application.py`'s list, subscribed to the event bus.

- It reuses `NotificationFormatter`, so a fill or halt is worded the same on Telegram and on the phone, and strips the formatter's leading "trader: " because the trader is the notification's title.
- `PUSH_NOTIFICATIONS` is Telegram's list without `daily_summaries` (Telegram builds those from the session summaries at rollover; not ported to push yet) plus `requests`: permission requests, questions and plans waiting for the user. Those matter most on a phone, because a permission request lapses after five minutes (`[approvals] expiry_minutes`), and the scalper's 15:05 `flatten_trader` waits for one.
- Every notification carries `trader` in its data, which the app reads on tap to open that trader's chat; requests also carry `request_id`.
- A phone Firebase reports as `UNREGISTERED` (the app was uninstalled or its data cleared) is dropped from the store.
- Answers to the user's own messages are not pushed: the user is looking at the chat when they asked.

Tested on 2026-10-18 on the user's Galaxy M53 through a test gateway: the test notification arrived with the app in the background, and tapping a scalper fill-shaped notification switched the app to the scalper trader's chat.
