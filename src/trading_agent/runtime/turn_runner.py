"""The base class for whatever answers a desk's triggers.

A desk runtime hands each trigger to its turn runner. Milestone 1 uses a runner with no model; later milestones add runners that drive Gemma 4, Qwen, OpenAI and Claude.

Typical usage example:

  result = await turn_runner.run_turn(trigger)
"""

import dataclasses

from trading_agent.runtime import trigger as trigger_module


@dataclasses.dataclass(frozen=True)
class TurnResult:
    """What one turn produced.

    Attributes:
        text: The final text the desk replied with.
    """

    text: str


class TurnRunner:
    """Runs one turn for one trigger. Subclasses provide the actual work."""

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> TurnResult:
        """Runs one turn.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            TurnResult: What the turn produced.

        Raises:
            NotImplementedError: Always, because subclasses must override this method.
        """
        raise NotImplementedError

    async def reset(self) -> None:
        """Forgets the conversation so far, for the /new command.

        Runners that remember nothing keep this empty default.
        """

    async def close(self) -> None:
        """Releases anything the runner started, such as a Claude Code process.

        The desk calls this when it stops. Runners that start nothing keep this empty default.
        """
