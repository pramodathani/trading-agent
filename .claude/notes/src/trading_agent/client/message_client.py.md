# message_client.py

`trading-agent send` and `trading-agent -p` both use this client. It connects to the event stream before posting the message, so no event of the turn can be missed, and then prints only the events of the turn it follows until `turn_finished`. Its logging is set to warnings only, so httpx's request lines do not mix with the reply.

## Following a steered message

When a desk is busy, `DeskRuntime` hands a plain message to the running turn instead of queueing it. The message's own trigger then never gets a `turn_finished`; the answer arrives under the running turn's trigger. The old client only followed its own trigger id, so it waited for its 600-second timeout. `TurnFollower` now watches for the `steering` event of its trigger: with `delivered: true` it switches to `into_trigger_id`, which is what `TelegramChannel` does, and with `delivered: false` it keeps waiting, because the message becomes the next turn under its own id. The fix was checked live on 2026-10-18 against a scratch gateway: a message sent 12 seconds into a 25-second `bash_run` came back with the shared answer after 21 seconds.

## Requests

`user_request` events carry no `trigger_id`, so the client prints every request of its desk while it follows the turn, with the request id and a pointer to the terminal program or the web page. Requests are not answered here, because a one-shot command cannot wait for a person.

## Output formats

The three formats copy `claude -p --output-format`. `json` prints one object at the end, with `answered_in_trigger_id` showing when the answer came from the running turn. `stream-json` prints each raw gateway event the follower took, then the same result object, so a script sees exactly what the web page sees. Problems before the turn starts (no gateway, a refused message) are printed as a result object with `is_error: true` in the two JSON formats, so a script never has to parse prose.

## Event stream filter

The client opens `/ws/events?desk=<desk>`, so it receives only that desk's events and desk-less ones. This also keeps a busy multi-desk gateway from filling the socket.
