"""Keeps each trader's record in its own folder, and creates new traders.

  workspace/traders/<name>/
    trader.toml   the mandate, models, schedule and whether the trader is retired
    Persona.md    the mandate as instructions, written when the trader is created

Records are TOML so the user can read and edit them by hand. Python's standard library reads TOML but cannot write it, and the records hold only plain values, so the store writes them itself.

Typical usage example:

  store = TraderStore(layout, configuration.traders)
  record = store.create(NewTrader(name='banknifty-momentum', mandate='Intraday momentum in Bank Nifty options, buying only'))
  for record in store.active():
      ...
"""

import dataclasses
import datetime
import json
import re
import tomllib
import zoneinfo

import pydantic

from trading_agent.configuration import agent_configuration
from trading_agent.workspace import workspace_layout

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_FIRST_TRADER_MANDATE = 'None of its own. This is the general trader, for trying trading-agent out, answering questions about the account and the market, and planning new traders before each gets a mandate of its own.'


class TraderStoreError(ValueError):
    """A trader cannot be created or changed as asked."""


@dataclasses.dataclass(frozen=True)
class NewTrader:
    """What the user gives when creating a trader.

    Attributes:
        name: The trader's name.
        mandate: What the trader will trade and how.
        backend_order: The backends to use, most preferred first, or an empty tuple for the defaults.
        heartbeat_minutes: Minutes between heartbeats, 0 for no heartbeat, or None for the default.
        scheduled_checks: India times, as HH:MM, when the trader is woken on trading days.
    """

    name: str
    mandate: str
    backend_order: tuple[str, ...] = ()
    heartbeat_minutes: int | None = None
    scheduled_checks: tuple[str, ...] = ()


