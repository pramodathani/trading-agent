# turn_runner.py

`close` was added in milestone 3 so that a runner which starts something, like a Claude Code process, can stop it when its trader stops. The default does nothing, so runners that start nothing need no code for it.

## saved_state and restore_state (milestone 11)

Two optional hooks for crash recovery. The defaults say "nothing to save" and "could not resume", which is right for any runner whose conversation lives only in memory. The model router calls them; the trader runtime never does.

## compact (milestone 12)

Optional, for `/compact`. The default says there is nothing to compact.

## Thinking, since 2026-10-18

`THINKING_LEVELS` and the `thinking`/`set_thinking` pair give `/think` one interface over very different backends. The base class returns None and False, meaning "no thinking setting", which is right for the no-model runner and for providers that decide on thinking themselves.

## Side questions, since 2026-10-18

`side_question` answers from the runner's conversation without changing it. `SIDE_QUESTION_NOTE` is put in front of the question by every runner, so all models are told the same thing: answer from what you know, use no tools, and nothing will be kept. The base class answers that there is no model, which only the no-model runner relies on.
