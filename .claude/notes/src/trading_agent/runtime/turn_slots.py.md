# turn_slots.py

Ported from research-agent (commit `eabbd86`). Creating traders on demand means the number of traders running a model turn at once is no longer fixed at four. `[traders] maximum_running` lets the user cap it, for example to keep the local Ollama models or the Claude subscription's rate limit from being swamped; it is unset by default, so nothing changes unless the user asks.

A semaphore gives the waiting turns their slots in the order they asked. `is_free` is only used to show the trader as "waiting" before it blocks; it can be out of date by the time the slot is taken, which only affects that label.
