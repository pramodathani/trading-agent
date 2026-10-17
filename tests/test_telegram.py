"""Tests for the Telegram channel, with a stand-in for Telegram's servers."""

import asyncio
import datetime
from pathlib import Path
from typing import Any

import fastapi
import fastapi.testclient

from trading_agent.channels import notification_formatter
from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.channels import telegram_api
from trading_agent.channels import telegram_channel
from trading_agent.channels import telegram_commands
from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check
from trading_agent.doctor.checks import telegram_check
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_parts
from trading_agent.gateway.routes import channel_routes
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner

_OWNER = 111
_STRANGER = 999
_TOKEN = 'test-token-that-is-long-enough-1234567890'


class _Clock:
    """A clock the tests move by hand.

    Attributes:
        now: The current time, in UTC.
    """

    def __init__(self):
        """Starts the clock at a fixed moment."""
        self.now = datetime.datetime(2026, 10, 19, 4, 0, tzinfo=datetime.UTC)

    def __call__(self) -> datetime.datetime:
        """Gives the current time.

        Returns:
            datetime.datetime: The time.
        """
        return self.now


class _StandInApi:
    """Telegram's servers, as a queue of incoming messages and a list of sent ones.

    Attributes:
        sent: Every message sent, as (chat id, text).
    """

    def __init__(self):
        """Creates the stand-in with nothing received or sent."""
        self._incoming: asyncio.Queue = asyncio.Queue()
        self.sent: list[tuple[int, str]] = []

    async def start(self) -> str:
        """Pretends the token works.

        Returns:
            str: The bot's username.
        """
        return 'test_bot'

    async def messages(self) -> list[telegram_api.IncomingMessage]:
        """Waits for the next message the test sends.

        Returns:
            list[telegram_api.IncomingMessage]: One message.
        """
        return [
            await self._incoming.get(),
        ]

    async def send(self, chat_id: int, text: str) -> None:
        """Records a sent message.

        Args:
            chat_id (int): The chat.
            text (str): The message.
        """
        self.sent.append((chat_id, text))

    async def close(self) -> None:
        """Does nothing."""

    def receive(self, chat_id: int, text: str) -> None:
        """Makes a message arrive from a chat.

        Args:
            chat_id (int): The chat.
            text (str): The message.
        """
        self._incoming.put_nowait(
            telegram_api.IncomingMessage(
                chat_id=chat_id, sender_name='Someone', text=text
            )
        )

    def sent_to(self, chat_id: int) -> list[str]:
        """The messages sent to one chat.

        Args:
            chat_id (int): The chat.

        Returns:
            list[str]: The texts, in order.
        """
        return [text for chat, text in self.sent if chat == chat_id]


class _EchoTurnRunner(turn_runner.TurnRunner):
    """A turn runner that answers every message by echoing it.

    Attributes:
        texts: Every trigger's text, in order.
    """

    def __init__(self):
        """Creates the runner."""
        self.texts: list[str] = []

    async def run_turn(
        self, trigger: trigger_module.Trigger
    ) -> turn_runner.TurnResult:
        """Echoes the message.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: The echo.
        """
        self.texts.append(trigger.text)
        return turn_runner.TurnResult(
            text=f'echo: {trigger.text.splitlines()[-1]}'
        )


class _StandInKillSwitch:
    """A kill switch that records each time it fires.

    Attributes:
        reasons: Each reason it fired with.
    """

    def __init__(self):
        """Creates the stand-in."""
        self.reasons: list[str] = []

    async def trigger(
        self, reason: str, until_date: datetime.date, now: datetime.datetime
    ) -> dict[str, Any]:
        """Records the reason.

        Args:
            reason (str): Why.
            until_date (datetime.date): The first day trading is allowed again.
            now (datetime.datetime): The current time.

        Returns:
            dict[str, Any]: A made-up answer.
        """
        del until_date, now
        self.reasons.append(reason)
        return {
            'flattened': True,
        }


