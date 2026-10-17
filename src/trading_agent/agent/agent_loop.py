"""The agent loop: ask the model, run the tools it asks for, give it the results, repeat.

This is the loop at the heart of Pi and every other agent. One run of the loop is one turn: it ends when the model replies without asking for a tool, or when the round limit is reached.

With a context compressor, a conversation that has filled 70% of the model's window is compressed before the next turn: the desk first gets a silent memory-flush turn to save what matters, then the older messages are replaced by a summary. Between the tool rounds of one long turn, a conversation past 85% is compressed at once, without the flush.

Typical usage example:

  loop = AgentLoop('main', backend, executor, event_bus, maximum_rounds=20)
  result = await loop.run_turn(conversation, trigger)
"""

import asyncio

from trading_agent.agent import context_compressor as context_compressor_module
from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import backend as backend_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import steering_inbox as steering_inbox_module
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
        compressor: context_compressor_module.ContextCompressor | None = None,
        steering_inbox: steering_inbox_module.SteeringInbox | None = None,
    ):
        """Creates the loop.

        Args:
            desk_name (str): The desk the loop runs for, used to tag its events.
            backend (backend_module.ModelBackend): The model to ask.
            executor (tool_call_executor_module.ToolCallExecutor): What runs the model's tool calls.
            event_bus (event_bus_module.EventBus): Where every step is published.
            maximum_rounds (int): The most model calls one turn may make.
            compressor (context_compressor_module.ContextCompressor | None): Compresses the conversation when it gets too full, or None to let it grow.
            steering_inbox (steering_inbox_module.SteeringInbox | None): The desk's mid-turn messages, added to the conversation after each tool round, or None for a loop that cannot be steered, such as a subagent's.
        """
        self._desk_name = desk_name
        self.backend = backend
        self._executor = executor
        self._event_bus = event_bus
        self._maximum_rounds = maximum_rounds
        self._compressor = compressor
        self._steering_inbox = steering_inbox

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
        if self._compressor is not None and self._compressor.is_full(
            conversation
        ):
            await self._flush_and_compress(conversation, trigger, 'threshold')
        return await self._run_rounds(conversation, trigger)

    async def compact(
        self,
        conversation: conversation_module.Conversation,
        trigger: trigger_module.Trigger,
    ) -> bool:
        """Flushes and compresses the conversation now, for the /compact command.

        Args:
            conversation (conversation_module.Conversation): The desk's conversation.
            trigger (trigger_module.Trigger): The command's trigger, used to tag events.

        Returns:
            bool: True when the conversation was compressed, False when there is no compressor or nothing to compress.

        Raises:
            backend_module.BackendUnavailableError: The model could not be reached.
        """
        if self._compressor is None or not conversation.messages:
            return False
        return await self._flush_and_compress(conversation, trigger, 'command')

    async def _flush_and_compress(
        self,
        conversation: conversation_module.Conversation,
        trigger: trigger_module.Trigger,
        reason: str,
    ) -> bool:
        """Gives the desk a memory-flush turn, then compresses everything said so far.

        Args:
            conversation (conversation_module.Conversation): The desk's conversation.
            trigger (trigger_module.Trigger): The trigger that caused it, used to tag events.
            reason (str): "threshold" or "command", for the event.

        Returns:
            bool: True when the conversation was compressed.
        """
        flush_trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.COMPRESSION,
            trigger.desk,
            context_compressor_module.FLUSH_REQUEST,
        )
        await self._run_rounds(conversation, flush_trigger)
        return await self._compressor.compress(
            conversation,
            self.backend,
            len(conversation.messages),
            reason,
            trigger.trigger_id,
        )

    async def _run_rounds(
        self,
        conversation: conversation_module.Conversation,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Runs the rounds of one turn: model call, tool calls, and again.

        Args:
            conversation (conversation_module.Conversation): The desk's conversation, which grows by this turn's messages.
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: The model's final text.
        """
        self._executor.start_turn()
        conversation.append(messages.ConversationMessage.user(trigger.text))
        try:
            return await self._rounds(conversation, trigger)
        except asyncio.CancelledError:
            self._answer_unanswered_calls(conversation)
            raise

    async def _rounds(
        self,
        conversation: conversation_module.Conversation,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Asks the model and runs its tool calls until it answers without tools.

        Args:
            conversation (conversation_module.Conversation): The conversation, whose last message is the turn's trigger.
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: The model's final text.
        """
        turn_start = len(conversation.messages) - 1
        for round_number in range(1, self._maximum_rounds + 1):
            if round_number > 1 and self._is_overflowing(conversation):
                compressed = await self._compressor.compress(
                    conversation,
                    self.backend,
                    turn_start,
                    'emergency',
                    trigger.trigger_id,
                )
                if compressed:
                    turn_start = 1
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
            if reply.prompt_tokens:
                conversation.record_usage(
                    reply.prompt_tokens + reply.completion_tokens
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
                        result.image_png,
                    )
                )
            self._add_steering(conversation)
        return turn_runner.TurnResult(
            text=f'Stopped after {self._maximum_rounds} rounds of tool calls without a final answer.'
        )

    def _add_steering(
        self,
        conversation: conversation_module.Conversation,
    ) -> None:
        """Adds the user's mid-turn messages, if any, before the next model call.

        Args:
            conversation (conversation_module.Conversation): The conversation.
        """
        if self._steering_inbox is None:
            return
        text = self._steering_inbox.take_text()
        if text is not None:
            conversation.append(messages.ConversationMessage.user(text))

    def _answer_unanswered_calls(
        self,
        conversation: conversation_module.Conversation,
    ) -> None:
        """Gives a result to every tool call the model asked for but that never finished, after /stop.

        Model servers refuse a conversation in which a tool call has no result, so a stopped turn must not leave one behind.

        Args:
            conversation (conversation_module.Conversation): The conversation.
        """
        if not conversation.messages:
            return
        last = conversation.messages[-1]
        if last.role != messages.Role.ASSISTANT or not last.tool_calls:
            return
        for call in last.tool_calls:
            conversation.append(
                messages.ConversationMessage.tool_result(
                    call,
                    'Not finished: the user stopped the turn with /stop.',
                    True,
                    None,
                )
            )

    def _is_overflowing(
        self,
        conversation: conversation_module.Conversation,
    ) -> bool:
        """Says whether the conversation must be compressed before the next model call.

        Args:
            conversation (conversation_module.Conversation): The conversation.

        Returns:
            bool: True when there is a compressor and the emergency threshold is reached.
        """
        if self._compressor is None:
            return False
        return self._compressor.is_overflowing(conversation)

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
