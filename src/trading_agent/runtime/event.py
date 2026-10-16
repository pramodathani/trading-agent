"""One thing that happened inside the agent, as published on the event bus.

Typical usage example:

  event = Event.now(EventKind.TURN_STARTED, desk='main', payload={'trigger_id': trigger_id})
"""

import dataclasses
import datetime
import enum
from typing import Any, Self


class EventKind(enum.StrEnum):
    """The kinds of event the agent publishes."""

    DESK_STARTED = 'desk_started'
    DESK_STOPPED = 'desk_stopped'
    TRIGGER_RECEIVED = 'trigger_received'
    TURN_STARTED = 'turn_started'
    TEXT_DELTA = 'text_delta'
    TOOL_CALL = 'tool_call'
    TOOL_RESULT = 'tool_result'
    MODEL_USAGE = 'model_usage'
    RATE_LIMIT = 'rate_limit'
    BACKEND_UNAVAILABLE = 'backend_unavailable'
    BACKEND_SWITCH = 'backend_switch'
    RISK_DECISION = 'risk_decision'
    KILL_SWITCH = 'kill_switch'
    TEXT = 'text'
    TURN_FINISHED = 'turn_finished'
    ERROR = 'error'


@dataclasses.dataclass(frozen=True)
class Event:
    """One published event.

    Attributes:
        kind: What happened.
        desk: The desk it happened on, or None for the whole gateway.
        payload: Details that depend on the kind, kept JSON-serialisable.
        created_at: When it happened, in UTC.
    """

    kind: EventKind
    desk: str | None
    payload: dict[str, Any]
    created_at: datetime.datetime

    @classmethod
    def now(
        cls,
        kind: EventKind,
        desk: str | None,
        payload: dict[str, Any] | None = None,
    ) -> Self:
        """Creates an event stamped with the current time.

        Args:
            kind (EventKind): What happened.
            desk (str | None): The desk it happened on, or None for the whole gateway.
            payload (dict[str, Any] | None): Details of the event, or None for no details.

        Returns:
            Event: The new event.
        """
        if payload is None:
            payload = {}
        return cls(
            kind=kind,
            desk=desk,
            payload=payload,
            created_at=datetime.datetime.now(datetime.UTC),
        )

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the event to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: The event's fields, with the time as an ISO 8601 string.
        """
        return {
            'kind': str(self.kind),
            'desk': self.desk,
            'payload': self.payload,
            'created_at': self.created_at.isoformat(),
        }
