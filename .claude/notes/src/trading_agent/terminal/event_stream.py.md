# event_stream.py

The reconnect rule copies `eventSocket.ts`: wait 1 second, doubling up to 15, and start again at 1 after a connection that worked. A wrong token shows up two ways depending on when the gateway checks it: a 403 at the handshake (`InvalidStatus`) or a close with code 1008 after accepting, so both raise `AccessRefusedError` and stop retrying, as the web page clears its token on 1008.
