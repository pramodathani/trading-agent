# instrument_arguments.py

The fields copy tradingmachine_mcp's InstrumentDescription so that both projects name instruments the same way. The tools that need an instrument and more (get_candles) subclass these arguments rather than nest them, so the JSON schema the model sees stays flat, without `$ref` links that some servers and small models handle badly.

On 2026-10-17 Claude first asked for "NIFTY 50", which UBI does not know; the error suggested search_instruments, which found "NIFTY", and Claude retried on its own.
