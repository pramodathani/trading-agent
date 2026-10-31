"""Limits how many traders run a model turn at the same time, when the user sets a limit.

Every trader shares one TurnSlots. With no limit, which is the default, every turn starts at once. With a limit, a turn beyond it waits until another trader's turn ends, in the order the turns asked.

Typical usage example:

  slots = TurnSlots(3)
  async with slots.slot():
      result = await runner.run_turn(trigger)
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator


class TurnSlots:
    """The shared limit on model turns running at once.

    Attributes:
        maximum: The most turns at once, or None for no limit.
    """

    def __init__(self, maximum: int | None):
        """Creates the slots.

        Args:
            maximum (int | None): The most turns at once, or None for no limit.
        """
        self.maximum = maximum
        self._semaphore = None
        if maximum is not None:
            self._semaphore = asyncio.Semaphore(maximum)

    def is_free(self) -> bool:
        """Says whether a turn asking now would start at once.

        Returns:
            bool: True when there is no limit or a slot is free.
        """
        if self._semaphore is None:
            return True
        return not self._semaphore.locked()

    @contextlib.asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """Holds one slot for the length of a turn, waiting for one when all are taken.

        Yields:
            None: Control passes to the turn while the slot is held.
        """
        if self._semaphore is None:
            yield
            return
        async with self._semaphore:
            yield
