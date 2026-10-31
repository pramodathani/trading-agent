# cancel_order_tool.py

Cancelling takes risk away, so the risk engine is not asked. When the record has a `parent_id`, the order is cancelled with `cancel_parent` even if the model named it by `order_id`, because cancelling only a broker leg of a synthetic order leaves the synthetic order running. A position the order already opened stays open, which the tool's description tells the model.

After a whole order is cancelled, the trader's claim on the instrument is released when nothing else of the trader's remains there (see `order_tool.py.md`), and the answer says so, so the model knows other traders may now trade it. Cancelling one part of a bracket keeps the claim, because the rest of the bracket is still working.
