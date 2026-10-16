"""The agent loop: ask the model, run the tools it asks for, give it the results, repeat.

This is the loop at the heart of Pi and every other agent. One run of the loop is one turn: it ends when the model replies without asking for a tool, or when the round limit is reached.

Typical usage example:

  loop = AgentLoop('main', backend, executor, event_bus, maximum_rounds=20)
  result = await loop.run_turn(conversation, trigger)
"""

import asyncio

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import backend as backend_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.tools import tool_call_executor as tool_call_executor_module


class AgentLoop:
    """Runs turns for one desk against one backend.

    Attributes:
        backend: The model the loop asks.
    """

    def __init__(
        self,
        desk_name: str,
        backend: backend_module.ModelBackend,
        executor: tool_call_executor_module.ToolCallExecutor,
        event_bus: event_bus_module.EventBus,
        maximum_rounds: int,
    ):
        """Creates the loop.

        Args:
            desk_name (str): The desk the loop runs for, used to tag its events.
            backend (backend_module.ModelBackend): The model to ask.
            executor (tool_call_executor_module.ToolCallExecutor): What runs the model's tool calls.
            event_bus (event_bus_module.EventBus): Where every step is published.
            maximum_rounds (int): The most model calls one turn may make.
        """
        self._desk_name = desk_name
        self.backend = backend
        self._executor = executor
        self._event_bus = event_bus
        self._maximum_rounds = maximum_rounds

    async def run_turn(
        self,
        conversation: conversation_module.Conversation,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Runs one turn for a trigger, appending everything to the conversation.

        Args:
            conversation (conversation_module.Conversation): The desk's conversation, which grows by this turn's messages.
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: The model's final text.

        Raises:
            backend_module.BackendUnavailableError: The model could not be reached.
        """
        self._executor.start_turn()
        conversation.append(messages.ConversationMessage.user(trigger.text))
        for round_number in range(1, self._maximum_rounds + 1):
            reply = await self.backend.complete(
                conversation,
                self._executor.tool_registry.definitions(),
                lambda piece: self._publish_text_delta(trigger, piece),
            )
            self._publish(
                event_module.EventKind.MODEL_USAGE,
                {
                    'trigger_id': trigger.trigger_id,
                    'backend': self.backend.name,
                    'model': self.backend.model,
                    'round': round_number,
                    'prompt_tokens': reply.prompt_tokens,
                    'completion_tokens': reply.completion_tokens,
                },
            )
            conversation.append(
                messages.ConversationMessage.assistant(
                    reply.text,
                    reply.tool_calls,
                )
            )
            if not reply.tool_calls:
                return turn_runner.TurnResult(text=reply.text)
            results = await asyncio.gather(
                *[
                    self._executor.execute(trigger, call)
                    for call in reply.tool_calls
                ]
            )
            for call, result in zip(reply.tool_calls, results, strict=True):
                conversation.append(
                    messages.ConversationMessage.tool_result(
                        call,
                        result.text,
                        result.is_error,
                    )
                )
        return turn_runner.TurnResult(
            text=f'Stopped after {self._maximum_rounds} rounds of tool calls without a final answer.'
        )

    def _publish_text_delta(
        self,
        trigger: trigger_module.Trigger,
        piece: str,
    ) -> None:
        """Publishes one streamed piece of the model's text.

        Args:
            trigger (trigger_module.Trigger): The trigger of the current turn.
            piece (str): The new text.
        """
        self._publish(
            event_module.EventKind.TEXT_DELTA,
            {
                'trigger_id': trigger.trigger_id,
                'text': piece,
            },
        )

    def _publish(self, kind: event_module.EventKind, payload: dict) -> None:
        """Publishes an event from this desk.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The event's details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, self._desk_name, payload)
        )
