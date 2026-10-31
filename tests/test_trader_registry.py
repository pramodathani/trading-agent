"""Tests for the trader store and registry: records, creation, retirement and the shared dictionaries."""

import asyncio
import datetime
import tomllib
from pathlib import Path

import fastapi
import fastapi.testclient
import pytest

from tests import test_telegram
from trading_agent import trader_builder
from trading_agent.channels import notification_formatter
from trading_agent.channels import pairing_store
from trading_agent.channels import telegram_channel
from trading_agent.channels import telegram_commands
from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import roster_routes
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime
from trading_agent.traders import trader_registry
from trading_agent.traders import trader_store
from trading_agent.workspace import workspace_layout

_OWNER_CHAT = 111


class _Workspace:
    """A real workspace, store, builder and registry, with traders that have no models.

    Attributes:
        layout: Where the files are.
        store: The traders' records.
        event_bus: The bus.
        builder: The builder.
        registry: The registry.
    """

    def __init__(self, directory: Path):
        """Builds everything over an empty folder.

        Args:
            directory (Path): An empty folder.
        """
        configuration = agent_configuration.AgentConfiguration(
            workspace_directory=directory / 'workspace',
            tradingmachine_environment_file=directory / 'tradingmachine.env',
        )
        self.layout = workspace_layout.WorkspaceLayout(
            configuration.workspace_directory
        )
        self.store = trader_store.TraderStore(
            self.layout, configuration.traders
        )
        self.event_bus = event_bus_module.EventBus()
        self.builder = trader_builder.TraderBuilder(
            configuration,
            secrets_module.Secrets(_env_file=None),
            self.event_bus,
        )
        self.registry = trader_registry.TraderRegistry(
            self.store, self.builder, self.layout, self.event_bus
        )

    def start_with_general(self) -> None:
        """Gives the workspace its first trader and builds it.

        Returns:
            None.
        """
        self.store.ensure_first()
        self.layout.create_missing(['general'])
        self.registry.load()


class TestTraderStore:
    """Records are written as TOML in each trader's folder and read back."""

    def test_first_trader_is_created_once(self, tmp_path: Path) -> None:
        """An empty workspace gets the general trader, and a second call creates nothing.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)

        first = workspace.store.ensure_first()
        again = workspace.store.ensure_first()

        assert first.name == 'general'
        assert again is None
        assert workspace.layout.persona_file('general').is_file()

    def test_existing_folder_gets_a_record_and_keeps_its_persona(
        self, tmp_path: Path
    ) -> None:
        """A general folder from before records existed keeps its Persona.md.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        persona = workspace.layout.persona_file('general')
        persona.parent.mkdir(parents=True)
        persona.write_text('My own persona.', encoding='utf-8')

        workspace.store.ensure_first()

        assert persona.read_text(encoding='utf-8') == 'My own persona.'
        assert workspace.store.find('general') is not None

    def test_record_round_trips_through_toml(self, tmp_path: Path) -> None:
        """A record with quotes and lists is written as valid TOML, read back unchanged, and turned into a persona.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)

        created = workspace.store.create(
            trader_store.NewTrader(
                name='banknifty-momentum',
                mandate='Buy "breakouts" in Bank Nifty options, never sell them',
                heartbeat_minutes=5,
                scheduled_checks=(
                    '15:05',
                    '09:10',
                ),
            )
        )
        text = workspace.layout.trader_file('banknifty-momentum').read_text(
            encoding='utf-8'
        )
        persona = workspace.layout.persona_file('banknifty-momentum').read_text(
            encoding='utf-8'
        )

        assert tomllib.loads(text)['name'] == 'banknifty-momentum'
        assert workspace.store.find('banknifty-momentum') == created
        assert created.scheduled_checks == [
            '09:10',
            '15:05',
        ]
        assert 'Mandate: Buy "breakouts"' in persona
        assert 'a heartbeat every 5 minutes' in persona
        assert 'Scheduled checks (India time, trading days): 09:10, 15:05.' in (
            persona
        )

    def test_heartbeat_zero_means_none_and_none_means_default(
        self, tmp_path: Path
    ) -> None:
        """A heartbeat of 0 turns it off, and leaving it out takes the [traders] default.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        store = trader_store.TraderStore(
            workspace.layout,
            agent_configuration.TradersConfiguration(heartbeat_minutes=10),
        )

        quiet = store.create(
            trader_store.NewTrader(
                name='quiet',
                mandate='x',
                heartbeat_minutes=0,
            )
        )
        usual = store.create(trader_store.NewTrader(name='usual', mandate='x'))

        assert quiet.heartbeat_minutes is None
        assert usual.heartbeat_minutes == 10

    def test_name_may_be_two_hundred_characters(self, tmp_path: Path) -> None:
        """A name of 200 characters is accepted, and one of 201 is refused.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        longest = 'a' * 200

        created = workspace.store.create(
            trader_store.NewTrader(name=longest, mandate='x')
        )

        assert created.name == longest
        with pytest.raises(trader_store.TraderStoreError, match='200'):
            workspace.store.create(
                trader_store.NewTrader(name='b' * 201, mandate='x')
            )

    def test_bad_requests_are_refused(self, tmp_path: Path) -> None:
        """A bad name, a taken name, an empty mandate, an unknown backend and a bad check time are refused.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        store = trader_store.TraderStore(
            workspace.layout,
            agent_configuration.TradersConfiguration(),
            ('claude',),
        )
        store.create(trader_store.NewTrader(name='value', mandate='Value.'))

        with pytest.raises(trader_store.TraderStoreError, match='valid'):
            store.create(trader_store.NewTrader(name='Bad Name', mandate='x'))
        with pytest.raises(trader_store.TraderStoreError, match='exists'):
            store.create(trader_store.NewTrader(name='value', mandate='x'))
        with pytest.raises(trader_store.TraderStoreError, match='mandate'):
            store.create(trader_store.NewTrader(name='other', mandate=' '))
        with pytest.raises(trader_store.TraderStoreError, match='backend'):
            store.create(
                trader_store.NewTrader(
                    name='other',
                    mandate='x',
                    backend_order=('gpt',),
                )
            )
        with pytest.raises(
            trader_store.TraderStoreError, match='scheduled_checks'
        ):
            store.create(
                trader_store.NewTrader(
                    name='other',
                    mandate='x',
                    scheduled_checks=('25:00',),
                )
            )
        assert not workspace.layout.trader_directory('other').exists()


