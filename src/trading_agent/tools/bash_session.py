"""One long-lived bash process inside the sandbox, like a terminal that stays open.

The folder and variables a command sets carry over to the next command. Each command runs with its input from /dev/null, so a command that waits for typing cannot swallow what comes after it. After each command a marker line with the exit status is printed, which is how the end of its output is found. A command that runs too long has its whole session restarted.

Typical usage example:

  session = BashSession(sandbox, timeout_seconds=120, maximum_output_characters=20000)
  outcome = await session.run('ls -la')
  await session.close()
"""

import asyncio
import dataclasses
import logging
import shlex
import uuid

from trading_agent.tools import bash_sandbox as bash_sandbox_module

_LOGGER = logging.getLogger(__name__)
_MARKER_PREFIX = '__TRADING_AGENT_COMMAND_DONE__'
_BACKGROUND_FOLDER = '.background'


@dataclasses.dataclass(frozen=True)
class CommandOutcome:
    """What one command produced.

    Attributes:
        output: Its combined standard output and error, cut to the maximum length.
        exit_status: Its exit status, or None when it was stopped for running too long.
        truncated: Whether output was left out because it was too long.
    """

    output: str
    exit_status: int | None
    truncated: bool


class BashSession:
    """A persistent bash process in the sandbox."""

    def __init__(
        self,
        sandbox: bash_sandbox_module.BashSandbox,
        timeout_seconds: float,
        maximum_output_characters: int,
    ):
        """Creates the session without starting bash.

        Args:
            sandbox (bash_sandbox_module.BashSandbox): The sandbox to run in.
            timeout_seconds (float): How long one command may run.
            maximum_output_characters (int): How much output to keep from one command.
        """
        self._sandbox = sandbox
        self.timeout_seconds = timeout_seconds
        self._maximum_output_characters = maximum_output_characters
        self._process = None
        self._lock = asyncio.Lock()

    async def run(self, command: str) -> CommandOutcome:
        """Runs one command and waits for it to finish.

        Commands from parallel tool calls run one after another, never at the same time.

        Args:
            command (str): The command, as typed at a bash prompt.

        Returns:
            CommandOutcome: Its output and exit status.
        """
        async with self._lock:
            process = await self._started_process()
            marker = f'{_MARKER_PREFIX}{uuid.uuid4().hex}'
            script = '\n'.join(
                [
                    '{',
                    command,
                    '} < /dev/null',
                    f'printf \'\\n{marker} %s\\n\' "$?"',
                    '',
                ]
            )
            try:
                process.stdin.write(script.encode('utf-8'))
                await process.stdin.drain()
            except ConnectionError:
                return await self._failed_start(process)
            try:
                return await asyncio.wait_for(
                    self._read_until(process, marker),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError:
                await self._stop()
                return CommandOutcome(
                    output=f'The command did not finish within {self.timeout_seconds:g} seconds. The terminal was restarted, so the folder and variables are reset; use bash_background for long commands.',
                    exit_status=None,
                    truncated=False,
                )

    async def run_in_background(self, command: str) -> str:
        """Starts a long command that keeps running after this call returns.

        Its output goes to a log file in the scratch folder. Background commands stop when the session restarts.

        Args:
            command (str): The command.

        Returns:
            str: The job's identifier, for check_background.
        """
        job_id = uuid.uuid4().hex[:8]
        folder = shlex.quote(
            str(self._sandbox.scratch_directory / _BACKGROUND_FOLDER)
        )
        await self.run(
            f'mkdir -p {folder} && (nohup bash -c {shlex.quote(command)} > {folder}/{job_id}.log 2>&1 & echo $! > {folder}/{job_id}.pid)'
        )
        return job_id

    async def check_background(self, job_id: str) -> CommandOutcome:
        """Reports whether a background job is still running, and the end of its log.

        Args:
            job_id (str): The identifier from run_in_background.

        Returns:
            CommandOutcome: "running" or "finished", then the last 4,000 characters of its log.
        """
        folder = shlex.quote(
            str(self._sandbox.scratch_directory / _BACKGROUND_FOLDER)
        )
        safe_id = shlex.quote(job_id)
        return await self.run(
            '\n'.join(
                [
                    f'if [ ! -f {folder}/{safe_id}.pid ]; then echo "no such job: {job_id}"; else',
                    f'  if kill -0 "$(cat {folder}/{safe_id}.pid)" 2>/dev/null; then echo running; else echo finished; fi',
                    f'  tail -c 4000 {folder}/{safe_id}.log',
                    'fi',
                ]
            )
        )

    async def restart(self) -> None:
        """Stops bash, so the next command starts a fresh terminal."""
        async with self._lock:
            await self._stop()

    async def close(self) -> None:
        """Stops bash for good, when the trader stops."""
        await self._stop()

    async def _started_process(self) -> asyncio.subprocess.Process:
        """Returns the running bash process, starting it if needed.

        Returns:
            asyncio.subprocess.Process: The process.
        """
        if self._process is not None and self._process.returncode is None:
            return self._process
        command = self._sandbox.command(
            [
                'bash',
                '--noprofile',
                '--norc',
            ]
        )
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        return self._process

    async def _failed_start(
        self,
        process: asyncio.subprocess.Process,
    ) -> CommandOutcome:
        """Reports why the sandbox's bash process ended before taking a command.

        Args:
            process (asyncio.subprocess.Process): The process that ended.

        Returns:
            CommandOutcome: What the process printed before it ended, usually bwrap's error.
        """
        printed = await process.stdout.read()
        self._process = None
        message = printed.decode('utf-8', errors='replace').strip()
        return CommandOutcome(
            output=f'The terminal could not start: {message}',
            exit_status=None,
            truncated=False,
        )

    async def _read_until(
        self,
        process: asyncio.subprocess.Process,
        marker: str,
    ) -> CommandOutcome:
        """Reads output lines until the command's marker line.

        Args:
            process (asyncio.subprocess.Process): The bash process.
            marker (str): The marker this command prints when it ends.

        Returns:
            CommandOutcome: The output and exit status.
        """
        kept = []
        kept_length = 0
        truncated = False
        while True:
            raw_line = await process.stdout.readline()
            if not raw_line:
                return CommandOutcome(
                    output=''.join(kept) + '\n[the terminal exited]',
                    exit_status=None,
                    truncated=truncated,
                )
            line = raw_line.decode('utf-8', errors='replace')
            if line.startswith(marker):
                status_text = line[len(marker) :].strip()
                output = ''.join(kept)
                output = output.rstrip('\n')
                return CommandOutcome(
                    output=output,
                    exit_status=int(status_text)
                    if status_text.isdigit()
                    else None,
                    truncated=truncated,
                )
            if kept_length + len(line) <= self._maximum_output_characters:
                kept.append(line)
                kept_length += len(line)
            else:
                truncated = True

    async def _stop(self) -> None:
        """Kills the bash process and waits for it to end."""
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return
        process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            _LOGGER.warning('The bash sandbox did not exit after being killed')
