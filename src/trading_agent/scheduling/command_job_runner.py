"""Runs a scheduled command job: one shell command in the trader's sandbox, with no model.

The command runs with `bash -c` inside the same bwrap sandbox as the trader's bash tools, so it can read the filesystem except hidden secrets and write only in the trader's scratch folder. It is stopped after its time limit, and at most 4,000 characters of its output are kept.

Typical usage example:

  exit_code, output = await CommandJobRunner(sandbox, 120.0).run('python3 scan.py')
"""

import asyncio

from trading_agent.tools import bash_sandbox as bash_sandbox_module

_MAXIMUM_OUTPUT_CHARACTERS = 4000


class CommandJobRunner:
    """Runs command jobs for one trader."""

    def __init__(
        self,
        sandbox: bash_sandbox_module.BashSandbox,
        timeout_seconds: float,
    ):
        """Creates the runner.

        Args:
            sandbox (bash_sandbox_module.BashSandbox): The trader's sandbox.
            timeout_seconds (float): How long one command may run.
        """
        self._sandbox = sandbox
        self._timeout_seconds = timeout_seconds

    async def run(self, command: str) -> tuple[int | None, str]:
        """Runs one command and collects its output.

        Args:
            command (str): The shell command.

        Returns:
            tuple[int | None, str]: A tuple (exit_code, output), where exit_code is None when the command could not start or was stopped for taking too long, and output is its standard output and error, shortened.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *self._sandbox.command(
                    [
                        'bash',
                        '-c',
                        command,
                    ]
                ),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except (OSError, FileNotFoundError) as error:
            return None, f'The command could not start: {error}'
        try:
            output, _ = await asyncio.wait_for(
                process.communicate(),
                self._timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return None, f'Stopped after {self._timeout_seconds:.0f} seconds.'
        text = output.decode(errors='replace')
        if len(text) > _MAXIMUM_OUTPUT_CHARACTERS:
            text = text[-_MAXIMUM_OUTPUT_CHARACTERS:]
            text = f'[output cut to its last {_MAXIMUM_OUTPUT_CHARACTERS} characters]\n{text}'
        return process.returncode, text
