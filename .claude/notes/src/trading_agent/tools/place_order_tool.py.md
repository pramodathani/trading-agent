# place_order_tool.py

The lot-size check runs before the risk engine, because UBI does not check lots itself and a wrong quantity is the commonest model mistake with futures and options. A plain limit order is held inside UBI's engine as a `virtual_limit` until the market reaches its price, and a plain market order runs as a `marketable_limit` for up to 30 seconds; both are UBI's defaults and are described to the model rather than overridden.
