"""The present_plan tool: shows the user a plan to approve before the desk acts on it, as Claude Code's plan approval does.

The desk does not wait. The plan is saved and shown in the web chat and on Telegram, and the user's decision arrives later as a new message.

Typical usage example:

  tool = PresentPlanTool(store, event_bus, 'main')
"""

import pydantic

from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import user_request_store as user_request_store_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.tools import tool


class PresentPlanArguments(pydantic.BaseModel):
    """The arguments of present_plan.

    Attributes:
        title: A short name for the plan, such as "Monday pre-market plan".
        plan: The plan in Markdown: what you will do, with levels, sizes and the conditions that would change it.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    title: str = pydantic.Field(min_length=3, max_length=80)
    plan: str = pydantic.Field(min_length=10, max_length=20000)


class PresentPlanTool(tool.Tool):
    """Saves and shows the desk's plan to the user for approval."""

    name = 'present_plan'
    description = 'Shows the user a plan in Markdown and asks them to approve it or ask for changes; it appears as a plan card in the web chat and with buttons on Telegram. Use it when the user asked to see a plan before you act, or for a new strategy or a large change of approach. Do not use it for routine trades the rules already allow; act on those. The call does not wait: end your turn after it. The decision arrives later as a new message naming the request; until it is approved, do not act on the plan.'
    arguments_model = PresentPlanArguments

    def __init__(
        self,
        store: user_request_store_module.UserRequestStore,
        event_bus: event_bus_module.EventBus,
        desk_name: str,
    ):
        """Creates the tool.

        Args:
            store (user_request_store_module.UserRequestStore): Where the request is saved.
            event_bus (event_bus_module.EventBus): Where it is published for the web page and Telegram.
            desk_name (str): The desk presenting the plan.
        """
        self._store = store
        self._event_bus = event_bus
        self._desk_name = desk_name

    async def run(self, arguments: PresentPlanArguments) -> tool.ToolResult:
        """Saves the plan and publishes it.

        Args:
            arguments (PresentPlanArguments): The plan.

        Returns:
            tool.ToolResult: The request's identifier and what happens next.
        """
        request = user_request_module.UserRequest.new(
            self._desk_name,
            user_request_module.PLAN,
            arguments.model_dump(),
        )
        self._store.save(request)
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.USER_REQUEST,
                self._desk_name,
                request.to_json_dictionary(),
            )
        )
        return tool.ToolResult.success(
            f'The plan was sent to the user as request {request.request_id}. Do not act on it yet, and do not wait: end this turn. The decision will arrive as a new message naming the request.'
        )
