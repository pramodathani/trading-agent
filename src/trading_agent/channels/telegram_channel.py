"""The Telegram channel: talk to the desks and hear from them on your phone.

It runs two loops beside the desks:

1. The message loop asks Telegram for new messages. A chat that is not paired gets a pairing code and nothing else; every such message is logged as a channel event. A paired chat's code-only commands (/status, /positions, /pnl, /pause, /resume, /kill, /desk, /help) are answered at once; anything else is sent to the chat's desk as a user message.
2. The event loop listens to the event bus. A desk's answer to a message from Telegram goes back to the chat it came from. The notifications chosen in [telegram] notifications, such as fills and halts, go to every paired chat.

A message sent while its desk is working steers the running turn, as on the web page; the chat is told so, and the running turn's answer comes to it too.

Typical usage example:

  channel = TelegramChannel(api, pairing, commands, formatter, desks, parts, event_bus, 'main')
  await channel.run()
"""

import asyncio
import logging
from collections.abc import Mapping

from trading_agent.channels import (
    notification_formatter as notification_formatter_module,
)
from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.channels import telegram_api as telegram_api_module
from trading_agent.channels import telegram_commands as telegram_commands_module
from trading_agent.gateway import gateway_parts
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module

_LOGGER = logging.getLogger(__name__)
_FIRST_RETRY_SECONDS = 5.0
_LONGEST_RETRY_SECONDS = 120.0
_QUEUE_SIZE = 20000
_MOST_REMEMBERED_TRIGGERS = 500
_PAIRING_REPLY = 'This bot obeys only its owner. To pair this chat, approve this code within an hour, in the web page (Channels) or with:\n\ntrading-agent pairing approve {code}\n\nYour code: {code}'
_STATE_OFF = 'off'
_STATE_CONNECTING = 'connecting'
_STATE_CONNECTED = 'connected'
_STATE_FAILED = 'failed'


