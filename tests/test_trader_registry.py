"""Tests for the trader store and registry: records, creation, retirement and the shared dictionaries."""

import asyncio
import datetime
import tomllib
from pathlib import Path

import pytest

from trading_agent import trader_builder
from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime
from trading_agent.traders import trader_registry
from trading_agent.traders import trader_store
from trading_agent.workspace import workspace_layout


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
