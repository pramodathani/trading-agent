"""Stops a model from calling the same tool with the same arguments over and over in one turn.

Small models sometimes get stuck repeating one call. For a trading agent that could mean sending the same order again and again, so the guard refuses a call once it has been made too many times in a turn. The risk engine (milestone 9) also limits orders per minute; the guard catches the loop earlier and for every tool.

Typical usage example:

  guard = LoopGuard(maximum_identical_calls=3)
  guard.start_turn()
  if guard.allows(call):
      ...
"""

import json

from trading_agent.agent import messages


class LoopGuard:
    """Counts identical tool calls within the current turn."""

    def __init__(self, maximum_identical_calls: int):
        """Creates the guard.

        Args:
            maximum_identical_calls (int): How many times one tool may be called with the same arguments in a turn.
        """
        self._maximum_identical_calls = maximum_identical_calls
        self._counts = {}

    def start_turn(self) -> None:
        """Forgets the previous turn's calls."""
        self._counts = {}

    def allows(self, call: messages.ToolCall) -> bool:
        """Records a call and says whether it may run.

        Args:
            call (messages.ToolCall): The call the model made.

        Returns:
            bool: False once the same tool and arguments have been seen more than the maximum in this turn.
        """
        key = call.name + ' ' + json.dumps(call.arguments, sort_keys=True)
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key] <= self._maximum_identical_calls

    def refusal_text(self, call: messages.ToolCall) -> str:
        """The message sent to the model instead of running a refused call.

        Args:
            call (messages.ToolCall): The refused call.

        Returns:
            str: An explanation the model can act on.
        """
        return f'Refused: you have already called {call.name} with these exact arguments {self._maximum_identical_calls} times in this turn. Use the earlier results, try different arguments, or give your answer.'
