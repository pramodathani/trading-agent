"""Reads and changes the state of systemd user units, for the apps that packages bring.

Apps such as sridhara already run as systemd user units, which start at login and restart after a crash. trading-agent reports whether each app's unit is running and can start, stop or restart it, but only units named by an installed package's app.toml, and only with `systemctl --user`, never as root.

Typical usage example:

  units = SystemdUserUnits()
  state = await units.state('sridhara.service')
  await units.act('sridhara.service', 'restart')
"""

import asyncio
import dataclasses
import re
from pathlib import Path

_UNIT_PATTERN = re.compile(r'^[A-Za-z0-9@._-]+\.service$')
_TIMEOUT_SECONDS = 30.0
ACTIONS = (
    'start',
    'stop',
    'restart',
)


class UnitError(RuntimeError):
    """systemctl failed, or was asked about a unit name it should not be given."""


@dataclasses.dataclass(frozen=True)
class UnitState:
    """What systemd says about one unit.

    Attributes:
        load_state: "loaded" when systemd knows the unit, "not-found" when it does not.
        active_state: Such as "active", "inactive" or "failed".
        sub_state: Such as "running" or "dead".
    """

    load_state: str
    active_state: str
    sub_state: str


class SystemdUserUnits:
    """Talks to the user's systemd through systemctl --user."""

    async def state(self, unit: str) -> UnitState:
        """Asks systemd for a unit's state.

        Args:
            unit (str): The unit, such as sridhara.service.

        Returns:
            UnitState: The unit's state.

        Raises:
            UnitError: The name is not a service unit, or systemctl failed.
        """
        self._check(unit)
        output = await self._systemctl(
            'show',
            unit,
            '--property=LoadState,ActiveState,SubState',
        )
        values = {}
        for line in output.splitlines():
            name, _, value = line.partition('=')
            values[name] = value
        return UnitState(
            load_state=values.get('LoadState', 'unknown'),
            active_state=values.get('ActiveState', 'unknown'),
            sub_state=values.get('SubState', 'unknown'),
        )

    async def act(self, unit: str, action: str) -> None:
        """Starts, stops or restarts a unit.

        Args:
            unit (str): The unit.
            action (str): "start", "stop" or "restart".

        Raises:
            UnitError: The action is unknown, the name is not a service unit, or systemctl failed.
        """
        if action not in ACTIONS:
            raise UnitError(
                f'Unknown action {action!r}; use start, stop or restart'
            )
        self._check(unit)
        await self._systemctl(action, unit)

    async def enable(self, unit: str, unit_file: Path | None) -> None:
        """Links a unit file if one is given, then enables and starts the unit.

        Args:
            unit (str): The unit.
            unit_file (Path | None): The unit file to link first, or None when systemd already knows the unit.

        Raises:
            UnitError: The name is not a service unit, the file's name does not match it, or systemctl failed.
        """
        self._check(unit)
        if unit_file is not None:
            if unit_file.name != unit:
                raise UnitError(
                    f'The unit file {unit_file} must be named {unit}'
                )
            if not unit_file.is_file():
                raise UnitError(f'The unit file {unit_file} does not exist')
            await self._systemctl('link', str(unit_file.resolve()))
        await self._systemctl('enable', '--now', unit)

    async def disable(self, unit: str) -> None:
        """Stops a unit and stops it starting at login.

        Args:
            unit (str): The unit.

        Raises:
            UnitError: The name is not a service unit, or systemctl failed.
        """
        self._check(unit)
        await self._systemctl('disable', '--now', unit)

    def _check(self, unit: str) -> None:
        """Refuses anything that is not a plain service unit name, so no option or path reaches systemctl.

        Args:
            unit (str): The unit name.

        Raises:
            UnitError: The name is not letters, digits, @, dot, underscore or hyphen ending in .service.
        """
        if not _UNIT_PATTERN.match(unit):
            raise UnitError(f'{unit!r} is not a service unit name')

    async def _systemctl(self, *arguments: str) -> str:
        """Runs systemctl --user with arguments.

        Args:
            *arguments (str): The command and its arguments.

        Returns:
            str: What systemctl printed.

        Raises:
            UnitError: systemctl is missing, timed out or failed.
        """
        command = ' '.join(arguments)
        try:
            process = await asyncio.create_subprocess_exec(
                'systemctl',
                '--user',
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise UnitError('systemctl is not installed') from error
        try:
            output, errors = await asyncio.wait_for(
                process.communicate(), _TIMEOUT_SECONDS
            )
        except TimeoutError as error:
            process.kill()
            raise UnitError(
                f'systemctl --user {command} took longer than {_TIMEOUT_SECONDS:.0f} s'
            ) from error
        if process.returncode != 0:
            raise UnitError(
                f'systemctl --user {command} failed: {errors.decode(errors="replace").strip()}'
            )
        return output.decode(errors='replace')
