"""The send_message tool: tells the user something without waiting for a reply.

The message is published as a message event. The web interface (milestone 18) and Telegram (milestone 19) show it; until then it is in the journal and on the gateway's event stream.

Typical usage example:

  tool = SendMessageTool(event_bus, 'main')
"""

import pydantic

from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.tools import tool


class SendMessageArguments(pydantic.BaseModel):
    """The arguments of send_message.

    Attributes:
        text: The message.
        urgent: Whether it needs the user's attention now, such as a stop being hit.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    text: str = pydantic.Field(min_length=1, max_length=4000)
    urgent: bool = False


class SendMessageTool(tool.Tool):
    """Publishes a message to the user."""

    name = 'send_message'
    description = 'Sends the user a message without waiting for a reply, through the web interface and Telegram. Use it from scheduled jobs, heartbeats and alerts, when something happened the user should know about, such as a fill, a stop hit or a plan for tomorrow. Do not use it to repeat your normal answer; the user already sees that when they asked. Set urgent for things that need attention now.'
    arguments_model = SendMessageArguments

    def __init__(self, event_bus: event_bus_module.EventBus, trader_name: str):
        """Creates the tool.

        Args:
            event_bus (event_bus_module.EventBus): Where the message is published.
            trader_name (str): The trader sending it.
        """
        self._event_bus = event_bus
        self._trader_name = trader_name

    async def run(self, arguments: SendMessageArguments) -> tool.ToolResult:
        """Publishes the message.

        Args:
            arguments (SendMessageArguments): The message.

        Returns:
            tool.ToolResult: A confirmation.
        """
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.MESSAGE,
                self._trader_name,
                {
                    'text': arguments.text,
                    'urgent': arguments.urgent,
                },
            )
        )
        return tool.ToolResult.success('Message sent.')
