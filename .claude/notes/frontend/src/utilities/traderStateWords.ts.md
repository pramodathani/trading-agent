# traderStateWords.ts

Ported from research-agent's `analystStateWords.ts`. The gateway now reports two more states, `sleeping` and `waiting`, and every page used to treat anything other than `idle` as working. This class puts a state into words the same way on the cards, the trader menu, the side panel and the chat header, and decides what counts as working: only `busy` and `waiting`, because a sleeping trader has no turn to stop or steer. The explanation of sleeping lists alerts, fills and heartbeats as well as messages, because those wake a trader too.
