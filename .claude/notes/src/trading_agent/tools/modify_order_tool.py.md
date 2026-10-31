# modify_order_tool.py

A trader may change only an order recorded under its own name in the trader order book. Legs of a bracket are not recorded on their own, so they are changed through the bracket's `parent_id` and `part`.

Only a bigger quantity is sent to the risk engine, and only the extra quantity, valued at the new price if one is given. A smaller quantity or a new price does not add risk in a way the limits measure. A change to a bracket's part leaves the recorded entry quantity and price alone.

The record is updated after a dry-run order's change and after a live change, but not after a UBI dry run of a change to a live order, because that dry run changed nothing.
