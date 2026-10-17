# secret_redactor.py

Two layers. Exact values: the agent's own secrets, and every value in tradingmachine's `.env` whose name contains PASSWORD, SECRET, TOKEN or KEY. Shapes: Anthropic tokens (`sk-ant-...`), bearer tokens, `token=` parameters and `api-key`/`api-secret` values, which catch secrets the redactor was never told about. Values shorter than eight characters are ignored so that ordinary words are never masked.

It is applied to the journal and to the live event stream. It is not applied to what tools return to the model, because the tools that could see secrets are already kept away from them by the sandbox and the path policy.

On 2026-10-17 the journal of a live turn was checked against five real secret values (the gateway token, the Claude token and three tradingmachine passwords) and contained none.

## Webhook token (milestone 15)

The webhook token is masked like the other secrets.

The Telegram bot token was added to the masked values in milestone 19.
