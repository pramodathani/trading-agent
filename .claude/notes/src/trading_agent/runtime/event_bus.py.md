# event_bus.py

Each subscriber gets its own bounded queue rather than all subscribers sharing one. A slow web browser tab must never make a trader wait, so when a subscriber's queue is full its oldest event is thrown away and counted in `dropped_count`. A subscriber that must not lose events, such as the trade journal, will be written to keep up or will be given a larger queue.

`publish` is a plain method, not a coroutine, so that synchronous code (for example a tool running in a worker thread) can publish without awaiting. It iterates over a copy of the subscription set because a subscriber may unsubscribe while events are being delivered.
