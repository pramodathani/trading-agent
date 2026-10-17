"""The `trading-agent checkpoints` commands: list and restore a desk's snapshots.

Typical usage example:

  exit_code = CheckpointCommands(checkpoints).run('list', None)
"""

import sys
from typing import TextIO

from trading_agent.memory import checkpoints as checkpoints_module


class CheckpointCommands:
    """Prints and restores one desk's checkpoints for the user."""

    def __init__(
        self,
        checkpoints: checkpoints_module.Checkpoints,
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            checkpoints (checkpoints_module.Checkpoints): The desk's checkpoint repository.
            output (TextIO): Where to print.
        """
        self._checkpoints = checkpoints
        self._output = output

    def run(
        self,
        action: str,
        checkpoint_id: str | None,
        limit: int = 20,
    ) -> int:
        """Runs one action.

        Args:
            action (str): "list" or "restore".
            checkpoint_id (str | None): The checkpoint to restore, for "restore".
            limit (int): The most checkpoints "list" prints.

        Returns:
            int: 0 on success, 1 when git failed or the checkpoint does not exist.
        """
        try:
            if action == 'list':
                self._list(limit)
            elif action == 'restore':
                before = self._checkpoints.restore(checkpoint_id)
                self._print(
                    f'Restored the desk files to checkpoint {checkpoint_id}. The files as they were just before are checkpoint {before}; restore that to undo this.'
                )
        except checkpoints_module.CheckpointError as error:
            self._print(str(error))
            return 1
        return 0

    def _list(self, limit: int) -> None:
        """Prints one line per checkpoint, newest first.

        Args:
            limit (int): The most checkpoints to print.
        """
        checkpoints = self._checkpoints.list(limit)
        if not checkpoints:
            self._print('No checkpoints yet.')
            return
        for checkpoint in checkpoints:
            self._print(
                f'{checkpoint.checkpoint_id}  {checkpoint.created_at}  {checkpoint.reason}'
            )

    def _print(self, text: str) -> None:
        """Prints one line.

        Args:
            text (str): The line.
        """
        print(text, file=self._output)
