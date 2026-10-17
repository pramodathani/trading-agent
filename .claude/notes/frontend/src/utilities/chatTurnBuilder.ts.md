# chatTurnBuilder.ts

The session log stores only each turn's question and final answer, but the desk's journal stores every step. The chat is built from the journal plus live events, grouped by trigger id, so every turn of the day shows its tool calls, risk decisions and model switches, not only the answer.

A turn is "waiting in the queue" from the moment the desk receives the trigger until its turn starts, because the desk announces the trigger on arrival and the turn separately.

Risk decisions and order events carry no trigger id. They happen inside a turn, so they are attached to the turn that is running at that moment. Events outside any turn, such as a fill while the desk is idle, are shown on their own line.
