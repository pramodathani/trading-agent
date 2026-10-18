# Orders

The desks trade through seven tools. Every one that opens or changes a position asks the risk engine first, and every order carries its desk's name as UBI's `tag`, which is how positions and profit are attributed to desks.

| Tool | What it does |
|---|---|
| `place_order` | One order in one instrument |
| `place_bracket_order` | An entry that, on its first fill, sets up a stop-loss and a target held by UBI's engine |
| `modify_order` | Changes the quantity, price or trigger of one of the desk's own open orders |
| `cancel_order` | Cancels one of the desk's own orders |
| `flatten_desk` | Cancels every open order the desk placed and closes every position it owns, leaving other desks and your own trades alone |
| `get_orders` | Today's orders, trades, or the parents UBI's engine still holds |
| `get_portfolio` | The account's positions, holdings or funds across every broker |

<figure class="diagram">
--8<-- "docs/assets/diagrams/order-path.svg"
<figcaption>An order from a desk's model is checked, judged by the risk engine, sent to UBI tagged with the desk, recorded in the desk order book and published. The blue dots are the answers coming back.</figcaption>
</figure>

## Dry runs

In `dry_run` mode, every order goes to UBI with `dry_run` set: UBI checks it fully and sends nothing to a broker. UBI refuses even dry-run orders when its instrument list is not loaded, as at weekends, so dry runs can only be tried on a trading day.

## Fills

A plain limit order is held by UBI's engine until it is placed at the broker, so it starts with a `parent_id` and gets an `order_id` later. The desk order book keeps both. The market watcher reads UBI's order book every fifteen seconds while a market is open, matches each finished order to the desk that placed it, and wakes that desk with the result: filled, rejected or cancelled, with the quantity and the average price.

A desk can only change or cancel its own orders, and `flatten_desk` closes only its own positions, never another desk's or yours.

## Flattening waits for you

On this machine `flatten_desk` is listed in `[approvals]`, so when a desk calls it, the call is held and you are asked for permission in Chat and on Telegram. If nobody answers within five minutes, nothing is closed. Your own Flatten button on the Desks page is not held. [Questions, plans and permissions](../using/questions-and-permissions.md#permission-prompts) explains the rules, including what this means for the scalper's 15:05 exit.