class TraderStore:
    """The traders' records in one workspace."""

    def __init__(
        self,
        layout: workspace_layout.WorkspaceLayout,
        defaults: agent_configuration.TradersConfiguration,
        backend_names: tuple[str, ...] = (),
    ):
        """Describes the store without touching the disk.

        Args:
            layout (workspace_layout.WorkspaceLayout): Where the traders' folders are.
            defaults (agent_configuration.TradersConfiguration): The settings a new trader gets.
            backend_names (tuple[str, ...]): The backends defined in [backends], which a new trader's backend order may name; empty skips that check.
        """
        self._layout = layout
        self._defaults = defaults
        self._backend_names = backend_names

    def records(self) -> list[agent_configuration.TraderConfiguration]:
        """Every trader's record, retired ones included, oldest first.

        Returns:
            list[agent_configuration.TraderConfiguration]: The records, ordered by creation time and then by name.

        Raises:
            TraderStoreError: A record cannot be read or does not match its folder.
        """
        directory = self._layout.traders_directory
        if not directory.is_dir():
            return []
        records = []
        for folder in sorted(directory.iterdir()):
            if self._layout.trader_file(folder.name).is_file():
                records.append(self._read(folder.name))
        records.sort(key=self._sort_key)
        return records

    @staticmethod
    def _sort_key(
        record: agent_configuration.TraderConfiguration,
    ) -> tuple[str, str]:
        """The key that orders records oldest first.

        Args:
            record (agent_configuration.TraderConfiguration): A record.

        Returns:
            tuple[str, str]: The creation time and the name.
        """
        return (record.created_at, record.name)

    def active(self) -> list[agent_configuration.TraderConfiguration]:
        """The records of the traders that are not retired, oldest first.

        Returns:
            list[agent_configuration.TraderConfiguration]: The records.

        Raises:
            TraderStoreError: A record cannot be read.
        """
        active = []
        for record in self.records():
            if not record.retired:
                active.append(record)
        return active

    def find(self, name: str) -> agent_configuration.TraderConfiguration | None:
        """One trader's record.

        Args:
            name (str): The trader's name.

        Returns:
            agent_configuration.TraderConfiguration | None: The record, or None when there is no such trader.

        Raises:
            TraderStoreError: The record cannot be read.
        """
        if not re.fullmatch(agent_configuration.TRADER_NAME_PATTERN, name):
            return None
        if not self._layout.trader_file(name).is_file():
            return None
        return self._read(name)

    def create(
        self, request: NewTrader
    ) -> agent_configuration.TraderConfiguration:
        """Creates a trader's folder, record and Persona.md.

        Args:
            request (NewTrader): The new trader.

        Returns:
            agent_configuration.TraderConfiguration: The record written.

        Raises:
            TraderStoreError: The name is invalid or taken, the mandate is empty, a backend is unknown, or a setting is out of range.
        """
        if not re.fullmatch(
            agent_configuration.TRADER_NAME_PATTERN, request.name
        ):
            raise TraderStoreError(
                f'{request.name!r} is not a valid trader name; use lower-case letters, digits, hyphens and underscores, starting with a letter, at most 200 characters'
            )
        if self._layout.trader_directory(request.name).exists():
            raise TraderStoreError(
                f'A trader named {request.name!r} already exists'
            )
        if not request.mandate.strip():
            raise TraderStoreError('A new trader needs a mandate')
        backend_order = list(request.backend_order)
        if not backend_order:
            backend_order = list(self._defaults.backend_order)
        for backend_name in backend_order:
            if self._backend_names and backend_name not in self._backend_names:
                raise TraderStoreError(f'Unknown backend {backend_name!r}')
        heartbeat_minutes = self._defaults.heartbeat_minutes
        if request.heartbeat_minutes is not None:
            heartbeat_minutes = request.heartbeat_minutes or None
        try:
            record = agent_configuration.TraderConfiguration(
                name=request.name,
                mandate=request.mandate.strip(),
                created_at=datetime.datetime.now(_INDIA).isoformat(
                    timespec='seconds'
                ),
                backend_order=backend_order,
                heartbeat_minutes=heartbeat_minutes,
                rollover_time=self._defaults.rollover_time,
                scheduled_checks=sorted(request.scheduled_checks),
            )
        except pydantic.ValidationError as error:
            raise TraderStoreError(self._validation_message(error)) from error
        self._layout.trader_directory(request.name).mkdir(parents=True)
        self.save(record)
        self._layout.persona_file(request.name).write_text(
            self.persona_text(record), encoding='utf-8'
        )
        return record

    @staticmethod
    def _validation_message(error: pydantic.ValidationError) -> str:
        """A short sentence for each setting that was out of range.

        Args:
            error (pydantic.ValidationError): What pydantic found.

        Returns:
            str: One line per problem, naming the setting.
        """
        lines = []
        for problem in error.errors():
            location = '.'.join(str(part) for part in problem['loc'])
            lines.append(f'{location}: {problem["msg"]}')
        return '; '.join(lines)

    def ensure_first(self) -> agent_configuration.TraderConfiguration | None:
        """Creates the first trader when the workspace has none.

        A trader folder made before records existed, such as general with only its Persona.md, gets a record and keeps its persona.

        Returns:
            agent_configuration.TraderConfiguration | None: The record created, or None when a trader already existed.

        Raises:
            TraderStoreError: A record cannot be read.
        """
        if self.records():
            return None
        name = self._defaults.first_trader
        if not self._layout.trader_directory(name).exists():
            return self.create(
                NewTrader(name=name, mandate=_FIRST_TRADER_MANDATE)
            )
        record = agent_configuration.TraderConfiguration(
            name=name,
            mandate=_FIRST_TRADER_MANDATE,
            backend_order=list(self._defaults.backend_order),
            heartbeat_minutes=self._defaults.heartbeat_minutes,
            rollover_time=self._defaults.rollover_time,
        )
        self.save(record)
        return record

    def set_retired(
        self, name: str, retired: bool
    ) -> agent_configuration.TraderConfiguration:
        """Retires a trader or brings it back.

        Args:
            name (str): The trader.
            retired (bool): True to retire, False to bring back.

        Returns:
            agent_configuration.TraderConfiguration: The changed record.

        Raises:
            TraderStoreError: There is no such trader.
        """
        record = self.find(name)
        if record is None:
            raise TraderStoreError(f'No trader named {name!r}')
        changed = record.model_copy(
            update={
                'retired': retired,
            }
        )
        self.save(changed)
        return changed

    def save(self, record: agent_configuration.TraderConfiguration) -> None:
        """Writes one record to its trader.toml, replacing the old one in one step.

        Args:
            record (agent_configuration.TraderConfiguration): The record.

        Returns:
            None.
        """
        target = self._layout.trader_file(record.name)
        temporary = target.with_suffix('.toml.tmp')
        temporary.write_text(self.record_text(record), encoding='utf-8')
        temporary.replace(target)

    def record_text(
        self, record: agent_configuration.TraderConfiguration
    ) -> str:
        """Writes a record as TOML.

        Args:
            record (agent_configuration.TraderConfiguration): The record.

        Returns:
            str: The file's text: one key per line, in the model's field order, with unset optional values left out.
        """
        lines = []
        for key, value in record.model_dump().items():
            if value is None:
                continue
            lines.append(f'{key} = {self._toml_value(value)}')
        return '\n'.join(lines) + '\n'

    def persona_text(
        self, record: agent_configuration.TraderConfiguration
    ) -> str:
        """Writes the Persona.md of a new trader from its record.

        Args:
            record (agent_configuration.TraderConfiguration): The new trader's record.

        Returns:
            str: The persona, in the same shape as the starter personas.
        """
        if record.heartbeat_minutes is None:
            checking = 'no heartbeat; woken by price alerts, fills, messages and the scheduled checks'
        else:
            checking = f'a heartbeat every {record.heartbeat_minutes} minutes while NSE equities trade, plus price alerts and fills'
        if record.scheduled_checks:
            checks = ', '.join(record.scheduled_checks)
        else:
            checks = 'none'
        return '\n'.join(
            [
                f'# Persona.md: the {record.name} trader',
                '',
                'Written by trading-agent when this trader was created. Edit it to match how you want this trader to trade.',
                '',
                f'- Mandate: {record.mandate}',
                '- Style, holding period and products: to be proposed by this trader from its mandate.',
                f'- How often to check the market: {checking}.',
                f'- Scheduled checks (India time, trading days): {checks}.',
                "- What this trader must never do: trade outside its mandate, or touch another trader's instruments or positions.",
                '',
            ]
        )

    def _read(self, name: str) -> agent_configuration.TraderConfiguration:
        """Reads and checks one record.

        Args:
            name (str): The trader's folder name.

        Returns:
            agent_configuration.TraderConfiguration: The record.

        Raises:
            TraderStoreError: The file is not valid TOML, does not fit the record's shape, or names another trader.
        """
        record_file = self._layout.trader_file(name)
        try:
            data = tomllib.loads(record_file.read_text(encoding='utf-8'))
            record = agent_configuration.TraderConfiguration.model_validate(
                data
            )
        except (tomllib.TOMLDecodeError, pydantic.ValidationError) as error:
            raise TraderStoreError(
                f'{record_file} cannot be read: {error}'
            ) from error
        if record.name != name:
            raise TraderStoreError(
                f'{record_file} names the trader {record.name!r}, not its folder {name!r}'
            )
        return record

    def _toml_value(self, value: object) -> str:
        """Writes one plain value as TOML.

        Args:
            value (object): A string, number, bool or list of strings.

        Returns:
            str: The value in TOML.

        Raises:
            TypeError: The value is of a kind records never hold.
        """
        if isinstance(value, bool):
            if value:
                return 'true'
            return 'false'
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, list):
            items = []
            for item in value:
                items.append(self._toml_value(item))
            return '[' + ', '.join(items) + ']'
        raise TypeError(f'Records hold no value like {value!r}')
