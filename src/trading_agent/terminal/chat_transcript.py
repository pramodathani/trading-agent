"""Groups one trader's events into chat turns, one per trigger, as the web page does.

It follows the rules of the web page's chatTurnBuilder.ts and eventSocket.ts, but it is fed one event at a time, and each call says which item changed, so a screen only redraws that item.

Typical usage example:

  transcript = ChatTranscript()
  for event in journal_events:
      transcript.add(event)
  changed = transcript.add(live_event)
"""

from typing import Any, TypeAlias

from trading_agent.terminal import chat_items
from trading_agent.terminal import event_describer

_TURN_LESS_KINDS_SHOWN = (
    'order',
    'risk_decision',
    'fill',
    'price_alert',
    'message',
    'trader_halt',
    'kill_switch',
    'session_started',
    'cron_fired',
    'cron_result',
)
_STEP_KINDS_SHOWN = (
    'backend_switch',
    'backend_unavailable',
    'risk_decision',
    'order',
    'subagent_started',
    'subagent_finished',
    'context_compressed',
    'message',
)

ChatItem: TypeAlias = chat_items.ChatTurn | chat_items.LooseEvent


class ChatTranscript:
    """The chat of one trader, built from its events.

    Attributes:
        items: The turns and loose events, oldest first.
    """

    def __init__(self):
        """Creates an empty transcript."""
        self.items: list[ChatItem] = []
        self._turns: dict[str, chat_items.ChatTurn] = {}
        self._shown: set[str] = set()
        self._open_turn: chat_items.ChatTurn | None = None
        self._request_steps: dict[str, chat_items.RequestStep] = {}
        self._request_turns: dict[str, chat_items.ChatTurn] = {}
        self._seen_keys: set[str] = set()
        self._describer = event_describer.EventDescriber()

    def add(self, event: dict[str, Any]) -> ChatItem | None:
        """Adds one event.

        An event already added, such as one read from the journal and received live too, is ignored.

        Args:
            event (dict[str, Any]): The event, with kind, trader, payload and created_at.

        Returns:
            ChatItem | None: The turn or loose event that changed or was added, or None when nothing shown changed.
        """
        kind = event.get('kind', '')
        if kind != 'text_delta':
            key = self.key(event)
            if key in self._seen_keys:
                return None
            self._seen_keys.add(key)
        payload = event.get('payload') or {}
        if kind == 'user_response':
            return self._add_response(payload)
        trigger_id = payload.get('trigger_id')
        if not isinstance(trigger_id, str):
            trigger_id = None
        if kind == 'trigger_received' and trigger_id is not None:
            return self._add_trigger(event, trigger_id)
        if kind == 'text_delta':
            turn = self._turns.get(trigger_id or '')
            if turn is None:
                return None
            turn.streaming_text += str(payload.get('text', ''))
            return self._shown_item(turn)
        newly_shown = None
        if (
            kind == 'turn_started'
            and trigger_id is not None
            and trigger_id not in self._shown
        ):
            queued_message = self._turns.get(trigger_id)
            if queued_message is not None:
                self.items.append(queued_message)
                self._shown.add(trigger_id)
                newly_shown = queued_message
        turn = self._open_turn
        if trigger_id is not None:
            turn = self._turns.get(trigger_id)
        if kind == 'user_request':
            step = chat_items.RequestStep(request=dict(payload))
            request_id = str(payload.get('request_id', ''))
            self._request_steps[request_id] = step
            if turn is None:
                return None
            turn.steps.append(step)
            self._request_turns[request_id] = turn
            return turn
        if turn is None:
            if kind not in _TURN_LESS_KINDS_SHOWN:
                return None
            if self._describer.describe(event).tone == 'quiet':
                return None
            loose = chat_items.LooseEvent(event=event)
            self.items.append(loose)
            return loose
        if kind == 'turn_started':
            turn.started = True
            turn.started_at = event.get('created_at')
            self._open_turn = turn
            return turn
        if kind == 'turn_finished':
            turn.finished = True
            turn.finished_at = event.get('created_at')
            for step in turn.steps:
                if (
                    isinstance(step, chat_items.ToolStep)
                    and step.result_text is None
                ):
                    step.ended_early = True
            if self._open_turn is turn:
                self._open_turn = None
            return turn
        if self._add_to_turn(turn, event):
            return self._shown_item(turn)
        return newly_shown

    def turn(self, trigger_id: str) -> chat_items.ChatTurn | None:
        """Finds a turn by its trigger.

        Args:
            trigger_id (str): The trigger's id.

        Returns:
            chat_items.ChatTurn | None: The turn, or None when no such trigger was seen.
        """
        return self._turns.get(trigger_id)

    def running_turn(self) -> chat_items.ChatTurn | None:
        """The turn that has started and not finished, if any.

        Returns:
            chat_items.ChatTurn | None: The open turn, or None.
        """
        return self._open_turn

    def key(self, event: dict[str, Any]) -> str:
        """A key that is the same for the journal's copy and the live copy of one event; the web page's key plus the trigger id.

        Args:
            event (dict[str, Any]): The event.

        Returns:
            str: The key.
        """
        payload = event.get('payload') or {}
        call_id = payload.get('call_id')
        if not isinstance(call_id, str):
            call_id = ''
        trigger_id = payload.get('trigger_id')
        if not isinstance(trigger_id, str):
            trigger_id = ''
        trader = event.get('trader') or ''
        return f'{event.get("created_at", "")}|{event.get("kind", "")}|{trader}|{trigger_id}|{call_id}'

    def _shown_item(
        self,
        turn: chat_items.ChatTurn,
    ) -> chat_items.ChatTurn | None:
        """The item on screen that holds a turn.

        Args:
            turn (chat_items.ChatTurn): The turn that changed.

        Returns:
            chat_items.ChatTurn | None: The turn itself when it is shown, the running turn it steered when it is shown inside one, or None.
        """
        if turn.trigger_id in self._shown:
            return turn
        if turn.steering_into is not None:
            return self._turns.get(turn.steering_into)
        return None

    def _add_response(self, payload: dict[str, Any]) -> ChatItem | None:
        """Records the user's answer to a request on the request's step.

        Args:
            payload (dict[str, Any]): The user_response event's payload.

        Returns:
            ChatItem | None: The turn holding the request, or None when the request is not in this transcript.
        """
        request_id = str(payload.get('request_id', ''))
        step = self._request_steps.get(request_id)
        if step is None:
            return None
        updated = dict(step.request)
        updated['status'] = payload.get('status')
        updated['response'] = payload.get('response')
        via = payload.get('via')
        if not isinstance(via, str):
            via = None
        updated['responded_via'] = via
        step.request = updated
        return self._request_turns.get(request_id)

    def _add_trigger(
        self,
        event: dict[str, Any],
        trigger_id: str,
    ) -> ChatItem | None:
        """Starts a turn from its trigger, inside the running turn when it steers it.

        Args:
            event (dict[str, Any]): The trigger_received event.
            trigger_id (str): The trigger's id.

        Returns:
            ChatItem | None: The new turn, or the running turn it was added to.
        """
        payload = event.get('payload') or {}
        steering_into = payload.get('steering_into')
        if not isinstance(steering_into, str):
            steering_into = None
        attachments = payload.get('attachments')
        if not isinstance(attachments, list):
            attachments = []
        request_id = payload.get('request_id')
        if not isinstance(request_id, str):
            request_id = None
        turn = chat_items.ChatTurn(
            trigger_id=trigger_id,
            source=str(payload.get('source', '')),
            text=str(payload.get('text', '')),
            attachments=attachments,
            received_at=str(event.get('created_at', '')),
            steering_into=steering_into,
            request_id=request_id,
        )
        if steering_into is not None:
            turn.steering_outcome = 'waiting'
        self._turns[trigger_id] = turn
        running = None
        if steering_into is not None:
            running = self._turns.get(steering_into)
        if running is not None:
            running.steps.append(chat_items.SteeringStep(message=turn))
            return running
        self.items.append(turn)
        self._shown.add(trigger_id)
        return turn

    def _add_to_turn(
        self,
        turn: chat_items.ChatTurn,
        event: dict[str, Any],
    ) -> bool:
        """Adds one event to a turn.

        Args:
            turn (chat_items.ChatTurn): The turn.
            event (dict[str, Any]): The event.

        Returns:
            bool: True when the turn changed in a way a reader can see.
        """
        kind = event.get('kind', '')
        payload = event.get('payload') or {}
        if kind == 'tool_call':
            arguments = payload.get('arguments')
            if not isinstance(arguments, dict):
                arguments = {}
            turn.streaming_text = ''
            turn.steps.append(
                chat_items.ToolStep(
                    call_id=str(payload.get('call_id', '')),
                    name=str(payload.get('name', '')),
                    arguments=arguments,
                )
            )
            return True
        if kind == 'tool_result':
            picture_path = payload.get('picture_path')
            if not isinstance(picture_path, str):
                picture_path = None
            for step in turn.steps:
                if isinstance(
                    step, chat_items.ToolStep
                ) and step.call_id == payload.get('call_id'):
                    step.result_text = str(payload.get('text', ''))
                    step.is_error = payload.get('is_error') is True
                    step.picture_path = picture_path
            return True
        if kind == 'text':
            turn.answer = str(payload.get('text', ''))
            turn.silent = payload.get('silent') is True
            turn.streaming_text = ''
            return True
        if kind == 'error':
            turn.error = str(payload.get('error', ''))
            return True
        if kind == 'steering':
            turn.steering_outcome = 'queued'
            if payload.get('delivered') is True:
                turn.steering_outcome = 'delivered'
            return True
        if kind == 'stopped':
            turn.stopped = True
            return True
        if kind == 'backend_switch' and isinstance(payload.get('to'), str):
            turn.backend = payload['to']
            if payload.get('from') is None:
                return True
        if kind == 'model_usage' and isinstance(payload.get('backend'), str):
            turn.backend = payload['backend']
            return True
        if kind in _STEP_KINDS_SHOWN:
            turn.steps.append(chat_items.EventStep(event=event))
            return True
        return False
