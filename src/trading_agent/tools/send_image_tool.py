"""The send_image tool: shows the user a picture, in the web chat and on Telegram.

The picture is copied into the desk's uploads folder, so it stays viewable after the desk's scratch files are cleared, and is published as a message event that carries it. The web page shows it in the chat, and Telegram sends it as a photo: to the chat that asked when the user wrote from Telegram, otherwise to every paired chat when messages are pushed.

Typical usage example:

  tool = SendImageTool(policy, store, event_bus, 'main')
"""

import asyncio
from pathlib import Path

import pydantic

from trading_agent.attachments import attachment as attachment_module
from trading_agent.attachments import (
    attachment_store as attachment_store_module,
)
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.tools import path_policy as path_policy_module
from trading_agent.tools import tool


class SendImageArguments(pydantic.BaseModel):
    """The arguments of send_image.

    Attributes:
        path: The picture; a relative path starts at your desk folder.
        caption: A line shown with the picture, or an empty string.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    path: str = pydantic.Field(min_length=1)
    caption: str = pydantic.Field(default='', max_length=1000)


class SendImageTool(tool.Tool):
    """Sends the user a picture file."""

    name = 'send_image'
    description = 'Shows the user a picture file (PNG, JPEG, WebP or GIF, at most 20 MB) in the web chat and on Telegram, with an optional caption. Use it whenever the user asks to see a picture, chart or table you made, or a screenshot: they cannot see files in your folder or the pictures your tools show you. Make the picture first, for example with Python in scratch/ or with browser_screenshot, then pass its path. A relative path starts at your desk folder.'
    arguments_model = SendImageArguments

    def __init__(
        self,
        policy: path_policy_module.PathPolicy,
        store: attachment_store_module.AttachmentStore,
        event_bus: event_bus_module.EventBus,
        desk_name: str,
    ):
        """Creates the tool.

        Args:
            policy (path_policy_module.PathPolicy): The desk's read rules.
            store (attachment_store_module.AttachmentStore): Keeps the copy of the picture that is shown.
            event_bus (event_bus_module.EventBus): Where the message is published.
            desk_name (str): The desk sending it.
        """
        self._policy = policy
        self._store = store
        self._event_bus = event_bus
        self._desk_name = desk_name

    async def run(self, arguments: SendImageArguments) -> tool.ToolResult:
        """Copies the picture and publishes it.

        Args:
            arguments (SendImageArguments): The picture and its caption.

        Returns:
            tool.ToolResult: A confirmation, or an error the model can act on.
        """
        try:
            path = self._policy.readable(arguments.path)
        except path_policy_module.PathRefusedError as error:
            return tool.ToolResult.error(str(error))
        if not path.is_file():
            return tool.ToolResult.error(f'{arguments.path} is not a file.')
        if path.suffix.lower() not in attachment_store_module.IMAGE_EXTENSIONS:
            return tool.ToolResult.error(
                f'{arguments.path} is not a picture. Send a file ending in {", ".join(attachment_store_module.IMAGE_EXTENSIONS)}; save a chart or table as PNG first.'
            )
        if path.stat().st_size > attachment_store_module.MAXIMUM_BYTES:
            return tool.ToolResult.error(
                f'{arguments.path} is larger than 20 MB; save a smaller picture.'
            )
        try:
            attachment = await asyncio.to_thread(self._save, path)
        except attachment_store_module.AttachmentRefusedError as error:
            return tool.ToolResult.error(str(error))
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.MESSAGE,
                self._desk_name,
                {
                    'text': arguments.caption,
                    'urgent': False,
                    'attachments': [
                        attachment.to_json_dictionary(),
                    ],
                },
            )
        )
        return tool.ToolResult.success(
            f'The user can now see {arguments.path}. Do not describe it again unless they ask.'
        )

    def _save(self, path: Path) -> attachment_module.Attachment:
        """Copies the picture into the uploads folder.

        Args:
            path (Path): The picture.

        Returns:
            attachment_module.Attachment: The stored copy.

        Raises:
            attachment_store_module.AttachmentRefusedError: The file is empty or not a picture that can be read.
        """
        return self._store.save(self._desk_name, path.name, path.read_bytes())