class TelegramChannel:
    """The bot, its paired chats and its notifications.

    Attributes:
        state: "connecting", "connected" or "failed".
        error: Why the last attempt failed, or an empty string.
        username: The bot's username once connected.
    """

    def __init__(
        self,
        api: telegram_api_module.TelegramApi,
        pairing: pairing_store_module.PairingStore,
        commands: telegram_commands_module.TelegramCommands,
        formatter: notification_formatter_module.NotificationFormatter,
        desks: Mapping[str, desk_runtime.DeskRuntime],
        parts: Mapping[str, gateway_parts.DeskParts],
        event_bus: event_bus_module.EventBus,
        default_desk: str,
    ):
        """Creates the channel without contacting Telegram.

        Args:
            api (telegram_api_module.TelegramApi): The connection to Telegram.
            pairing (pairing_store_module.PairingStore): The paired chats and codes.
            commands (telegram_commands_module.TelegramCommands): The code-only commands.
            formatter (notification_formatter_module.NotificationFormatter): Decides what is pushed.
            desks (Mapping[str, desk_runtime.DeskRuntime]): The running desks.
            parts (Mapping[str, gateway_parts.DeskParts]): Each desk's session store, for the daily summaries.
            event_bus (event_bus_module.EventBus): Where the desks' events arrive.
            default_desk (str): The desk a newly paired chat talks to.
        """
        self._api = api
        self._pairing = pairing
        self._commands = commands
        self._formatter = formatter
        self._desks = desks
        self._parts = parts
        self._event_bus = event_bus
        self._default_desk = default_desk
        self._subscription = event_bus.subscribe(maximum_queued=_QUEUE_SIZE)
        self._reply_chats: dict[str, set[int]] = {}
        self._trigger_sources: dict[str, tuple[str, str]] = {}
        self.state = _STATE_OFF
        self.error = ''
        self.username = ''

    async def run(self) -> None:
        """Connects, then runs the message loop and the event loop until cancelled."""
        try:
            await self._connect()
            async with asyncio.TaskGroup() as group:
                group.create_task(self._message_loop())
                group.create_task(self._event_loop())
        finally:
            await self.close()

    async def close(self) -> None:
        """Closes the connection to Telegram."""
        self._event_bus.unsubscribe(self._subscription)
        await self._api.close()

    def approve(self, code: str) -> pairing_store_module.PairedChat:
        """Pairs the chat that was given a code, and tells the chat.

        Args:
            code (str): The pairing code.

        Returns:
            pairing_store_module.PairedChat: The paired chat.

        Raises:
            pairing_store_module.PairingError: No valid code matches.
        """
        chat = self._pairing.approve(code, self._default_desk)
        self._publish_channel('paired', chat.chat_id, chat.name, '')
        asyncio.get_running_loop().create_task(
            self._send(
                chat.chat_id,
                f'Paired. You are talking to the {chat.desk} desk. Send /help to see what you can do.',
            )
        )
        return chat

    async def _connect(self) -> None:
        """Checks the token, waiting longer after each failure until Telegram answers."""
        wait = _FIRST_RETRY_SECONDS
        while True:
            self.state = _STATE_CONNECTING
            try:
                self.username = await self._api.start()
            except telegram_api_module.TelegramApiError as error:
                self.state = _STATE_FAILED
                self.error = str(error)
                _LOGGER.warning(
                    'Telegram did not answer (%s); retrying in %.0f s',
                    error,
                    wait,
                )
                await asyncio.sleep(wait)
                wait = min(wait * 2, _LONGEST_RETRY_SECONDS)
                continue
            self.state = _STATE_CONNECTED
            self.error = ''
            self._publish_channel('connected', None, self.username, '')
            return

    async def _message_loop(self) -> None:
        """Handles new messages until cancelled, pausing after Telegram errors."""
        wait = _FIRST_RETRY_SECONDS
        while True:
            try:
                incoming = await self._api.messages()
            except telegram_api_module.TelegramApiError as error:
                self.state = _STATE_FAILED
                self.error = str(error)
                _LOGGER.warning(
                    'Telegram polling failed (%s); retrying in %.0f s',
                    error,
                    wait,
                )
                await asyncio.sleep(wait)
                wait = min(wait * 2, _LONGEST_RETRY_SECONDS)
                continue
            self.state = _STATE_CONNECTED
            self.error = ''
            wait = _FIRST_RETRY_SECONDS
            for message in incoming:
                await self._handle(message)

    async def _handle(
        self, message: telegram_api_module.IncomingMessage
    ) -> None:
        """Handles one message: pairing for strangers, commands and desk messages for paired chats.

        Args:
            message (telegram_api_module.IncomingMessage): The message.
        """
        chat = self._pairing.paired_chat(message.chat_id)
        if chat is None:
            await self._handle_stranger(message)
            return
        if self._commands.handles(message.text):
            reply = await self._commands.answer(chat, message.text)
            await self._send(chat.chat_id, reply)
            return
        desk = self._desks.get(chat.desk)
        if desk is None:
            await self._send(
                chat.chat_id,
                f'The desk {chat.desk!r} is not running. Choose another with /desk.',
            )
            return
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.USER_MESSAGE,
            chat.desk,
            message.text,
        )
        self._reply_chats.setdefault(trigger.trigger_id, set()).add(
            chat.chat_id
        )
        desk.submit(trigger)

    async def _handle_stranger(
        self, message: telegram_api_module.IncomingMessage
    ) -> None:
        """Answers a chat that is not paired with a pairing code, and logs the message.

        Args:
            message (telegram_api_module.IncomingMessage): The message.
        """
        code = self._pairing.request(message.chat_id, message.sender_name)
        self._publish_channel(
            'stranger', message.chat_id, message.sender_name, message.text[:200]
        )
        if code is None:
            return
        await self._send(message.chat_id, _PAIRING_REPLY.format(code=code))

    async def _event_loop(self) -> None:
        """Sends answers and notifications as events arrive, until cancelled."""
        while True:
            published_event = await self._subscription.next_event()
            try:
                await self._forward(published_event)
            except Exception:
                _LOGGER.exception('Could not forward an event to Telegram')

    async def _forward(self, published_event: event_module.Event) -> None:
        """Sends one event where it belongs: an answer to its chat, a notification to every chat.

        Args:
            published_event (event_module.Event): The event.
        """
        kind = published_event.kind
        payload = published_event.payload
        trigger_id = payload.get('trigger_id')
        if kind == event_module.EventKind.TEXT_DELTA:
            return
        if kind == event_module.EventKind.TRIGGER_RECEIVED:
            self._remember_trigger(payload)
            return
        if kind == event_module.EventKind.STEERING:
            await self._forward_steering(payload)
            return
        if kind == event_module.EventKind.TURN_FINISHED:
            self._reply_chats.pop(trigger_id, None)
            return
        waiting_chats = self._reply_chats.get(trigger_id, set())
        if waiting_chats and kind in (
            event_module.EventKind.TEXT,
            event_module.EventKind.ERROR,
        ):
            text = (
                payload.get('text')
                if kind == event_module.EventKind.TEXT
                else f'The turn failed: {payload.get("error")}'
            )
            for chat_id in waiting_chats:
                await self._send(chat_id, str(text))
            return
        if (
            kind == event_module.EventKind.SESSION_STARTED
            and payload.get('reason') == 'daily_rollover'
        ):
            await self._send_daily_summary(published_event.desk)
            return
        source, trigger_text = self._trigger_sources.get(
            trigger_id, (None, None)
        )
        notification = self._formatter.format(
            published_event, source, trigger_text
        )
        if notification is not None:
            await self._broadcast(notification)

    async def _forward_steering(self, payload: dict) -> None:
        """Tells a chat that its message reached the running turn, and sends it that turn's answer too.

        Args:
            payload (dict): The steering event's payload.
        """
        chats = self._reply_chats.get(payload.get('trigger_id'), set())
        if not chats or not payload.get('delivered'):
            return
        self._reply_chats.pop(payload.get('trigger_id'), None)
        into = payload.get('into_trigger_id')
        if into:
            self._reply_chats.setdefault(into, set()).update(chats)
        for chat_id in chats:
            await self._send(
                chat_id,
                'The desk was working, so your message was handed to the running turn. Its answer will come here.',
            )

    def _remember_trigger(self, payload: dict) -> None:
        """Keeps a trigger's source and text, so its answer can be described later.

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

    async def _send_daily_summary(self, desk_name: str | None) -> None:
        """Pushes the summary a desk wrote for the day just ended.

        Args:
            desk_name (str | None): The desk that rolled over.
        """
        if (
            not self._formatter.wants_daily_summaries()
            or desk_name not in self._parts
        ):
            return
        summaries = self._parts[desk_name].sessions.summaries()
        if not summaries:
            return
        latest = summaries[0]
        await self._broadcast(
            f'{desk_name}: summary of {latest.trading_date.isoformat()}\n\n{latest.text}'
        )

    async def _broadcast(self, text: str) -> None:
        """Sends a notification to every paired chat.

        Args:
            text (str): The notification.
        """
        for chat in self._pairing.paired_chats():
            await self._send(chat.chat_id, text)

    async def _send(self, chat_id: int, text: str) -> None:
        """Sends a message, logging a failure instead of raising it.

        Args:
            chat_id (int): The chat.
            text (str): The message.
        """
        try:
            await self._api.send(chat_id, text)
        except telegram_api_module.TelegramApiError as error:
            _LOGGER.warning(
                'Could not send to Telegram chat %s: %s', chat_id, error
            )

    def _publish_channel(
        self, action: str, chat_id: int | None, name: str, text: str
    ) -> None:
        """Publishes what happened on the channel, for the journal and the web page.

        Args:
            action (str): "connected", "stranger" or "paired".
            chat_id (int | None): The chat, if any.
            name (str): The sender's or the bot's name.
            text (str): The start of a stranger's message, or an empty string.
        """
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.CHANNEL,
                None,
                {
                    'channel': 'telegram',
                    'action': action,
                    'chat_id': chat_id,
                    'name': name,
                    'text': text,
                },
            )
        )
