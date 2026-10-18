"""One thing a desk asked the user: a question, a plan to approve, or permission for an action.

A desk never waits for the answer. The request is saved and shown to the user, the desk's turn ends, and the user's answer reaches the desk later as a new message.

Typical usage example:

  request = UserRequest.new('main', QUESTION, {'questions': [...]})
  request.to_json_dictionary()
"""

import dataclasses
import datetime
import uuid
from typing import Any, Self

QUESTION = 'question'
PLAN = 'plan'
PERMISSION = 'permission'
KINDS = (
    QUESTION,
    PLAN,
    PERMISSION,
)

PENDING = 'pending'
ANSWERED = 'answered'
DISMISSED = 'dismissed'
EXPIRED = 'expired'


@dataclasses.dataclass(frozen=True)
class UserRequest:
    """A question, plan or permission request, and the user's response once given.

    Attributes:
        request_id: Its identifier.
        desk: The desk that asked.
        kind: "question", "plan" or "permission".
        content: What was asked: the questions, the plan, or the action awaiting permission.
        created_at: When it was asked, as ISO 8601 text in UTC.
        status: "pending", "answered", "dismissed" or "expired".
        response: The user's response, or None while pending.
        responded_at: When the user responded, as ISO 8601 text, or None.
        responded_via: Where the user responded, "web", "terminal" or "telegram", or None.
        expires_at: When the request lapses, as ISO 8601 text, or None when it never does.
    """

    request_id: str
    desk: str
    kind: str
    content: dict[str, Any]
    created_at: str
    status: str
    response: dict[str, Any] | None = None
    responded_at: str | None = None
    responded_via: str | None = None
    expires_at: str | None = None

    @classmethod
    def new(
        cls,
        desk: str,
        kind: str,
        content: dict[str, Any],
        expires_at: datetime.datetime | None = None,
    ) -> Self:
        """Creates a pending request with a new identifier.

        Args:
            desk (str): The desk asking.
            kind (str): "question", "plan" or "permission".
            content (dict[str, Any]): What is asked.
            expires_at (datetime.datetime | None): When it lapses, or None for never.

        Returns:
            UserRequest: The request.

        Raises:
            ValueError: The kind is not one of KINDS.
        """
        if kind not in KINDS:
            raise ValueError(f'Unknown request kind: {kind!r}')
        now = datetime.datetime.now(datetime.UTC)
        return cls(
            request_id=f'{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}',
            desk=desk,
            kind=kind,
            content=content,
            created_at=now.isoformat(),
            status=PENDING,
            expires_at=None if expires_at is None else expires_at.isoformat(),
        )

    @classmethod
    def from_json_dictionary(cls, dictionary: dict[str, Any]) -> Self:
        """Reads a request saved by to_json_dictionary.

        Args:
            dictionary (dict[str, Any]): The saved fields.

        Returns:
            UserRequest: The request.
        """
        return cls(**dictionary)

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the request to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: Every field.
        """
        return dataclasses.asdict(self)

    def title(self) -> str:
        """A short name for the request, for messages and notifications.

        Returns:
            str: The plan's title, the action's name, or the first question.
        """
        if self.kind == PLAN:
            return str(self.content.get('title', 'plan'))
        if self.kind == PERMISSION:
            return str(self.content.get('tool_name', 'an action'))
        questions = self.content.get('questions') or [
            {},
        ]
        return str(questions[0].get('question', 'question'))

    def is_expired(self, now: datetime.datetime) -> bool:
        """Says whether a pending request has passed its expiry time.

        Args:
            now (datetime.datetime): The current time, with a time zone.

        Returns:
            bool: True when it has an expiry time and that time has passed.
        """
        if self.expires_at is None:
            return False
        return now >= datetime.datetime.fromisoformat(self.expires_at)