class TestTraderRegistry:
    """Traders can be created, retired and restored while the gateway runs."""

    def test_created_trader_runs_and_appears_everywhere(
        self, tmp_path: Path
    ) -> None:
        """A new trader is in the shared dictionaries, gets its loop, answers its introduction and is named in the others' prompts.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        workspace.start_with_general()
        traders = workspace.registry.traders
        schedules = workspace.registry.schedules
        parts = workspace.builder.trader_parts()
        subscription = workspace.event_bus.subscribe()

        async def scenario() -> list[event_module.Event]:
            """Starts the registry, creates a trader and waits for its first answer.

            Returns:
                list[event_module.Event]: The events published until the answer.
            """
            await workspace.registry.start()
            await workspace.registry.create(
                trader_store.NewTrader(
                    name='momentum', mandate='Momentum in NSE shares.'
                )
            )
            seen = []
            while True:
                published = await asyncio.wait_for(subscription.next_event(), 5)
                seen.append(published)
                if (
                    published.kind == event_module.EventKind.TEXT
                    and published.trader == 'momentum'
                ):
                    break
            await workspace.registry.stop()
            return seen

        seen = asyncio.run(scenario())
        kinds = []
        for published in seen:
            kinds.append(published.kind)

        assert event_module.EventKind.TRADER_CREATED in kinds
        assert list(traders) == [
            'general',
            'momentum',
        ]
        assert 'momentum' in schedules
        assert 'momentum' in parts
        assert workspace.layout.memory_file('momentum').is_file()
        assert traders['momentum'].state == trader_runtime.TraderState.STOPPED
        assert workspace.registry.names() == [
            'general',
            'momentum',
        ]

    def test_retired_trader_leaves_and_can_come_back(
        self, tmp_path: Path
    ) -> None:
        """Retiring stops the trader and keeps its files; restoring brings it back; the last trader cannot be retired.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        workspace.start_with_general()

        async def scenario() -> None:
            """Creates, retires and restores a trader, then tries to retire the last one.

            Returns:
                None.
            """
            await workspace.registry.start()
            await workspace.registry.create(
                trader_store.NewTrader(name='value', mandate='Value.'),
                introduce=False,
            )
            await workspace.registry.retire('value')
            assert 'value' not in workspace.registry.traders
            assert 'value' not in workspace.registry.schedules
            assert 'value' not in workspace.builder.trader_parts()
            assert workspace.store.find('value').retired
            assert workspace.layout.persona_file('value').is_file()
            await workspace.registry.restore('value')
            assert 'value' in workspace.registry.traders
            await workspace.registry.retire('value')
            with pytest.raises(trader_store.TraderStoreError, match='last'):
                await workspace.registry.retire('general')
            await workspace.registry.stop()

        asyncio.run(scenario())

    def test_trader_that_owns_an_instrument_cannot_be_retired(
        self, tmp_path: Path
    ) -> None:
        """A trader that still owns an instrument is refused, because no one would watch the position.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        workspace.start_with_general()

        async def scenario() -> None:
            """Creates a trader, gives it an instrument and tries to retire it.

            Returns:
                None.
            """
            await workspace.registry.start()
            await workspace.registry.create(
                trader_store.NewTrader(name='holder', mandate='Holds.'),
                introduce=False,
            )
            workspace.builder.shared_parts().ledger.claim(
                'NSE:RELIANCE',
                'holder',
                datetime.datetime(2026, 11, 2, 10, 0, tzinfo=datetime.UTC),
            )
            with pytest.raises(
                trader_store.TraderStoreError, match='owns NSE:RELIANCE'
            ):
                await workspace.registry.retire('holder')
            assert 'holder' in workspace.registry.traders
            assert not workspace.store.find('holder').retired
            await workspace.registry.stop()

        asyncio.run(scenario())


class TestRosterRoutes:
    """The API creates, lists, retires and restores traders through the registry."""

    def _client(self, workspace: _Workspace) -> fastapi.testclient.TestClient:
        """Builds a client for the roster routes.

        Args:
            workspace (_Workspace): The workspace.

        Returns:
            fastapi.testclient.TestClient: The client.
        """
        application = fastapi.FastAPI()
        application.include_router(
            roster_routes.RosterRoutes(
                access_guard.AccessGuard('test-token'), workspace.registry
            ).router()
        )
        return fastapi.testclient.TestClient(application)

    def test_create_list_retire_and_restore(self, tmp_path: Path) -> None:
        """A trader made through the API is listed as running, then as retired, then running again; bad requests get 400.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        workspace.start_with_general()
        client = self._client(workspace)
        headers = {
            'Authorization': 'Bearer test-token',
        }

        created = client.post(
            '/api/traders',
            headers=headers,
            json={
                'name': 'momentum',
                'mandate': 'Momentum in NSE shares.',
                'heartbeat_minutes': 15,
                'scheduled_checks': [
                    '09:20',
                ],
                'introduce': False,
            },
        )
        duplicate = client.post(
            '/api/traders',
            headers=headers,
            json={
                'name': 'momentum',
                'mandate': 'Again.',
            },
        )
        bad_time = client.post(
            '/api/traders',
            headers=headers,
            json={
                'name': 'late',
                'mandate': 'Late.',
                'scheduled_checks': [
                    '9am',
                ],
            },
        )
        listing = client.get('/api/trader-records', headers=headers)
        retired = client.post('/api/traders/momentum/retire', headers=headers)
        after_retiring = client.get('/api/trader-records', headers=headers)
        restored = client.post('/api/traders/momentum/restore', headers=headers)
        unauthorised = client.get('/api/trader-records')

        assert created.status_code == 201
        assert created.json()['mandate'] == 'Momentum in NSE shares.'
        assert created.json()['heartbeat_minutes'] == 15
        assert created.json()['scheduled_checks'] == [
            '09:20',
        ]
        assert duplicate.status_code == 400
        assert 'already exists' in duplicate.json()['detail']
        assert bad_time.status_code == 400
        assert 'scheduled_checks' in bad_time.json()['detail']
        names_and_states = []
        for record in listing.json()['records']:
            names_and_states.append((record['name'], record['running']))
        assert names_and_states == [
            (
                'general',
                True,
            ),
            (
                'momentum',
                True,
            ),
        ]
        assert retired.json()['retired'] is True
        assert after_retiring.json()['records'][1]['running'] is False
        assert restored.status_code == 200
        assert 'momentum' in workspace.registry.traders
        assert unauthorised.status_code == 401


