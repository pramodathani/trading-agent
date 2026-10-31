# flatten_trader_tool.py

The plan named this tool `flatten_account`. It was built as `flatten_trader` instead, because `Account.flatten` closes every position in the account, which would undo other traders' trades and could sell the user's own holdings. Flattening the whole account stays with the kill switch, which the risk engine fires at the loss limits, and with the user's kill buttons in the web interface and Telegram.

Positions are closed with a market order whose `quantity_reference` is `liquidate_position` for the position's product, so UBI works out the exact quantity and side from the live positions. Holdings the trader owns that are not in today's positions are sold by their held quantity with product `cnc`. Each close still passes the risk engine, which lets a trader reduce its own position but refuses when the exchange is closed.

Each step is reported on its own line and a failed step does not stop the rest, so the model can see what is left and retry it.

## Releasing claims

After cancelling and closing, the tool releases each of the trader's claims that no longer has an open order or a position behind it, and lists each release. The symbols are read from the open orders before they are cancelled, because the ledger keeps only instrument ids. A position being closed by a market order is still held when the snapshot is read, so its claim stays until the risk engine's grace period ends.
