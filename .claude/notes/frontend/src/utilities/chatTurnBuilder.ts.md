# chatTurnBuilder.ts

The session log stores only each turn's question and final answer, but the trader's journal stores every step. The chat is built from the journal plus live events, grouped by trigger id, so every turn of the day shows its tool calls, risk decisions and model switches, not only the answer.

A turn is "waiting in the queue" from the moment the trader receives the trigger until its turn starts, because the trader announces the trigger on arrival and the turn separately.

Risk decisions and order events carry no trigger id. They happen inside a turn, so they are attached to the turn that is running at that moment. Events outside any turn, such as a fill while the trader is idle, are shown on their own line.

## Steering (milestone 18, part 2)

A trigger_received event with `steering_into` belongs inside the running turn, so it becomes a step of that turn rather than a new item. If the running turn ended before taking it, the message is queued as its own turn; when that turn starts, the message is added to the chat as a normal turn at that point.

## Attachments, since 2026-10-17

A turn's `attachments` come from the `trigger_received` event's payload, where the gateway writes them with the trigger, so pictures reappear after a reload or a restart without another request.

`ToolStep.picturePath` comes from the `picture_path` key of a `tool_result` event, set when the tool showed the model a picture saved in the trader folder.
