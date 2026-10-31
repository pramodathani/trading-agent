"""Tests for the event bus."""

import asyncio

from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module


def _text_event(text: str) -> event_module.Event:
    """Builds a text event for the tests.

    Args:
        text (str): The text to put in the payload.

    Returns:
        event_module.Event: The event.
    """
    return event_module.Event.now(
        event_module.EventKind.TEXT,
        'main',
        {
            'text': text,
        },
    )


class TestEventBus:
    """Tests for EventBus and EventSubscription."""

    def test_publish_reaches_every_subscriber(self) -> None:
        """Each subscriber receives its own copy of a published event."""

        async def scenario() -> list[str]:
            """Publishes one event to two subscribers.

            Returns:
                list[str]: The text each subscriber received.
            """
            event_bus = event_bus_module.EventBus()
            first = event_bus.subscribe()
            second = event_bus.subscribe()
            event_bus.publish(_text_event('hello'))
            received = [
                (await first.next_event()).payload['text'],
                (await second.next_event()).payload['text'],
            ]
            return received

        assert asyncio.run(scenario()) == [
            'hello',
            'hello',
        ]

    def test_full_queue_drops_oldest_event(self) -> None:
        """A subscriber that falls behind loses its oldest events, not its newest."""

        async def scenario() -> tuple[str, int]:
            """Publishes three events to a subscription that holds two.

            Returns:
                tuple[str, int]: The first event left in the queue and the dropped count.
            """
            event_bus = event_bus_module.EventBus()
            subscription = event_bus.subscribe(maximum_queued=2)
            for text in [
                'one',
                'two',
                'three',
            ]:
                event_bus.publish(_text_event(text))
            first_left = (await subscription.next_event()).payload['text']
            return first_left, subscription.dropped_count

        assert asyncio.run(scenario()) == ('two', 1)

    def test_closed_subscription_stops_receiving(self) -> None:
        """Leaving the with block unsubscribes."""
        event_bus = event_bus_module.EventBus()
        with event_bus.subscribe():
            assert event_bus.subscriber_count == 1
        assert event_bus.subscriber_count == 0

    def test_event_converts_to_json_dictionary(self) -> None:
        """An event's dictionary form holds plain strings for kind and time."""
        dictionary = _text_event('hello').to_json_dictionary()

        assert dictionary['kind'] == 'text'
        assert dictionary['trader'] == 'main'
        assert dictionary['created_at'].endswith('+00:00')
