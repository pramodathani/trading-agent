# jev_check.py

The doctor's check of the Jev key.

It reads each trader's trader.toml directly with tomllib instead of going through the trader store, because the doctor only has trader names. A trader whose file cannot be read is skipped here; other checks report broken trader files.

With the key set, it makes one real request about a made-up state, labelled as a connection test. A request costs a few hundred input tokens at $42 per billion, far below a paisa, and it is the only way to know the key is accepted, because TypeSafe documents no free endpoint such as a model list.

A key with no Jev trader is a warning rather than a failure, because it is harmless but probably unintended.
