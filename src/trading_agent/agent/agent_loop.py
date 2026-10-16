"""The agent loop: ask the model, run the tools it asks for, give it the results, repeat.

This is the loop at the heart of Pi and every other agent. One run of the loop is one turn: it ends when the model replies without asking for a tool, or when the round limit is reached.

Typical usage example:

  loop = AgentLoop('main', backend, registry, event_bus, loop_guard, maximum_rounds=20)
  result = await loop.run_turn(conversation, trigger)
"""

import asyncio

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import loop_guard as loop_guard_module
from trading_agent.agent import messages
from trading_agent.backends import backend as backend_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner
from trading_agent.tools import tool as tool_module
from trading_agent.tools import tool_registry as tool_registry_module


class AgentLoop:
    """Runs turns for one desk against one backend."""

    def __init__(
        self,
        desk_name: str,
        backend: backend_module.ModelBackend,
        tool_registry: tool_registry_module.ToolRegistry,
        event_bus: event_bus_module.EventBus,
        loop_guard: loop_guard_module.LoopGuard,
        maximum_rounds: int,
    ):
        """Creates the loop.

        Args:
            desk_name (str): The desk the loop runs for, used to tag its events.
            backend (backend_module.ModelBackend): The model to ask.
            tool_registry (tool_registry_module.ToolRegistry): The tools the model may use.
            event_bus (event_bus_module.EventBus): Where every step is published.
            loop_guard (loop_guard_module.LoopGuard): The guard against repeated identical calls.
            maximum_rounds (int): The most model calls one turn may make.
        """
        self._desk_name = desk_name
        self._backend = backend
        self._tool_registry = tool_registry
        self._event_bus = event_bus
        self._loop_guard = loop_guard
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
        self._loop_guard.start_turn()
        conversation.append(messages.ConversationMessage.user(trigger.text))
        for round_number in range(1, self._maximum_rounds + 1):
            reply = await self._backend.complete(
                conversation,
                self._tool_registry.definitions(),
                lambda piece: self._publish_text_delta(trigger, piece),
            )
            self._publish(
                event_module.EventKind.MODEL_USAGE,
                {
                    'trigger_id': trigger.trigger_id,
                    'backend': self._backend.name,
                    'model': self._backend.model,
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
                *[self._run_call(trigger, call) for call in reply.tool_calls]
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

    async def _run_call(
        self,
        trigger: trigger_module.Trigger,
        call: messages.ToolCall,
    ) -> tool_module.ToolResult:
        """Runs one tool call through the loop guard and publishes its call and result.

        Args:
            trigger (trigger_module.Trigger): The trigger of the current turn.
            call (messages.ToolCall): The call to run.

        Returns:
            tool_module.ToolResult: The tool's result, or the guard's refusal.
        """
        self._publish(
            event_module.EventKind.TOOL_CALL,
            {
                'trigger_id': trigger.trigger_id,
                'call_id': call.call_id,
                'name': call.name,
                'arguments': call.arguments,
            },
        )
        if self._loop_guard.allows(call):
            result = await self._tool_registry.run(call)
        else:
            result = tool_module.ToolResult.error(
                self._loop_guard.refusal_text(call)
            )
        self._publish(
            event_module.EventKind.TOOL_RESULT,
            {
                'trigger_id': trigger.trigger_id,
                'call_id': call.call_id,
                'name': call.name,
                'is_error': result.is_error,
                'text': result.text,
            },
        )
        return result

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
