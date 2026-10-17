"""Messages from the user that arrive while a desk is in the middle of a model turn.

Without steering, a message sent while the desk is busy waits until the turn ends, which can be minutes. With it, the message goes into this inbox instead, and the running turn picks it up at its next tool round: the agent loop adds it to the conversation before the next model call, and the Claude runner hands it over in a PostToolUse hook. A message the turn never picks up, because the turn ended without another tool round, is queued as its own turn afterwards, so nothing is lost.

Typical usage example:

  inbox = SteeringInbox(event_bus, 'main')
  inbox.add(trigger, running_trigger_id)
  text = inbox.take_text()
"""

import zoneinfo

from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class SteeringInbox:
    """One desk's messages waiting to be handed to the running turn."""

    def __init__(self, event_bus: event_bus_module.EventBus, desk_name: str):
        """Creates an empty inbox.

        Args:
            event_bus (event_bus_module.EventBus): Where deliveries are announced.
            desk_name (str): The desk.
        """
        self._event_bus = event_bus
        self._desk_name = desk_name
        self._waiting: list[trigger_module.Trigger] = []
        self._running_trigger_id: str | None = None

    def add(
        self, trigger: trigger_module.Trigger, running_trigger_id: str
    ) -> None:
        """Keeps a message for the running turn.

        Args:
            trigger (trigger_module.Trigger): The user's message.
            running_trigger_id (str): The trigger of the turn that is running.
        """
        self._waiting.append(trigger)
        self._running_trigger_id = running_trigger_id

    def take_text(self) -> str | None:
        """Hands every waiting message to the running turn, as one block of text.

        Returns:
            str | None: The messages, each with its time, or None when none is waiting.
        """
        if not self._waiting:
            return None
        taken = self._waiting
        self._waiting = []
        parts = []
        for trigger in taken:
            moment = trigger.created_at.astimezone(_INDIA)
            parts.append(
                f'[Message from the user at {moment:%H:%M:%S} IST, sent while you were working. Take it into account now; it may change what you are doing.]\n{trigger.text}'
            )
            self._event_bus.publish(
                event_module.Event.now(
                    event_module.EventKind.STEERING,
                    self._desk_name,
                    {
                        'trigger_id': trigger.trigger_id,
                        'into_trigger_id': self._running_trigger_id,
                        'delivered': True,
                    },
                )
            )
        return '\n\n'.join(parts)

    def take_undelivered(self) -> list[trigger_module.Trigger]:
        """Removes the messages the turn never picked up, so they can be queued as their own turns.

        Returns:
            list[trigger_module.Trigger]: The messages, oldest first.
        """
        taken = self._waiting
        self._waiting = []
        for trigger in taken:
            self._event_bus.publish(
                event_module.Event.now(
                    event_module.EventKind.STEERING,
                    self._desk_name,
                    {
                        'trigger_id': trigger.trigger_id,
                        'into_trigger_id': self._running_trigger_id,
                        'delivered': False,
                    },
                )
            )
        return taken
