# steering_inbox.py

Steering lets the user change a desk's course while it works, instead of waiting minutes for a long turn to finish. A user message that arrives while a model turn runs waits here, and the turn takes it at its next tool round.

## Why at the tool round, and not at once

A model call cannot be interrupted part way and resumed with extra input. The natural joins in a turn are the moments between tool rounds, when the model is about to be asked again anyway. The agent loop adds the messages as a user message there; the Claude runner hands them over through a PostToolUse hook, which Claude Code reads before Claude's next step. The plan described this as "injected at the next tool round".

## What if the turn never reaches another tool round

A turn that ends with a plain answer never asks for the messages. The desk then queues each one as its own turn, so nothing the user wrote is lost. A `steering` event says which happened: `delivered: true` when the running turn took it, `false` when it was queued instead.

## Only the desk's own turns

The inbox is given to the desk's own runners, not to its subagents, so a message meant for the desk cannot be swallowed by a helper working on one task. Slash commands are never steering; they wait in the queue as before, except /stop.

Each message is labelled with its India time and told to the model as sent "while you were working", so the model knows it may change what it is doing.
