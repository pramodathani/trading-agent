# file_routes.py

The user's files (Agents.md, User.md, TradingRules.md and each trader's Persona.md) can be edited through the API, because the agents cannot edit them and the user needs a way to. Each trader's Memory.md is listed too, because the user may want to correct what a trader remembers.

## Why TradingRules.md is checked before saving

The risk engine reads its limits from TradingRules.md. If a typing mistake made the limits unreadable, the engine would refuse every new position. Saving first and finding out later would leave the traders stuck until the user noticed. So the new text is written to a temporary file and read with the same `TradingLimitsReader`; if that fails, nothing is saved and the answer is 400 with the reason.

## Why Memory.md is checkpointed first

Memory.md is otherwise written only by the trader, and every trader write is checkpointed. A user edit is checkpointed in the same way, so it can be undone from the checkpoints page. If the snapshot fails, the edit still goes ahead and the failure is logged, because losing the ability to undo is less harmful than refusing the user's edit.

## Paths

Every name goes through `WorkspaceLayout.user_owned_file`, which accepts only the known file names. A name such as `../../.env` is refused with 400.

## Proposals

The proposal list includes the difference each proposal would make, so the frontend can show it without a second request. Accepting or rejecting a proposal that is not pending answers 409, because the request conflicts with the proposal's current state rather than being malformed.