class TestTelegramTraderCommands:
    """From Telegram, /create makes a trader that introduces itself in that chat, and /traders and /retire work."""

    def test_create_introduces_itself_in_the_chat_that_asked(
        self, tmp_path: Path
    ) -> None:
        """/create switches the chat to the new trader and its introduction comes back there; /traders lists it and /retire stops it.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        workspace = _Workspace(tmp_path)
        workspace.start_with_general()
        pairing = pairing_store.PairingStore(tmp_path / 'pairing.json')
        code = pairing.request(_OWNER_CHAT, 'Owner')
        pairing.approve(code, 'general')
        api = test_telegram._StandInApi()
        traders = workspace.registry.traders
        channel = telegram_channel.TelegramChannel(
            api,
            pairing,
            telegram_commands.TelegramCommands(
                traders,
                workspace.builder.shared_parts(),
                pairing,
                'dry_run',
                registry=workspace.registry,
            ),
            notification_formatter.NotificationFormatter([]),
            traders,
            {},
            workspace.event_bus,
            'general',
        )

        async def scenario() -> None:
            """Runs the registry and the channel through /create, /traders and /retire.

            Returns:
                None.
            """
            await workspace.registry.start()
            channel_task = asyncio.create_task(channel.run())
            api.receive(_OWNER_CHAT, '/create momentum Momentum in NSE shares.')
            await self._wait_for(api, 2)
            api.receive(_OWNER_CHAT, '/traders')
            await self._wait_for(api, 3)
            api.receive(_OWNER_CHAT, '/retire momentum')
            await self._wait_for(api, 4)
            channel_task.cancel()
            await asyncio.gather(channel_task, return_exceptions=True)
            await workspace.registry.stop()

        asyncio.run(scenario())
        replies = api.sent_to(_OWNER_CHAT)

        assert replies[0].startswith('Created momentum')
        assert replies[1].startswith('No model')
        assert trader_registry.INTRODUCTION in replies[1]
        assert pairing.paired_chat(_OWNER_CHAT).trader == 'momentum'
        assert 'momentum (' in replies[2]
        assert 'Momentum in NSE shares.' in replies[2]
        assert replies[3].startswith('Retired momentum.')
        assert 'momentum' not in workspace.registry.traders

    async def _wait_for(
        self, api: test_telegram._StandInApi, count: int
    ) -> None:
        """Waits until the owner's chat has received a number of messages.

        Args:
            api (test_telegram._StandInApi): The stand-in for Telegram.
            count (int): How many messages to wait for.

        Returns:
            None.

        Raises:
            AssertionError: They did not arrive within three seconds.
        """
        for _ in range(300):
            if len(api.sent_to(_OWNER_CHAT)) >= count:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f'The chat got {api.sent_to(_OWNER_CHAT)}')


class TestSleepSetting:
    """sleep_after_minutes = 0 keeps traders awake."""

    def test_zero_means_never_sleep(self, tmp_path: Path) -> None:
        """A builder with a sleep time of 0 gives no sleep timer, and the default gives 30 minutes.

        Args:
            tmp_path (Path): A scratch folder.

        Returns:
            None.
        """
        never = agent_configuration.AgentConfiguration(
            workspace_directory=tmp_path / 'workspace',
            tradingmachine_environment_file=tmp_path / 'tradingmachine.env',
            traders=agent_configuration.TradersConfiguration(
                sleep_after_minutes=0
            ),
        )
        usual = agent_configuration.AgentConfiguration(
            workspace_directory=tmp_path / 'workspace',
            tradingmachine_environment_file=tmp_path / 'tradingmachine.env',
        )
        never_builder = trader_builder.TraderBuilder(
            never,
            secrets_module.Secrets(_env_file=None),
            event_bus_module.EventBus(),
        )
        usual_builder = trader_builder.TraderBuilder(
            usual,
            secrets_module.Secrets(_env_file=None),
            event_bus_module.EventBus(),
        )

        assert never_builder._sleep_after_seconds() is None
        assert usual_builder._sleep_after_seconds() == 1800.0
