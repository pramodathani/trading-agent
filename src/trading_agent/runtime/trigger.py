"""A reason to wake a desk and run one turn.

Typical usage example:

  trigger = Trigger.now(TriggerSource.USER_MESSAGE, desk='main', text='How is the market?')
"""

import dataclasses
import datetime
import enum
import uuid
from typing import Any, Self

from trading_agent.attachments import attachment as attachment_module


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
        attachments: The pictures and documents the user sent with a message.
        request_id: The desk's question, plan or permission request this message answers, or None.
    """

    trigger_id: str
    source: TriggerSource
    desk: str
    text: str
    created_at: datetime.datetime
    attachments: tuple[attachment_module.Attachment, ...] = ()
    request_id: str | None = None

    @classmethod
    def now(
        cls,
        source: TriggerSource,
        desk: str,
        text: str,
        attachments: tuple[attachment_module.Attachment, ...] = (),
        request_id: str | None = None,
    ) -> Self:
        """Creates a trigger with a new identifier and the current time.

        Args:
            source (TriggerSource): Where the trigger came from.
            desk (str): The desk that should handle it.
            text (str): What the desk is asked or told.
            attachments (tuple[attachment_module.Attachment, ...]): The pictures and documents sent with it.
            request_id (str | None): The request this message answers, or None.

        Returns:
            Trigger: The new trigger.
        """
        return cls(
            trigger_id=uuid.uuid4().hex,
            source=source,
            desk=desk,
            text=text,
            created_at=datetime.datetime.now(datetime.UTC),
            attachments=attachments,
            request_id=request_id,
        )

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the trigger to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: The trigger's fields, with the time as an ISO 8601 string; attachments only when there are some.
        """
        dictionary = {
            'trigger_id': self.trigger_id,
            'source': str(self.source),
            'desk': self.desk,
            'text': self.text,
            'created_at': self.created_at.isoformat(),
        }
        if self.attachments:
            described = []
            for attachment in self.attachments:
                described.append(attachment.to_json_dictionary())
            dictionary['attachments'] = described
        if self.request_id is not None:
            dictionary['request_id'] = self.request_id
        return dictionary

    @property
    def images(self) -> tuple[attachment_module.Attachment, ...]:
        """The attachments that are pictures."""
        pictures = []
        for attachment in self.attachments:
            if attachment.is_image:
                pictures.append(attachment)
        return tuple(pictures)
