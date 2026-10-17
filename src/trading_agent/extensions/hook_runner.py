"""Runs the user's hook scripts when events happen.

A hook is any executable file in a folder named after an event, under workspace/shared/hooks/ or under an installed package's hooks/ folder:

  workspace/shared/hooks/order_placed/notify.sh
  workspace/shared/hooks/kill_switch/page-me.py

Each matching hook runs as its own process with the event as JSON on its standard input, the event's name in TRADING_AGENT_EVENT and the desk in TRADING_AGENT_DESK. The folder name can be any event kind, such as order, risk_decision, kill_switch, session_started, desk_stopped or error, or one of two narrower names: order_placed (an order event whose action is "placed") and risk_rejected (a risk decision that refused an order).

Hooks run outside the gateway's process, at most four at a time, each for at most 30 seconds. A hook that fails, hangs or is missing is logged and has no effect on any desk. Secrets are masked in the JSON a hook receives, and a hook gets only a few safe environment variables, as MCP servers do.

Typical usage example:

  runner = HookRunner(event_bus, Path('workspace/shared/hooks'), packages, redactor)
  task = asyncio.create_task(runner.run())
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from trading_agent.extensions import (
    installed_packages as installed_packages_module,
)
from trading_agent.journal import secret_redactor as secret_redactor_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module

_LOGGER = logging.getLogger(__name__)
_TIMEOUT_SECONDS = 30.0
_MAXIMUM_RUNNING = 4
_QUEUE_SIZE = 10000
_SKIPPED_KINDS = (event_module.EventKind.TEXT_DELTA,)
_INHERITED_VARIABLES = (
    'HOME',
    'LANG',
    'LOGNAME',
    'PATH',
    'USER',
)


class HookRunner:
    """Starts hook processes for events."""

    def __init__(
        self,
        event_bus: event_bus_module.EventBus,
        hooks_directory: Path,
        packages: installed_packages_module.InstalledPackages | None = None,
        redactor: secret_redactor_module.SecretRedactor | None = None,
    ):
        """Subscribes to the bus at once, so no event is missed.

        Args:
            event_bus (event_bus_module.EventBus): The bus to listen to.
            hooks_directory (Path): The user's hooks folder, holding one subfolder per event.
            packages (installed_packages_module.InstalledPackages | None): The installed packages, whose hooks/ folders are read for every event so a new package counts at once, or None.
            redactor (secret_redactor_module.SecretRedactor | None): Masks secrets in the JSON given to hooks, or None to pass events unchanged.
        """
        self._hooks_directory = hooks_directory
        self._packages = packages
        self._redactor = redactor
        self._subscription = event_bus.subscribe(maximum_queued=_QUEUE_SIZE)
        self._limit = asyncio.Semaphore(_MAXIMUM_RUNNING)
        self._running: set[asyncio.Task] = set()

    async def run(self) -> None:
        """Starts hooks for each event until cancelled, then stops the ones still running."""
        try:
            while True:
                published_event = await self._subscription.next_event()
                for name, program in self.programs_for(published_event):
                    task = asyncio.create_task(
                        self._run_hook(name, program, published_event)
                    )
                    self._running.add(task)
                    task.add_done_callback(self._running.discard)
        finally:
            for task in list(self._running):
                task.cancel()
            self._subscription.close()

    def programs_for(
        self,
        published_event: event_module.Event,
    ) -> list[tuple[str, Path]]:
        """The hook programs an event should start.

        Args:
            published_event (event_module.Event): The event.

        Returns:
            list[tuple[str, Path]]: Tuples (name, program), where name is the hook folder's event name and program an executable file in it.
        """
        if published_event.kind in _SKIPPED_KINDS:
            return []
        programs = []
        for name in self._names(published_event):
            for root in self._roots():
                folder = root / name
                if not folder.is_dir():
                    continue
                for path in sorted(folder.iterdir()):
                    if path.name.startswith('.') or not path.is_file():
                        continue
                    if os.access(path, os.X_OK):
                        programs.append((name, path))
        return programs

    def _roots(self) -> list[Path]:
        """The folders holding one subfolder per event.

        Returns:
            list[Path]: The user's hooks folder, then each package's.
        """
        roots = [
            self._hooks_directory,
        ]
        if self._packages is not None:
            roots.extend(self._packages.hook_roots())
        return roots

    def _names(self, published_event: event_module.Event) -> list[str]:
        """The hook folder names that match an event.

        Args:
            published_event (event_module.Event): The event.

        Returns:
            list[str]: The event's kind, plus order_placed or risk_rejected when they apply.
        """
        names = [
            str(published_event.kind),
        ]
        kind = published_event.kind
        payload = published_event.payload
        placed = payload.get('action') == 'placed'
        if kind == event_module.EventKind.ORDER and placed:
            names.append('order_placed')
        refused = payload.get('approved') is False
        if kind == event_module.EventKind.RISK_DECISION and refused:
            names.append('risk_rejected')
        return names

    async def _run_hook(
        self,
        name: str,
        program: Path,
        published_event: event_module.Event,
    ) -> None:
        """Runs one hook process and logs how it ended.

        Args:
            name (str): The hook folder's event name.
            program (Path): The executable.
            published_event (event_module.Event): The event, given as JSON on standard input.
        """
        data = published_event.to_json_dictionary()
        if self._redactor is not None:
            data = self._redactor.redact(data)
        stdin_bytes = json.dumps(data, ensure_ascii=False, default=str).encode()
        async with self._limit:
            try:
                process = await asyncio.create_subprocess_exec(
                    str(program.resolve()),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=program.parent.resolve(),
                    env=self._environment(name, published_event),
                )
            except OSError as error:
                _LOGGER.warning('Hook %s could not start: %s', program, error)
                return
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(stdin_bytes),
                    _TIMEOUT_SECONDS,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                _LOGGER.warning(
                    'Hook %s was stopped after %.0f seconds',
                    program,
                    _TIMEOUT_SECONDS,
                )
                return
        if process.returncode != 0:
            _LOGGER.warning(
                'Hook %s exited with status %d: %s',
                program,
                process.returncode,
                stderr.decode(errors='replace').strip()[-500:],
            )
        else:
            _LOGGER.info('Hook %s ran for %s', program, name)

    def _environment(
        self,
        name: str,
        published_event: event_module.Event,
    ) -> dict[str, str]:
        """The environment a hook runs with.

        Args:
            name (str): The hook folder's event name.
            published_event (event_module.Event): The event.

        Returns:
            dict[str, str]: A few safe variables from the gateway, plus the event and desk names.
        """
        environment = {}
        for variable in _INHERITED_VARIABLES:
            value = os.environ.get(variable)
            if value is not None:
                environment[variable] = value
        environment['TRADING_AGENT_EVENT'] = name
        environment['TRADING_AGENT_DESK'] = published_event.desk or ''
        return environment
