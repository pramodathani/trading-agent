# result_formatter.py

Candles are written as CSV because it costs far fewer tokens than JSON for the same table and models read it well; only the last rows are kept (50 by default), with a header saying how many there were, so a year of daily candles cannot fill Gemma's context. Everything else is JSON with one-space indentation, a compromise between readability and size. NumPy numbers, pandas timestamps and NaN, which `json.dumps` cannot write, are turned into plain numbers, ISO text and null. Answers are capped at 15,000 characters.
