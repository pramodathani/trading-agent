# chat_items.py

The data classes mirror the TypeScript types in `chatTurnBuilder.ts`. `ChatTurn.status_text()` copies `turnStatus` from `ChatPage.tsx`, and `segments()` copies `stepSegments`, so that tool calls in a row fold into one line as Claude Code shows them. `running_tool()` copies `runningTool` from `TurnProgress.tsx`: only the newest tool call counts, because once a later call has a result the earlier unanswered one is not what the desk is doing now.
