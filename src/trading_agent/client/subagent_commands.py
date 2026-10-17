"""The `trading-agent subagents list` command: shows every subagent definition and any that cannot be read.

Typical usage example:

  exit_code = SubagentCommands(library).list()
"""

import sys
from typing import TextIO

from trading_agent.subagents import subagent_library as subagent_library_module
from trading_agent.subagents import subagent_toolbox


class SubagentCommands:
    """Lists subagents for the user."""

    def __init__(
        self,
        library: subagent_library_module.SubagentLibrary,
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            library (subagent_library_module.SubagentLibrary): The definitions.
            output (TextIO): Where to print.
        """
        self._library = library
        self._output = output

    def list(self) -> int:
        """Prints each subagent, then each file that could not be read.

        Returns:
            int: 0 when every file was readable, 1 otherwise.
        """
        definitions = self._library.definitions()
        if not definitions:
            self._print(f'No subagents in {self._library.agents_directory}.')
        for definition in definitions:
            models = (
                ', '.join(definition.models)
                if definition.models
                else "the desk's order"
            )
            tools = definition.tool_names or subagent_toolbox.DEFAULT_TOOL_NAMES
            self._print(f'{definition.name}: {definition.description}')
            self._print(
                f'  model: {models}; up to {definition.maximum_turns} turns and {definition.timeout_seconds} s'
            )
            self._print(f'  tools: {", ".join(tools)}')
            self._print(f'  file: {definition.path}')
        broken = self._library.broken()
        for item in broken:
            self._print(f'cannot read {item.path}: {item.error}')
        if broken:
            return 1
        return 0

    def _print(self, text: str) -> None:
        """Prints one line.

        Args:
            text (str): The line.
        """
        print(text, file=self._output)
