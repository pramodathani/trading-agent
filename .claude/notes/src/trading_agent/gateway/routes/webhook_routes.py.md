# webhook_routes.py

Incoming webhooks (block 39).

## Decisions

- **Its own token.** `TRADING_AGENT_WEBHOOK_TOKEN` in .env, not the gateway access token, because a webhook URL gets pasted into outside services such as TradingView, and that token must not be the one that controls the gateway. Without it, the route answers 404 as if it did not exist.
- **Token in the URL or a header.** TradingView cannot set request headers, so `?token=` is accepted; `X-Webhook-Token` too. Compared with `hmac.compare_digest`, so timing does not reveal the token. The token is in the redactor, so it never appears in the journal; it can still appear in reverse-proxy access logs if one is ever put in front.
- **Body.** Plain text, or JSON whose `text` or `message` field is used, at most 10,000 characters.
- **Labelled.** The desk is told the message came from outside, from whoever holds the token, and to check it against its rules before acting. A webhook can only wake a desk; any order still goes through the risk engine.

## Verified on 2026-10-17

A wrong token got 401; the right one queued a TradingView-style alert, and Qwen acknowledged it and declined to act because the market was closed and no strategy covered it.
