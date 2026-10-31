"""Pushes the events worth a phone notification to every phone running the Android app.

It listens to the event bus like the Telegram channel does and words most notifications with the same NotificationFormatter, so a fill reads the same on Telegram and on the phone. The user chooses the kinds in trading_agent.toml's [push] notifications list. Requests that need the user (a permission, a question or a plan) are pushed too, so the user can answer them in the app before they lapse.

Each notification carries the trader's name, so tapping it opens that trader's chat.

Typical usage example:

  channel = PushChannel(store, sender, formatter, event_bus, ['fills', 'requests'])
  await channel.run()
"""

import logging
from collections.abc import Sequence
from typing import Protocol

from trading_agent.channels import (
    notification_formatter as notification_formatter_module,
)
from trading_agent.devices import device_store as device_store_module
from trading_agent.requests import user_request as user_request_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module

_LOGGER = logging.getLogger(__name__)
_QUEUE_SIZE = 20000
_MOST_REMEMBERED_TRIGGERS = 500
_APP_TITLE = 'Trading Agent'
_SENT = 'sent'
_UNREGISTERED = 'unregistered'


class NotificationSender(Protocol):
    """Anything that can send one notification to one phone, such as FirebaseSender."""

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: dict[str, str],
    ) -> str:
        """Sends one notification.

        Args:
            token (str): The phone's token.
            title (str): The title.
            body (str): The text.
            data (dict[str, str]): Values the app reads when the notification is tapped.

        Returns:
            str: "sent", "unregistered" or "failed".
        """


class PushChannel:
    """The worker that turns events into phone notifications."""

    def __init__(
        self,
        store: device_store_module.DeviceStore,
        sender: NotificationSender,
        formatter: notification_formatter_module.NotificationFormatter,
        event_bus: event_bus_module.EventBus,
        notifications: Sequence[str],
    ):
        """Subscribes to the bus without sending anything yet.

        Args:
            store (device_store_module.DeviceStore): The registered phones.
            sender (NotificationSender): Sends to one phone.
            formatter (notification_formatter_module.NotificationFormatter): Words the events.
            event_bus (event_bus_module.EventBus): The bus to listen to.
            notifications (Sequence[str]): The kinds to push, from [push] notifications; "requests" pushes questions, plans and permission requests.
        """
        self._store = store
        self._sender = sender
        self._formatter = formatter
        self._subscription = event_bus.subscribe(maximum_queued=_QUEUE_SIZE)
        self._push_requests = 'requests' in notifications
        self._trigger_sources: dict[str, tuple[str, str]] = {}

    async def run(self) -> None:
        """Pushes notifications as events arrive, until cancelled."""
        while True:
            published_event = await self._subscription.next_event()
            try:
                await self.handle(published_event)
            except Exception:
                _LOGGER.exception('Could not push an event to the phones')

    async def handle(self, published_event: event_module.Event) -> None:
        """Pushes one event if it is worth a notification.

        Args:
            published_event (event_module.Event): The event.
        """
        kind = published_event.kind
        payload = published_event.payload
        if kind == event_module.EventKind.TEXT_DELTA:
            return
        if kind == event_module.EventKind.TRIGGER_RECEIVED:
            self._remember_trigger(payload)
            return
        if kind == event_module.EventKind.USER_REQUEST:
            if self._push_requests:
                await self._push_request(payload)
            return
        source, trigger_text = self._trigger_sources.get(
            str(payload.get('trigger_id')), (None, None)
        )
        text = self._formatter.format(published_event, source, trigger_text)
        if text is None:
            return
        trader = published_event.trader or ''
        await self.push(
            trader or _APP_TITLE,
            self._without_trader_prefix(trader, text),
            {
                'trader': trader,
                'kind': str(kind),
            },
        )

    async def push(self, title: str, body: str, data: dict[str, str]) -> int:
        """Sends one notification to every registered phone, forgetting phones Firebase no longer knows.

        Args:
            title (str): The title.
            body (str): The text.
            data (dict[str, str]): Values the app reads when the notification is tapped.

        Returns:
            int: How many phones it was sent to.
        """
        sent = 0
        for device in self._store.devices():
            if await self.push_to(device, title, body, data):
                sent += 1
        return sent

    async def push_to(
        self,
        device: device_store_module.PhoneDevice,
        title: str,
        body: str,
        data: dict[str, str],
    ) -> bool:
        """Sends one notification to one phone, forgetting it when Firebase no longer knows it.

        Args:
            device (device_store_module.PhoneDevice): The phone.
            title (str): The title.
            body (str): The text.
            data (dict[str, str]): Values the app reads when the notification is tapped.

        Returns:
            bool: True when Firebase accepted the notification.
        """
        outcome = await self._sender.send(device.token, title, body, data)
        if outcome == _UNREGISTERED:
            _LOGGER.info(
                'Firebase no longer knows the phone %s; removing it',
                device.name,
            )
            self._store.forget_token(device.token)
        return outcome == _SENT

    async def _push_request(self, payload: dict) -> None:
        """Pushes a request that waits for the user: a permission, a question or a plan.

        Args:
            payload (dict): The user_request event's payload.
        """
        request = user_request_module.UserRequest.from_json_dictionary(payload)
        if request.status != 'pending':
            return
        content = request.content
        if request.kind == user_request_module.PERMISSION:
            title = f'{request.trader} needs your permission'
            body = f'It wants to run {content.get("tool_name", "a tool")}. Open the app to allow or deny it.'
        elif request.kind == user_request_module.PLAN:
            title = f'{request.trader} presents a plan'
            body = str(
                content.get('title', 'A plan is waiting for your approval.')
            )
        else:
            title = f'{request.trader} has a question'
            questions = content.get('questions') or []
            body = 'Open the app to answer it.'
            if questions:
                body = str(questions[0].get('question', body))
        await self.push(
            title,
            body,
            {
                'trader': request.trader,
                'kind': 'user_request',
                'request_id': request.request_id,
            },
        )

    def _remember_trigger(self, payload: dict) -> None:
        """Keeps a trigger's source and text, so the formatter can tell a scheduled report from a reply.

        Args:
            payload (dict): The trigger_received event's payload.
        """
        if len(self._trigger_sources) >= _MOST_REMEMBERED_TRIGGERS:
            oldest = next(iter(self._trigger_sources))
            del self._trigger_sources[oldest]
        self._trigger_sources[str(payload.get('trigger_id'))] = (
            str(payload.get('source')),
            str(payload.get('text', '')),
        )

    @staticmethod
    def _without_trader_prefix(trader: str, text: str) -> str:
        """Drops the "trader: " the formatter starts with, because the trader is already the title.

        Args:
            trader (str): The trader.
            text (str): The formatted notification.

        Returns:
            str: The text without the prefix.
        """
        prefix = f'{trader}: '
        if trader and text.startswith(prefix):
            return text[len(prefix) :]
        return text
