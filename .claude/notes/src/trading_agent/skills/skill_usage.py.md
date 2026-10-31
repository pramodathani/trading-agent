# skill_usage.py

Usage tracking for the curator (block 24). It is an event-bus listener run by the gateway beside the journal, so no tool or backend had to change.

## How a use is judged

A `load_skill` tool call opens a use. Failed tool results after it in the same turn count against it, except the failure of the `load_skill` call itself, which means the skill was not found and drops the use. When the trader's turn finishes, the use is written to `skills/usage.jsonl`; a turn that ended in an error event marks it failed. Trader turns run one at a time, so every open use at `turn_finished` belongs to that turn, including uses inside the rollover's summary and review turns, which publish no `turn_finished` of their own.

This is a rough signal: a tool can fail for reasons that have nothing to do with the skill. The curator is told to read "troubled" uses as hints to review, not as proof.

## Verified on 2026-10-17

Qwen ran `/range-check SBIN`; one line was written with `tool_errors_after: 0` and `turn_failed: false`.
