"""The running traders, which can be created, retired and restored while the gateway runs.

The registry owns the dictionaries the rest of the gateway reads: the traders themselves, their tool registries and their schedules. Route groups, the scheduler, the market watcher, Telegram and the request responder are given these same dictionary objects, never copies, so a trader created later is visible to all of them at once. The builder's parts dictionary is shared in the same way.

Each trader runs as its own asyncio task. The gateway calls start() when the web server starts and stop() when it stops; a trader created in between gets its task at once.

Typical usage example:

  registry = TraderRegistry(store, builder, layout, event_bus)
  registry.load()
  await registry.start()
  trader = await registry.create(NewTrader(name='banknifty-momentum', mandate='Intraday momentum in Bank Nifty options, buying only'))
"""

import asyncio

from trading_agent import trader_builder as trader_builder_module
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trader_runtime
from trading_agent.runtime import trigger as trigger_module
from trading_agent.scheduling import cron_scheduler
from trading_agent.tools import tool_registry as tool_registry_module
from trading_agent.traders import trader_store as trader_store_module
from trading_agent.workspace import workspace_layout

INTRODUCTION = '[New trader] You have just been created with the mandate in your Persona.md. Reply to the user with: the mandate in your own words; the instruments, products, holding period and times of day you would trade; how you would size and protect each trade within the limits in TradingRules.md; and the first steps you would take. Then use propose_file_change to propose a fuller Persona.md for the user to accept, and, if the mandate calls for limits of its own such as allowed products or a daily loss limit, a [traders.<your name>] table in TradingRules.md.'


