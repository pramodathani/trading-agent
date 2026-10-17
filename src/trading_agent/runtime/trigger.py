"""A reason to wake a desk and run one turn.

Typical usage example:

  trigger = Trigger.now(TriggerSource.USER_MESSAGE, desk='main', text='How is the market?')
"""

import dataclasses
import datetime
import enum
import uuid
from typing import Any, Self


class TriggerSource(enum.StrEnum):
    """Where a trigger came from."""

    USER_MESSAGE = 'user_message'
    CRON = 'cron'
    HEARTBEAT = 'heartbeat'
    MARKET_WATCHER = 'market_watcher'
    WEBHOOK = 'webhook'
    ROLLOVER = 'rollover'
    COMPRESSION = 'compression'
    SUBAGENT = 'subagent'


@dataclasses.dataclass(frozen=True)
class Trigger:
    """One reason to run a turn.

    Attributes:
        trigger_id: A unique identifier, used to match events to the trigger that caused them.
        source: Where the trigger came from.
        desk: The desk that should handle it.
        text: What the desk is asked or told.
        created_at: When the trigger was created, in UTC.
    """

    trigger_id: str
    source: TriggerSource
    desk: str
    text: str
    created_at: datetime.datetime

    @classmethod
    def now(cls, source: TriggerSource, desk: str, text: str) -> Self:
        """Creates a trigger with a new identifier and the current time.

        Args:
            source (TriggerSource): Where the trigger came from.
            desk (str): The desk that should handle it.
            text (str): What the desk is asked or told.

        Returns:
            Trigger: The new trigger.
        """
        return cls(
            trigger_id=uuid.uuid4().hex,
            source=source,
            desk=desk,
            text=text,
            created_at=datetime.datetime.now(datetime.UTC),
        )

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the trigger to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: The trigger's fields, with the time as an ISO 8601 string.
        """
        return {
            'trigger_id': self.trigger_id,
            'source': str(self.source),
            'desk': self.desk,
            'text': self.text,
            'created_at': self.created_at.isoformat(),
        }
