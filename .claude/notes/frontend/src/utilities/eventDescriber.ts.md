# eventDescriber.ts

Every event kind the gateway publishes gets a short title, an optional detail, and a tone. The tone decides the colour and whether the event is routine. Routine events (token use, turn start and end, account checks, the first model choice, and sessions resumed after a restart) are hidden on the Activity page unless the user asks for them, because they made up most of the feed in the browser check on 17 October and hid the events that matter.

A model switch away from a model that was in use is a warning, because it means a model failed or hit a limit. The first choice of a model in a turn is routine.

Trigger sources are named in plain words, such as "Message from you" instead of `user_message`.

`steering` and `stopped` events, added in part 2, say whether a mid-turn message reached the running turn and that the user stopped a turn.

## Trader roster events

`trader_created` (also sent on a restore), `trader_retired` and `trader_sleeping` get sentences, with the mandate as detail. Falling asleep is quiet, and it is hidden from the cards' last-event line, so a card keeps showing what the trader last did.