class TraderRegistry:
    """Builds, runs, creates, retires and restores traders.

    Attributes:
        traders: The running traders, keyed by name, oldest first; shared with the rest of the gateway.
        tool_registries: Each running trader's tools, keyed by name; shared with the request responder.
        schedules: Each running trader's schedule, keyed by name; shared with the cron scheduler.
    """

    def __init__(
        self,
        store: trader_store_module.TraderStore,
        builder: trader_builder_module.TraderBuilder,
        layout: workspace_layout.WorkspaceLayout,
        event_bus: event_bus_module.EventBus,
    ):
        """Creates an empty registry.

        Args:
            store (trader_store_module.TraderStore): Where the traders' records are kept.
            builder (trader_builder_module.TraderBuilder): Builds each trader's parts.
            layout (workspace_layout.WorkspaceLayout): Where the traders' files are.
            event_bus (event_bus_module.EventBus): Where creations and retirements are published.
        """
        self._store = store
        self._builder = builder
        self._layout = layout
        self._event_bus = event_bus
        self.traders: dict[str, trader_runtime.TraderRuntime] = {}
        self.tool_registries: dict[str, tool_registry_module.ToolRegistry] = {}
        self.schedules: dict[str, cron_scheduler.TraderSchedule] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._started = False
        self._lock = asyncio.Lock()
        builder.set_roster(self.names)

    def names(self) -> list[str]:
        """The running traders' names, oldest first.

        Returns:
            list[str]: The names.
        """
        return list(self.traders)

    def records(self) -> list[agent_configuration.TraderConfiguration]:
        """Every trader's record, retired ones included, oldest first.

        Returns:
            list[agent_configuration.TraderConfiguration]: The records.

        Raises:
            trader_store_module.TraderStoreError: A record cannot be read.
        """
        return self._store.records()

    def record(
        self, name: str
    ) -> agent_configuration.TraderConfiguration | None:
        """One trader's record.

        Args:
            name (str): The trader.

        Returns:
            agent_configuration.TraderConfiguration | None: The record, or None when there is no such trader.

        Raises:
            trader_store_module.TraderStoreError: The record cannot be read.
        """
        return self._store.find(name)

    def load(self) -> None:
        """Builds every trader that is not retired, without starting them.

        Returns:
            None.

        Raises:
            trader_store_module.TraderStoreError: A record cannot be read.
        """
        for record in self._store.active():
            self._add(record)

    async def start(self) -> None:
        """Starts every built trader's loop; traders created later start at once.

        Returns:
            None.
        """
        self._started = True
        for trader in self.traders.values():
            self._start_task(trader)

    async def stop(self) -> None:
        """Cancels every trader's loop and waits for each to close.

        Returns:
            None.
        """
        self._started = False
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def create(
        self,
        request: trader_store_module.NewTrader,
        introduce: bool = True,
    ) -> trader_runtime.TraderRuntime:
        """Creates a trader's files, builds it and starts it.

        Args:
            request (trader_store_module.NewTrader): The new trader.
            introduce (bool): Whether to send it a first message asking it to restate its mandate, propose its first steps and propose a fuller Persona.md.

        Returns:
            trader_runtime.TraderRuntime: The running trader.

        Raises:
            trader_store_module.TraderStoreError: The name is invalid or taken, the mandate is empty, a backend is unknown, or a setting is out of range.
        """
        async with self._lock:
            record = self._store.create(request)
            self._layout.create_missing([record.name])
            trader = self._add(record)
            if self._started:
                self._start_task(trader)
        self._publish(event_module.EventKind.TRADER_CREATED, record)
        if introduce:
            trader.submit(
                trigger_module.Trigger.now(
                    trigger_module.TriggerSource.USER_MESSAGE,
                    record.name,
                    INTRODUCTION,
                )
            )
        return trader

    async def retire(
        self, name: str
    ) -> agent_configuration.TraderConfiguration:
        """Stops a trader and marks it retired; its files stay.

        A trader that still owns an instrument or has an open order cannot be retired, because no one would watch them afterwards.

        Args:
            name (str): The trader.

        Returns:
            agent_configuration.TraderConfiguration: Its record, now retired.

        Raises:
            trader_store_module.TraderStoreError: There is no such running trader, it is the last one, or it still owns instruments or has open orders.
        """
        async with self._lock:
            if name not in self.traders:
                raise trader_store_module.TraderStoreError(
                    f'No running trader named {name!r}'
                )
            if len(self.traders) == 1:
                raise trader_store_module.TraderStoreError(
                    'The last running trader cannot be retired'
                )
            self._refuse_while_holding(name)
            task = self._tasks.pop(name, None)
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            del self.traders[name]
            self.tool_registries.pop(name, None)
            self.schedules.pop(name, None)
            self._builder.forget(name)
            record = self._store.set_retired(name, True)
        self._publish(event_module.EventKind.TRADER_RETIRED, record)
        return record

    async def restore(self, name: str) -> trader_runtime.TraderRuntime:
        """Brings a retired trader back, with its memory and sessions.

        Args:
            name (str): The trader.

        Returns:
            trader_runtime.TraderRuntime: The running trader.

        Raises:
            trader_store_module.TraderStoreError: There is no such trader, or it is not retired.
        """
        async with self._lock:
            record = self._store.find(name)
            if record is None or not record.retired:
                raise trader_store_module.TraderStoreError(
                    f'No retired trader named {name!r}'
                )
            record = self._store.set_retired(name, False)
            self._layout.create_missing([name])
            trader = self._add(record)
            if self._started:
                self._start_task(trader)
        self._publish(event_module.EventKind.TRADER_CREATED, record)
        return trader

    def _refuse_while_holding(self, name: str) -> None:
        """Refuses to go on while a trader owns instruments or has open orders.

        Args:
            name (str): The trader.

        Returns:
            None.

        Raises:
            trader_store_module.TraderStoreError: The trader owns an instrument or has an open order.
        """
        shared = self._builder.shared_parts()
        owned = sorted(shared.ledger.owned_by(name))
        open_orders = shared.order_book.open_orders(name)
        if not owned and not open_orders:
            return
        problems = []
        if owned:
            problems.append(f'owns {", ".join(owned)}')
        if open_orders:
            problems.append(f'has {len(open_orders)} open orders')
        raise trader_store_module.TraderStoreError(
            f'The {name} trader still {" and ".join(problems)}; flatten it first'
        )

    def _add(
        self, record: agent_configuration.TraderConfiguration
    ) -> trader_runtime.TraderRuntime:
        """Builds one trader and puts it into the shared dictionaries.

        Args:
            record (agent_configuration.TraderConfiguration): Its record.

        Returns:
            trader_runtime.TraderRuntime: The trader, not yet running.
        """
        trader = self._builder.build(record)
        self.traders[record.name] = trader
        self.tool_registries[record.name] = self._builder.trader_parts()[
            record.name
        ].tools
        self.schedules[record.name] = self._builder.trader_schedule(trader)
        return trader

    def _start_task(self, trader: trader_runtime.TraderRuntime) -> None:
        """Starts one trader's loop as its own task.

        Args:
            trader (trader_runtime.TraderRuntime): The trader.

        Returns:
            None.
        """
        self._tasks[trader.name] = asyncio.create_task(
            trader.run(), name=f'trader-{trader.name}'
        )

    def _publish(
        self,
        kind: event_module.EventKind,
        record: agent_configuration.TraderConfiguration,
    ) -> None:
        """Publishes a creation, restoration or retirement.

        Args:
            kind (event_module.EventKind): TRADER_CREATED or TRADER_RETIRED.
            record (agent_configuration.TraderConfiguration): The trader's record.

        Returns:
            None.
        """
        self._event_bus.publish(
            event_module.Event.now(
                kind,
                record.name,
                {
                    'mandate': record.mandate,
                    'retired': record.retired,
                },
            )
        )
