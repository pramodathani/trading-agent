"""The ask_user tool: puts one to four multiple-choice questions to the user, as Claude Code's question card does.

The trader does not wait. The questions are saved and shown in the web chat and on Telegram, and the user's answers arrive later as a new message.

Typical usage example:

  tool = AskUserTool(store, event_bus, 'main')
"""

import pydantic

from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import (
    user_request_store as user_request_store_module,
)
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.tools import tool

_RESERVED_LABEL = 'other'


class QuestionOption(pydantic.BaseModel):
    """One choice in a question.

    Attributes:
        label: The short text on the choice, one to five words.
        description: What choosing it means, or its trade-offs.
        preview: Optional Markdown shown beside the choices when this one is highlighted, such as a table of levels or an order ticket.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    label: str = pydantic.Field(min_length=1, max_length=40)
    description: str = pydantic.Field(min_length=1, max_length=300)
    preview: str | None = pydantic.Field(default=None, max_length=4000)


class Question(pydantic.BaseModel):
    """One question with its choices.

    Attributes:
        question: The full question, ending with a question mark.
        header: A tag of at most 12 characters naming the topic, such as "Stop loss".
        options: Two to four choices; an "Other" box for a free answer is added automatically.
        multi_select: True when more than one choice may be picked.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    question: str = pydantic.Field(min_length=3, max_length=300)
    header: str = pydantic.Field(min_length=1, max_length=12)
    options: list[QuestionOption] = pydantic.Field(min_length=2, max_length=4)
    multi_select: bool = False

    @pydantic.model_validator(mode='after')
    def _check_labels(self) -> Question:
        """Checks that the labels differ and that none is "Other", which is added automatically.

        Returns:
            Question: The question.

        Raises:
            ValueError: Two labels are the same, or one is "Other".
        """
        seen = set()
        for option in self.options:
            key = option.label.strip().lower()
            if key == _RESERVED_LABEL:
                raise ValueError(
                    'Do not add an "Other" choice; it is added automatically'
                )
            if key in seen:
                raise ValueError(
                    f'Two choices are both labelled {option.label!r}'
                )
            seen.add(key)
        return self


class AskUserArguments(pydantic.BaseModel):
    """The arguments of ask_user.

    Attributes:
        questions: One to four questions, shown together.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    questions: list[Question] = pydantic.Field(min_length=1, max_length=4)


class AskUserTool(tool.Tool):
    """Saves and shows the trader's questions to the user."""

    name = 'ask_user'
    description = 'Asks the user one to four multiple-choice questions, shown as a question card in the web chat and with buttons on Telegram. Use it only for a decision that is genuinely the user\'s and that you cannot settle from the rules, your memory or a sensible default, such as a missing strategy detail or a choice between two approaches. Never use it to ask permission for something the rules already allow; act instead. Each question needs a short header and two to four options with descriptions; an "Other" box is added automatically, so never add one. If you recommend an option, put it first and end its label with "(Recommended)". The call does not wait: end your turn after it, and carry on with other work meanwhile. The answers arrive later as a new message from the user naming the request.'
    arguments_model = AskUserArguments

    def __init__(
        self,
        store: user_request_store_module.UserRequestStore,
        event_bus: event_bus_module.EventBus,
        trader_name: str,
    ):
        """Creates the tool.

        Args:
            store (user_request_store_module.UserRequestStore): Where the request is saved.
            event_bus (event_bus_module.EventBus): Where it is published for the web page and Telegram.
            trader_name (str): The trader asking.
        """
        self._store = store
        self._event_bus = event_bus
        self._trader_name = trader_name

    async def run(self, arguments: AskUserArguments) -> tool.ToolResult:
        """Saves the questions and publishes them.

        Args:
            arguments (AskUserArguments): The questions.

        Returns:
            tool.ToolResult: The request's identifier and what happens next.
        """
        request = user_request_module.UserRequest.new(
            self._trader_name,
            user_request_module.QUESTION,
            arguments.model_dump(),
        )
        self._store.save(request)
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.USER_REQUEST,
                self._trader_name,
                request.to_json_dictionary(),
            )
        )
        return tool.ToolResult.success(
            f'The question was sent to the user as request {request.request_id}. Do not wait for it: end this turn. The answer will arrive as a new message naming the request.'
        )
