# message_client.py

`trading-agent send` connects to the event stream before posting the message, so no event of the turn can be missed, and then prints only the events of its own trigger until `turn_finished`. It is the way to talk to a desk from the terminal, and with `!` from Claude Code, until the web interface exists. Its logging is set to warnings only, so httpx's request lines do not mix with the reply.