class _Scenario:
    """A gateway with two desks, a pairing file and a Telegram channel on the stand-in."""

    def __init__(self, directory: Path, notifications: list[str] | None = None):
        """Builds everything.

        Args:
            directory (Path): A scratch folder.
            notifications (list[str] | None): The notifications to push; None pushes every kind.
        """
        self.event_bus = event_bus_module.EventBus()
        self.runner = _EchoTurnRunner()
        self.desks = {}
        for name in ('main', 'intraday'):
            self.desks[name] = desk_runtime.DeskRuntime(
                agent_configuration.DeskConfiguration(name=name),
                self.event_bus,
                self.runner,
            )
        self.clock = _Clock()
        self.pairing = pairing_store_module.PairingStore(
            directory / 'telegram_pairing.json', self.clock
        )
        self.kill_switch = _StandInKillSwitch()
        shared = gateway_parts.SharedParts(
            layout=None,
            reader=None,
            snapshot_reader=None,
            risk_engine=None,
            ledger=None,
            kill_switch=self.kill_switch,
            order_book=None,
            proposals=None,
            subagents=None,
            packages=None,
            calendar=None,
        )
        self.api = _StandInApi()
        self.channel = telegram_channel.TelegramChannel(
            self.api,
            self.pairing,
            telegram_commands.TelegramCommands(
                self.desks, shared, self.pairing, 'dry_run'
            ),
            notification_formatter.NotificationFormatter(
                notifications
                or list(agent_configuration.TELEGRAM_NOTIFICATIONS)
            ),
            self.desks,
            {},
            self.event_bus,
            'main',
        )

    def pair_owner(self) -> None:
        """Pairs the owner's chat, as the user would by approving its code."""
        code = self.pairing.request(_OWNER, 'Owner')
        self.pairing.approve(code, 'main')

    async def run_until(self, chat_id: int, count: int) -> None:
        """Runs the desks and the channel until a chat has received a number of messages.

        Args:
            chat_id (int): The chat to watch.
            count (int): How many messages to wait for.
        """
        tasks = [
            asyncio.create_task(desk.run()) for desk in self.desks.values()
        ]
        tasks.append(asyncio.create_task(self.channel.run()))
        try:
            for _ in range(300):
                if len(self.api.sent_to(chat_id)) >= count:
                    return
                await asyncio.sleep(0.01)
            raise AssertionError(
                f'Chat {chat_id} got {self.api.sent_to(chat_id)}'
            )
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def converse(
        self, chat_id: int, texts: list[str], replies: int
    ) -> None:
        """Sends messages from a chat and waits for the replies.

        Args:
            chat_id (int): The chat.
            texts (list[str]): The messages.
            replies (int): How many replies to wait for.
        """
        for text in texts:
            self.api.receive(chat_id, text)
        await self.run_until(chat_id, replies)

    async def publish_then_wait(
        self, published_event: event_module.Event, count: int
    ) -> None:
        """Publishes an event once the channel runs, and waits for the owner's messages.

        Args:
            published_event (event_module.Event): The event.
            count (int): How many messages the owner should get.
        """
        asyncio.get_running_loop().call_later(
            0.05, self.event_bus.publish, published_event
        )
        await self.run_until(_OWNER, count)


class TestPairingStore:
    """Tests for pairing codes."""

    def test_same_chat_keeps_its_code(self, tmp_path: Path) -> None:
        """Asking twice gives the same code, so a stranger cannot fill the list alone."""
        store = pairing_store_module.PairingStore(
            tmp_path / 'pairing.json', _Clock()
        )

        assert store.request(_STRANGER, 'A') == store.request(_STRANGER, 'A')
        assert len(store.pending()) == 1

    def test_code_expires_after_an_hour(self, tmp_path: Path) -> None:
        """A code that is more than an hour old can no longer be approved."""
        clock = _Clock()
        store = pairing_store_module.PairingStore(
            tmp_path / 'pairing.json', clock
        )
        code = store.request(_OWNER, 'Owner')
        clock.now += datetime.timedelta(minutes=61)

        try:
            store.approve(code, 'main')
        except pairing_store_module.PairingError:
            assert store.paired_chats() == []
            return
        raise AssertionError('An expired code was accepted')

    def test_code_is_accepted_in_any_case_with_a_dash(
        self, tmp_path: Path
    ) -> None:
        """A code typed in lower case with a dash in the middle still pairs."""
        store = pairing_store_module.PairingStore(
            tmp_path / 'pairing.json', _Clock()
        )
        code = store.request(_OWNER, 'Owner')

        chat = store.approve(f'{code[:4].lower()}-{code[4:]}', 'main')

        assert chat.chat_id == _OWNER
        assert store.pending() == []

    def test_waiting_codes_are_limited(self, tmp_path: Path) -> None:
        """After five waiting codes, more strangers get none."""
        store = pairing_store_module.PairingStore(
            tmp_path / 'pairing.json', _Clock()
        )
        codes = [store.request(chat_id, 'x') for chat_id in range(6)]

        assert all(code is not None for code in codes[:5])
        assert codes[5] is None

    def test_codes_avoid_look_alike_characters(self, tmp_path: Path) -> None:
        """Codes never hold 0, O, 1 or I, which are easy to misread."""
        store = pairing_store_module.PairingStore(
            tmp_path / 'pairing.json', _Clock()
        )
        code = store.request(_OWNER, 'Owner')

        assert len(code) == 8
        assert not set(code) & set('0O1I')

    def test_revoked_chat_is_no_longer_paired(self, tmp_path: Path) -> None:
        """Revoking removes the chat."""
        store = pairing_store_module.PairingStore(
            tmp_path / 'pairing.json', _Clock()
        )
        store.approve(store.request(_OWNER, 'Owner'), 'main')

        store.revoke(_OWNER)

        assert store.paired_chat(_OWNER) is None


