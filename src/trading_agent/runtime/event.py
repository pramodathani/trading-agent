"""One thing that happened inside the agent, as published on the event bus.

Typical usage example:

  event = Event.now(EventKind.TURN_STARTED, trader='main', payload={'trigger_id': trigger_id})
"""

import dataclasses
import datetime
import enum
from typing import Any, Self


class EventKind(enum.StrEnum):
    """The kinds of event the agent publishes."""

    TRADER_STARTED = 'trader_started'
    TRADER_STOPPED = 'trader_stopped'
    TRADER_CREATED = 'trader_created'
    TRADER_RETIRED = 'trader_retired'
    TRADER_SLEEPING = 'trader_sleeping'
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
    ORDER = 'order'
    SESSION_STARTED = 'session_started'
    CONTEXT_COMPRESSED = 'context_compressed'
    SUBAGENT_STARTED = 'subagent_started'
    SUBAGENT_FINISHED = 'subagent_finished'
    CRON_FIRED = 'cron_fired'
    CRON_RESULT = 'cron_result'
    MESSAGE = 'message'
    FILL = 'fill'
    PRICE_ALERT = 'price_alert'
    TRADER_HALT = 'trader_halt'
    ACCOUNT_STATUS = 'account_status'
    STEERING = 'steering'
    CHANNEL = 'channel'
    STOPPED = 'stopped'
    TEXT = 'text'
    TURN_FINISHED = 'turn_finished'
    USER_REQUEST = 'user_request'
    USER_RESPONSE = 'user_response'
    ERROR = 'error'


@dataclasses.dataclass(frozen=True)
class Event:
    """One published event.

    Attributes:
        kind: What happened.
        trader: The trader it happened on, or None for the whole gateway.
        payload: Details that depend on the kind, kept JSON-serialisable.
        created_at: When it happened, in UTC.
    """

    kind: EventKind
    trader: str | None
    payload: dict[str, Any]
    created_at: datetime.datetime

    @classmethod
    def now(
        cls,
        kind: EventKind,
        trader: str | None,
        payload: dict[str, Any] | None = None,
    ) -> Self:
        """Creates an event stamped with the current time.

        Args:
            kind (EventKind): What happened.
            trader (str | None): The trader it happened on, or None for the whole gateway.
            payload (dict[str, Any] | None): Details of the event, or None for no details.

        Returns:
            Event: The new event.
        """
        if payload is None:
            payload = {}
        return cls(
            kind=kind,
            trader=trader,
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
            'trader': self.trader,
            'payload': self.payload,
            'created_at': self.created_at.isoformat(),
        }
