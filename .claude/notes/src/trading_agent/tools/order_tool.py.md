# order_tool.py and the five order tools

The order tools are place_order, place_bracket_order, modify_order, cancel_order and flatten_desk. They share one shallow base class, `OrderTool`, which holds only the mechanism that is the same for all of them: looking up a `TradeableInstrument`, valuing an order, building the risk engine's `OrderRequest`, recording an order in the desk order book, publishing an `order` event, and turning UBI's exceptions into error results. Each tool's own steps stay visible in its own file.

`OrderServices` is built once in `DeskBuilder`, so every desk shares one risk engine, one risk ledger and one desk order book. Sharing is what lets the engine give an instrument to one desk at a time.

## Dry run

In `dry_run` mode every request goes to UBI with `dry_run=True`. UBI checks it and answers without recording or sending anything, so a dry run gets no `parent_id`. `_remember` therefore records it under a made-up id starting with `dry-`, and modify_order, cancel_order and flatten_desk handle those records locally, so a desk can practise the whole life of an order.

## The tag

UBI's `tag` allows up to twenty letters and digits, so the desk name is stripped of every other character and cut to twenty. The tag is how positions and orders will be attributed to desks in milestone 16.

## Errors

`OrderOutcomeUnknownError` is caught before the general UBI error, because it means the order may have gone through, and the model must check get_orders before retrying or it may send the order twice.

## Valuation price

An order is valued at its limit price, else its trigger price, else the last traded price. A market order on an instrument with no last price is refused rather than valued at zero, because a zero value would slip past the margin limits.

## Testing on 2026-10-17

That day was a Saturday, and UBI refused even dry-run orders with `ServiceUnavailableError` because the day's instrument catalogue was not published. The approved path was therefore tested with fakes in `tests/test_order_tools.py`. Through the gateway, Qwen (place_order), Gemma (place_bracket_order) and Claude (place_order and flatten_desk) each called the tools correctly and reported the risk engine's weekend refusal word for word. The full path through UBI's dry run waits for a weekday.