class TestTelegramChannel:
    """Tests for messages to and from the desks."""

    def test_stranger_gets_a_code_and_is_not_obeyed(
        self, tmp_path: Path
    ) -> None:
        """A chat that is not paired gets a pairing code, and its message never reaches a desk."""
        scenario = _Scenario(tmp_path)

        asyncio.run(scenario.converse(_STRANGER, ['buy everything'], 1))

        reply = scenario.api.sent_to(_STRANGER)[0]
        code = scenario.pairing.pending()[0].code
        assert code in reply
        assert 'trading-agent pairing approve' in reply
        assert scenario.runner.texts == []

    def test_paired_chat_talks_to_its_desk(self, tmp_path: Path) -> None:
        """A paired chat's message goes to its desk, and the desk's answer comes back."""
        scenario = _Scenario(tmp_path)
        scenario.pair_owner()

        asyncio.run(scenario.converse(_OWNER, ['hello desk'], 1))

        assert scenario.api.sent_to(_OWNER) == [
            'echo: hello desk',
        ]

    def test_desk_command_changes_the_desk(self, tmp_path: Path) -> None:
        """/desk intraday makes later messages go to intraday."""
        scenario = _Scenario(tmp_path)
        scenario.pair_owner()

        asyncio.run(scenario.converse(_OWNER, ['/desk intraday'], 1))

        assert scenario.pairing.paired_chat(_OWNER).desk == 'intraday'
        assert 'now talking to intraday' in scenario.api.sent_to(_OWNER)[0]

    def test_pause_all(self, tmp_path: Path) -> None:
        """/pause all pauses every desk without asking a model."""
        scenario = _Scenario(tmp_path)
        scenario.pair_owner()

        asyncio.run(scenario.converse(_OWNER, ['/pause all'], 1))

        assert all(desk.paused for desk in scenario.desks.values())
        assert scenario.runner.texts == []

    def test_kill_needs_confirm(self, tmp_path: Path) -> None:
        """/kill without CONFIRM explains itself and does not fire."""
        scenario = _Scenario(tmp_path)
        scenario.pair_owner()

        asyncio.run(scenario.converse(_OWNER, ['/kill now'], 1))

        assert scenario.kill_switch.reasons == []
        assert '/kill CONFIRM' in scenario.api.sent_to(_OWNER)[0]

    def test_kill_with_confirm_fires(self, tmp_path: Path) -> None:
        """/kill CONFIRM fires the kill switch with the reason."""
        scenario = _Scenario(tmp_path)
        scenario.pair_owner()

        asyncio.run(
            scenario.converse(_OWNER, ['/kill CONFIRM market crash'], 1)
        )

        assert scenario.kill_switch.reasons == [
            'The user fired the kill switch from Telegram: market crash',
        ]

    def test_desk_commands_are_passed_to_the_desk(self, tmp_path: Path) -> None:
        """A desk's own command, such as /usage, goes to the desk rather than being answered by the channel."""
        scenario = _Scenario(tmp_path)
        scenario.pair_owner()

        asyncio.run(scenario.converse(_OWNER, ['/help'], 1))

        assert (
            'You are talking to the main desk'
            in scenario.api.sent_to(_OWNER)[0]
        )
        assert not scenario.channel._commands.handles('/usage')


