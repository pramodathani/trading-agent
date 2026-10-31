# TradersPage.tsx

The home page. Each card shows a trader's state, today's profit or loss from the risk engine's per-trader figures, any halt, its models in the order they will be tried, and the last thing it did since the page opened.

Flatten asks for a reason and runs the trader's own `flatten_trader` tool through the API, so it goes through the risk engine and the journal like the trader's own flatten. Pause and resume take effect at once.

The account figures are polled every 15 seconds; the traders' state is refreshed by the layout every 5 seconds and at once when a turn starts or ends.

## Creating, retiring and restoring traders (ported from research-agent's `079753a`)

The page gains a New trader form, a Retire button on each card behind a confirmation, and a Retired traders section with Restore. Each card shows the trader's mandate and schedule from `/api/trader-records`, which is polled every 30 seconds and refreshed at once by `trader_created` and `trader_retired` events. After a creation the new trader is selected and its chat opened, so the user watches its introduction arrive.

What differs from research-agent:

- The form asks for the models, the heartbeat and the scheduled checks as well as the name and mandate, as the user chose. The models are the `[backends]` from `/api/configuration`, with the `[traders] backend_order` ticked by default and listed first; the ticked ones are tried in the order shown, which avoids a drag-to-reorder control. An empty heartbeat takes the default and 0 means none. Check times are validated as HH:MM before sending, and the gateway's own refusal is shown as it gives it.
- The form says plainly that a new trader may trade within the account-wide limits until it has limits of its own, because the user chose not to hold new traders back.
- Retire explains that a trader holding positions or open orders must be flattened first; the gateway refuses otherwise, and its sentence appears in the dialog. The confirmation asks no reason, unlike Flatten, because retiring changes no order and goes to no journal of trades.
- Names may be 200 characters long, so names wrap anywhere on the cards and the retired list, and the header menu cuts them off with an ellipsis.

Checked on 31 October 2026 with headless Chrome against a gateway started from the branch on a copy of the migrated live workspace, at 1400 and 412 pixels wide: the form's errors, creation and the opened chat, retiring with the dialog, restoring, and no sideways scrolling on the phone, with no console errors.
