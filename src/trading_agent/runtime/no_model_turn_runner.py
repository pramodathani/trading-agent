"""A turn runner for a desk that has no model connected yet.

It lets the queue, the event bus and the gateway be tested end to end before any model is involved.

Typical usage example:

  desk = DeskRuntime(desk_configuration, event_bus, NoModelTurnRunner())
"""

from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner


class NoModelTurnRunner(turn_runner.TurnRunner):
    """Answers every trigger by saying that no model is connected."""

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Replies that no model is connected, quoting the trigger.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: A reply that names the trigger's source and text.
        """
        return turn_runner.TurnResult(
            text=(
                f'No model is connected to this desk yet. Received a {trigger.source} trigger: {trigger.text}'
            ),
        )
