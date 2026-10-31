"""Delivers every published event to every subscriber.

Each subscriber gets its own bounded queue. A subscriber that falls behind loses its oldest events rather than slowing the traders down, and the number lost is counted.

Typical usage example:

  event_bus = EventBus()
  with event_bus.subscribe() as subscription:
      event_bus.publish(Event.now(EventKind.TEXT, trader='main'))
      event = await subscription.next_event()
"""

import asyncio
from types import TracebackType
from typing import Self

from trading_agent.runtime import event as event_module

_DEFAULT_MAXIMUM_QUEUED = 1000


class EventSubscription:
    """One subscriber's queue of events.

    Attributes:
        dropped_count: How many events were thrown away because the queue was full.
    """

    def __init__(self, event_bus: EventBus, maximum_queued: int):
        """Creates an empty subscription.

        Args:
            event_bus (EventBus): The bus this subscription belongs to.
            maximum_queued (int): How many unread events to keep before dropping the oldest.
        """
        self._event_bus = event_bus
        self._queue = asyncio.Queue(maxsize=maximum_queued)
        self.dropped_count = 0

    def deliver(self, published_event: event_module.Event) -> None:
        """Adds an event to the queue, dropping the oldest one if it is full.

        Args:
            published_event (event_module.Event): The event to deliver.
        """
        if self._queue.full():
            self._queue.get_nowait()
            self.dropped_count += 1
        self._queue.put_nowait(published_event)

    async def next_event(self) -> event_module.Event:
        """Waits for and returns the next event.

        Returns:
            event_module.Event: The oldest unread event.
        """
        return await self._queue.get()

    def close(self) -> None:
        """Stops delivery to this subscription."""
        self._event_bus.unsubscribe(self)

    def __enter__(self) -> Self:
        """Returns the subscription for use in a with statement.

        Returns:
            EventSubscription: This subscription.
        """
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Closes the subscription when the with statement ends.

        Args:
            exception_type (type[BaseException] | None): The type of exception raised in the block, if any.
            exception (BaseException | None): The exception raised in the block, if any.
            traceback (TracebackType | None): The traceback of that exception, if any.
        """
        self.close()


class EventBus:
    """The publish and subscribe hub that every component shares."""

    def __init__(self):
        """Creates a bus with no subscribers."""
        self._subscriptions = set()

    def publish(self, published_event: event_module.Event) -> None:
        """Delivers an event to every current subscriber.

        Args:
            published_event (event_module.Event): The event to deliver.
        """
        for subscription in list(self._subscriptions):
            subscription.deliver(published_event)

    def subscribe(
        self,
        maximum_queued: int = _DEFAULT_MAXIMUM_QUEUED,
    ) -> EventSubscription:
        """Starts a new subscription that receives every later event.

        Args:
            maximum_queued (int): How many unread events to keep before dropping the oldest.

        Returns:
            EventSubscription: The new subscription.
        """
        subscription = EventSubscription(self, maximum_queued)
        self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """Stops delivering events to a subscription.

        Args:
            subscription (EventSubscription): The subscription to stop.
        """
        self._subscriptions.discard(subscription)

    @property
    def subscriber_count(self) -> int:
        """How many subscriptions are currently receiving events."""
        return len(self._subscriptions)
