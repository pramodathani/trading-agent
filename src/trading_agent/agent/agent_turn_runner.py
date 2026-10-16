"""The turn runner that drives a model through the agent loop.

It keeps the desk's conversation between turns, so the desk remembers what was said earlier. Milestone 5 replaces the short built-in system prompt with one built from the workspace files, and milestones 11 and 12 add lasting memory and compression.

Typical usage example:

  runner = AgentTurnRunner(agent_loop, system_prompt)
  result = await runner.run_turn(trigger)
"""

from trading_agent.agent import agent_loop as agent_loop_module
from trading_agent.agent import conversation as conversation_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner


class AgentTurnRunner(turn_runner.TurnRunner):
    """Runs each trigger as a turn of the agent loop, in one ongoing conversation."""

    def __init__(
        self,
        agent_loop: agent_loop_module.AgentLoop,
        system_prompt: str,
    ):
        """Creates the runner with an empty conversation.

        Args:
            agent_loop (agent_loop_module.AgentLoop): The loop to run each turn with.
            system_prompt (str): The instructions for the model.
        """
        self._agent_loop = agent_loop
        self.conversation = conversation_module.Conversation(system_prompt)

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Runs one turn of the agent loop.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: The model's final text.
        """
        return await self._agent_loop.run_turn(self.conversation, trigger)
