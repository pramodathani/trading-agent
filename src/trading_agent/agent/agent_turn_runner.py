"""The turn runner that drives a model through the agent loop.

It keeps the desk's conversation between turns, so the desk remembers what was said earlier, and rebuilds the system prompt before every turn, so an edit to a workspace file takes effect on the next turn.

Typical usage example:

  runner = AgentTurnRunner(agent_loop, prompt_builder)
  result = await runner.run_turn(trigger)
"""

from trading_agent.agent import agent_loop as agent_loop_module
from trading_agent.agent import context_usage as context_usage_module
from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import prompt_builder as prompt_builder_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner


class AgentTurnRunner(turn_runner.TurnRunner):
    """Runs each trigger as a turn of the agent loop, in one ongoing conversation.

    Attributes:
        conversation: The conversation so far.
    """

    def __init__(
        self,
        agent_loop: agent_loop_module.AgentLoop,
        prompt_builder: prompt_builder_module.PromptBuilder,
        context_window: int = 0,
    ):
        """Creates the runner with an empty conversation.

        Args:
            agent_loop (agent_loop_module.AgentLoop): The loop to run each turn with.
            prompt_builder (prompt_builder_module.PromptBuilder): Builds the desk's system prompt.
            context_window (int): How many tokens the model is given, for context_usage; 0 when it is not known.
        """
        self._agent_loop = agent_loop
        self._prompt_builder = prompt_builder
        self._context_window = context_window
        self.conversation = conversation_module.Conversation(
            prompt_builder.build().text
        )

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Refreshes the system prompt and runs one turn of the agent loop.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: The model's final text.
        """
        self.conversation.system_prompt = self._prompt_builder.build().text
        return await self._agent_loop.run_turn(self.conversation, trigger)

    async def compact(self, trigger: trigger_module.Trigger) -> str:
        """Flushes and compresses the conversation now, for the /compact command.

        Args:
            trigger (trigger_module.Trigger): The command's trigger, used to tag events.

        Returns:
            str: What happened, for the user.

        Raises:
            backend_module.BackendUnavailableError: The model could not be reached.
        """
        before = self.conversation.estimated_tokens()
        compressed = await self._agent_loop.compact(self.conversation, trigger)
        if not compressed:
            return 'There was nothing to compact.'
        return f'Compressed the conversation from about {before:,} tokens into a summary, after a memory-flush turn.'

    def active_model(self) -> str | None:
        """The model the loop's backend uses now.

        Returns:
            str | None: The model's name.
        """
        return self._agent_loop.backend.model

    def use_model(self, model: str | None) -> None:
        """Switches the loop's backend to another model on the same server, keeping the conversation.

        Args:
            model (str | None): The model's name, or None for the configured model.
        """
        self._agent_loop.backend.use_model(model)

    def context_usage(self) -> context_usage_module.ContextUsage | None:
        """Estimates how full the model's context window is.

        Returns:
            context_usage_module.ContextUsage | None: The estimate, or None when the context window is not known.
        """
        if self._context_window <= 0:
            return None
        backend = self._agent_loop.backend
        return context_usage_module.ContextUsage.estimate(
            backend.name,
            backend.model,
            self._context_window,
            self.conversation,
            self._agent_loop.tool_definitions(),
        )

    async def reset(self) -> None:
        """Starts a new, empty conversation."""
        self.conversation = conversation_module.Conversation(
            self._prompt_builder.build().text
        )