class TestNotifications:
    """Tests for what is pushed without being asked."""

    def test_fill_is_pushed_with_its_symbol(self, tmp_path: Path) -> None:
        """A fill goes to every paired chat, naming the desk and the stock."""
        scenario = _Scenario(tmp_path)
        scenario.pair_owner()
        fill = event_module.Event.now(
            event_module.EventKind.FILL,
            'intraday',
            {
                'symbol': 'INFY',
                'transaction_type': 'BUY',
                'quantity': 10,
                'status': 'COMPLETE',
                'filled_quantity': 10,
                'average_price': 1501.2,
                'message': '',
            },
        )

        asyncio.run(scenario.publish_then_wait(fill, 1))

        assert scenario.api.sent_to(_OWNER) == [
            'intraday: COMPLETE buy 10 INFY, 10 filled at 1501.2',
        ]

    def test_switched_off_notifications_are_not_pushed(self) -> None:
        """A kind left out of the notifications list is not pushed."""
        formatter = notification_formatter.NotificationFormatter(
            [
                'halts',
            ]
        )
        fill = event_module.Event.now(
            event_module.EventKind.FILL,
            'intraday',
            {
                'status': 'COMPLETE',
            },
        )

        assert formatter.format(fill, None, None) is None

    def test_scheduled_report_is_pushed_but_answers_and_silence_are_not(
        self,
    ) -> None:
        """A desk's words at a scheduled check are pushed; a reply to a message and a silent heartbeat are not."""
        formatter = notification_formatter.NotificationFormatter(
            list(agent_configuration.TELEGRAM_NOTIFICATIONS)
        )
        report = event_module.Event.now(
            event_module.EventKind.TEXT,
            'positional',
            {
                'text': 'Holding INFY overnight.',
                'silent': False,
            },
        )
        silent = event_module.Event.now(
            event_module.EventKind.TEXT,
            'scalper',
            {
                'text': 'NOTHING_TO_DO',
                'silent': True,
            },
        )

        assert 'Holding INFY overnight.' in formatter.format(
            report, 'cron', '[Scheduled check at 15:40]'
        )
        assert formatter.format(report, 'user_message', 'hello') is None
        assert formatter.format(silent, 'heartbeat', '[Heartbeat]') is None
        assert formatter.format(report, 'cron', '/rollover') is None

    def test_rejection_and_kill_switch_are_pushed(self) -> None:
        """Risk refusals and the kill switch read as plain sentences."""
        formatter = notification_formatter.NotificationFormatter(
            list(agent_configuration.TELEGRAM_NOTIFICATIONS)
        )
        refusal = event_module.Event.now(
            event_module.EventKind.RISK_DECISION,
            'scalper',
            {
                'approved': False,
                'order': 'buy 1 IDEA',
                'reasons': [
                    'IDEA belongs to intraday.',
                ],
            },
        )
        kill = event_module.Event.now(
            event_module.EventKind.KILL_SWITCH,
            None,
            {
                'stage': 'fired',
                'reason': 'loss limit',
                'until_date': '2026-10-21',
                'dry_run': True,
            },
        )

        assert (
            formatter.format(refusal, None, None)
            == 'scalper: the risk engine refused buy 1 IDEA. IDEA belongs to intraday.'
        )
        assert formatter.format(kill, None, None).startswith(
            'KILL SWITCH fired (dry run)'
        )


class TestTelegramPieces:
    """Tests for message splitting, the doctor check and the pairing route."""

    def test_long_messages_are_split(self) -> None:
        """A message longer than Telegram allows is split at line breaks."""
        text = '\n'.join(['x' * 100] * 100)

        parts = telegram_api.TelegramApi.parts(text)

        assert len(parts) == 3
        assert all(len(part) <= 4000 for part in parts)
        assert '\n'.join(parts) == text

    def test_doctor_without_token(self) -> None:
        """Doctor is content when Telegram is off, and fails when it is on without a token."""
        secrets = secrets_module.Secrets(_env_file=None, telegram_bot_token='')
        off = telegram_check.TelegramCheck(
            agent_configuration.TelegramConfiguration(), secrets
        ).run()
        on = telegram_check.TelegramCheck(
            agent_configuration.TelegramConfiguration(enabled=True), secrets
        ).run()

        assert off.status == doctor_check.CheckStatus.OK
        assert on.status == doctor_check.CheckStatus.FAILED

    def test_pairing_route_approves_a_code(self, tmp_path: Path) -> None:
        """The web page's approve button pairs the chat; an unknown code is 404."""
        store = pairing_store_module.PairingStore(
            tmp_path / 'pairing.json', _Clock()
        )
        code = store.request(_OWNER, 'Owner')
        group = channel_routes.ChannelRoutes(
            access_guard.AccessGuard(_TOKEN),
            store,
            agent_configuration.TelegramConfiguration(),
            False,
            None,
        )
        application = fastapi.FastAPI()
        application.include_router(group.router())
        client = fastapi.testclient.TestClient(application)
        headers = {
            'Authorization': f'Bearer {_TOKEN}',
        }

        approved = client.post(
            f'/api/channels/telegram/pairings/{code}/approve', headers=headers
        )
        unknown = client.post(
            '/api/channels/telegram/pairings/ZZZZZZZZ/approve', headers=headers
        )
        listing = client.get('/api/channels', headers=headers)

        assert approved.status_code == 200
        assert unknown.status_code == 404
        assert listing.json()['telegram']['paired'][0]['chat_id'] == _OWNER
