# broker_tool.py and the read-only trading tools

The five tools (search_instruments, get_quote, get_candles, get_portfolio, get_orders) only read: they call GET routes or read properties of plain Instruments. The routes and their names follow tradingmachine_mcp's read-only server. Each tool's UBI work is a plain `_read` method, passed to the base class with `functools.partial`, so it runs in the worker thread under the UBI lock; the style guide asks for a named method rather than a multi-line lambda.

UBI and instrument errors become error results that say what to do next, rather than exceptions, so one failed read does not end the turn.

On 2026-10-17 UBI's daily candles ended at 2026-10-15 although Friday 2026-10-16's close was in the quote, so the get_candles description tells the model to use get_quote for current prices.
