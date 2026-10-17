"""The base class for whatever answers a desk's triggers.

A desk runtime hands each trigger to its turn runner. Milestone 1 uses a runner with no model; later milestones add runners that drive Gemma 4, Qwen, OpenAI and Claude.

Typical usage example:

  result = await turn_runner.run_turn(trigger)
"""

import dataclasses
from typing import Any

from trading_agent.agent import context_usage as context_usage_module
from trading_agent.runtime import trigger as trigger_module

THINKING_LEVELS = (
    'off',
    'low',
    'medium',
    'high',
    'xhigh',
    'max',
)
SIDE_QUESTION_NOTE = '[A side question from the user. Answer it briefly from what you already know, without calling any tools. Neither the question nor your answer will be kept in the conversation.]'


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

    async def compact(self, trigger: trigger_module.Trigger) -> str:
        """Saves what matters and compresses the conversation now, for the /compact command.

        Runners that keep no conversation keep this default.

        Args:
            trigger (trigger_module.Trigger): The command's trigger, used to tag events.

        Returns:
            str: What happened, for the user.
        """
        del trigger
        return (
            'This desk keeps no conversation, so there is nothing to compact.'
        )

    def saved_state(self) -> dict[str, Any] | None:
        """What the runner needs to continue its conversation after a restart.

        Runners whose conversation lives only in memory keep this default; after a restart the model router tells them what they missed instead.

        Returns:
            dict[str, Any] | None: A JSON-serialisable dictionary, or None when nothing can be saved.
        """
        return None

    async def restore_state(self, state: dict[str, Any]) -> bool:
        """Continues the conversation described by saved_state, after a restart.

        Args:
            state (dict[str, Any]): What saved_state returned before the restart.

        Returns:
            bool: True when the runner remembers the conversation again, False when it starts afresh.
        """
        del state
        return False

    def active_model(self) -> str | None:
        """The model the runner uses now.

        Runners without a model keep this default.

        Returns:
            str | None: The model's name, or None.
        """
        return None

    def use_model(self, model: str | None) -> None:
        """Switches to another model of the same provider, or back to the configured one.

        Args:
            model (str | None): The model's name, or None for the configured model.

        Raises:
            ValueError: Always, because this runner has no model to switch.
        """
        if model is not None:
            raise ValueError('This desk runs without a model')

    def thinking(self) -> str | None:
        """The thinking level the runner uses now, for /think.

        Runners without a thinking setting keep this default.

        Returns:
            str | None: The level, such as "medium" or "off", or None when the runner has no thinking setting.
        """
        return None

    def set_thinking(self, level: str | None) -> bool:
        """Changes how hard the model thinks from the next turn on, keeping the conversation.

        Runners without a thinking setting keep this default.

        Args:
            level (str | None): One of THINKING_LEVELS, or None for the level in trading_agent.toml.

        Returns:
            bool: True when the level was applied, False when the runner has no thinking setting.
        """
        del level
        return False

    async def side_question(self, question: str) -> str:
        """Answers a question from what the conversation already holds, without adding the question or the answer to it.

        Runners without a model keep this default.

        Args:
            question (str): The user's question.

        Returns:
            str: The answer.
        """
        del question
        return 'This desk has no model to ask.'

    def context_usage(self) -> context_usage_module.ContextUsage | None:
        """How full the runner's context window is, as of its last turn.

        Runners that keep no conversation keep this default.

        Returns:
            context_usage_module.ContextUsage | None: The latest snapshot, or None when there is none.
        """
        return None

    async def close(self) -> None:
        """Releases anything the runner started, such as a Claude Code process.

        The desk calls this when it stops. Runners that start nothing keep this empty default.
        """
