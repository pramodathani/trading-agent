# order_tool.py and the five order tools

The order tools are place_order, place_bracket_order, modify_order, cancel_order and flatten_trader. They share one shallow base class, `OrderTool`, which holds only the mechanism that is the same for all of them: looking up a `TradeableInstrument`, valuing an order, building the risk engine's `OrderRequest`, recording an order in the trader order book, publishing an `order` event, and turning UBI's exceptions into error results. Each tool's own steps stay visible in its own file.

`OrderServices` is built once in `TraderBuilder`, so every trader shares one risk engine, one risk ledger and one trader order book. Sharing is what lets the engine give an instrument to one trader at a time.

## Dry run

In `dry_run` mode every request goes to UBI with `dry_run=True`. UBI checks it and answers without recording or sending anything, so a dry run gets no `parent_id`. `_remember` therefore records it under a made-up id starting with `dry-`, and modify_order, cancel_order and flatten_trader handle those records locally, so a trader can practise the whole life of an order.

## The tag

UBI's `tag` allows up to twenty letters and digits, so the trader name is stripped of every other character and cut to twenty. The tag is how positions and orders will be attributed to traders in milestone 16.

## Errors

`OrderOutcomeUnknownError` is caught before the general UBI error, because it means the order may have gone through, and the model must check get_orders before retrying or it may send the order twice.

## Valuation price

An order is valued at its limit price, else its trigger price, else the last traded price. A market order on an instrument with no last price is refused rather than valued at zero, because a zero value would slip past the margin limits.

## Testing on 2026-10-17

That day was a Saturday, and UBI refused even dry-run orders with `ServiceUnavailableError` because the day's instrument catalogue was not published. The approved path was therefore tested with fakes in `tests/test_order_tools.py`. Through the gateway, Qwen (place_order), Gemma (place_bracket_order) and Claude (place_order and flatten_trader) each called the tools correctly and reported the risk engine's weekend refusal word for word. The full path through UBI's dry run waits for a weekday.

## Releasing unused claims

`_release_unused_claim` gives up the trader's claim on an instrument once it has no open order there (in the trader order book) and the account holds no position or holding in it. Before this, a claim was only released by the risk engine's `release_unheld`, 30 minutes after it was made, so a cancelled order kept the instrument off limits to the other traders for up to half an hour; for an after-market order, whose claim is dated from the next open, the claim held through the weekend even after a flatten (seen on 2026-10-31, when the general trader flattened its dry-run IDEA order and IDEA stayed its own until 09:45 on Monday). The trader order book has no filled state, so an old filled order in the instrument still counts as open and keeps the claim; the grace period then releases it as before. When the account cannot be read, the claim is kept rather than risk releasing an instrument the trader holds.
